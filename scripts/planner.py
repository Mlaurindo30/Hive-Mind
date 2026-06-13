#!/usr/bin/env python3
"""
Hive-Mind — Planner (Intent Memory / Phase HM-11)
Decompõe objetivos em passos atômicos e persiste no banco de dados.
"""

import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ValidationError

_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent))
sys.path.insert(0, SINAPSE_HOME)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class GoalStep(BaseModel):
    id: str
    action: str
    why: str
    depends_on: list[str] = []


class GoalPlan(BaseModel):
    steps: list[GoalStep]


# ---------------------------------------------------------------------------
# System prompt for goal decomposition
# ---------------------------------------------------------------------------

_PLANNER_SYSTEM_PROMPT = (
    "Você é um assistente especialista em planejamento. "
    "Dado um objetivo, decomponha-o em passos atômicos e independentes. "
    "Responda APENAS com JSON válido no formato:\n"
    '{"steps": [{"id": "step-1", "action": "<ação>", "why": "<motivo>", '
    '"depends_on": []}]}\n'
    "Use ids sequenciais (step-1, step-2, …). "
    "depends_on lista os ids dos passos que precisam completar antes deste."
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _get_llm_caller():
    """Lazy import of call_llm_with_fallback — kept as module-level binding
    so tests can patch ``scripts.planner.call_llm_with_fallback`` directly."""
    import importlib
    dc = importlib.import_module("scripts.dream_cycle")
    return dc.call_llm_with_fallback


# Module-level reference — tests patch this name.
call_llm_with_fallback = None  # populated on first call; patchable by tests


def decompose_goal(goal: str, context: Optional[str] = None) -> list[dict]:
    """Decompõe um objetivo em passos atômicos via LLM.

    Retorna uma lista de dicts com keys: id, action, why, depends_on.
    Em caso de falha retorna um único passo fallback com o objetivo original.
    """
    global call_llm_with_fallback
    if call_llm_with_fallback is None:
        call_llm_with_fallback = _get_llm_caller()

    fallback = [{"id": "step-1", "action": goal, "why": "objetivo original não decomposto", "depends_on": []}]

    prompt = f"OBJETIVO: {goal}"
    if context:
        prompt += f"\n\nCONTEXTO ADICIONAL:\n{context}"

    try:
        result: GoalPlan = call_llm_with_fallback(
            "dreamer",
            prompt,
            _PLANNER_SYSTEM_PROMPT,
            GoalPlan,
        )
        return [s.model_dump() for s in result.steps]
    except (ValidationError, Exception):
        return fallback


def save_goal(goal: str, steps: list[dict], db_conn=None) -> str:
    """Persiste o objetivo e seus passos na tabela `goals`.

    Cria a tabela se não existir (idempotente).
    Retorna o goal_id gerado.
    """
    from core.database import get_connection

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    goal_id = f"goal-{ts}"

    _own_conn = db_conn is None
    conn = get_connection() if _own_conn else db_conn

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id          TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                steps_json  TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'active',
                created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO goals (id, description, steps_json) VALUES (?, ?, ?)",
            (goal_id, goal, json.dumps(steps)),
        )
        conn.commit()
    finally:
        if _own_conn:
            conn.close()

    return goal_id
