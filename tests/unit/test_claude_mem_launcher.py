from pathlib import Path

from hive_mind.services.claude_mem_launcher import (
    _new_auth_failure,
    command,
    is_provider_auth_failure,
    stop_legacy_daemon,
    worker_candidates,
)


def test_launcher_uses_installed_worker_without_mutating_plugin(tmp_path, monkeypatch):
    worker = (
        tmp_path / ".claude" / "plugins" / "cache" / "thedotmack" / "claude-mem"
        / "13.12.4" / "scripts" / "worker-wrapper.cjs"
    )
    worker.parent.mkdir(parents=True)
    worker.write_text("original worker", encoding="utf-8")
    monkeypatch.setattr("hive_mind.services.claude_mem_launcher.resolve_bun", lambda: "bun.exe")
    # Sem clone vendored: o fallback do cache global é o único candidato.
    monkeypatch.setattr(
        "hive_mind.services.claude_mem_launcher._vendored_worker", lambda root=None: None
    )

    assert worker_candidates(tmp_path) == [worker]
    assert command(tmp_path) == ["bun.exe", str(worker)]
    assert worker.read_text(encoding="utf-8") == "original worker"


def test_launcher_prefers_vendored_worker_over_cache(tmp_path, monkeypatch):
    # P1 (2026-08-12): o clone vendored em integrations/ tem precedência sobre o
    # cache de plugins global — elimina o não-determinismo de versão.
    vendored = tmp_path / "integrations" / "claude-mem" / "plugin" / "scripts" / "worker-wrapper.cjs"
    vendored.parent.mkdir(parents=True)
    vendored.write_text("vendored worker", encoding="utf-8")

    cached = (
        tmp_path / ".claude" / "plugins" / "cache" / "thedotmack" / "claude-mem"
        / "13.15.0" / "scripts" / "worker-wrapper.cjs"
    )
    cached.parent.mkdir(parents=True)
    cached.write_text("cached worker", encoding="utf-8")

    monkeypatch.setattr(
        "hive_mind.services.claude_mem_launcher._vendored_worker", lambda root=None: vendored
    )

    candidates = worker_candidates(tmp_path)
    assert candidates[0] == vendored
    assert cached in candidates


def test_launcher_replaces_only_bun_listener_on_reserved_port(monkeypatch):
    module = "hive_mind.services.claude_mem_launcher"
    terminated: list[int] = []
    monkeypatch.setattr(f"{module}._listener_pid", lambda port: 1234)
    monkeypatch.setattr(f"{module}._process_image", lambda pid: Path(r"C:\\Users\\miche\\.bun\\bin\\bun.exe"))
    monkeypatch.setattr(f"{module}._terminate_process_tree", terminated.append)

    assert stop_legacy_daemon() is True
    assert terminated == [1234]


def test_launcher_never_stops_non_bun_listener(monkeypatch):
    module = "hive_mind.services.claude_mem_launcher"
    terminated: list[int] = []
    monkeypatch.setattr(f"{module}._listener_pid", lambda port: 5678)
    monkeypatch.setattr(f"{module}._process_image", lambda pid: Path(r"C:\\Tools\\other.exe"))
    monkeypatch.setattr(f"{module}._terminate_process_tree", terminated.append)

    assert stop_legacy_daemon() is False
    assert terminated == []


def test_launcher_recognizes_provider_403_as_a_fallback_trigger():
    assert is_provider_auth_failure(
        "[ERROR] [SESSION] Generator failed {provider=openrouter, "
        "error=OpenRouter auth error (status 403)}"
    ) is True


def test_launcher_reads_only_new_403_worker_log_lines(tmp_path):
    log = tmp_path / "claude-mem.log"
    log.write_text("old line\n", encoding="utf-8")
    offset = log.stat().st_size
    log.write_text(
        "old line\n"
        "[ERROR] OpenRouter auth error (status 403)\n",
        encoding="utf-8",
    )

    detected, next_offset = _new_auth_failure(log, offset)

    assert detected is True
    assert next_offset == log.stat().st_size
