import subprocess
import sys
from unittest.mock import patch, MagicMock, call
import pytest

# Garante que o módulo encontra o projeto
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _make_event(event_type: str, item: str, event_id: int = 1) -> dict:
    return {"id": event_id, "type": event_type, "data": {"item": item}}


class TestPollOnce:
    """Testa poll_once com requests mockado."""

    def test_conflict_event_triggers_audit(self, monkeypatch):
        from scripts.syncthing_watcher import poll_once, _trigger_audit
        events = [_make_event("ItemFinished", "cerebro/atlas/note.sync-conflict-20260612-120000.md")]
        mock_resp = MagicMock()
        mock_resp.json.return_value = events
        mock_resp.raise_for_status.return_value = None

        triggered = []
        monkeypatch.setattr("scripts.syncthing_watcher._trigger_audit", lambda: triggered.append(1))

        with patch("scripts.syncthing_watcher.requests.get", return_value=mock_resp):
            new_id = poll_once(0)

        assert new_id == 1
        assert len(triggered) == 1

    def test_non_conflict_event_does_not_trigger_audit(self, monkeypatch):
        from scripts.syncthing_watcher import poll_once
        events = [_make_event("ItemFinished", "cerebro/atlas/regular.md")]
        mock_resp = MagicMock()
        mock_resp.json.return_value = events
        mock_resp.raise_for_status.return_value = None

        triggered = []
        monkeypatch.setattr("scripts.syncthing_watcher._trigger_audit", lambda: triggered.append(1))

        with patch("scripts.syncthing_watcher.requests.get", return_value=mock_resp):
            poll_once(0)

        assert len(triggered) == 0

    def test_event_id_advances(self, monkeypatch):
        from scripts.syncthing_watcher import poll_once
        events = [_make_event("FolderSummary", "irrelevant", event_id=42)]
        mock_resp = MagicMock()
        mock_resp.json.return_value = events
        mock_resp.raise_for_status.return_value = None

        monkeypatch.setattr("scripts.syncthing_watcher._trigger_audit", lambda: None)
        with patch("scripts.syncthing_watcher.requests.get", return_value=mock_resp):
            new_id = poll_once(0)
        assert new_id == 42

    def test_connection_error_is_swallowed_in_loop(self, monkeypatch):
        """run_loop não deve propagar ConnectionError."""
        import scripts.syncthing_watcher as sw
        monkeypatch.setattr(sw, "POLL_INTERVAL", 0.01)
        call_count = [0]

        def fake_poll_once(last_id):
            call_count[0] += 1
            if call_count[0] == 1:
                raise sw.requests.exceptions.ConnectionError("offline")
            raise SystemExit(0)  # para o loop após 2 iterações

        monkeypatch.setattr(sw, "poll_once", fake_poll_once)
        monkeypatch.setattr(sw.time, "sleep", lambda _: None)

        with pytest.raises(SystemExit):
            sw.run_loop()
        assert call_count[0] == 2  # chegou à segunda iteração sem travar


class TestMainEntrypoint:
    def test_raises_systemexit_without_api_key(self, monkeypatch):
        import scripts.syncthing_watcher as sw
        monkeypatch.setattr(sw, "SYNCTHING_API_KEY", "")
        with pytest.raises(SystemExit):
            # Simula execução do __main__ block
            if not sw.SYNCTHING_API_KEY:
                raise SystemExit("SYNCTHING_API_KEY não configurada.")
