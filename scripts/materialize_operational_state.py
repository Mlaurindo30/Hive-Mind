#!/usr/bin/env python3
"""Materialize truthful production-readiness intent and causal state."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.database import ensure_migrations, get_connection


GOAL_ID = "goal-hive-mind-production-readiness-20260613"
CAUSE_ID = "ops:project-local-runtime"
EFFECT_ID = "ops:production-readiness-validation"
EDGE_ID = "causal:project-local-runtime:production-readiness"
OBSERVATION_ID = "observation:production-readiness-intent"

STEPS = [
    {
        "id": "step-1",
        "action": "Isolar dependencias e dados no checkout do Hive-Mind",
        "why": "Eliminar resolucao global acidental no runtime",
        "depends_on": [],
    },
    {
        "id": "step-2",
        "action": "Validar servicos, recuperacao e integracoes reais",
        "why": "Produzir evidencia operacional antes da classificacao de prontidao",
        "depends_on": ["step-1"],
    },
]


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def materialize(conn) -> dict:
    ensure_migrations(conn)
    conn.execute(
        """
        INSERT INTO goals(id, description, steps_json, status)
        VALUES (?, ?, ?, 'active')
        ON CONFLICT(id) DO UPDATE SET
            description=excluded.description,
            steps_json=excluded.steps_json
        """,
        (
            GOAL_ID,
            "Tornar o Hive-Mind reproduzivel e validado para producao",
            json.dumps(STEPS, ensure_ascii=False),
        ),
    )

    neurons = (
        (
            CAUSE_ID,
            "Runtime local ao projeto",
            "O runtime usa .venv, lockfiles e checkouts fixados dentro do projeto.",
            "shared",
        ),
        (
            EFFECT_ID,
            "Validacao de prontidao operacional",
            "O isolamento local permite testes reais, recovery e auditoria reproduzivel.",
            "private",
        ),
    )
    for neuron_id, label, content, visibility in neurons:
        conn.execute(
            """
            INSERT INTO neurons(
                id, label, type, content, hash, metadata, visibility, indexed_at
            ) VALUES (?, ?, 'operational_fact', ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                label=excluded.label,
                type=excluded.type,
                content=excluded.content,
                hash=excluded.hash,
                metadata=excluded.metadata,
                visibility=excluded.visibility,
                indexed_at=CASE
                    WHEN neurons.hash IS NOT excluded.hash THEN NULL
                    ELSE neurons.indexed_at
                END,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                neuron_id,
                label,
                content,
                _hash(content),
                json.dumps(
                    {"source": "production-readiness-audit", "truthful": True},
                    sort_keys=True,
                ),
                visibility,
            ),
        )

    conn.execute(
        """
        INSERT INTO causal_edges(
            id, cause_neuron_id, effect_neuron_id, label, confidence, source
        ) VALUES (?, ?, ?, ?, 1.0, 'production-readiness-audit')
        ON CONFLICT(id) DO UPDATE SET
            cause_neuron_id=excluded.cause_neuron_id,
            effect_neuron_id=excluded.effect_neuron_id,
            label=excluded.label,
            confidence=excluded.confidence,
            source=excluded.source
        """,
        (
            EDGE_ID,
            CAUSE_ID,
            EFFECT_ID,
            "enables reproducible validation",
        ),
    )
    conn.execute(
        """
        INSERT INTO observations(
            id, project, type, title, content, neuron_id, archived, metadata,
            goal_id, why, intent_source
        ) VALUES (?, 'Hive-Mind', 'decision', ?, ?, ?, 0, ?, ?, ?, 'user')
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            content=excluded.content,
            neuron_id=excluded.neuron_id,
            metadata=excluded.metadata,
            goal_id=excluded.goal_id,
            why=excluded.why,
            intent_source=excluded.intent_source
        """,
        (
            OBSERVATION_ID,
            "Isolar e validar o Hive-Mind para producao",
            "Dependencias globais nao podem participar do runtime.",
            EFFECT_ID,
            json.dumps({"source": "production-readiness-audit"}, sort_keys=True),
            GOAL_ID,
            "Evitar perda de dados, drift e sucesso falso em testes.",
        ),
    )
    conn.commit()
    return {
        "goal_id": GOAL_ID,
        "neurons": [CAUSE_ID, EFFECT_ID],
        "causal_edge": EDGE_ID,
        "observation": OBSERVATION_ID,
    }


def main() -> int:
    conn = get_connection()
    try:
        state = materialize(conn)
        from core.indexing import index_neuron_ids

        state["indexed"] = index_neuron_ids(conn, state["neurons"])
        print(json.dumps(state, indent=2, ensure_ascii=False))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
