"""
Unit tests for scripts/planner.py — no real LLM calls.
All calls to call_llm_with_fallback are patched via the module-level binding
in scripts.planner so dream_cycle is never imported.
"""

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on sys.path so `scripts` and `core` are importable.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_goal_plan(steps_data: list[dict]):
    """Builds a real GoalPlan from scripts.planner using the Pydantic models."""
    from scripts.planner import GoalPlan, GoalStep
    return GoalPlan(steps=[GoalStep(**s) for s in steps_data])


def _in_memory_conn():
    """Returns a fresh in-memory SQLite connection with Row factory."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture(autouse=True)
def reset_planner_llm_binding():
    """Reset the module-level call_llm_with_fallback to None before each test
    so the patch always wins (avoids bleed-through from a previous test that
    triggered the lazy import)."""
    import scripts.planner as planner_mod
    original = planner_mod.call_llm_with_fallback
    planner_mod.call_llm_with_fallback = None
    yield
    planner_mod.call_llm_with_fallback = original


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDecomposeGoal:
    def test_decompose_goal_returns_list(self):
        """Valid LLM response: decompose_goal returns a list with ≥1 step."""
        mock_plan = _make_goal_plan([
            {"id": "step-1", "action": "Pesquisar requisitos", "why": "Entender o escopo", "depends_on": []},
            {"id": "step-2", "action": "Implementar solução", "why": "Resolver o problema", "depends_on": ["step-1"]},
        ])

        with patch("scripts.planner.call_llm_with_fallback", return_value=mock_plan):
            import scripts.planner as planner
            # Ensure binding points to our mock (autouse fixture zeroed it out)
            planner.call_llm_with_fallback = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(return_value=mock_plan)
            steps = planner.decompose_goal("Construir um sistema de login")

        assert isinstance(steps, list)
        assert len(steps) >= 1
        assert steps[0]["id"] == "step-1"
        assert "action" in steps[0]
        assert "why" in steps[0]
        assert "depends_on" in steps[0]

    def test_decompose_goal_fallback_on_exception(self):
        """When LLM call raises, decompose_goal returns single fallback step."""
        from unittest.mock import MagicMock
        goal = "Objetivo que falhou"

        import scripts.planner as planner
        planner.call_llm_with_fallback = MagicMock(side_effect=RuntimeError("LLM indisponível"))
        steps = planner.decompose_goal(goal)

        assert isinstance(steps, list)
        assert len(steps) == 1
        assert steps[0]["id"] == "step-1"
        assert steps[0]["action"] == goal
        assert steps[0]["why"] == "objetivo original não decomposto"
        assert steps[0]["depends_on"] == []

    def test_decompose_goal_fallback_on_parse_error(self):
        """When LLM raises ValueError (parse/validation error), fallback is returned."""
        from unittest.mock import MagicMock
        goal = "Objetivo com dados ruins"

        import scripts.planner as planner
        planner.call_llm_with_fallback = MagicMock(side_effect=ValueError("JSON malformado"))
        steps = planner.decompose_goal(goal)

        assert len(steps) == 1
        assert steps[0]["action"] == goal
        assert steps[0]["why"] == "objetivo original não decomposto"


class TestSaveGoal:
    def test_save_goal_creates_row(self):
        """save_goal inserts a row with the correct description."""
        from scripts.planner import save_goal

        steps = [{"id": "step-1", "action": "Fazer X", "why": "Porque sim", "depends_on": []}]
        goal_desc = "Meu objetivo de teste"

        conn = _in_memory_conn()
        goal_id = save_goal(goal_desc, steps, db_conn=conn)

        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        assert row is not None
        assert row["description"] == goal_desc
        assert row["status"] == "active"

        saved_steps = json.loads(row["steps_json"])
        assert saved_steps == steps

        conn.close()

    def test_save_goal_idempotent_table(self):
        """Calling save_goal twice on same conn must not raise (DDL is idempotent)
        and each call inserts exactly one distinct row."""
        from scripts.planner import save_goal

        steps = [{"id": "step-1", "action": "Passo único", "why": "razão", "depends_on": []}]
        conn = _in_memory_conn()

        goal_id_1 = save_goal("Objetivo 1", steps, db_conn=conn)
        goal_id_2 = save_goal("Objetivo 2", steps, db_conn=conn)

        rows = conn.execute("SELECT id FROM goals").fetchall()
        assert len(rows) == 2
        ids = {r["id"] for r in rows}
        assert goal_id_1 in ids
        assert goal_id_2 in ids

        conn.close()
