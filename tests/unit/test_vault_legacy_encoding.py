"""BUG-MEM-ENCODING — read legacy non-UTF8 vault notes without losing bytes.

`save_learning` reads `Patterns.md` before appending, and the live vault note
carries a lone `0xB7` (the `·` separator written by a cp1252 console) inside
text that is otherwise valid UTF-8. Opening it as strict UTF-8 raised
`UnicodeDecodeError`, which is a `ValueError` — neither of the handlers in
`save_learning` (`FileNotFoundError`, `OSError`) caught it, so the whole tool
failed.

Decoding such a file as cp1252 instead is not a fix: the same file already
contains correctly encoded `C2 B7` sequences, and cp1252 would turn each of
them into `Â·` on the next write. These tests pin the behaviour that matters —
the file is read, the append works, and every original byte survives the
round-trip untouched.
"""
from __future__ import annotations

import pytest

from core.memory.writers import atomic_write, read_vault_text, save_learning


# The exact shape found in the live vault: valid UTF-8 `·` (C2 B7) in one line
# and a bare cp1252 `·` (B7) in another.
MIXED = (
    b"---\n## MCP Pattern (2026-07-09)\n\n"
    b"> confidence: hypothesis \xc2\xb7 next_review: 2026-10-07\n\n"
    b"> confidence: hypothesis \xb7 next_review: 2026-10-07\n"
)


def test_reads_plain_utf8(tmp_path):
    path = tmp_path / "Patterns.md"
    path.write_bytes("# título\n\nconteúdo · ok\n".encode("utf-8"))

    assert read_vault_text(str(path)) == "# título\n\nconteúdo · ok\n"


def test_reads_utf8_with_bom(tmp_path):
    path = tmp_path / "Patterns.md"
    path.write_bytes(b"\xef\xbb\xbf" + "# título\n".encode("utf-8"))

    text = read_vault_text(str(path))

    assert text == "# título\n"
    assert not text.startswith("﻿"), "BOM must not leak into the content"


def test_reads_legacy_cp1252_byte_and_warns(tmp_path):
    path = tmp_path / "Patterns.md"
    path.write_bytes(MIXED)
    events = []

    text = read_vault_text(str(path), lambda level, event, **kw: events.append((level, event, kw)))

    assert "MCP Pattern" in text
    assert len(events) == 1
    level, event, fields = events[0]
    assert (level, event) == ("warning", "vault_legacy_encoding")
    assert fields["byte"] == "0xB7"
    assert fields["file"] == "Patterns.md"
    # The warning must not carry note content.
    assert "MCP Pattern" not in str(fields)


def test_legacy_bytes_survive_the_round_trip(tmp_path):
    """The historical file must come back byte for byte, not be repaired."""
    path = tmp_path / "Patterns.md"
    path.write_bytes(MIXED)

    assert atomic_write(str(path), read_vault_text(str(path)))

    assert path.read_bytes() == MIXED


def test_valid_utf8_is_not_rewritten_as_mojibake(tmp_path):
    """A cp1252 fallback would turn the correct `C2 B7` into `Â·`; this pins it."""
    path = tmp_path / "Patterns.md"
    path.write_bytes(MIXED)

    atomic_write(str(path), read_vault_text(str(path)))

    assert b"\xc3\x82\xc2\xb7" not in path.read_bytes()
    assert path.read_bytes().count(b"\xc2\xb7") == 1
    assert path.read_bytes().count(b"\xb7") == 2  # the lone B7 plus the one in C2 B7


def test_non_ascii_unicode_is_preserved(tmp_path):
    path = tmp_path / "Patterns.md"
    original = "héllo · 日本語 · emoji 🧠 · ok\n"
    path.write_text(original, encoding="utf-8")

    assert atomic_write(str(path), read_vault_text(str(path)))

    assert path.read_text(encoding="utf-8") == original


def test_nothing_is_truncated(tmp_path):
    path = tmp_path / "Patterns.md"
    body = b"x" * 5000 + b"\xb7" + b"y" * 5000
    path.write_bytes(body)

    assert len(path.read_bytes()) == len(body)
    atomic_write(str(path), read_vault_text(str(path)))
    assert path.read_bytes() == body


def test_missing_file_still_raises_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_vault_text(str(tmp_path / "absent.md"))


def test_save_learning_appends_to_a_legacy_file(tmp_path):
    """The end-to-end failure: this raised UnicodeDecodeError before the fix."""
    path = tmp_path / "Patterns.md"
    path.write_bytes(MIXED)

    result = save_learning("Novo aprendizado", "corpo da nota", str(path))

    assert result == str(path)
    written = path.read_bytes()
    assert written.startswith(MIXED), "the legacy content must be preserved verbatim"
    assert "Novo aprendizado".encode("utf-8") in written


def test_save_learning_does_not_rewrite_when_it_only_reads(tmp_path):
    """A duplicate title returns early; the file must be left exactly as found."""
    path = tmp_path / "Patterns.md"
    path.write_bytes(MIXED + "\n\n## Já existe (2026-07-09)\n\ncorpo\n".encode("utf-8"))
    before = path.read_bytes()

    assert save_learning("Já existe", "outro corpo", str(path)) is None
    assert path.read_bytes() == before
