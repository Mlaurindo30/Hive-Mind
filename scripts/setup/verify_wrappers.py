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


def _service_images(compose: dict[str, Any]) -> dict[str, str]:
    services = compose.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError("compose sem services")
    images: dict[str, str] = {}
    for service_name, service in services.items():
        if not isinstance(service, dict) or not service.get("image"):
            raise ValueError(f"service sem image: {service_name}")
        images[str(service_name)] = str(service["image"])
    return images


def _docker_compose_config(path: Path) -> tuple[bool | None, str]:
    """Valida o compose via docker. Retorna (None, msg) quando docker nao existe."""
    if not shutil.which("docker"):
        return None, "docker nao encontrado"
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


def verify_wrapper(root: Path, name: str, *, require_docker: bool = False) -> dict[str, Any]:
    compose_path = _compose_file(root, name)
    report: dict[str, Any] = {
        "name": name,
        "compose": str(compose_path),
        "ok": False,
        "image": "",
        "images": {},
        "image_has_digest": False,
        "compose_config_ok": False,
        "compose_config_skipped": False,
        "errors": [],
        "warnings": [],
    }
    try:
        if not compose_path.is_file():
            raise FileNotFoundError(compose_path)
        compose = _load_compose(compose_path)
        images = _service_images(compose)
        report["images"] = images
        report["image"] = ", ".join(f"{service}={image}" for service, image in images.items())
        unpinned = [
            f"{service}={image}"
            for service, image in images.items()
            if not _DIGEST_RE.search(image)
        ]
        report["image_has_digest"] = not unpinned
        if unpinned:
            report["errors"].append("images sem digest sha256 pinado: " + ", ".join(unpinned))

        config_ok, config_output = _docker_compose_config(compose_path)
        if config_ok is None and not require_docker:
            # Docker so e' pre-requisito no perfil local-full. Sem ele, a
            # verificacao estatica (compose parseavel + imagens pinadas por
            # digest) continua valendo; o `docker compose config` fica adiado
            # para quando o wrapper for realmente usado.
            report["compose_config_ok"] = True
            report["compose_config_skipped"] = True
            report["warnings"].append(
                "docker ausente: `docker compose config` adiado (wrappers sao opcionais fora do local-full)"
            )
        elif not config_ok:
            report["compose_config_ok"] = False
            report["errors"].append(config_output or "docker compose config falhou")
        else:
            report["compose_config_ok"] = True
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")

    report["ok"] = bool(report["image_has_digest"] and report["compose_config_ok"] and not report["errors"])
    return report


def verify_all_wrappers(root: Path = ROOT, *, require_docker: bool = False) -> list[dict[str, Any]]:
    return [verify_wrapper(root, name, require_docker=require_docker) for name in WRAPPERS]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Hive-Mind K1 wrapper compose files")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--require-docker",
        action="store_true",
        help="Falha se docker estiver ausente (perfil local-full, onde os wrappers sobem de fato)",
    )
    args = parser.parse_args()
    reports = verify_all_wrappers(args.root, require_docker=args.require_docker)
    for report in reports:
        status = "OK" if report["ok"] else "FAIL"
        print(f"{status} {report['name']} image={report['image'] or '-'} compose={report['compose']}")
        for warning in report.get("warnings", []):
            print(f"  ~ {warning}")
        for error in report["errors"]:
            print(f"  - {error}")
    return 0 if all(report["ok"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
