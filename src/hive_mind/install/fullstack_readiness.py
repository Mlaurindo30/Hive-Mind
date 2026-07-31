from __future__ import annotations

import argparse
import json
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib import error, request

from hive_mind.maintenance.runtime_services import service_specs


@dataclass(frozen=True)
class FullStackReadinessResult:
    ready: bool
    missing: tuple[str, ...]
    diagnostics: tuple[str, ...]

    def to_legacy_dict(self) -> dict[str, object]:
        return {
            "Ready": self.ready,
            "Missing": list(self.missing),
            "Diagnostics": list(self.diagnostics),
        }


def test_tcp_readiness(target_host: str, port: int, timeout_seconds: float = 2.0) -> bool:
    try:
        with socket.create_connection((target_host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def test_http_readiness(url: str, accepted_status: tuple[int, ...], timeout_seconds: float = 5.0) -> bool:
    try:
        with request.urlopen(url, timeout=timeout_seconds) as response:
            return int(response.status) in accepted_status
    except error.HTTPError as exc:
        return int(exc.code) in accepted_status
    except (error.URLError, TimeoutError, OSError, ValueError):
        return False


def fullstack_requirements(profile: str) -> list[dict[str, object]]:
    if profile == "local-min":
        return []
    requirements: list[dict[str, object]] = []
    for spec in service_specs():
        if not spec.get("external"):
            continue
        if not spec.get("required", False):
            continue
        if profile not in spec.get("enabled_profiles", []):
            continue
        requirements.append(
            {
                "name": spec["name"],
                "readiness": dict(spec["readiness"]),
            }
        )
    return requirements


def _default_probe(requirement: dict[str, object]) -> bool:
    readiness = dict(requirement["readiness"])
    readiness_type = readiness.get("type")
    if readiness_type == "tcp":
        return test_tcp_readiness(
            str(readiness["host"]),
            int(readiness["port"]),
            float(readiness.get("timeout_seconds", 2)),
        )
    if readiness_type == "http":
        return test_http_readiness(
            str(readiness["url"]),
            tuple(int(code) for code in readiness.get("expected_status", [200])),
            float(readiness.get("timeout_seconds", 5)),
        )
    if readiness_type == "command":
        command = [str(part) for part in readiness.get("command", [])]
        if not command:
            return False
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=float(readiness.get("timeout_seconds", 60)),
        )
        return result.returncode == 0
    if readiness_type == "none":
        return True
    return False


def test_fullstack_readiness(
    *,
    root: str | Path,
    profile: str,
    probe: Callable[[str], bool] | None = None,
    timeout_seconds: int = 180,
) -> FullStackReadinessResult:
    del root  # reserved for future root-specific probes; keep the public contract stable
    requirements = fullstack_requirements(profile)
    if not requirements:
        return FullStackReadinessResult(True, (), ())

    deadline = time.monotonic() + timeout_seconds
    missing: list[str] = []
    while True:
        missing = []
        for requirement in requirements:
            name = str(requirement["name"])
            ok = probe(name) if probe else _default_probe(requirement)
            if not ok:
                missing.append(name)
        if not missing or probe is not None or time.monotonic() >= deadline:
            break
        time.sleep(2)
    diagnostics = tuple(f"required service is not ready: {name}" for name in missing)
    return FullStackReadinessResult(not missing, tuple(missing), diagnostics)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hive-Mind native full-stack readiness probes")
    sub = parser.add_subparsers(dest="command", required=True)

    tcp = sub.add_parser("tcp")
    tcp.add_argument("--host", required=True)
    tcp.add_argument("--port", required=True, type=int)
    tcp.add_argument("--timeout", type=float, default=2.0)

    http = sub.add_parser("http")
    http.add_argument("--url", required=True)
    http.add_argument("--accepted-status", nargs="+", required=True, type=int)
    http.add_argument("--timeout", type=float, default=5.0)

    full = sub.add_parser("full")
    full.add_argument("--root", required=True)
    full.add_argument("--profile", choices=("local-min", "local-full"), required=True)
    full.add_argument("--timeout-seconds", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "tcp":
        print(json.dumps({"Ready": test_tcp_readiness(args.host, args.port, args.timeout)}))
        return 0
    if args.command == "http":
        print(json.dumps({"Ready": test_http_readiness(args.url, tuple(args.accepted_status), args.timeout)}))
        return 0

    result = test_fullstack_readiness(
        root=args.root,
        profile=args.profile,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result.to_legacy_dict(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
