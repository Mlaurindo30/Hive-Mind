#!/usr/bin/env python3
"""Orquestrador de consolidação contínua do cerebro.

Fecha o gargalo de automação (2026-08-12): antes, o bridge rodava 1x/dia, a
promoção K3 só manual/Dream Cycle, e os preenchedores dos outros lobos
(decisões, trabalho, projetos, saúde, diário) só 1x/dia ou semana. Este daemon
mantém o cerebro inteiro atualizado em cascata, cada camada na sua cadência.

Camadas (por iteração de HIVE_CONSOLIDATE_INTERVAL_SECONDS, default 60s):

  FAST (toda iteração) — lobo temporal (memória de longo prazo):
    bridge() → importa observações novas do claude-mem
    promote_pending_observations() → promove + materializa .md (via K3)
    materialize_orphan_neurons() → resíduo defensivo

  MEDIUM (a cada HIVE_CONSOLIDATE_MEDIUM_SECONDS, default 300s = 5min) —
  derivados do temporal:
    decision_promoter.run()     → cortex/frontal/decisoes
    work_tracker.run()          → cortex/frontal/trabalho
    project_synthesizer.write_all() → cortex/frontal/projetos
    health_dashboard (main)     → cortex/insula/saude

  SLOW (a cada HIVE_CONSOLIDATE_SLOW_SECONDS, default 3600s = 1h) —
  consolidação do temporal:
    topic_consolidator (log-only, sem --apply por segurança)

Os SEMANAIS (weekly_synthesizer, pattern_distiller, conflict_detector,
capture_maintenance) continuam no cron — são sínteses de longo período que não
fazem sentido a cada minuto.

Cada camada é best-effort e isolada: uma falha num preenchedor não derruba a
iteração nem os demais. Idempotente por natureza (SELECT-por-estado).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent.parent
sys.path.insert(0, str(ROOT))

from core.database import get_connection
from core.knowledge.claude_mem_bridge import bridge
from core.knowledge.materialize import materialize_orphan_neurons
from core.knowledge.promotion import promote_pending_observations

_PY = str(ROOT / ".venv" / "Scripts" / "python.exe")


def _fast_layer(conn) -> dict:
    report = {"bridge": 0, "promoted": 0, "materialized": 0}
    br = bridge(limit=1000)
    report["bridge"] = br.get("inserted", 0) if isinstance(br, dict) else 0
    pr = promote_pending_observations(conn, limit=1000, apply=True)
    report["promoted"] = pr.get("promoted", 0) if isinstance(pr, dict) else 0
    mr = materialize_orphan_neurons(conn)
    report["materialized"] = mr.get("materialized", 0) if isinstance(mr, dict) else 0
    return report


def _medium_layer() -> dict:
    """Preenchedores dos lobos derivados (frontal + ínsula), via subprocess.

    Cada um é um processo isolado (best-effort): decisões, trabalho ativo,
    status por projeto, snapshot de saúde e o diário do dia (cerebelo/diario).
    """
    report = {"decision": 0, "work": 0, "projects": 0, "health": 0, "daily": 0}
    jobs = [
        # F2.1 (2026-08-13): decision_promoter DEVE rodar com --with-llm. Sem isso,
        # ele reescreve as decisões com "_(a preencher)_" e desfaz qualquer backfill
        # (o campo Rationale/Alternativas/Consequências só é preenchido via LLM).
        # FIX (2026-08-13): usa _PY (caminho explícito do .venv), NÃO sys.executable.
        # sys.executable sob o launcher pythonw do uv aponta para o interpretador
        # base .uv, fazendo os subprocessos nascerem com o interpretador errado.
        ("decision", [_PY, str(ROOT / "scripts/knowledge/decision_promoter.py"), "--apply", "--with-llm"]),
        ("work", [_PY, str(ROOT / "scripts/knowledge/work_tracker.py"), "--apply"]),
        ("projects", [_PY, str(ROOT / "scripts/knowledge/project_synthesizer.py"), "--apply"]),
        ("health", [_PY, str(ROOT / "scripts/health/health_dashboard.py")]),
        ("daily", [_PY, str(ROOT / "scripts/dream/daily_writer.py"), "--no-llm"]),
    ]
    for key, cmd in jobs:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(ROOT))
            # marcamos 1 se o processo concluiu sem exceção (o conteúdo real é
            # verificado pelo próprio script; aqui registramos a execução).
            report[key] = 1 if r.returncode == 0 else 0
        except Exception:
            report[key] = 0
    return report


def _daily_layer() -> int:
    """Sínteses de longo período (semanal/mensal/anual) — cadência diária."""
    report = {"weekly": 0, "monthly": 0, "yearly": 0}
    for key, script in [
        ("weekly", "weekly_synthesizer.py"),
        ("monthly", "monthly_synthesizer.py"),
        ("yearly", "yearly_synthesizer.py"),
    ]:
        try:
            r = subprocess.run(
                [_PY, str(ROOT / "scripts/dream" / script)],
                capture_output=True, text=True, timeout=600, cwd=str(ROOT),
            )
            report[key] = 1 if r.returncode == 0 else 0
        except Exception:
            report[key] = 0
    return report


def _slow_layer() -> int:
    """Consolidação de tópicos (log-only, sem --apply por segurança)."""
    try:
        r = subprocess.run(
            [_PY, str(ROOT / "scripts/knowledge/topic_consolidator.py")],
            capture_output=True, text=True, timeout=600, cwd=str(ROOT),
        )
        return 1 if r.returncode == 0 else 0
    except Exception:
        return 0


def _acquire_single_instance():
    """Garante que apenas UMA instância do consolidate_loop rode.

    FIX (2026-08-13): padrão do claude-mem (worker-spawn-gate.ts) — lock por
    criação atômica de arquivo com O_CREAT|O_EXCL (flag 'x' no open), NÃO mutex
    Windows. O mutex CreateMutexW falhava porque o segundo processo (.uv, lançado
    pelo launcher pythonw do uv) usa outro contexto. O arquivo com O_EXCL é o
    mutex em si: quem cria vence, quem encontra EEXIST sai. Stale por mtime.

    Retorna um guard com .release(); se já há dono, sai com exit 0 (duplicação
    é sucesso, não falha — mesmo padrão do claude-mem 'Port already in use').
    """
    lock_path = ROOT / "claude-mem" / "data" / "consolidate.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    import time as _time
    _STALE_SECONDS = 90

    # Quebra lock obsoleto por mtime (mesmo padrão do SPAWN_LOCK_STALE_MS).
    if lock_path.exists():
        try:
            age = _time.time() - lock_path.stat().st_mtime
            if age > _STALE_SECONDS:
                lock_path.unlink()
        except OSError:
            pass

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("[single-instance] outra instância do consolidate_loop já roda — saindo.", flush=True)
        sys.exit(0)
    except OSError as exc:
        print(f"[single-instance] falha ao criar lock: {exc}", flush=True)
        sys.exit(1)

    os.write(fd, str(os.getpid()).encode())
    os.close(fd)

    class _LockGuard:
        def release(self):
            try:
                if lock_path.exists():
                    # owner-checked: só apaga se o pid gravado é o nosso.
                    data = lock_path.read_text(encoding="utf-8").strip()
                    if data == str(os.getpid()):
                        lock_path.unlink()
            except OSError:
                pass

    return _LockGuard()


def main() -> int:
    parser = argparse.ArgumentParser(description="Orquestrador contínuo do cerebro")
    parser.add_argument("--once", action="store_true", help="uma iteração e sai")
    parser.add_argument("--interval", type=int, default=None)
    args = parser.parse_args()

    # DIAG (2026-08-13): registra identidade do processo no boot, para auditar a
    # duplicação .venv vs .uv (ver report de auditoria).
    import os as _os
    print(f"[boot] pid={_os.getpid()} ppid={_os.getppid()} "
          f"exe={sys.executable} argv={sys.argv}", flush=True)

    # Single-instance: impede corrida quando o launcher dispara 2 processos.
    _acquire_single_instance()

    interval = args.interval or int(os.environ.get("HIVE_CONSOLIDATE_INTERVAL_SECONDS", "60"))
    medium_interval = int(os.environ.get("HIVE_CONSOLIDATE_MEDIUM_SECONDS", "300"))
    slow_interval = int(os.environ.get("HIVE_CONSOLIDATE_SLOW_SECONDS", "3600"))
    daily_interval = int(os.environ.get("HIVE_CONSOLIDATE_DAILY_SECONDS", "21600"))  # 6h

    conn = get_connection()
    t0 = time.time()
    last_medium = 0.0
    last_slow = 0.0
    last_daily = 0.0
    try:
        while True:
            now = time.time()
            ts = time.strftime("%H:%M:%S")
            try:
                fast = _fast_layer(conn)
                line = (
                    f"[{ts}] temporal: bridge={fast['bridge']} "
                    f"promoted={fast['promoted']} materialized={fast['materialized']}"
                )
                if now - last_medium >= medium_interval:
                    med = _medium_layer()
                    last_medium = now
                    line += (
                        f" | frontal: decisões={med['decision']} trabalho={med['work']} "
                        f"projetos={med['projects']} saúde={med['health']} diário={med['daily']}"
                    )
                if now - last_slow >= slow_interval:
                    slow = _slow_layer()
                    last_slow = now
                    line += f" | tópicos={slow}"
                if now - last_daily >= daily_interval:
                    dly = _daily_layer()
                    last_daily = now
                    line += (
                        f" | cadência: semanal={dly['weekly']} "
                        f"mensal={dly['monthly']} anual={dly['yearly']}"
                    )
                print(line, flush=True)
            except Exception as exc:
                print(f"[{ts}] erro: {exc}", flush=True)
            if args.once:
                break
            time.sleep(interval)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
