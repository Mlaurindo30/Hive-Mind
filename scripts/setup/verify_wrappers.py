#!/usr/bin/env python3
"""Verify K1 service wrappers without starting containers.

K1 treats Milvus and RAGFlow as wrappers, not git components. The installer and
real tests use this module to fail closed when a wrapper compose file is invalid
or its image is not pinned by digest.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent.parent
WRAPPERS = ("milvus", "ragflow")
_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")


def _compose_file(root: Path, name: str) -> Path:
    return root / "integrations" / name / "docker-compose.yml"


def _load_compose(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"compose invalido: {path}")
    return data


def _first_service_image(compose: dict[str, Any]) -> str:
    services = compose.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError("compose sem services")
    first = next(iter(services.values()))
    if not isinstance(first, dict) or not first.get("image"):
        raise ValueError("service sem image")
    return str(first["image"])


def _docker_compose_config(path: Path) -> tuple[bool, str]:
    if not shutil.which("docker"):
        return False, "docker nao encontrado"
    proc = subprocess.run(
        ["docker", "compose", "-f", str(path), "config", "--quiet"],
        cwd=str(path.parent),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, output


def verify_wrapper(root: Path, name: str) -> dict[str, Any]:
    compose_path = _compose_file(root, name)
    report: dict[str, Any] = {
        "name": name,
        "compose": str(compose_path),
        "ok": False,
        "image": "",
        "image_has_digest": False,
        "compose_config_ok": False,
        "errors": [],
    }
    try:
        if not compose_path.is_file():
            raise FileNotFoundError(compose_path)
        compose = _load_compose(compose_path)
        image = _first_service_image(compose)
        report["image"] = image
        report["image_has_digest"] = bool(_DIGEST_RE.search(image))
        if not report["image_has_digest"]:
            report["errors"].append("image sem digest sha256 pinado")

        config_ok, config_output = _docker_compose_config(compose_path)
        report["compose_config_ok"] = config_ok
        if not config_ok:
            report["errors"].append(config_output or "docker compose config falhou")
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")

    report["ok"] = bool(report["image_has_digest"] and report["compose_config_ok"] and not report["errors"])
    return report


def verify_all_wrappers(root: Path = ROOT) -> list[dict[str, Any]]:
    return [verify_wrapper(root, name) for name in WRAPPERS]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Hive-Mind K1 wrapper compose files")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    reports = verify_all_wrappers(args.root)
    for report in reports:
        status = "OK" if report["ok"] else "FAIL"
        print(f"{status} {report['name']} image={report['image'] or '-'} compose={report['compose']}")
        for error in report["errors"]:
            print(f"  - {error}")
    return 0 if all(report["ok"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
