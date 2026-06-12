"""Conftest para testes de integração REAIS do pipeline LLM Council.

Gating: todos os testes aqui batem em APIs (Ollama local, Ollama cloud, Google,
OpenAI-compat). São pulados automaticamente se:
  - pytest não foi invocado com chave real disponível
  - ollama local não responde em localhost:11434
  - o provedor-alvo não tem credencial resolvida por core.auth.get_credentials

Não usam mock. Falham honestamente quando o provedor real cai.

Variável de ambiente opt-in:
  HIVE_RUN_INTEGRATION=1    habilita a suíte inteira
  HIVE_RUN_VISION=1         habilita subset de visão
  HIVE_RUN_BUG7=1           habilita subset Bug 7 (precisa Ollama local + modelo thinking)
"""
import os
import socket
from pathlib import Path
import pytest

# Repo root na sys.path para `from core.*` funcionar em qualquer cwd
_ROOT = Path(__file__).resolve().parents[3]
import sys
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _provider_has_credential(provider: str) -> bool:
    """Se o provider exige credencial, pergunta ao core.auth (sem efeitos colaterais)."""
    try:
        from core.auth import get_credentials
        return bool(get_credentials(provider))
    except Exception:
        return False


# -------------------- pytest hooks --------------------

def pytest_collection_modifyitems(config, items):
    """Aplica skip-default a não ser que a variável opt-in esteja setada."""
    if os.environ.get("HIVE_RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(
        reason="Integração real desabilitada. Defina HIVE_RUN_INTEGRATION=1 para rodar."
    )
    for item in items:
        item.add_marker(skip)


# -------------------- fixtures --------------------

@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _ROOT


@pytest.fixture(scope="session")
def ollama_local_alive() -> bool:
    """True se Ollama local responde em 11434."""
    return _port_open("127.0.0.1", 11434)


@pytest.fixture
def ollama_model_available(ollama_local_alive):
    """Factory: yield has(‘gemma4:26b’) etc. via `ollama list`."""
    if not ollama_local_alive:
        pytest.skip("Ollama local não está em :11434")
    import subprocess
    try:
        out = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("`ollama` CLI não disponível")
    models = {line.split()[0] for line in out.splitlines() if line.strip() and not line.startswith("NAME")}
    return lambda name: name in models


@pytest.fixture
def requires_ollama_cloud(ollama_local_alive):
    """Pula se ollama-cloud não tem credencial. NÃO pula por chave ausente — apenas
    exige que get_credentials resolva algo. Em dev local a chave pode estar no
    ~/.config/ruflo/providers.json sem vazar pra env."""
    if not _provider_has_credential("ollama-cloud"):
        pytest.skip("Credencial ollama-cloud ausente (verifique ~/.config/ruflo/providers.json)")
    return True


@pytest.fixture
def requires_google():
    if not _provider_has_credential("google"):
        pytest.skip("Credencial google ausente")
    return True


@pytest.fixture
def saved_env(monkeypatch):
    """Salva e restaura TODAS as vars HIVE_* entre testes (evita leak de C1→C2)."""
    keys = [k for k in os.environ if k.startswith("HIVE_")]
    saved = {k: os.environ.get(k) for k in keys}
    yield monkeypatch
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    for k, v in saved.items():
        if v is not None:
            monkeypatch.setenv(k, v)


@pytest.fixture
def vision_png(tmp_path: Path) -> Path:
    """PNG 128x128 vermelho real, codificado em zlib (não usa Pillow pra ser
    independente de deps de teste)."""
    import struct
    import zlib

    w = h = 128
    rgb = (220, 30, 30)
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(t: bytes, d: bytes) -> bytes:
        return (
            struct.pack(">I", len(d))
            + t
            + d
            + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    idat = zlib.compress(raw, 9)
    png = sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    p = tmp_path / "vision_real.png"
    p.write_bytes(png)
    return p
