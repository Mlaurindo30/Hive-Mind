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


def test_capture_screen_com_monitor_explicitado(monkeypatch, tmp_path):
    monkeypatch.setattr(visual_capture, "is_wsl", lambda: False)
    monkeypatch.setattr(visual_capture.mss, "mss", lambda: _FakeMSS())
    # FIX (2026-08-13): o teste escrevia b"fake" no INBOX_VISUAL REAL do vault,
    # poluindo o cerebro com PNGs de 4 bytes a cada execução. Redireciona o
    # output_dir para tmp_path via monkeypatch do módulo core.paths (cp é
    # importado DENTRO de capture_screen).
    import core.paths as cp_module
    monkeypatch.setattr(cp_module, "INBOX_VISUAL", tmp_path)

    path = visual_capture.capture_screen("teste", monitor=2)
    assert Path(path).exists()
    assert Path(path).parent == tmp_path
