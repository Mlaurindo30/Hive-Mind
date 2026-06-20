import os
import sys
import pytest
import sqlite3 as _sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

# Setup paths
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = str(_HERE.parent.parent)
sys.path.append(SINAPSE_HOME)

from core import paths as cp
from core.schemas.weekly_models import WeeklySummaryModel, ProjectStatus
from scripts.dream.weekly_synthesizer import collect_daily_logs, get_week_range, generate_markdown

# Minimal SQLite schema
_MINIMAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS neurons (
    id TEXT PRIMARY KEY,
    label TEXT,
    type TEXT,
    source_file TEXT,
    content TEXT,
    hash TEXT,
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

def _make_in_memory_db() -> _sqlite3.Connection:
    conn = _sqlite3.connect(":memory:")
    conn.row_factory = _sqlite3.Row
    conn.executescript(_MINIMAL_SCHEMA)
    return conn

class TestWeeklySynthesizer:
    def test_get_week_range(self):
        # 2026-W25 starts 2026-06-15 (Mon) and ends 2026-06-21 (Sun)
        start, end = get_week_range(2026, 25)
        assert start == date(2026, 6, 15)
        assert end == date(2026, 6, 21)

    def test_collect_daily_logs(self, tmp_path):
        # Mock paths.daily_path to point to tmp_path
        start_date = date(2026, 6, 15)
        end_date = date(2026, 6, 17) # Just 3 days for test
        
        with patch("core.paths.daily_path") as mock_daily_path:
            def side_effect(d):
                return tmp_path / f"{d.isoformat()}.md"
            mock_daily_path.side_effect = side_effect
            
            # Create one log file
            log_file = tmp_path / "2026-06-15.md"
            log_file.write_text("Daily log content")
            
            logs = collect_daily_logs(start_date, end_date)
            assert len(logs) == 3
            assert logs[0]["date"] == "2026-06-15"
            assert logs[0]["content"] == "Daily log content"
            assert logs[1]["content"] is None # 2026-06-16 missing

    def test_generate_markdown(self):
        summary = WeeklySummaryModel(
            overview="Test overview",
            top_atoms=["Atom 1", "Atom 2"],
            decisions_closed=["Decision 1"],
            decisions_open=["Decision 2"],
            projects=[ProjectStatus(name="Project X", status="active", blockers="None", delta="Big progress")],
            patterns=["Pattern 1"],
            next_week_priorities=["Priority 1"]
        )
        daily_logs = [{"date": "2026-06-15", "content": "exists"}, {"date": "2026-06-16", "content": None}]
        
        md = generate_markdown(summary, 2026, 25, date(2026, 6, 15), date(2026, 6, 21), daily_logs)
        
        assert "Semana 2026-W25" in md
        assert "Test overview" in md
        assert "| 2026-06-15 | ✅ |" in md
        assert "| 2026-06-16 | ❌ |" in md
        assert "Atom 1" in md
        assert "Decision 1" in md
        assert "Project X" in md
        assert "Big progress" in md
        assert "Priority 1" in md

    @patch("scripts.dream.weekly_synthesizer.get_connection")
    def test_query_week_data(self, mock_get_conn):
        from scripts.dream.weekly_synthesizer import query_week_data
        
        db_conn = _make_in_memory_db()
        db_conn.execute("INSERT INTO neurons (id, label, type, created_at) VALUES ('1', 'Fact 1', 'fact', '2026-06-16T10:00:00')")
        db_conn.execute("INSERT INTO neurons (id, label, type, created_at) VALUES ('2', 'Decision 1', 'decision', '2026-06-17T12:00:00')")
        db_conn.execute("INSERT INTO neurons (id, label, type, created_at) VALUES ('3', 'Fact Old', 'fact', '2026-01-01T10:00:00')")
        db_conn.commit()
        
        mock_get_conn.return_value = db_conn
        
        data = query_week_data(date(2026, 6, 15), date(2026, 6, 21))
        assert len(data["atoms"]) == 1
        assert data["atoms"][0]["label"] == "Fact 1"
        assert len(data["decisions"]) == 1
        assert data["decisions"][0]["label"] == "Decision 1"
