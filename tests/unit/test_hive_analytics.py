import sqlite3
import pytest
from pathlib import Path


def _create_test_db(tmp_path: Path) -> Path:
    """Cria um SQLite real com dados mínimos para os testes."""
    db = tmp_path / "test_hive.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS observations (
            id TEXT PRIMARY KEY,
            content TEXT,
            archived INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS neurons (
            id TEXT PRIMARY KEY,
            label TEXT,
            type TEXT DEFAULT 'fact'
        );
        INSERT INTO observations VALUES ('obs1', 'Conteudo A', 0, '2026-06-12 10:00:00');
        INSERT INTO observations VALUES ('obs2', 'Conteudo B', 1, '2026-06-12 11:00:00');
        INSERT INTO observations VALUES ('obs3', 'Conteudo C', 2, '2026-06-12 12:00:00');
        INSERT INTO neurons VALUES ('n1', 'Neuronio A', 'fact');
        INSERT INTO neurons VALUES ('n2', 'Neuronio B', 'decision');
        INSERT INTO neurons VALUES ('n3', 'Neuronio C', 'fact');
    """)
    conn.close()
    return db


class TestHiveAnalytics:
    def test_quarantine_rate_returns_correct_counts(self, tmp_path):
        from scripts.hive_analytics import run
        db = _create_test_db(tmp_path)
        result = run("quarantine_rate", db_path=db)
        # pandas DataFrame ou lista de tuplas
        try:
            row = result.iloc[0]
            assert row["pendentes"] == 1
            assert row["processadas"] == 1
            assert row["quarentena"] == 1
        except AttributeError:
            row = result[0]
            assert row[1] == 1  # pendentes
            assert row[2] == 1  # processadas
            assert row[3] == 1  # quarentena

    def test_top_topics_returns_neuron_types(self, tmp_path):
        from scripts.hive_analytics import run
        db = _create_test_db(tmp_path)
        result = run("top_topics", db_path=db)
        try:
            # pandas DataFrame path
            types = result["type"].tolist()
        except (AttributeError, TypeError):
            # list of tuples path (no pandas)
            types = [r[0] for r in result]
        assert "fact" in types
        assert "decision" in types

    def test_growth_returns_daily_counts(self, tmp_path):
        from scripts.hive_analytics import run
        db = _create_test_db(tmp_path)
        result = run("growth", db_path=db)
        try:
            assert len(result) >= 1
            assert "dia" in result.columns
        except AttributeError:
            assert len(result) >= 1

    def test_raises_on_missing_db(self, tmp_path):
        from scripts.hive_analytics import run
        with pytest.raises(FileNotFoundError):
            run("quarantine_rate", db_path=tmp_path / "nao_existe.db")

    def test_raises_on_unknown_query(self, tmp_path):
        from scripts.hive_analytics import run
        db = _create_test_db(tmp_path)
        with pytest.raises(ValueError, match="Query desconhecida"):
            run("query_que_nao_existe", db_path=db)

    def test_intent_by_goal_skips_when_column_missing(self, tmp_path):
        from scripts.hive_analytics import run
        db = _create_test_db(tmp_path)
        with pytest.raises(RuntimeError, match="goal_id"):
            run("intent_by_goal", db_path=db)

    def test_empty_db_quarantine_rate_no_crash(self, tmp_path):
        """DB com zero observações não deve travar — retorna NULL/0."""
        from scripts.hive_analytics import run
        db = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE observations (id TEXT, content TEXT, archived INTEGER, created_at TEXT);
            CREATE TABLE neurons (id TEXT, label TEXT, type TEXT);
        """)
        conn.close()
        result = run("quarantine_rate", db_path=db)
        # Não deve lançar exceção — resultado com NULL é aceitável
        assert result is not None
