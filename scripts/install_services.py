#!/usr/bin/env python3
"""Install idempotent user services pointing only at project-local runtimes."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
USER_UNITS = Path.home() / ".config" / "systemd" / "user"


def unit_definitions() -> dict[str, str]:
    path = str(ROOT)
    common_unit = "StartLimitIntervalSec=60\nStartLimitBurst=3"
    return {
        "sinapse-claude-mem.service": f"""[Unit]
Description=Sinapse Agent - claude-mem Worker (global)
After=network.target
{common_unit}

[Service]
Type=simple
UMask=0077
WorkingDirectory=%h/.claude-mem
Environment=CLAUDE_MEM_WORKER_HOST=127.0.0.1
Environment=CLAUDE_MEM_WORKER_PORT=37700
Environment=CLAUDE_MEM_CHROMA_ENABLED=false
Environment=CLAUDE_MEM_MANAGED=true
Environment=PATH={path}/.tools/bin:{path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/scripts/claude-mem-local.sh
Restart=on-failure
RestartSec=2

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
Environment=CLAUDE_MEM_DB=%h/.claude-mem/claude-mem.db
Environment=FASTEMBED_CACHE_PATH=%h/.claude-mem/models
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/plugins/sqlite-vec-worker/worker.py
Restart=on-failure
RestartSec=5

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
ExecStart={path}/scripts/start-watcher.sh
Restart=on-failure
RestartSec=10

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
ExecStart={path}/.venv/bin/python {path}/scripts/sinapse-api.py
Restart=on-failure
RestartSec=5

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
ExecStart={path}/.venv/bin/python {path}/scripts/capture-tailer.py --all --scan --since-hours 1
""",
        "sinapse-capture-realtime.service": f"""[Unit]
Description=Hive-Mind capture realtime (inotify -> claude-mem, tempo real p/ copilot)
After=network.target sinapse-claude-mem.service
{common_unit}

[Service]
Type=simple
UMask=0077
WorkingDirectory={path}
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/scripts/capture-realtime.py
Restart=always
RestartSec=3

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
Environment=PATH={path}/.venv/bin:{path}/.tools/bin:{path}/rtk/target/release:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/scripts/validate_after_reboot.py validate
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
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/.venv/bin/python {path}/scripts/capture_maintenance.py
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
Environment=CLAUDE_MEM_DB=%h/.claude-mem/claude-mem.db
Environment=PATH={path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart={path}/.venv/bin/python {path}/scripts/claude_mem_bridge.py
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
ExecStart={path}/.venv/bin/python {path}/scripts/dream_cycle.py
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
ExecStart={path}/.venv/bin/python {path}/scripts/daily_writer.py
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
ExecStart={path}/.venv/bin/python {path}/scripts/weekly_synthesizer.py
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
ExecStart={path}/.venv/bin/python {path}/scripts/topic_consolidator.py
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
ExecStart={path}/.venv/bin/python {path}/scripts/health_dashboard.py
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
ExecStart={path}/.venv/bin/python {path}/scripts/drift_detector.py
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


def validate_runtime() -> None:
    required = (
        ROOT / ".venv" / "bin" / "python",
        ROOT / ".tools" / "bin" / "bun",
        ROOT / "hive_mind.db",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("missing project-local runtime files:\n" + "\n".join(missing))


def api_enabled() -> bool:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return False
    for line in env_path.read_text().splitlines():
        if line.startswith("HIVE_MIND_API_KEY=") and line.partition("=")[2].strip():
            return True
    return bool(os.environ.get("HIVE_MIND_API_KEY"))


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ("systemctl", "--user", *args),
        check=check,
        text=True,
    )


def install(start: bool) -> int:
    validate_runtime()
    if shutil.which("systemctl") is None:
        print("[services] systemctl unavailable; unit installation skipped")
        return 0
    USER_UNITS.mkdir(parents=True, exist_ok=True)
    definitions = unit_definitions()
    enabled = [
        "sinapse-claude-mem.service",
        "sinapse-sqlite-vec.service",
        "sinapse-graphify-watch.service",
        "sinapse-capture-realtime.service",
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
    ]
    if api_enabled():
        enabled.append("sinapse-api.service")

    for name, content in definitions.items():
        destination = USER_UNITS / name
        if not destination.exists() or destination.read_text() != content:
            destination.write_text(content)
        destination.chmod(0o600)

    systemctl("daemon-reload")
    systemctl("enable", *enabled)
    systemctl("disable", "sinapse-api.service", check=False) if not api_enabled() else None
    if start:
        systemctl("restart", *enabled)
        if not api_enabled():
            systemctl("stop", "sinapse-api.service", check=False)
    print("[services] installed: " + ", ".join(enabled))
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
            str(ROOT / "scripts" / "validate_after_reboot.py"),
            "prepare",
        ),
        check=True,
        text=True,
    )
    systemctl("reset-failed", "sinapse-post-reboot-validation.service", check=False)
    systemctl("enable", "sinapse-post-reboot-validation.service")
    print("[services] post-reboot validation armed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    install_cmd = sub.add_parser("install")
    install_cmd.add_argument("--no-start", action="store_true")
    sub.add_parser("check")
    sub.add_parser("arm-post-reboot")
    args = parser.parse_args()
    if args.command == "install":
        return install(start=not args.no_start)
    if args.command == "arm-post-reboot":
        return arm_post_reboot()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
