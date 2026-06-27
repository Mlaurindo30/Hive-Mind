import os
import sys
import sqlite3 as _sqlite3
from pathlib import Path
from unittest.mock import patch

# Setup paths
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = str(_HERE.parent)
sys.path.append(SINAPSE_HOME)

import pytest

from core.database import get_connection
from core.schemas.synthesis_models import SynthesisOutput
from core.schemas.diff_models import SemanticDiffResult, DiffCategory


# ---------------------------------------------------------------------------
# Helpers shared by all offline tests
# ---------------------------------------------------------------------------

# Minimal SQLite schema — avoids the sqlite-vec (vec0) extension that the full
# umc_schema.sql requires and that cannot be loaded in a plain :memory: DB.
_MINIMAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS neurons (
    id TEXT PRIMARY KEY,
    label TEXT,
    type TEXT,
    source_file TEXT,
    content TEXT,
    hash TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ambiguities (
    id TEXT PRIMARY KEY,
    neuron_id TEXT,
    source_a_hash TEXT,
    source_b_hash TEXT,
    content_a TEXT,
    content_b TEXT,
    status TEXT DEFAULT 'pending',
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _make_in_memory_db() -> _sqlite3.Connection:
    """Return an in-memory SQLite connection with the minimal schema applied."""
    conn = _sqlite3.connect(":memory:")
    conn.row_factory = _sqlite3.Row
    conn.executescript(_MINIMAL_SCHEMA)
    return conn


def _make_synthesis_mock(
    final_content="Use PostgreSQL for the primary database. SQLite remains available for local testing.",
    logic_applied="Fusão: PostgreSQL is chosen for production; SQLite retained for local/test use.",
    provenance_summary="Version A: PostgreSQL recommendation. Version B: SQLite recommendation.",
    parent_hashes=None,
    conflict_resolved=True,
) -> SynthesisOutput:
    """Build a SynthesisOutput instance that mimics what the real LLM would return."""
    return SynthesisOutput(
        final_content=final_content,
        logic_applied=logic_applied,
        provenance_summary=provenance_summary,
        parent_hashes=parent_hashes or ["hash1", "hash2"],
        conflict_resolved=conflict_resolved,
    )


def _make_diff_mock() -> SemanticDiffResult:
    """Build a SemanticDiffResult that flags two observations as contradictory."""
    return SemanticDiffResult(
        contradiction_score=0.9,
        category=DiffCategory.CONTRADICTORY,
        reasoning=(
            "Version A recommends PostgreSQL; Version B recommends SQLite. "
            "These are mutually exclusive choices."
        ),
        suggested_resolution=(
            "Use PostgreSQL for production and SQLite for local/test environments."
        ),
    )


# ---------------------------------------------------------------------------
# Offline mock-based tests — no API key required
# ---------------------------------------------------------------------------

class TestSynthesisOffline:
    """Offline tests for Phase 9 (Síntese Dialética) — no real API key needed."""

    def test_synthesis_output_schema_valid(self):
        """SynthesisOutput Pydantic model accepts a well-formed payload."""
        output = _make_synthesis_mock()
        assert output.conflict_resolved is True
        assert output.final_content != ""
        assert isinstance(output.parent_hashes, list)
        assert len(output.parent_hashes) == 2

    def test_synthesis_output_schema_conflict_not_resolved(self):
        """SynthesisOutput correctly represents an unresolved conflict."""
        output = _make_synthesis_mock(conflict_resolved=False)
        assert output.conflict_resolved is False

    def test_diff_result_contradictory(self):
        """SemanticDiffResult correctly classifies contradictory observations."""
        diff = _make_diff_mock()
        assert diff.category == DiffCategory.CONTRADICTORY
        assert diff.contradiction_score > 0.5

    def test_run_synthesis_cycle_mocked(self, tmp_path):
        """
        Full conflict-resolution flow with two contradictory observations.

        Mocked surfaces:
          - scripts.dream_cycle.call_llm_with_fallback  -> SynthesisOutput
          - scripts.semantic_diff.run_semantic_diff      -> SemanticDiffResult
          - scripts.dream_cycle.get_connection           -> in-memory SQLite

        Assertions:
          - ambiguity row transitions from 'pending' to 'synthesized'
          - neuron content is updated to the synthesized text
          - the Atlas Markdown file is written with hive-synthesizer in frontmatter
        """
        neuron_id = "mock-neuron-db-choice"
        amb_id = "mock-amb-db-choice"

        db_conn = _make_in_memory_db()

        # Atlas Markdown file in a tmp directory so nothing touches the real repo
        atlas_file = tmp_path / "atlas.md"
        atlas_file.write_text("# DB Choice\n\nOriginal Content")

        db_conn.execute(
            "INSERT INTO neurons (id, label, type, source_file, content, hash) VALUES (?,?,?,?,?,?)",
            (neuron_id, "DB Choice", "fact", str(atlas_file), "Use PostgreSQL", "hash1"),
        )
        db_conn.execute(
            "INSERT INTO ambiguities (id, neuron_id, source_a_hash, source_b_hash, content_a, content_b, status)"
            " VALUES (?,?,?,?,?,?,?)",
            (amb_id, neuron_id, "hash1", "hash2", "Use PostgreSQL", "Use SQLite", "pending"),
        )
        db_conn.commit()

        synthesis_result = _make_synthesis_mock()
        diff_result = _make_diff_mock()

        # run_synthesis_cycle calls conn.close() on the object we passed in.
        # We patch get_connection to return a MagicMock whose .close() is a
        # no-op while all real sqlite3 methods are delegated to db_conn.
        from unittest.mock import MagicMock
        mock_conn = MagicMock(wraps=db_conn)
        mock_conn.close = MagicMock()  # suppress the actual close

        with (
            patch("scripts.dream.dream_cycle.get_connection", return_value=mock_conn),
            patch("scripts.dream.semantic_diff.run_semantic_diff", return_value=diff_result),
            patch("scripts.dream.dream_cycle.call_llm_with_fallback", return_value=synthesis_result),
        ):
            from scripts.dream.dream_cycle import run_synthesis_cycle
            run_synthesis_cycle()

        # Ambiguity must be marked 'synthesized'
        amb_row = db_conn.execute(
            "SELECT status FROM ambiguities WHERE id = ?", (amb_id,)
        ).fetchone()
        assert amb_row is not None, "Ambiguity row must still exist after synthesis"
        assert amb_row["status"] == "synthesized", (
            f"Expected status='synthesized', got '{amb_row['status']}'"
        )

        # Neuron content must contain the winner
        neuron_row = db_conn.execute(
            "SELECT content FROM neurons WHERE id = ?", (neuron_id,)
        ).fetchone()
        assert neuron_row is not None
        assert "PostgreSQL" in neuron_row["content"], (
            "Neuron content must contain the synthesized text"
        )

        # Atlas Markdown must be rewritten
        md_text = atlas_file.read_text()
        assert "PostgreSQL" in md_text, "Atlas Markdown must be updated with synthesized content"
        assert "hive-synthesizer" in md_text, (
            "Atlas Markdown must have 'hive-synthesizer' in the frontmatter"
        )

    def test_synthesis_does_not_update_on_unresolved_conflict(self, tmp_path):
        """When conflict_resolved is False the neuron content must NOT change."""
        neuron_id = "mock-neuron-unresolved"
        amb_id = "mock-amb-unresolved"

        db_conn = _make_in_memory_db()

        original_content = "Use PostgreSQL"
        # source_file=None: run_synthesis_cycle skips file I/O when the path is absent
        db_conn.execute(
            "INSERT INTO neurons (id, label, type, source_file, content, hash) VALUES (?,?,?,?,?,?)",
            (neuron_id, "DB Choice", "fact", None, original_content, "hash1"),
        )
        db_conn.execute(
            "INSERT INTO ambiguities (id, neuron_id, source_a_hash, source_b_hash, content_a, content_b, status)"
            " VALUES (?,?,?,?,?,?,?)",
            (amb_id, neuron_id, "hash1", "hash2", "Use PostgreSQL", "Use SQLite", "pending"),
        )
        db_conn.commit()

        unresolved = _make_synthesis_mock(conflict_resolved=False)
        diff_result = _make_diff_mock()

        from unittest.mock import MagicMock
        mock_conn = MagicMock(wraps=db_conn)
        mock_conn.close = MagicMock()

        with (
            patch("scripts.dream.dream_cycle.get_connection", return_value=mock_conn),
            patch("scripts.dream.semantic_diff.run_semantic_diff", return_value=diff_result),
            patch("scripts.dream.dream_cycle.call_llm_with_fallback", return_value=unresolved),
        ):
            from scripts.dream.dream_cycle import run_synthesis_cycle
            run_synthesis_cycle()

        neuron_row = db_conn.execute(
            "SELECT content FROM neurons WHERE id = ?", (neuron_id,)
        ).fetchone()
        assert neuron_row["content"] == original_content, (
            "Neuron content must NOT change when conflict is not resolved"
        )

        amb_row = db_conn.execute(
            "SELECT status FROM ambiguities WHERE id = ?", (amb_id,)
        ).fetchone()
        assert amb_row["status"] == "pending", (
            "Ambiguity must remain 'pending' when conflict is not resolved"
        )


# ---------------------------------------------------------------------------
# Original integration test — kept as-is, skipped in CI
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skip(reason="integration: requer API key de LLM real (chama o Ciclo de Síntese)")
def test_synthesis_integration():
    conn = get_connection()

    # 1. Setup Test Data
    neuron_id = "test-neuron-123"
    topic = "test_topic"
    atlas_dir = Path(SINAPSE_HOME) / "cerebro" / "atlas" / topic
    atlas_dir.mkdir(parents=True, exist_ok=True)
    atlas_file = atlas_dir / "test-fact.md"

    # Create Markdown file
    with open(atlas_file, "w") as f:
        f.write("# Test Fact\n\nOriginal Content")

    # Insert Neuron
    conn.execute("DELETE FROM neurons WHERE id = ?", (neuron_id,))
    conn.execute(
        """
        INSERT INTO neurons (id, label, type, source_file, content, hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (neuron_id, "Test Fact", "fact", f"{topic}/test-fact.md", "Original Content", "hash1"),
    )

    # Insert Ambiguity
    amb_id = "amb-123"
    conn.execute("DELETE FROM ambiguities WHERE id = ?", (amb_id,))
    conn.execute(
        """
        INSERT INTO ambiguities (id, neuron_id, source_a_hash, source_b_hash, content_a, content_b, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (amb_id, neuron_id, "hash1", "hash2", "Original Content", "Updated Content with more info", "pending"),
    )

    conn.commit()
    conn.close()

    print(f"Test data setup complete. Running synthesis cycle...")

    # 2. Run Synthesis Cycle
    from scripts.dream.dream_cycle import run_synthesis_cycle
    run_synthesis_cycle()

    # 3. Verify Results
    conn = get_connection()
    neuron = conn.execute("SELECT * FROM neurons WHERE id = ?", (neuron_id,)).fetchone()
    amb = conn.execute("SELECT * FROM ambiguities WHERE id = ?", (amb_id,)).fetchone()

    print("\n=== Verification ===")
    print(f"Neuron Content: {neuron['content']}")
    print(f"Ambiguity Status: {amb['status']}")

    # Check Markdown
    with open(atlas_file, "r") as f:
        md_content = f.read()
    print(f"Markdown Content preview: {md_content[:100]}...")

    if amb['status'] == 'synthesized' and "Updated" in neuron['content']:
        print("\nSUCCESS: Synthesis stage worked end-to-end!")
    else:
        print("\nFAILURE: Synthesis stage did not work as expected.")
        sys.exit(1)

    conn.close()


if __name__ == "__main__":
    test_synthesis_integration()
