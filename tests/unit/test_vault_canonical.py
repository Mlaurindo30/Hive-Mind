"""Testes da camada canônica de escrita no vault (FASE 0, 2026-08-12)."""
import tempfile
import unittest
from pathlib import Path

from core.vault import (
    canonical_slug,
    neuron_sinapses,
    project_display_name,
    vault_project_dir,
    write_vault_note,
)


class VaultProjectDirTests(unittest.TestCase):
    def test_git_prefix_removed_hash_kept(self):
        self.assertEqual(
            vault_project_dir("git/moneyprinterturbo-83ef01772a6d"),
            "moneyprinterturbo-83ef01772a6d",
        )

    def test_root_prefix_removed_hash_kept(self):
        self.assertEqual(
            vault_project_dir("root/agent-corporativo-596377768abf"),
            "agent-corporativo-596377768abf",
        )

    def test_local_prefix_removed(self):
        self.assertEqual(vault_project_dir("local/75a99723f2d2"), "75a99723f2d2")

    def test_unclassified_prefix_removed(self):
        self.assertEqual(vault_project_dir("unclassified/legacy"), "legacy")

    def test_plain_project_unchanged(self):
        self.assertEqual(vault_project_dir("hive-mind"), "hive-mind")

    def test_empty_falls_back_to_unclassified(self):
        self.assertEqual(vault_project_dir(""), "unclassified")
        self.assertEqual(vault_project_dir("/"), "unclassified")

    def test_no_triple_nesting_possible(self):
        # Nunca retorna um path com barra — garante 2 níveis no vault.
        for pid in ("git/a-hash", "root/b-hash", "unclassified/c", "local/d", "plain"):
            self.assertNotIn("/", vault_project_dir(pid), pid)


class CanonicalSlugTests(unittest.TestCase):
    def test_hyphen_underscore_space_are_same_separator(self):
        self.assertEqual(canonical_slug("code-inspection"), "code-inspection")
        self.assertEqual(canonical_slug("code_inspection"), "code-inspection")
        self.assertEqual(canonical_slug("code inspection"), "code-inspection")

    def test_idempotent(self):
        for t in ("Code Inspection", "code_inspection", "code-inspection",
                  "how_it_works", "how-it-works", "How It Works"):
            self.assertEqual(canonical_slug(canonical_slug(t)), canonical_slug(t))

    def test_accents_removed(self):
        self.assertEqual(canonical_slug("rápida"), "r-pida")


class WriteVaultNoteTests(unittest.TestCase):
    def test_writes_frontmatter_and_sinapses(self):
        tmp = Path(tempfile.mkdtemp())
        path = tmp / "proj" / "topico" / "neuronio-x.md"
        write_vault_note(
            path,
            frontmatter={"type": "fact", "project_id": "git/x-hash", "topic": "t"},
            body="# Titulo\n\nConteúdo.",
            sinapses=neuron_sinapses("x-hash", "t"),
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn("type: fact", text)
        self.assertIn("## Sinapses", text)
        self.assertIn("projeto:: [[x-hash]]", text)
        self.assertIn("lobo:: [[cortex-temporal]]", text)

    def test_aliases_block(self):
        tmp = Path(tempfile.mkdtemp())
        path = tmp / "n.md"
        write_vault_note(path, frontmatter={"type": "fact"}, body="", aliases=["a", "b"])
        text = path.read_text(encoding="utf-8")
        self.assertIn("aliases:", text)
        self.assertIn("- a", text)
        self.assertIn("- b", text)


class ProjectDisplayNameTests(unittest.TestCase):
    def test_display_name_from_git_id(self):
        self.assertEqual(project_display_name("git/moneyprinterturbo-83ef01772a6d"), "Moneyprinterturbo-83ef01772a6d")


if __name__ == "__main__":
    unittest.main()
