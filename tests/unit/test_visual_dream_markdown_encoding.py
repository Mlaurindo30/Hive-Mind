from pathlib import Path


def test_visual_dream_writes_markdown_as_utf8():
    source = Path("scripts/dream/dream_cycle.py").read_text(encoding="utf-8")

    assert 'open(note_file, "w", encoding="utf-8")' in source
