import importlib.util
import datetime
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


def test_runtime_updates_preferem_o_data_dir_do_projeto(tmp_path, monkeypatch):
    mod = _load()
    projeto = tmp_path / "claude-mem" / "data"
    projeto.mkdir(parents=True)
    monkeypatch.setattr(mod, "PROJECT_CMEM_DATA_DIR", projeto)

    updates = mod.runtime_updates()

    assert updates["CLAUDE_MEM_DATA_DIR"] == str(projeto)
    assert updates["FASTEMBED_CACHE_PATH"] == str(projeto / "models")
    assert updates["CLAUDE_MEM_CHROMA_ENABLED"] == "false"
    assert updates["CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH"] == str(
        projeto / "transcript-watch.json"
    )


def test_runtime_updates_fazem_fallback_para_o_global_sem_data_dir_do_projeto(
    tmp_path, monkeypatch
):
    mod = _load()
    monkeypatch.setattr(mod, "PROJECT_CMEM_DATA_DIR", tmp_path / "ausente")

    updates = mod.runtime_updates()

    data_dir = Path.home() / ".claude-mem"
    assert updates["CLAUDE_MEM_DATA_DIR"] == str(data_dir)
    assert updates["FASTEMBED_CACHE_PATH"] == str(data_dir / "models")


def test_env_claude_mem_data_dir_vence_a_resolucao(tmp_path, monkeypatch):
    mod = _load()
    projeto = tmp_path / "proj"
    projeto.mkdir()
    outro = tmp_path / "outro"
    monkeypatch.setattr(mod, "PROJECT_CMEM_DATA_DIR", projeto)
    monkeypatch.setenv("CLAUDE_MEM_DATA_DIR", str(outro))

    assert mod.resolve_data_dir() == outro


def test_recent_auth_error_recognizes_current_403(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "WORKER_LOG_DIR", tmp_path)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    (tmp_path / f"claude-mem-{datetime.date.today().isoformat()}.log").write_text(
        f"[{timestamp}] [ERROR] OpenRouter auth error (status 403)\n",
        encoding="utf-8",
    )

    assert mod._recent_auth_error() is True
