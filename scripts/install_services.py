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
Description=Sinapse Agent - claude-mem Worker
After=network.target
{common_unit}

[Service]
Type=simple
UMask=0077
WorkingDirectory={path}/claude-mem
Environment=CLAUDE_MEM_DATA_DIR={path}/claude-mem/data
Environment=CLAUDE_MEM_WORKER_HOST=127.0.0.1
Environment=CLAUDE_MEM_WORKER_PORT=37700
Environment=CLAUDE_MEM_CHROMA_ENABLED=false
Environment=CLAUDE_MEM_MANAGED=true
Environment=PATH={path}/claude-mem/plugin/node_modules/.bin:{path}/.tools/bin:{path}/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart={path}/scripts/claude-mem-local.sh
Restart=on-failure
RestartSec=5

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
Environment=CLAUDE_MEM_DB={path}/claude-mem/data/claude-mem.db
Environment=FASTEMBED_CACHE_PATH={path}/claude-mem/data/models
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
    }


def validate_runtime() -> None:
    required = (
        ROOT / ".venv" / "bin" / "python",
        ROOT / ".tools" / "bin" / "bun",
        ROOT / "claude-mem" / "plugin" / "scripts" / "worker-service.cjs",
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


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    install_cmd = sub.add_parser("install")
    install_cmd.add_argument("--no-start", action="store_true")
    sub.add_parser("check")
    args = parser.parse_args()
    if args.command == "install":
        return install(start=not args.no_start)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
