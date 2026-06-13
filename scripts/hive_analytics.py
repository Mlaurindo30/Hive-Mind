#!/usr/bin/env python3
"""
Camada analítica sobre hive_mind.db via DuckDB (read-only).
Não interfere com escritores SQLite — WAL nunca é bloqueado.

Uso: python3 scripts/hive_analytics.py [query_name]
Queries disponíveis: growth, top_topics, quarantine_rate, intent_by_goal
"""
import sys
import os
from pathlib import Path

try:
    import duckdb
except ImportError:
    raise SystemExit("duckdb não instalado. Execute: pip install duckdb")

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(Path(__file__).parent.parent))
DB_PATH = Path(SINAPSE_HOME) / "hive_mind.db"

QUERIES: dict[str, str] = {
    "growth": """
        SELECT strftime('%Y-%m-%d', created_at) AS dia,
               COUNT(*) AS novas_observacoes
        FROM hive.observations
        GROUP BY 1
        ORDER BY 1 DESC
        LIMIT 30
    """,
    "top_topics": """
        SELECT type, COUNT(*) AS c
        FROM hive.neurons
        GROUP BY type
        ORDER BY c DESC
        LIMIT 10
    """,
    "quarantine_rate": """
        SELECT
            CAST(ROUND(100.0 * SUM(CASE WHEN archived = 2 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS DOUBLE) AS pct_quarentena,
            SUM(CASE WHEN archived = 0 THEN 1 ELSE 0 END) AS pendentes,
            SUM(CASE WHEN archived = 1 THEN 1 ELSE 0 END) AS processadas,
            SUM(CASE WHEN archived = 2 THEN 1 ELSE 0 END) AS quarentena
        FROM hive.observations
    """,
    "intent_by_goal": """
        SELECT goal_id,
               COUNT(*) AS obs,
               ROUND(AVG(CASE WHEN archived = 1 THEN 1.0 ELSE 0.0 END), 2) AS taxa_conclusao
        FROM hive.observations
        WHERE goal_id IS NOT NULL
        GROUP BY goal_id
        ORDER BY obs DESC
    """,
}


def _has_column(conn: "duckdb.DuckDBPyConnection", table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info(hive.{table})").fetchall()
    return any(r[1] == column for r in rows)


def run(query_name: str, db_path: Path | None = None) -> "pd.DataFrame | list[tuple]":
    """Executa uma query analítica e retorna DataFrame (ou lista de tuplas se pandas ausente)."""
    path = db_path or DB_PATH
    if not path.exists():
        raise FileNotFoundError(f"Banco não encontrado: {path}")

    if query_name not in QUERIES:
        raise ValueError(f"Query desconhecida: {query_name!r}. Disponíveis: {list(QUERIES)}")

    conn = duckdb.connect(":memory:")
    conn.execute(f"ATTACH '{path}' AS hive (TYPE sqlite, READ_ONLY)")

    # intent_by_goal requer coluna goal_id — pula se ausente
    if query_name == "intent_by_goal" and not _has_column(conn, "observations", "goal_id"):
        conn.close()
        raise RuntimeError("Coluna goal_id ainda não existe em observations (Fase 11 pendente)")

    if _HAS_PANDAS:
        result = conn.execute(QUERIES[query_name]).fetchdf()
    else:
        result = conn.execute(QUERIES[query_name]).fetchall()

    conn.close()
    return result


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "quarantine_rate"
    try:
        result = run(query)
        if _HAS_PANDAS:
            print(result.to_string(index=False))
        else:
            for row in result:
                print(row)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"[hive_analytics] {e}", file=sys.stderr)
        sys.exit(1)
