"""P2-R2 — MINIO_HOST must not carry a port.

RAGFlow renders its MinIO endpoint from `conf/service_conf.yaml.template`:

    host: '${MINIO_HOST:-minio}:9000'

The template appends the port itself, so `MINIO_HOST` must be a bare hostname.
Setting `MINIO_HOST=minio:9000` renders `minio:9000:9000`, and the MinIO client
rejects it:

    >>> Minio('minio:9000:9000', ...)
    ValueError: invalid port

That is a silent failure: the container's healthcheck probes
`http://localhost:9000/minio/health/live` inside the *minio* service, so the
RAGFlow stack still reports healthy while every object-storage call raises. The
live host was found in exactly that state, with `host: 'minio:9000:9000'` in its
rendered config, which is why "the running container is healthy" was not
evidence that the value was correct.

This test pins the contract so the port can never be reintroduced.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "integrations" / "ragflow" / "docker-compose.yml"

# How RAGFlow builds the endpoint (conf/service_conf.yaml.template, v0.26.1).
RAGFLOW_TEMPLATE = "{minio_host}:9000"


def _ragflow_environment() -> dict:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return compose["services"]["ragflow"]["environment"]


def test_minio_host_is_a_bare_hostname():
    value = _ragflow_environment()["MINIO_HOST"]

    assert ":" not in value, (
        f"MINIO_HOST={value!r} carries a port; RAGFlow appends ':9000' itself, "
        f"which would render {RAGFLOW_TEMPLATE.format(minio_host=value)!r}"
    )
    assert value == "minio"


def test_the_rendered_endpoint_has_exactly_one_port():
    rendered = RAGFLOW_TEMPLATE.format(minio_host=_ragflow_environment()["MINIO_HOST"])

    assert rendered.count(":") == 1
    host, _, port = rendered.partition(":")
    assert host == "minio"
    assert port == "9000"


def test_minio_host_matches_the_compose_service_name():
    """The value must resolve over the compose network, not via published ports."""
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))

    assert _ragflow_environment()["MINIO_HOST"] in compose["services"]


def test_minio_publishes_the_port_the_template_assumes():
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    container_ports = [str(p).rsplit(":", 1)[-1] for p in compose["services"]["minio"]["ports"]]

    assert "9000" in container_ports, (
        "RAGFlow's template hardcodes :9000; the minio service must listen there"
    )


@pytest.mark.parametrize(
    "minio_host,valid",
    [("minio", True), ("minio:9000", False), ("minio:9000:9000", False)],
)
def test_rendered_endpoint_shape_is_what_the_client_accepts(minio_host, valid):
    """Documents the parse rule without requiring the minio package at test time.

    Verified against the real client in the RAGFlow image:
      'minio:9000'      -> Minio(...) constructs, base_url.host == 'minio:9000'
      'minio:9000:9000' -> ValueError: invalid port
    """
    rendered = RAGFLOW_TEMPLATE.format(minio_host=minio_host)
    host, _, port = rendered.partition(":")

    accepted = rendered.count(":") == 1 and port.isdigit() and bool(host)

    assert accepted is valid
