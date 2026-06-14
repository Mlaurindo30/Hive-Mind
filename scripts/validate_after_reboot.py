#!/usr/bin/env python3
"""Produce an auditable validation report after a real machine reboot."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from recovery import verify_database


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
MARKER = LOG_DIR / "pre-reboot.json"
REPORT = LOG_DIR / "post-reboot-validation.json"
CORE_SERVICES = (
    "sinapse-claude-mem.service",
    "sinapse-sqlite-vec.service",
    "sinapse-graphify-watch.service",
)
PORTS = (37700, 37701, 37702)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def run(*command: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True, capture_output=True)


def prepare() -> int:
    LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    api_unit = run(
        "systemctl",
        "--user",
        "is-enabled",
        "sinapse-api.service",
        check=False,
    )
    marker = {
        "prepared_at": now(),
        "boot_id": boot_id(),
        "require_api": api_unit.returncode == 0,
    }
    MARKER.write_text(json.dumps(marker, indent=2) + "\n")
    MARKER.chmod(0o600)
    REPORT.unlink(missing_ok=True)
    print(json.dumps(marker))
    return 0


def wait_for_runtime(
    services: tuple[str, ...],
    ports: tuple[int, ...],
    timeout: int = 120,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        active = all(
            run("systemctl", "--user", "is-active", service, check=False).returncode == 0
            for service in services
        )
        ports_open = all(port_open(port) for port in ports)
        if active and ports_open:
            return
        time.sleep(2)
    raise RuntimeError("runtime did not become healthy within 120 seconds")


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def service_state(service: str) -> dict[str, str | int]:
    result = run(
        "systemctl",
        "--user",
        "show",
        service,
        "-p",
        "ActiveState",
        "-p",
        "SubState",
        "-p",
        "NRestarts",
        "-p",
        "MainPID",
    )
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    values["NRestarts"] = int(values["NRestarts"])
    values["MainPID"] = int(values["MainPID"])
    return values


def listening_ports(expected_ports: tuple[int, ...] = PORTS) -> dict[str, str]:
    output = run("ss", "-ltn", "-H").stdout
    found: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        address = fields[3]
        for port in expected_ports:
            if address.endswith(f":{port}"):
                found[str(port)] = address
    return found


def claude_mem_database() -> dict[str, int | str]:
    import sqlite_vec

    db_path = ROOT / "claude-mem" / "data" / "claude-mem.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        observations = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        vectors = conn.execute("SELECT COUNT(*) FROM vec_observations").fetchone()[0]
    finally:
        conn.close()
    return {
        "path": str(db_path),
        "integrity_check": integrity,
        "foreign_key_violations": foreign_keys,
        "observations": observations,
        "vectors": vectors,
    }


def global_claude_mem_references() -> list[dict[str, str | int]]:
    forbidden = str(Path.home() / ".claude-mem")
    references: list[dict[str, str | int]] = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
        except OSError:
            continue
        matches: set[str] = set()
        for link in (proc / "cwd", proc / "exe"):
            try:
                target = os.readlink(link)
            except OSError:
                continue
            if forbidden in target:
                matches.add(target)
        try:
            cmdline = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            cmdline = ""
        if forbidden in cmdline:
            matches.add(cmdline)
        try:
            file_descriptors = list((proc / "fd").iterdir())
        except OSError:
            file_descriptors = ()
        for descriptor in file_descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            if forbidden in target:
                matches.add(target)
        if matches:
            references.append({"pid": int(proc.name), "references": sorted(matches)})
    return references


def validate() -> int:
    if not MARKER.is_file():
        raise RuntimeError("pre-reboot marker is missing")
    marker = json.loads(MARKER.read_text())
    current_boot = boot_id()
    if marker["boot_id"] == current_boot:
        raise RuntimeError("boot_id did not change; no real reboot was observed")

    service_names = CORE_SERVICES + (
        ("sinapse-api.service",) if marker.get("require_api") else ()
    )
    expected_ports = (37700, 37701) + ((37702,) if marker.get("require_api") else ())
    wait_for_runtime(service_names, expected_ports)
    services = {service: service_state(service) for service in service_names}
    ports = listening_ports(expected_ports)
    umc = verify_database(ROOT / "hive_mind.db")
    claude_mem = claude_mem_database()
    global_references = global_claude_mem_references()
    smoke = run("bash", "tests/smoke/test_smoke.sh", check=False)

    checks = {
        "boot_changed": True,
        "services_active": all(state["ActiveState"] == "active" for state in services.values()),
        "services_without_restarts": all(state["NRestarts"] == 0 for state in services.values()),
        "ports_loopback_only": all(
            str(port) in ports and ports[str(port)].startswith("127.0.0.1:")
            for port in expected_ports
        ),
        "umc_integrity": umc["integrity_check"] == "ok"
        and umc["quick_check"] == "ok"
        and umc["foreign_key_violations"] == 0,
        "claude_mem_integrity": claude_mem["integrity_check"] == "ok"
        and claude_mem["foreign_key_violations"] == 0,
        "claude_mem_vectors_complete": claude_mem["vectors"] >= claude_mem["observations"] >= 159,
        "no_global_claude_mem_references": not global_references,
        "smoke_passed": smoke.returncode == 0,
    }
    report = {
        "validated_at": now(),
        "prepared_boot_id": marker["boot_id"],
        "validated_boot_id": current_boot,
        "checks": checks,
        "services": services,
        "ports": ports,
        "umc": umc,
        "claude_mem": claude_mem,
        "global_claude_mem_references": global_references,
        "smoke": {
            "returncode": smoke.returncode,
            "stdout": smoke.stdout,
            "stderr": smoke.stderr,
        },
        "status": "pass" if all(checks.values()) else "fail",
    }
    LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    REPORT.chmod(0o600)
    print(json.dumps({"status": report["status"], "checks": checks}, indent=2))
    return 0 if report["status"] == "pass" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "validate"))
    args = parser.parse_args()
    return prepare() if args.command == "prepare" else validate()


if __name__ == "__main__":
    raise SystemExit(main())
