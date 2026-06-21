import importlib.util
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location(
        "sync_claude_mem_provider",
        SCRIPTS / "setup" / "sync-claude-mem-provider.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_runtime_updates_usam_claude_mem_global():
    mod = _load()
    updates = mod.runtime_updates()
    data_dir = Path.home() / ".claude-mem"

    assert updates["CLAUDE_MEM_DATA_DIR"] == str(data_dir)
    assert updates["FASTEMBED_CACHE_PATH"] == str(data_dir / "models")
    assert updates["CLAUDE_MEM_CHROMA_ENABLED"] == "false"
    assert updates["CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH"] == str(
        data_dir / "transcript-watch.json"
    )
    assert str(mod.ROOT / "claude-mem" / "data") not in "\n".join(updates.values())
