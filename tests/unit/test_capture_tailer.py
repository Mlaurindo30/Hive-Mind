import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "capture"


def _load_tailer():
    sys.path.insert(0, str(CAPTURE))
    spec = importlib.util.spec_from_file_location("capture_tailer", CAPTURE / "capture-tailer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rest_adapter_sem_sources_e_processado_quando_explicitamente_habilitado(monkeypatch, tmp_path):
    tailer = _load_tailer()

    calls = {"parser": 0, "ingest": 0}

    def parser(source):
        calls["parser"] += 1
        assert source is None
        return [{"sid": "screenpipe:1", "prompt": "ocr", "turns": [], "last": "ocr"}]

    class Store:
        pass

    monkeypatch.setattr(tailer.core, "worker_alive", lambda: True)
    monkeypatch.setattr(tailer.core, "SeenStore", lambda: Store())
    monkeypatch.setattr(tailer.core, "ingest", lambda *_a: calls.__setitem__("ingest", calls["ingest"] + 1) or 1)
    monkeypatch.setattr(tailer, "_acquire_lock", lambda: object())
    monkeypatch.setattr(tailer, "ADAPTERS", {
        "screenpipe": {
            "owner": "timer",
            "mode": "reparse",
            "parser": parser,
            "sources": [],
            "watch": [],
        }
    })
    monkeypatch.setattr(tailer, "adapters_by_owner", lambda owner: {"screenpipe": tailer.ADAPTERS["screenpipe"]})
    monkeypatch.setattr(sys, "argv", ["capture-tailer.py", "--all", "--scan"])

    assert tailer.main() == 0
    assert calls == {"parser": 1, "ingest": 1}


def test_screenpipe_adapter_nao_suja_memoria_por_padrao(monkeypatch):
    sys.path.insert(0, str(CAPTURE))
    from capture_adapters import _parse_screenpipe

    monkeypatch.delenv("SINAPSE_SCREENPIPE_CONTINUOUS", raising=False)
    assert _parse_screenpipe() == []
