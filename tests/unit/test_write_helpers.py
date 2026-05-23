import os
import pytest
from sinapse_memory import _save_decision, _save_learning, _sanitize_slug, _atomic_write, _validate_frontmatter_yaml


class TestSanitizeSlug:
    """U4.1-U4.3: Slug sanitization"""

    def test_basic_slug(self):
        assert _sanitize_slug("Hello World") == "Hello-World"

    def test_unicode_removal(self):
        slug = _sanitize_slug("João é uma ação")
        assert "Joao" in slug
        assert "e" in slug
        assert "uma" in slug

    def test_special_characters(self):
        slug = _sanitize_slug("Test / with & special !@# chars")
        assert "/" not in slug
        assert "&" not in slug
        assert "#" not in slug
        assert slug.startswith("Test")

    def test_max_length_truncation(self):
        slug = _sanitize_slug("a" * 100, max_len=20)
        assert len(slug) <= 20

    def test_empty_fallback(self):
        slug = _sanitize_slug("!!!@#$%")
        assert slug == "decision"

    def test_emoji_stripped(self):
        slug = _sanitize_slug("Decisão importante 🚀🔥")
        for ch in slug:
            assert ord(ch) < 128  # all ASCII


class TestAtomicWrite:
    """U4.4-U4.5: Atomic file writes"""

    def test_atomic_write_success(self, tmp_path):
        filepath = os.path.join(str(tmp_path), "test.md")
        result = _atomic_write(filepath, "# Header\ncontent")
        assert result is True
        assert os.path.isfile(filepath)
        with open(filepath) as f:
            assert f.read() == "# Header\ncontent"

    def test_atomic_write_creates_dirs(self, tmp_path):
        filepath = os.path.join(str(tmp_path), "deep", "nested", "file.md")
        result = _atomic_write(filepath, "data")
        assert result is True
        assert os.path.isfile(filepath)


class TestSaveDecision:
    """U4.6-U4.7: Decision saving"""

    def test_save_decision_creates_file(self, temp_vault, monkeypatch):
        monkeypatch.setattr("sinapse_memory.DECISIONS_DIR", f"{temp_vault}/work/active")
        path = _save_decision("Migrar servidor", "Decisão: migrar para Hetzner")
        assert path is not None
        assert os.path.isfile(path)
        with open(path) as f:
            content = f.read()
        assert "Migrar servidor" in content
        assert "tags: [decision]" in content

    def test_save_decision_frontmatter_valid(self, temp_vault, monkeypatch):
        monkeypatch.setattr("sinapse_memory.DECISIONS_DIR", f"{temp_vault}/work/active")
        path = _save_decision("Test", "Content")
        assert path is not None
        with open(path) as f:
            content = f.read()
        assert content.startswith("---")
        assert "tags:" in content
        assert "status:" in content
        assert "created:" in content


class TestSaveLearning:
    """U4.8: Learning saving with dedup"""

    def test_save_learning_append(self, temp_vault, monkeypatch):
        patterns_file = f"{temp_vault}/brain/Patterns.md"
        monkeypatch.setattr("sinapse_memory.PATTERNS_FILE", patterns_file)
        path = _save_learning("Padrão encontrado", "Descobriu-se que...")
        assert path is not None
        with open(patterns_file) as f:
            content = f.read()
        assert "Padrão encontrado" in content

    def test_learning_dedup(self, temp_vault, monkeypatch):
        patterns_file = f"{temp_vault}/brain/Patterns.md"
        monkeypatch.setattr("sinapse_memory.PATTERNS_FILE", patterns_file)
        # Write first time
        _save_learning("Unique Pattern", "Some insight")
        # Second save should be skipped
        with open(patterns_file) as f:
            before = f.read()
        result = _save_learning("Unique Pattern", "Some insight again")
        assert result is None  # dedup skipped
        with open(patterns_file) as f:
            assert f.read() == before  # unchanged


class TestFrontmatterValidation:
    """U4.9: Frontmatter validation"""

    def test_valid_frontmatter(self):
        content = """---
tags: [decision]
status: active
created: 2026-01-01
---

# Title

Body
"""
        assert _validate_frontmatter_yaml(content) is True

    def test_missing_tags(self):
        content = """---
status: active
created: 2026-01-01
---

Body
"""
        assert _validate_frontmatter_yaml(content) is False

    def test_no_frontmatter(self):
        content = "# Just a heading\n\nBody"
        assert _validate_frontmatter_yaml(content) is False

    def test_incomplete_frontmatter(self):
        content = "---\ntags: [decision]"
        assert _validate_frontmatter_yaml(content) is False
