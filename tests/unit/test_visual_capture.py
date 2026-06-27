from pathlib import Path

import pytest

from scripts.capture import visual_capture


class _FakeMSS:
    monitors = [
        {"left": 0, "top": 0, "width": 2880, "height": 900},
        {"left": 0, "top": 0, "width": 1440, "height": 900, "output": "DP-1", "is_primary": True},
        {"left": 1440, "top": 0, "width": 1440, "height": 900, "output": "DP-2", "is_primary": False},
    ]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def shot(self, mon=1, output=None):
        Path(output).write_bytes(b"fake")
        return output


def test_capture_screen_multimonitor_exige_monitor(monkeypatch, tmp_path):
    monkeypatch.setattr(visual_capture, "is_wsl", lambda: False)
    monkeypatch.setattr(visual_capture.mss, "mss", lambda: _FakeMSS())

    with pytest.raises(Exception) as exc:
        visual_capture.capture_screen("teste")

    assert "multi-monitor" in str(exc.value)
    assert "Informe monitor" in str(exc.value)


def test_capture_screen_com_monitor_explicitado(monkeypatch):
    monkeypatch.setattr(visual_capture, "is_wsl", lambda: False)
    monkeypatch.setattr(visual_capture.mss, "mss", lambda: _FakeMSS())

    path = visual_capture.capture_screen("teste", monitor=2)
    assert Path(path).exists()
