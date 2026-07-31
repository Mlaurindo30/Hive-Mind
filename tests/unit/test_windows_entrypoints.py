from __future__ import annotations

import sys

from hive_mind.windows import entrypoints


def test_gui_entrypoint_restores_null_standard_streams(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    entrypoints._ensure_standard_streams()

    assert sys.stdout is not None
    assert sys.stderr is not None
    assert sys.stdout.write("probe") == len("probe")
