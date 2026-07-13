#!/usr/bin/env python3
"""Install idempotent user services for the Hive-Mind local runtime.

Most services run from this checkout and its .venv.  The claude-mem temporal
runtime is intentionally global and multi-project, with data under
~/.claude-mem, so all services that read/write claude-mem must point there.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
USER_UNITS = Path.home() / ".config" / "systemd" / "user"


def unit_definitions() -> dict[str, str]:
    path = str(ROOT)
    claude_mem_data = str(Path.home() / ".claude-mem")
    claude_mem_db = str(Path.home() / ".claude-mem" / "claude-mem.db")
    claude_mem_models = str(Path.home() / ".claude-mem" / "models")
    common_unit = "StartLimitIntervalSec=300\nStartLimitBurst=5"
    return {
        "sinapse-claude-mem.service": f"""[Unit]
Description=Sinapse Agent - claude-mem Worker (global multi-project data)
After=network.target
{common_unit}

[Service]
Type=simple
UMask=0077
WorkingDirectory={path}
Environment=CLAUDE_MEM_DATA_DIR={claude_mem_data}
Environment=CLAUDE_MEM_WORKER_HOST=127.0.0.1
Environment=CLAUDE_MEM_WORKER_PORT=37700
Environment=CLAUDE_MEM_CHROMA_ENABLED=false
Environment=CLAUDE_MEM_MANAGED=true
Environment=FASTEMBED_CACHE_PATH={claude_mem_models}
Environment=PATH={path}/.tools/bin:{path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/scripts/services/claude-mem-local.sh
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
""",
        "sinapse-sqlite-vec.service": f"""[Unit]
Description=SQLite-Vec semantic search worker for Hive-Mind
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=simple
UMask=0077
WorkingDirectory={path}
Environment=VEC_WORKER_PORT=37701
Environment=CLAUDE_MEM_DB={claude_mem_db}
Environment=FASTEMBED_CACHE_PATH={claude_mem_models}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/plugins/sqlite-vec-worker/worker.py
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
""",
        "sinapse-graphify-watch.service": f"""[Unit]
Description=Hive-Mind Graphify vault watcher
After=network.target
{common_unit}

[Service]
Type=simple
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
Environment=GRAPHIFY_WATCH_DEBOUNCE=30.0
ExecStart={path}/scripts/services/start-watcher.sh
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
""",
        "sinapse-api.service": f"""[Unit]
Description=Hive-Mind authenticated REST API
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=simple
UMask=0077
WorkingDirectory={path}
EnvironmentFile={path}/.env
Environment=HIVE_MIND_API_HOST=127.0.0.1
Environment=HIVE_MIND_API_PORT=37702
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/scripts/services/sinapse-api.py
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
""",
        # P7: MCP via Streamable HTTP (paralelo ao stdio). Permite multiplos
        # agentes simultaneos no mesmo cerebro. Porta/host via env (nao hardcode).
        "sinapse-mcp-http.service": f"""[Unit]
Description=Hive-Mind MCP Streamable HTTP Server (spec 2025-03-26)
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=simple
UMask=0077
WorkingDirectory={path}
EnvironmentFile={path}/.env
Environment=SINAPSE_MCP_HTTP_HOST=127.0.0.1
Environment=SINAPSE_MCP_HTTP_PORT=37703
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/scripts/services/sinapse-mcp-http.py
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
""",
        "hive-otel-collector.service": f"""[Unit]
Description=Hive-Mind local OTLP collector
After=network.target
{common_unit}

[Service]
Type=simple
UMask=0077
WorkingDirectory={path}
Environment=HIVE_OTEL_PORT=3100
Environment=HIVE_OTEL_LOG={path}/logs/otel-spans.log
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/scripts/services/otel_collector.py --host 127.0.0.1
Restart=on-failure
RestartSec=15

[Install]
WantedBy=default.target
""",
        "sinapse-capture-tailer.service": f"""[Unit]
Description=Hive-Mind capture tailer (transcripts de agents → claude-mem)
After=network.target sinapse-claude-mem.service
StartLimitIntervalSec=0
StartLimitBurst=0

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/scripts/capture/capture-tailer.py --all --scan --since-hours 1
""",
        "sinapse-capture-realtime.service": f"""[Unit]
Description=Hive-Mind capture realtime (inotify -> claude-mem, tempo real p/ copilot)
Wants=sinapse-sqlite-vec.service
After=network.target sinapse-claude-mem.service sinapse-sqlite-vec.service
{common_unit}

[Service]
Type=simple
UMask=0077
WorkingDirectory={path}
EnvironmentFile={path}/.env
Environment=CLAUDE_MEM_DATA_DIR={claude_mem_data}
Environment=VEC_WORKER_URL=http://127.0.0.1:37701
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/scripts/capture/capture-realtime.py
Restart=always
RestartSec=15

[Install]
WantedBy=default.target
""",
        "sinapse-capture-tailer.timer": """[Unit]
Description=Hive-Mind capture tailer schedule (near-realtime)

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s
AccuracySec=5s
Persistent=true

[Install]
WantedBy=timers.target
""",
        "sinapse-post-reboot-validation.service": f"""[Unit]
Description=Hive-Mind post-reboot production validation
Wants=sinapse-claude-mem.service sinapse-sqlite-vec.service sinapse-graphify-watch.service
After=sinapse-claude-mem.service sinapse-sqlite-vec.service sinapse-graphify-watch.service sinapse-api.service
ConditionPathExists={path}/logs/pre-reboot.json

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=PATH={path}/.venv/bin:{path}/.tools/bin:{path}/integrations/rtk/target/release:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/scripts/health/validate_after_reboot.py validate
RemainAfterExit=yes

[Install]
WantedBy=default.target
""",
        "sinapse-maintenance.service": f"""[Unit]
Description=Sinapse claude-mem maintenance (compacta DB + GC dedup, SEM perder memória)
After=sinapse-claude-mem.service

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=CLAUDE_MEM_DATA_DIR={claude_mem_data}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/scripts/capture/capture_maintenance.py
""",
        "sinapse-maintenance.timer": """[Unit]
Description=Dispara a manutenção do claude-mem semanalmente (off-hours)

[Timer]
OnCalendar=Sun 04:00
Persistent=true

[Install]
WantedBy=timers.target
""",
        # ===== Ponte claude-mem → hive_mind (preserva project p/ o dream) =====
        # Read-only na fonte, idempotente; roda ANTES do dream p/ alimentar o eixo
        # multi-projeto. Seguro → vai no enabled.
        "sinapse-bridge.service": f"""[Unit]
Description=Memória Viva - Bridge claude-mem -> hive_mind (preserva project)
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=CLAUDE_MEM_DB={claude_mem_db}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/services/claude_mem_bridge.py
""",
        "sinapse-bridge.timer": """[Unit]
Description=Dispara a ponte claude-mem->hive_mind diariamente 02:45 (antes do dream)

[Timer]
OnCalendar=*-*-* 02:45:00
Persistent=true
Unit=sinapse-bridge.service

[Install]
WantedBy=timers.target
""",
        # ===== Cadências da Memória Viva (doc 08, §14.4-P1) =====
        # Reprodutibilidade: antes estes timers viviam só em .config/ (ou à mão) e
        # sumiam num reinstall. Agora são canônicos aqui. ExecStart aponta SEMPRE p/
        # .venv/bin/python; oneshot; falha de LLM não derruba o ciclo (scripts tratam).
        "sinapse-dream.service": f"""[Unit]
Description=Memória Viva - Dream Cycle (destila observations -> neurônios)
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/dream/dream_cycle.py
""",
        "sinapse-dream.timer": """[Unit]
Description=Dispara o dream cycle diariamente (off-hours)

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
Unit=sinapse-dream.service

[Install]
WantedBy=timers.target
""",
        "sinapse-daily.service": f"""[Unit]
Description=Memória Viva - Daily Log Writer (cerebelo/diario)
After=network.target
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/dream/daily_writer.py
""",
        "sinapse-daily.timer": """[Unit]
Description=Dispara o daily log writer todo dia 23:55

[Timer]
OnCalendar=*-*-* 23:55:00
Persistent=true
Unit=sinapse-daily.service

[Install]
WantedBy=timers.target
""",
        "sinapse-weekly.service": f"""[Unit]
Description=Memória Viva - Weekly Synthesizer (cerebelo/semanal)
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/dream/weekly_synthesizer.py
""",
        "sinapse-weekly.timer": """[Unit]
Description=Dispara o weekly synthesizer aos domingos 04:00

[Timer]
OnCalendar=Sun 04:00
Persistent=true
Unit=sinapse-weekly.service

[Install]
WantedBy=timers.target
""",
        # topic_consolidator roda SEM --apply: log-only por design (R8/§14.4-P1).
        # Merge real só sob revisão humana — nunca automatizar a fusão.
        "sinapse-topics.service": f"""[Unit]
Description=Memória Viva - Topic Consolidator (log-only, SEM --apply)
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/knowledge/topic_consolidator.py
""",
        "sinapse-topics.timer": """[Unit]
Description=Dispara o topic consolidator (log-only) aos domingos 06:00

[Timer]
OnCalendar=Sun 06:00
Persistent=true
Unit=sinapse-topics.service

[Install]
WantedBy=timers.target
""",
        # ===== Fase 3 — síntese viva (F3.4) =====
        # health: read-only, gera snapshot M1-M9 na Ínsula (seguro, vai no enabled).
        # drift: mensal e SEM --apply por design — o move/cold de memória é decisão
        # humana; rodar log-only no timer, aplicar à mão após revisar.
        "sinapse-health.service": f"""[Unit]
Description=Memória Viva - Health Dashboard (M1-M9 -> cortex/insula/saude)
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/health/health_dashboard.py
""",
        "sinapse-health.timer": """[Unit]
Description=Dispara o health dashboard diariamente 23:50 (antes da daily)

[Timer]
OnCalendar=*-*-* 23:50:00
Persistent=true
Unit=sinapse-health.service

[Install]
WantedBy=timers.target
""",
        # F5.1 alert_dispatcher: lê snapshot M1-M13, despacha para parietal/inbox/.
        # Read-only no snapshot → seguro no enabled.
        "sinapse-alert.service": f"""[Unit]
Description=Memória Viva - Alert Dispatcher (M1-M13 -> parietal/inbox)
After=network.target sinapse-health.service
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/health/alert_dispatcher.py --apply
""",
        "sinapse-alert.timer": """[Unit]
Description=Despacha alertas de saúde para inbox/ diariamente 23:52 (pós-health)

[Timer]
OnCalendar=*-*-* 23:52:00
Persistent=true
Unit=sinapse-alert.service

[Install]
WantedBy=timers.target
""",
        # ===== Fase 4 — memória executiva (F4.1) =====
        # decision_promoter materializa decisões em frontal/decisoes/. Roda --apply:
        # cria/atualiza arquivos PRÓPRIOS (idempotentes, regeneráveis), NÃO muta neurônios.
        "sinapse-decisions.service": f"""[Unit]
Description=Memória Viva - Decision Promoter (frontal/decisoes)
After=network.target
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/knowledge/decision_promoter.py --apply
""",
        "sinapse-decisions.timer": """[Unit]
Description=Dispara o decision promoter diariamente 23:40 (pós-dream)

[Timer]
OnCalendar=*-*-* 23:40:00
Persistent=true
Unit=sinapse-decisions.service

[Install]
WantedBy=timers.target
""",
        # F4.2 project_synthesizer: status agregado por projeto (arquivos próprios, idempotente).
        "sinapse-projects.service": f"""[Unit]
Description=Memória Viva - Project Synthesizer (frontal/projetos)
After=network.target
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/knowledge/project_synthesizer.py --apply
""",
        "sinapse-projects.timer": """[Unit]
Description=Dispara o project synthesizer diariamente 23:42

[Timer]
OnCalendar=*-*-* 23:42:00
Persistent=true
Unit=sinapse-projects.service

[Install]
WantedBy=timers.target
""",
        # F4.3 pattern_distiller: memória procedural (LLM). Semanal; arquivos próprios.
        "sinapse-patterns.service": f"""[Unit]
Description=Memória Viva - Pattern Distiller (cerebelo/padroes)
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/knowledge/pattern_distiller.py --apply
""",
        "sinapse-patterns.timer": """[Unit]
Description=Dispara o pattern distiller aos domingos 05:00

[Timer]
OnCalendar=Sun 05:00
Persistent=true
Unit=sinapse-patterns.service

[Install]
WantedBy=timers.target
""",
        # F4.4 conflict_detector: read-only nos neurônios, gera relatório (insula/conflitos).
        "sinapse-conflicts.service": f"""[Unit]
Description=Memória Viva - Conflict Detector (insula/conflitos)
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/knowledge/conflict_detector.py --apply
""",
        "sinapse-conflicts.timer": """[Unit]
Description=Dispara o conflict detector aos domingos 05:30

[Timer]
OnCalendar=Sun 05:30
Persistent=true
Unit=sinapse-conflicts.service

[Install]
WantedBy=timers.target
""",
        # Revisão diária automática (independe de sessão de chat): resume M9/saúde/projetos.
        "sinapse-review.service": f"""[Unit]
Description=Memória Viva - Daily Review (insula/saude/revisao)
After=network.target
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/knowledge/review_writer.py
""",
        "sinapse-review.timer": """[Unit]
Description=Dispara a revisão diária às 08:07 (após o ciclo noturno do dream)

[Timer]
OnCalendar=*-*-* 08:07:00
Persistent=true
Unit=sinapse-review.service

[Install]
WantedBy=timers.target
""",
        # F4.5 work_tracker: quadro de trabalho ativo (arquivo próprio, idempotente).
        "sinapse-work.service": f"""[Unit]
Description=Memória Viva - Work Tracker (frontal/trabalho/ativo)
After=network.target
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/knowledge/work_tracker.py --apply
""",
        "sinapse-work.timer": """[Unit]
Description=Dispara o work tracker diariamente 23:44

[Timer]
OnCalendar=*-*-* 23:44:00
Persistent=true
Unit=sinapse-work.service

[Install]
WantedBy=timers.target
""",
        # ===== Backup diário dos bancos SQLite críticos =====
        "sinapse-backup.service": f"""[Unit]
Description=Sinapse — Backup diário dos bancos SQLite (hot-backup)
After=network.target
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/health/backup_databases.py
""",
        "sinapse-backup.timer": """[Unit]
Description=Dispara backup dos bancos SQLite diariamente às 02:00

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
Unit=sinapse-backup.service

[Install]
WantedBy=timers.target
""",
        # drift roda log-only (SEM --apply): apenas reporta candidatos a cold/stale.
        "sinapse-drift.service": f"""[Unit]
Description=Memória Viva - Drift Detector (log-only, SEM --apply)
After=network.target
{common_unit}

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={path}
Environment=SINAPSE_HOME={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/knowledge/drift_detector.py
""",
        "sinapse-drift.timer": """[Unit]
Description=Dispara o drift detector (log-only) no 1o dia do mês 02:00

[Timer]
OnCalendar=*-*-01 02:00:00
Persistent=true
Unit=sinapse-drift.service

[Install]
WantedBy=timers.target
""",
    }


def _install_screenpipe() -> None:
    """Install Screenpipe CLI via npm if not already present.

    Screenpipe is optional — the capture adapter activates only when
    screenpipe_alive() == True (safe no-op when not running).

    Linux note: requires libopenblas.so.0 at runtime:
      sudo apt-get install libopenblas0
    or export LD_LIBRARY_PATH pointing to a directory with the lib.
    Set SCREENPIPE_API_KEY env var for authenticated instances.
    """
    import glob

    # Already installed and on PATH
    if shutil.which("screenpipe"):
        print("[screenpipe] already installed:", shutil.which("screenpipe"))
        return

    npm = shutil.which("npm")
    if npm is None:
        print("[screenpipe] npm not found — skipping. Install Node.js ≥18 and re-run.")
        return

    print("[screenpipe] installing @screenpipe/cli-linux-x64 via npm...")
    result = subprocess.run(
        [npm, "install", "-g", "@screenpipe/cli-linux-x64"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"[screenpipe] npm install failed: {result.stderr.strip()}")
        print("[screenpipe] manual: npm install -g @screenpipe/cli-linux-x64")
        return

    # nvm installs to a non-PATH location; look for the binary
    candidates = sorted(glob.glob(
        str(Path.home() / ".nvm/versions/node/*/lib/node_modules/@screenpipe/cli-linux-x64/bin/screenpipe")
    ))
    sp_bin = shutil.which("screenpipe") or (candidates[-1] if candidates else None)
    if sp_bin:
        print(f"[screenpipe] installed: {sp_bin}")
    else:
        print("[screenpipe] installed (binary path not resolved — check nvm setup)")
    print("[screenpipe] to start:  screenpipe record --port 3030 --disable-audio")
    print("[screenpipe] requires:  libopenblas.so.0 (sudo apt install libopenblas0)")
    print("[screenpipe] requires:  SCREENPIPE_API_KEY env var for auth")


def _start_falkordb() -> None:
    """Start FalkorDB via Docker Compose (idempotent).

    Uses docker-compose.falkordb.yml at the project root.
    Skips silently when Docker is unavailable.
    """
    docker = shutil.which("docker")
    if docker is None:
        print("[falkordb] docker not found — skipping. Install Docker and re-run.")
        return

    compose_file = ROOT / "docker-compose.falkordb.yml"
    if not compose_file.exists():
        print(f"[falkordb] {compose_file} not found — skipping.")
        return

    result = subprocess.run(
        [docker, "compose", "-f", str(compose_file), "up", "-d", "--quiet-pull"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"[falkordb] docker compose up failed: {result.stderr.strip()}")
        return

    print("[falkordb] FalkorDB container started (sinapse-falkordb on port 6379)")


def validate_runtime() -> None:
    required = (
        ROOT / ".venv" / "bin" / "python",
        ROOT / ".tools" / "bin" / "bun",
        ROOT / "hive_mind.db",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("missing Hive-Mind runtime files:\n" + "\n".join(missing))


def api_enabled() -> bool:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return False
    for line in env_path.read_text().splitlines():
        if line.startswith("HIVE_MIND_API_KEY=") and line.partition("=")[2].strip():
            return True
    return bool(os.environ.get("HIVE_MIND_API_KEY"))


def claude_mem_plugin_path(home: Path | None = None) -> Path | None:
    """Resolve the installed claude-mem plugin consistently for Claude and Codex."""
    home = home or Path.home()
    candidates: list[Path] = []
    for client in (".claude", ".codex"):
        root = home / client / "plugins"
        candidates.extend((root / "marketplaces" / "thedotmack" / leaf) for leaf in ("plugin", ""))
        cache_root = root / "cache" / "thedotmack" / "claude-mem"
        if cache_root.is_dir():
            for version in sorted(cache_root.iterdir(), reverse=True):
                candidates.extend((version / leaf) for leaf in ("plugin", ""))
    for candidate in candidates:
        for scripts in (candidate / "scripts", candidate / "plugin" / "scripts"):
            for entrypoint in ("worker-service.cjs", "worker-service.js", "worker-wrapper.cjs", "worker-wrapper.js"):
                if (scripts / entrypoint).is_file():
                    return candidate
    return None


def claude_mem_plugin_available() -> bool:
    return claude_mem_plugin_path() is not None

def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ("systemctl", "--user", *args),
        check=check,
        text=True,
    )


def _configure_claude_mem_settings() -> None:
    """Seed required defaults into ~/.claude-mem/settings.json.

    Idempotent: only writes keys that are missing or empty.
    """
    settings_path = Path.home() / ".claude-mem" / "settings.json"
    if not settings_path.exists():
        return
    try:
        cfg = json.loads(settings_path.read_text())
    except Exception:
        return

    changed = False

    # Ensure SwarmClaw sessions (CWD = ~/.swarmclaw/**) are excluded from the
    # claude-mem plugin so they don't appear as project="workspace".
    excluded = cfg.get("CLAUDE_MEM_EXCLUDED_PROJECTS", "")
    swarmclaw_pattern = "**/.swarmclaw/**"
    if swarmclaw_pattern not in excluded:
        parts = [p for p in excluded.split(",") if p.strip()]
        parts.append(swarmclaw_pattern)
        cfg["CLAUDE_MEM_EXCLUDED_PROJECTS"] = ",".join(parts)
        changed = True

    if changed:
        settings_path.write_text(json.dumps(cfg, indent=2) + "\n")
        print("[services] claude-mem settings patched: CLAUDE_MEM_EXCLUDED_PROJECTS updated")


def install(start: bool, with_tests: bool = False) -> int:
    validate_runtime()
    _configure_claude_mem_settings()
    _install_screenpipe()
    _start_falkordb()
    if shutil.which("systemctl") is None:
        print("[services] systemctl unavailable; unit installation skipped")
        return 0
    USER_UNITS.mkdir(parents=True, exist_ok=True)
    definitions = unit_definitions()
    enabled = [
        "sinapse-graphify-watch.service",
        "sinapse-capture-realtime.service",
        "hive-otel-collector.service",
        "sinapse-capture-tailer.timer",
        "sinapse-maintenance.timer",
        # Memória Viva (doc 08): cadências seguras. daily=markdown; weekly=resumo;
        # topics=log-only (sem --apply). dream NÃO entra aqui de propósito: seu
        # go-live é gated por M9 verde >= 7d (§14.4-P2) — habilitar manualmente
        # só após instrumentar dream_cycle_log.
        "sinapse-bridge.timer",   # alimenta o eixo multi-projeto antes do dream
        "sinapse-daily.timer",
        "sinapse-weekly.timer",
        "sinapse-topics.timer",
        # Fase 3: health é read-only (snapshot). drift NÃO entra (roda --apply só à mão).
        "sinapse-health.timer",
        # Fase 5.1: alert_dispatcher lê snapshot e escreve inbox/ (idempotente, seguro).
        "sinapse-alert.timer",
        # Fase 4: decisions/projects materializam arquivos próprios (idempotente) → seguro.
        "sinapse-decisions.timer",
        "sinapse-projects.timer",
        "sinapse-patterns.timer",
        "sinapse-conflicts.timer",
        "sinapse-work.timer",
        "sinapse-review.timer",   # revisão diária 08:07 (não depende de sessão)
        "sinapse-backup.timer",   # backup SQLite diário 02:00 (off-peak)
    ]
    if api_enabled():
        enabled.append("sinapse-api.service")

    # Workers temporais dependem do plugin claude-mem (worker-service.cjs),
    # instalado via `npx claude-mem install` quando existe uma IDE/agente.
    # Numa máquina sem agente, habilitá-los gera crash-loop no boot — a
    # memória temporal só liga junto com o primeiro agente registrado.
    if claude_mem_plugin_available():
        enabled.insert(0, "sinapse-claude-mem.service")
        enabled.insert(1, "sinapse-sqlite-vec.service")
    else:
        print(
            "[services] claude-mem plugin ausente (nenhuma IDE/agente instalado) — "
            "sinapse-claude-mem e sinapse-sqlite-vec NAO habilitados. "
            "Instale um agente (ex.: Claude Code), rode `npx claude-mem install` "
            "e reexecute `install_services.py install`."
        )

    for name, content in definitions.items():
        destination = USER_UNITS / name
        if not destination.exists() or destination.read_text() != content:
            destination.write_text(content)
        destination.chmod(0o600)

    systemctl("daemon-reload")
    systemctl("enable", *enabled)
    if not claude_mem_plugin_available():
        # Idempotência: desliga workers temporais habilitados por runs antigos.
        systemctl(
            "disable", "--now",
            "sinapse-claude-mem.service", "sinapse-sqlite-vec.service",
            check=False,
        )
        systemctl(
            "reset-failed",
            "sinapse-claude-mem.service", "sinapse-sqlite-vec.service",
            check=False,
        )
    systemctl("disable", "sinapse-api.service", check=False) if not api_enabled() else None
    if start:
        systemctl("restart", *enabled)
        if not api_enabled():
            systemctl("stop", "sinapse-api.service", check=False)
    print("[services] installed: " + ", ".join(enabled))
    if with_tests:
        import subprocess as _sp
        validator = ROOT / "scripts" / "health" / "validate_capture_sources.py"
        result = _sp.run(
            [sys.executable, str(validator)],
            check=False,
        )
        if result.returncode != 0:
            print("[services] --with-tests: capture source validation FAILED")
            return 1
        print("[services] --with-tests: capture source validation OK")
    return 0


def check() -> int:
    expected = unit_definitions()
    failed = False
    for name, content in expected.items():
        path = USER_UNITS / name
        status = "ok" if path.is_file() and path.read_text() == content else "drift"
        print(f"{name}: {status}")
        failed |= status != "ok"
    return 1 if failed else 0


def arm_post_reboot() -> int:
    install(start=False)
    subprocess.run(
        (
            str(ROOT / ".venv" / "bin" / "python"),
            str(ROOT / "scripts" / "health" / "validate_after_reboot.py"),
            "prepare",
        ),
        check=True,
        text=True,
    )
    systemctl("reset-failed", "sinapse-post-reboot-validation.service", check=False)
    systemctl("enable", "sinapse-post-reboot-validation.service")
    print("[services] post-reboot validation armed")
    return 0


# =============================================================================
# Multiplataforma (F2/F3): fonte única de specs → launchd (macOS) e manifesto
# JSON (supervisor Node no Windows). O gerador systemd (unit_definitions)
# permanece a referência no Linux; tests/unit/test_service_backends.py trava a
# consistência specs ↔ units.
# =============================================================================

def _enrich_service_specs(specs: list[dict]) -> list[dict]:
    """Add the v2 declarative runtime contract to platform-neutral specs."""
    windows_powershell = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    windows_python = str(ROOT / ".venv" / "Scripts" / "python.exe")
    linux_python = str(ROOT / ".venv" / "bin" / "python")
    command_variants = {
        "sinapse-claude-mem": {"windows": [windows_powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/services/claude-mem-local.ps1")], "linux": [str(ROOT / "scripts/services/claude-mem-local.sh")]},
        "sinapse-sqlite-vec": {"windows": [windows_python, str(ROOT / "plugins/sqlite-vec-worker/worker.py")], "linux": [linux_python, str(ROOT / "plugins/sqlite-vec-worker/worker.py")]},
        "sinapse-graphify-watch": {"windows": [windows_powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/services/start-watcher.ps1")], "linux": [str(ROOT / "scripts/services/start-watcher.sh")]},
        "sinapse-api": {"windows": [windows_python, str(ROOT / "scripts/services/sinapse-api.py")], "linux": [linux_python, str(ROOT / "scripts/services/sinapse-api.py")]},
        "sinapse-mcp-http": {"windows": [windows_python, str(ROOT / "scripts/services/sinapse-mcp-http.py")], "linux": [linux_python, str(ROOT / "scripts/services/sinapse-mcp-http.py")]},
        "hive-otel-collector": {"windows": [windows_python, str(ROOT / "scripts/services/otel_collector.py"), "--host", "127.0.0.1"], "linux": [linux_python, str(ROOT / "scripts/services/otel_collector.py"), "--host", "127.0.0.1"]},
        "sinapse-capture-realtime": {"windows": [windows_python, str(ROOT / "scripts/capture/capture-realtime.py")], "linux": [linux_python, str(ROOT / "scripts/capture/capture-realtime.py")]},
    }
    contracts = {
        "sinapse-claude-mem": ([], 10, {"type": "tcp", "host": "127.0.0.1", "port": 37700, "timeout_seconds": 60}),
        "sinapse-sqlite-vec": (["sinapse-claude-mem"], 20, {"type": "tcp", "host": "127.0.0.1", "port": 37701, "timeout_seconds": 60}),
        "sinapse-graphify-watch": ([], 30, {"type": "none"}),
        "sinapse-api": (["sinapse-sqlite-vec"], 40, {"type": "http", "url": "http://127.0.0.1:37702/api/v1/health", "expected_status": [200, 401], "timeout_seconds": 60}),
        "sinapse-mcp-http": (["sinapse-api"], 50, {"type": "http", "url": "http://127.0.0.1:37703/health", "expected_status": [200], "timeout_seconds": 60}),
        "hive-otel-collector": ([], 15, {"type": "none"}),
        "sinapse-capture-realtime": (["sinapse-claude-mem", "sinapse-sqlite-vec"], 60, {"type": "none"}),
    }
    specs.extend([
        {"name": "ollama", "description": "Ollama local model runtime", "external": True, "enabled_profiles": ["local-min", "local-full"], "required": True, "dependencies": [], "startup_order": 1, "readiness": {"type": "http", "url": "http://127.0.0.1:11434/api/tags", "expected_status": [200], "timeout_seconds": 60}},
        {"name": "docker-desktop", "description": "Docker Desktop engine", "external": True, "enabled_profiles": ["local-full"], "required": True, "dependencies": [], "startup_order": 2, "readiness": {"type": "command", "command": ["docker", "info", "--format", "{{.ServerVersion}}"], "timeout_seconds": 60}},
        {"name": "milvus", "description": "Milvus vector database", "external": True, "enabled_profiles": ["local-full"], "required": True, "dependencies": ["docker-desktop"], "startup_order": 70, "readiness": {"type": "tcp", "host": "127.0.0.1", "port": 19530, "timeout_seconds": 120}},
        {"name": "ragflow", "description": "RAGFlow document pipeline", "external": True, "enabled_profiles": ["local-full"], "required": True, "dependencies": ["docker-desktop"], "startup_order": 80, "readiness": {"type": "http", "url": "http://127.0.0.1:9380/api/v1/system/healthz", "expected_status": [200], "timeout_seconds": 180}},
        {"name": "falkordb", "description": "FalkorDB temporal graph", "external": True, "enabled_profiles": ["local-full"], "required": True, "dependencies": ["docker-desktop"], "startup_order": 75, "readiness": {"type": "tcp", "host": "127.0.0.1", "port": 6379, "timeout_seconds": 120}},
        {"name": "syncthing-watcher", "description": "Syncthing conflict watcher", "external": True, "enabled_profiles": ["local-full"], "required": True, "dependencies": [], "startup_order": 65, "readiness": {"type": "http", "url": "http://127.0.0.1:8384/rest/noauth/health", "expected_status": [200, 401, 403], "timeout_seconds": 60}},
    ])
    platform = "windows" if os.name == "nt" else ("darwin" if sys.platform == "darwin" else "linux")
    for spec in specs:
        if spec.get("external"):
            spec["working_directory"] = str(ROOT)
            spec["commands"] = {}
            spec["command"] = []
            spec["healthcheck"] = dict(spec["readiness"])
            spec["restart_policy"] = "external"
            spec["restart_delay_seconds"] = 0
            spec["restart_max_delay_seconds"] = 0
            spec["restart_limit"] = 0
            continue
        dependencies, startup_order, readiness = contracts[spec["name"]]
        spec["commands"] = command_variants[spec["name"]]
        spec["command"] = list(spec["commands"].get(platform, spec["commands"]["linux"]))
        spec["working_directory"] = str(ROOT)
        spec["enabled_profiles"] = ["local-min", "local-full"]
        spec["required"] = True
        spec["dependencies"] = dependencies
        spec["startup_order"] = startup_order
        spec["readiness"] = readiness
        spec["healthcheck"] = dict(readiness)
        spec["restart_policy"] = spec["restart"]
        spec["restart_delay_seconds"] = spec["restart_sec"]
        spec["restart_max_delay_seconds"] = 120
        spec["restart_limit"] = 10
        spec.pop("optional", None)
    return specs

def service_specs() -> list[dict]:
    """Serviços daemon do runtime em formato neutro de plataforma."""
    path = str(ROOT)
    is_windows = os.name == "nt"
    path_sep = ";" if is_windows else ":"
    claude_mem_data = str(Path.home() / ".claude-mem")
    claude_mem_db = str(Path.home() / ".claude-mem" / "claude-mem.db")
    claude_mem_models = str(Path.home() / ".claude-mem" / "models")
    venv_bin = str(ROOT / ".venv" / ("Scripts" if is_windows else "bin"))
    py = str(Path(venv_bin) / ("python.exe" if is_windows else "python"))
    tools_bin = str(ROOT / ".tools" / "bin")
    rtk_bin = str(ROOT / "integrations" / "rtk" / "target" / "release")
    if is_windows:
        system_path = path_sep.join(
            [tools_bin, venv_bin, rtk_bin, os.environ.get("PATH", "")]
        )
        powershell = str(
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
    else:
        system_path = path_sep.join([tools_bin, venv_bin, rtk_bin, "/usr/local/bin", "/usr/bin", "/bin"])
        powershell = "powershell.exe"

    def script_command(relative_sh: str) -> list[str]:
        script = ROOT / relative_sh
        if is_windows:
            ps1 = script.with_suffix(".ps1")
            return [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)]
        return [str(script)]

    return _enrich_service_specs([
        {
            "name": "sinapse-claude-mem",
            "description": "Sinapse Agent - claude-mem Worker (global multi-project data)",
            "command": script_command("scripts/services/claude-mem-local.sh"),
            "env": {
                "CLAUDE_MEM_DATA_DIR": claude_mem_data,
                "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
                "CLAUDE_MEM_WORKER_PORT": "37700",
                "CLAUDE_MEM_CHROMA_ENABLED": "false",
                "CLAUDE_MEM_MANAGED": "true",
                "FASTEMBED_CACHE_PATH": claude_mem_models,
                "PATH": system_path,
            },
            "restart": "on-failure",
            "restart_sec": 15,
            "requires_claude_mem_plugin": True,
        },
        {
            "name": "sinapse-sqlite-vec",
            "description": "SQLite-Vec semantic search worker for Hive-Mind",
            "command": [py, f"{path}/plugins/sqlite-vec-worker/worker.py"],
            "env": {
                "VEC_WORKER_PORT": "37701",
                "CLAUDE_MEM_DB": claude_mem_db,
                "FASTEMBED_CACHE_PATH": claude_mem_models,
                "PATH": system_path,
            },
            "restart": "on-failure",
            "restart_sec": 15,
            "requires_claude_mem_plugin": True,
        },
        {
            "name": "sinapse-graphify-watch",
            "description": "Hive-Mind Graphify vault watcher",
            "command": script_command("scripts/services/start-watcher.sh"),
            "env": {
                "SINAPSE_HOME": path,
                "PATH": system_path,
                "PYTHONUNBUFFERED": "1",
                "GRAPHIFY_WATCH_DEBOUNCE": "30.0",
            },
            "restart": "on-failure",
            "restart_sec": 15,
        },
        {
            "name": "sinapse-api",
            "description": "Hive-Mind authenticated REST API",
            "command": [py, f"{path}/scripts/services/sinapse-api.py"],
            "env_file": f"{path}/.env",
            "env": {
                "HIVE_MIND_API_HOST": "127.0.0.1",
                "HIVE_MIND_API_PORT": "37702",
                "PATH": system_path,
            },
            "restart": "on-failure",
            "restart_sec": 15,
        },
        {
            "name": "sinapse-mcp-http",
            "description": "Hive-Mind MCP Streamable HTTP Server (spec 2025-03-26)",
            "command": [py, f"{path}/scripts/services/sinapse-mcp-http.py"],
            "env_file": f"{path}/.env",
            "env": {
                "SINAPSE_MCP_HTTP_HOST": "127.0.0.1",
                "SINAPSE_MCP_HTTP_PORT": "37703",
                "PATH": system_path,
            },
            "restart": "on-failure",
            "restart_sec": 15,
            "optional": True,
        },
        {
            "name": "hive-otel-collector",
            "description": "Hive-Mind local OTLP collector",
            "command": [py, f"{path}/scripts/services/otel_collector.py", "--host", "127.0.0.1"],
            "env": {
                "HIVE_OTEL_PORT": "3100",
                "HIVE_OTEL_LOG": f"{path}/logs/otel-spans.log",
                "PATH": system_path,
            },
            "restart": "on-failure",
            "restart_sec": 15,
        },
        {
            "name": "sinapse-capture-realtime",
            "description": "Hive-Mind capture realtime (inotify -> claude-mem, tempo real p/ copilot)",
            "command": [py, f"{path}/scripts/capture/capture-realtime.py"],
            "env_file": f"{path}/.env",
            "env": {
                "CLAUDE_MEM_DATA_DIR": claude_mem_data,
                "VEC_WORKER_URL": "http://127.0.0.1:37701",
                "PATH": system_path,
            },
            "restart": "always",
            "restart_sec": 15,
            "optional": is_windows,
        },
    ])

LAUNCHD_LABEL_PREFIX = "com.hivemind."
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


def _launchd_program(spec: dict) -> list[str]:
    """launchd não tem EnvironmentFile: quando o serviço lê .env, embrulha em
    sh para carregar o arquivo em runtime (valores nunca ficam congelados no
    plist)."""
    env_file = spec.get("env_file")
    if not env_file:
        return list(spec["command"])
    quoted = " ".join(f"'{part}'" for part in spec["command"])
    return ["/bin/sh", "-c", f"set -a; [ -f '{env_file}' ] && . '{env_file}'; set +a; exec {quoted}"]


def launchd_definitions() -> dict[str, bytes]:
    """Gera plists launchd (macOS) a partir de service_specs()."""
    import plistlib

    log_dir = ROOT / "logs" / "launchd"
    plists: dict[str, bytes] = {}
    for spec in service_specs():
        if spec.get("external"):
            continue
        label = LAUNCHD_LABEL_PREFIX + spec["name"]
        payload: dict = {
            "Label": label,
            "ProgramArguments": _launchd_program(spec),
            "WorkingDirectory": str(ROOT),
            "EnvironmentVariables": dict(spec.get("env", {})),
            "RunAtLoad": True,
            # on-failure → reinicia só em saída com erro; always → sempre.
            "KeepAlive": True if spec.get("restart") == "always" else {"SuccessfulExit": False},
            "ThrottleInterval": int(spec.get("restart_sec", 15)),
            "StandardOutPath": str(log_dir / f"{spec['name']}.log"),
            "StandardErrorPath": str(log_dir / f"{spec['name']}.err.log"),
            "Umask": 0o077,
        }
        plists[f"{label}.plist"] = plistlib.dumps(payload)
    return plists


def launchd_install(start: bool = True) -> int:
    if sys.platform != "darwin":
        print("[services] launchd backend requer macOS", file=sys.stderr)
        return 1
    (ROOT / "logs" / "launchd").mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    plugin_ok = claude_mem_plugin_available()
    installed = []
    for filename, content in launchd_definitions().items():
        spec_name = filename[len(LAUNCHD_LABEL_PREFIX):-len(".plist")]
        spec = next(s for s in service_specs() if s["name"] == spec_name)
        if spec.get("requires_claude_mem_plugin") and not plugin_ok:
            print(f"[services] {spec_name}: claude-mem plugin ausente — não habilitado")
            continue
        if spec.get("optional"):
            continue
        destination = LAUNCH_AGENTS / filename
        destination.write_bytes(content)
        destination.chmod(0o600)
        if start:
            subprocess.run(["launchctl", "unload", str(destination)], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["launchctl", "load", str(destination)], check=False)
        installed.append(filename)
    print(f"[services] launchd instalado: {', '.join(installed)}")
    return 0


def manifest() -> dict:
    """Manifesto JSON dos serviços para o supervisor Node (Windows/fallback)."""
    return {
        "manifest_version": 2,
        "root": str(ROOT),
        "log_dir": str(ROOT / "logs" / "supervisor"),
        "claude_mem_plugin_available": claude_mem_plugin_available(),
        "services": service_specs(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    install_cmd = sub.add_parser("install")
    install_cmd.add_argument("--no-start", action="store_true")
    install_cmd.add_argument("--with-tests", action="store_true",
                             help="run validate_capture_sources after install")
    sub.add_parser("check")
    sub.add_parser("arm-post-reboot")
    sub.add_parser("manifest", help="imprime o manifesto JSON dos serviços (supervisor Node)")
    launchd_cmd = sub.add_parser("launchd", help="instala LaunchAgents (macOS)")
    launchd_cmd.add_argument("--no-start", action="store_true")
    args = parser.parse_args()
    if args.command == "install":
        return install(start=not args.no_start, with_tests=args.with_tests)
    if args.command == "arm-post-reboot":
        return arm_post_reboot()
    if args.command == "manifest":
        print(json.dumps(manifest(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "launchd":
        return launchd_install(start=not args.no_start)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
