"""D004-R1 — the native canary must not pass a broken pipeline.

The predecessor built a synthetic session, created mock schemas and
monkeypatched the bridge, so it could not fail while real capture was broken.
These tests pin the judgement rules that make the native canary honest.
"""
from __future__ import annotations

import sqlite3
import json
from pathlib import Path

import pytest

from hive_mind.validation.delivery import (
    inspect_legacy_recovery,
    inspect_outbox,
    inspect_umc,
    inspect_umc_legacy,
)
from hive_mind.validation.models import CanaryReport, CanaryResult, CanaryStatus
from hive_mind.validation.sources import SourceInventory


def _fresh_databases(tmp_path: Path, *, marker: str, sid: str = "fresh-sid",
                     cm_epoch: int = 200, identity: bool = True,
                     umc: bool = True,
                     bridged_at: str = "2026-07-22T00:00:00Z"):
    claude_mem = tmp_path / "claude-mem.db"
    conn = sqlite3.connect(claude_mem)
    conn.executescript("""
        CREATE TABLE user_prompts (
            content_session_id TEXT, prompt_text TEXT, created_at_epoch INTEGER
        );
        CREATE TABLE sdk_sessions (
            content_session_id TEXT UNIQUE, memory_session_id TEXT UNIQUE
        );
    """)
    conn.execute(
        "INSERT INTO sdk_sessions VALUES (?, ?)", (sid, "memory-fresh")
    )
    conn.execute(
        "INSERT INTO user_prompts VALUES (?, ?, ?)", (sid, marker, cm_epoch)
    )
    conn.commit()
    conn.close()

    identity_db = tmp_path / "capture-identity.db"
    conn = sqlite3.connect(identity_db)
    conn.execute("""
        CREATE TABLE capture_identity_decisions (
            content_session_id TEXT PRIMARY KEY, provider TEXT,
            project_id TEXT, delivery_state TEXT, bridged_at TEXT
        )
    """)
    if identity:
        conn.execute(
            "INSERT INTO capture_identity_decisions VALUES (?, ?, ?, ?, ?)",
            (sid, "codex", "hive-mind", "BRIDGED", bridged_at),
        )
    conn.commit()
    conn.close()

    umc_db = tmp_path / "hive_mind.db"
    conn = sqlite3.connect(umc_db)
    conn.execute("""
        CREATE TABLE observations (
            id TEXT PRIMARY KEY, content TEXT, metadata TEXT,
            created_at TEXT, workspace_id TEXT
        )
    """)
    if umc:
        conn.execute(
            "INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
            ("cm-fresh", "normalized bridge observation",
             json.dumps({"content_session_id": sid}),
             "2026-07-22T00:00:00Z", "hive-mind"),
        )
    conn.commit()
    conn.close()
    return claude_mem, identity_db, umc_db


class TestReportAggregation:
    def test_report_is_not_ok_when_any_provider_fails(self):
        report = CanaryReport(results=(
            CanaryResult("a", CanaryStatus.PASSED),
            CanaryResult("b", CanaryStatus.FAILED, reason="x"),
        ))
        assert report.ok is False
        assert len(report.failed) == 1

    def test_an_empty_run_is_not_ok(self):
        """No providers checked is not the same as everything healthy."""
        assert CanaryReport().ok is False

    def test_errors_count_as_failures(self):
        report = CanaryReport(results=(CanaryResult("a", CanaryStatus.ERROR),))
        assert report.ok is False

    def test_skipped_alone_is_not_success(self):
        report = CanaryReport(results=(CanaryResult("a", CanaryStatus.SKIPPED),))
        assert report.ok is True  # nothing failed
        assert report.passed == ()


class TestOutboxInspection:
    def _outbox(self, path: Path, rows):
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE capture_outbox (id INTEGER PRIMARY KEY, provider TEXT,"
            " occurred_at TEXT, delivered_at TEXT, dead_letter_at TEXT)"
        )
        conn.executemany(
            "INSERT INTO capture_outbox (provider, occurred_at, delivered_at,"
            " dead_letter_at) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        conn.close()

    def test_detects_a_fully_stalled_outbox(self, tmp_path):
        db = tmp_path / "capture.db"
        self._outbox(db, [("codex", "2026-01-01", None, None)] * 3)
        state = inspect_outbox(db)
        assert state.total == 3
        assert state.undelivered == 3
        assert state.stalled is True

    def test_a_delivering_outbox_is_not_stalled(self, tmp_path):
        db = tmp_path / "capture.db"
        self._outbox(db, [("codex", "2026-01-01", "2026-01-02", None)])
        assert inspect_outbox(db).stalled is False

    def test_counts_undelivered_per_provider(self, tmp_path):
        db = tmp_path / "capture.db"
        self._outbox(db, [
            ("codex", "2026-01-01", None, None),
            ("codex", "2026-01-01", None, None),
            ("mimo", "2026-01-01", None, None),
        ])
        assert dict(inspect_outbox(db).by_provider) == {"codex": 2, "mimo": 1}

    def test_records_oldest_and_newest_undelivered(self, tmp_path):
        db = tmp_path / "capture.db"
        self._outbox(db, [
            ("codex", "2026-01-01", None, None),
            ("codex", "2026-01-03", None, None),
            ("codex", "2026-01-02", "2026-01-05", None),
        ])
        state = inspect_outbox(db)
        assert state.oldest_undelivered == "2026-01-01"
        assert state.newest_undelivered == "2026-01-03"

    def test_missing_database_is_reported_not_raised(self, tmp_path):
        state = inspect_outbox(tmp_path / "absent.db")
        assert state.exists is False
        assert state.stalled is False

    def test_inspection_never_writes(self, tmp_path):
        db = tmp_path / "capture.db"
        self._outbox(db, [("codex", "2026-01-01", None, None)])
        before = db.stat().st_mtime_ns
        inspect_outbox(db)
        assert db.stat().st_mtime_ns == before


class TestUmcInspection:
    def _umc(self, path: Path, workspaces):
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE observations (id TEXT PRIMARY KEY, workspace_id TEXT)"
        )
        conn.executemany(
            "INSERT INTO observations (id, workspace_id) VALUES (?, ?)",
            [(str(i), w) for i, w in enumerate(workspaces)],
        )
        conn.commit()
        conn.close()

    def test_default_workspace_is_not_canonical(self, tmp_path):
        db = tmp_path / "umc.db"
        self._umc(db, ["default"] * 5)
        state = inspect_umc(db)
        assert state.observations == 5
        assert state.canonical == 0
        assert state.canonical_pct == 0.0

    def test_counts_canonical_workspaces(self, tmp_path):
        db = tmp_path / "umc.db"
        self._umc(db, ["hive-mind", "hive-mind", "default"])
        state = inspect_umc(db)
        assert state.canonical == 2
        assert state.legacy == 1

    def test_empty_workspace_counts_as_legacy(self, tmp_path):
        db = tmp_path / "umc.db"
        self._umc(db, ["", "hive-mind"])
        assert inspect_umc(db).legacy == 1


class TestUmcLegacyInspection:
    def test_breaks_default_and_unclassified_legacy_apart(self, tmp_path):
        db = tmp_path / "umc.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE observations (id TEXT PRIMARY KEY, workspace_id TEXT,"
            " project TEXT, archived INTEGER)"
        )
        conn.executemany(
            "INSERT INTO observations (id, workspace_id, project, archived)"
            " VALUES (?, ?, ?, ?)",
            [
                ("a", "default", "Hive-Mind", 0),
                ("b", "default", "ins", 0),
                ("c", "", "legacy-empty", 0),
                ("d", "unclassified/legacy", "Raju Trader", 0),
                ("e", "unclassified/legacy", "Hive-Mind", 0),
                ("f", "default", "archived-default", 2),
            ],
        )
        conn.commit()
        conn.close()

        state = inspect_umc_legacy(db)
        assert state.default_workspace == 3
        assert state.empty_workspace == 1
        assert state.unclassified_legacy == 2
        assert state.archived_quarantine == 1
        assert dict(state.default_active_by_project) == {"Hive-Mind": 1, "ins": 1}
        assert dict(state.unclassified_active_by_project) == {
            "Raju Trader": 1, "Hive-Mind": 1
        }

    def test_legacy_recovery_counts_bridged_sessions(self, tmp_path):
        umc = tmp_path / "umc.db"
        conn = sqlite3.connect(umc)
        conn.execute(
            "CREATE TABLE observations (id TEXT PRIMARY KEY, workspace_id TEXT,"
            " metadata TEXT, archived INTEGER)"
        )
        conn.executemany(
            "INSERT INTO observations (id, workspace_id, metadata, archived)"
            " VALUES (?, ?, ?, ?)",
            [
                ("a", "unclassified/legacy", json.dumps({"source_session": "sid-1"}), 0),
                ("b", "unclassified/legacy", json.dumps({"source_session": "sid-2"}), 0),
                ("c", "unclassified/legacy", json.dumps({"source_session": "sid-3"}), 0),
            ],
        )
        conn.commit()
        conn.close()

        identity = tmp_path / "capture-identities.db"
        conn = sqlite3.connect(identity)
        conn.execute(
            "CREATE TABLE capture_identity_decisions (content_session_id TEXT PRIMARY KEY,"
            " project_id TEXT, delivery_state TEXT)"
        )
        conn.executemany(
            "INSERT INTO capture_identity_decisions VALUES (?, ?, ?)",
            [
                ("sid-1", "hive-mind", "BRIDGED"),
                ("sid-2", "unclassified/other", "BRIDGED"),
                ("sid-3", "hive-mind", "POSTED"),
            ],
        )
        conn.commit()
        conn.close()

        state = inspect_legacy_recovery(umc, identity_db=identity)
        assert state.legacy_source_sessions == 3
        assert state.decisions_found == 3
        assert state.bridged_recoverable == 1
        assert dict(state.bridged_by_project) == {"hive-mind": 1}

    def test_legacy_recovery_measures_sessionstore_signal_without_reclassifying(self, monkeypatch, tmp_path):
        umc = tmp_path / "umc.db"
        conn = sqlite3.connect(umc)
        conn.execute(
            "CREATE TABLE observations (id TEXT PRIMARY KEY, workspace_id TEXT,"
            " metadata TEXT, archived INTEGER)"
        )
        conn.executemany(
            "INSERT INTO observations (id, workspace_id, metadata, archived)"
            " VALUES (?, ?, ?, ?)",
            [
                ("a", "unclassified/legacy", json.dumps({"source_session": "sid-1"}), 0),
                ("b", "unclassified/legacy", json.dumps({"source_session": "sid-2"}), 0),
                ("c", "unclassified/legacy", json.dumps({"source_session": "sid-3"}), 0),
            ],
        )
        conn.commit()
        conn.close()

        identity = tmp_path / "capture-identities.db"
        conn = sqlite3.connect(identity)
        conn.execute(
            "CREATE TABLE capture_identity_decisions (content_session_id TEXT PRIMARY KEY,"
            " project_id TEXT, delivery_state TEXT)"
        )
        conn.executemany(
            "INSERT INTO capture_identity_decisions VALUES (?, ?, ?)",
            [
                ("sid-1", "hive-mind", "BRIDGED"),
                ("sid-2", "unclassified/other", "BRIDGED"),
            ],
        )
        conn.commit()
        conn.close()

        claude_mem = tmp_path / "claude-mem.db"
        conn = sqlite3.connect(claude_mem)
        conn.execute(
            "CREATE TABLE sdk_sessions (memory_session_id TEXT PRIMARY KEY, project TEXT)"
        )
        conn.executemany(
            "INSERT INTO sdk_sessions VALUES (?, ?)",
            [
                ("sid-1", "Hive-Mind"),
                ("sid-2", "Raju Trader"),
            ],
        )
        conn.commit()
        conn.close()
        monkeypatch.setenv("CLAUDE_MEM_DB", str(claude_mem))

        state = inspect_legacy_recovery(umc, identity_db=identity)
        assert state.claude_mem_exists is True
        assert state.session_rows_found == 2
        assert state.session_project_signals == 2
        assert state.canonical_alias_matches == 2
        assert dict(state.canonical_signal_by_project) == {
            "hive-mind": 1,
            "local/75a99723f2d2": 1,
        }
        assert dict(state.unmapped_session_projects) == {}

    def test_legacy_recovery_includes_default_workspace_rows(self, monkeypatch, tmp_path):
        umc = tmp_path / "umc.db"
        conn = sqlite3.connect(umc)
        conn.execute(
            "CREATE TABLE observations (id TEXT PRIMARY KEY, workspace_id TEXT,"
            " metadata TEXT, archived INTEGER)"
        )
        conn.executemany(
            "INSERT INTO observations (id, workspace_id, metadata, archived)"
            " VALUES (?, ?, ?, ?)",
            [
                ("a", "default", json.dumps({"memory_session_id": "sid-1"}), 0),
                ("b", "default", json.dumps({"memory_session_id": "sid-2"}), 0),
                ("c", "unclassified/legacy", json.dumps({"source_session": "sid-3"}), 0),
            ],
        )
        conn.commit()
        conn.close()

        identity = tmp_path / "capture-identities.db"
        conn = sqlite3.connect(identity)
        conn.execute(
            "CREATE TABLE capture_identity_decisions (content_session_id TEXT PRIMARY KEY,"
            " project_id TEXT, delivery_state TEXT)"
        )
        conn.executemany(
            "INSERT INTO capture_identity_decisions VALUES (?, ?, ?)",
            [
                ("sid-1", "hive-mind", "BRIDGED"),
                ("sid-2", "unclassified/other", "POSTED"),
                ("sid-3", "hive-mind", "BRIDGED"),
            ],
        )
        conn.commit()
        conn.close()

        claude_mem = tmp_path / "claude-mem.db"
        conn = sqlite3.connect(claude_mem)
        conn.execute(
            "CREATE TABLE sdk_sessions (memory_session_id TEXT PRIMARY KEY, project TEXT)"
        )
        conn.executemany(
            "INSERT INTO sdk_sessions VALUES (?, ?)",
            [
                ("sid-1", "Hive-Mind"),
                ("sid-2", "ins"),
                ("sid-3", "Raju Trader"),
            ],
        )
        conn.commit()
        conn.close()
        monkeypatch.setenv("CLAUDE_MEM_DB", str(claude_mem))

        state = inspect_legacy_recovery(umc, identity_db=identity)

        assert state.source_workspaces == ("unclassified/legacy", "default")
        assert state.legacy_source_sessions == 3
        assert state.decisions_found == 3
        assert state.bridged_recoverable == 2
        assert dict(state.bridged_by_project) == {"hive-mind": 2}
        assert state.session_rows_found == 3
        assert state.session_project_signals == 3
        assert state.canonical_alias_matches == 2
        assert dict(state.canonical_signal_by_project) == {
            "hive-mind": 1,
            "local/75a99723f2d2": 1,
        }
        assert dict(state.unmapped_session_projects) == {"ins": 1}


class TestNoSyntheticData:
    """The native canary must not ship a synthetic session builder."""

    def test_validation_package_has_no_scenario_module(self):
        from hive_mind import validation

        pkg = Path(validation.__file__).parent
        assert not (pkg / "scenario.py").exists(), (
            "a synthetic-session builder would reintroduce the mock canary"
        )

    def test_canary_module_does_not_create_tables(self):
        from hive_mind.validation import canary

        source = Path(canary.__file__).read_text(encoding="utf-8")
        assert "CREATE TABLE" not in source.upper(), (
            "the canary must read real databases, never fabricate schemas"
        )

    def test_canary_module_does_not_monkeypatch(self):
        """Executable code only — the docstring may describe what it replaced."""
        import ast

        from hive_mind.validation import canary

        source = Path(canary.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        doc_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                if ast.get_docstring(node, clean=False) and node.body:
                    first = node.body[0]
                    doc_lines.update(
                        range(first.lineno, (first.end_lineno or first.lineno) + 1)
                    )
        code = "\n".join(
            line
            for n, line in enumerate(source.splitlines(), start=1)
            if n not in doc_lines and not line.strip().startswith("#")
        )
        for smell in ("monkeypatch", "setattr(", "get_connection ="):
            assert smell not in code, f"canary patches production code: {smell}"

    def test_delivery_opens_databases_read_only(self):
        from hive_mind.validation import delivery

        source = Path(delivery.__file__).read_text(encoding="utf-8")
        assert "mode=ro" in source, "protected databases must be opened read-only"


class TestProviderSourceSelection:
    def test_uses_next_newest_source_when_newest_has_no_sessions(self, monkeypatch, tmp_path):
        from hive_mind.validation import canary

        newest = tmp_path / "initialized-but-empty.jsonl"
        older = tmp_path / "session-history.jsonl"
        monkeypatch.setattr(
            canary.sources,
            "inventory",
            lambda provider: SourceInventory(provider, (newest, older), newest, 2.0),
        )
        parsed_sources = []

        def parse_sessions(provider, source):
            parsed_sources.append(source)
            return [] if source == newest else [{"session_id": "real-session"}]

        monkeypatch.setattr(canary.sources, "parse_sessions", parse_sessions)
        monkeypatch.setattr(
            canary,
            "_attach_identity",
            lambda provider, session, resolver, surface: {"project_id": "hive-mind"},
        )

        result = canary.run_provider("codex", resolver=object())

        assert result.status is CanaryStatus.PASSED
        assert result.project_id == "hive-mind"
        assert parsed_sources == [newest, older]

    def test_legacy_outbox_backlog_does_not_fail_the_provider(self, monkeypatch, tmp_path):
        from hive_mind.validation import canary
        from hive_mind.validation.delivery import OutboxState

        newest = tmp_path / "session-history.jsonl"
        newest.write_text("provider-owned", encoding="utf-8")
        monkeypatch.setattr(
            canary.sources,
            "inventory",
            lambda provider: SourceInventory(provider, (newest,), newest, 2.0),
        )
        monkeypatch.setattr(
            canary.sources, "parse_sessions",
            lambda provider, source: [{"session_id": "real-session"}],
        )
        monkeypatch.setattr(
            canary,
            "_attach_identity",
            lambda provider, session, resolver, surface: {"project_id": "hive-mind"},
        )

        result = canary.run_provider(
            "codex",
            resolver=object(),
            outbox=OutboxState(
                path=str(tmp_path / "capture.db"),
                exists=True,
                total=100,
                delivered=0,
                undelivered=100,
                by_provider=(("codex", 100),),
            ),
        )

        assert result.status is CanaryStatus.PASSED

    def test_reports_all_attempted_sources_when_every_source_is_empty(self, monkeypatch, tmp_path):
        from hive_mind.validation import canary

        newest = tmp_path / "initialized-but-empty.jsonl"
        older = tmp_path / "older-but-empty.jsonl"
        monkeypatch.setattr(
            canary.sources,
            "inventory",
            lambda provider: SourceInventory(provider, (newest, older), newest, 2.0),
        )
        parsed_sources = []

        def parse_sessions(provider, source):
            parsed_sources.append(source)
            return []

        monkeypatch.setattr(canary.sources, "parse_sessions", parse_sessions)

        result = canary.run_provider("codex")

        assert result.status is CanaryStatus.FAILED
        assert parsed_sources == [newest, older]
        assert newest.name in result.reason
        assert older.name in result.reason


class TestFreshMarkerChain:
    MARKER = "HM-FRESH-codex-123"

    def _paths(self, canary, paths):
        return canary.FreshMarkerPaths(
            claude_mem_db=paths[0], identity_db=paths[1], umc_db=paths[2]
        )

    def _source(self, monkeypatch, canary, tmp_path, *, marker=None,
                sid="fresh-sid", started_at=200):
        source = tmp_path / "real-provider.jsonl"
        source.write_text("provider-owned", encoding="utf-8")
        monkeypatch.setattr(
            canary.sources, "inventory",
            lambda provider: SourceInventory(provider, (source,), source, 200.0),
        )
        monkeypatch.setattr(
            canary.sources, "parse_sessions",
            lambda provider, path: [{
                "sid": sid, "started_at": started_at,
                "prompt": marker if marker is not None else self.MARKER,
            }],
        )

    def test_complete_marker_chain_passes(self, monkeypatch, tmp_path):
        from hive_mind.validation import canary

        dbs = _fresh_databases(tmp_path, marker=self.MARKER)
        self._source(monkeypatch, canary, tmp_path)
        mtimes = {path: path.stat().st_mtime_ns for path in dbs}

        report = canary.run_fresh_marker(
            marker=self.MARKER, since_epoch=100, providers=["codex"],
            paths=self._paths(canary, dbs),
        )

        assert report.ok is True
        assert report.results[0].project_id == "hive-mind"
        assert {path: path.stat().st_mtime_ns for path in dbs} == mtimes

    def test_marker_older_than_cutoff_fails(self, monkeypatch, tmp_path):
        from hive_mind.validation import canary

        dbs = _fresh_databases(tmp_path, marker=self.MARKER, cm_epoch=99)
        self._source(monkeypatch, canary, tmp_path)

        result = canary.run_fresh_marker(
            marker=self.MARKER, since_epoch=100, providers=["codex"],
            paths=self._paths(canary, dbs),
        ).results[0]

        assert result.status is CanaryStatus.FAILED
        assert "Claude Mem" in result.reason

    def test_identity_bridged_before_cutoff_fails(self, monkeypatch, tmp_path):
        from hive_mind.validation import canary

        dbs = _fresh_databases(
            tmp_path, marker=self.MARKER,
            bridged_at="1970-01-01T00:01:39Z",
        )
        self._source(monkeypatch, canary, tmp_path)

        result = canary.run_fresh_marker(
            marker=self.MARKER, since_epoch=100, providers=["codex"],
            paths=self._paths(canary, dbs),
        ).results[0]

        assert result.status is CanaryStatus.FAILED
        assert "identity" in result.reason

    @pytest.mark.parametrize(
        ("missing", "expected"),
        [
            ("source", "provider source"),
            ("claude_mem", "Claude Mem"),
            ("identity", "identity"),
            ("umc", "UMC"),
        ],
    )
    def test_absence_at_each_stage_fails(self, monkeypatch, tmp_path,
                                         missing, expected):
        from hive_mind.validation import canary

        dbs = _fresh_databases(
            tmp_path, marker=("different" if missing == "claude_mem" else self.MARKER),
            identity=missing != "identity", umc=missing != "umc",
        )
        self._source(
            monkeypatch, canary, tmp_path,
            marker="different" if missing == "source" else self.MARKER,
        )

        result = canary.run_fresh_marker(
            marker=self.MARKER, since_epoch=100, providers=["codex"],
            paths=self._paths(canary, dbs),
        ).results[0]

        assert result.status is CanaryStatus.FAILED
        assert expected in result.reason

    def test_stalled_outbox_is_irrelevant(self, monkeypatch, tmp_path):
        from hive_mind.validation import canary

        dbs = _fresh_databases(tmp_path, marker=self.MARKER)
        self._source(monkeypatch, canary, tmp_path)
        outbox = tmp_path / "capture.db"
        conn = sqlite3.connect(outbox)
        conn.execute("CREATE TABLE capture_outbox (delivered_at TEXT)")
        conn.execute("INSERT INTO capture_outbox VALUES (NULL)")
        conn.commit()
        conn.close()

        report = canary.run_fresh_marker(
            marker=self.MARKER, since_epoch=100, providers=["codex"],
            paths=self._paths(canary, dbs),
        )

        assert report.ok is True

    def test_cli_accepts_marker_since_and_explicit_providers(self):
        from hive_mind.cli import _build_parser

        args = _build_parser().parse_args([
            "validate", "agents", "--marker", self.MARKER,
            "--since", "100", "--only", "codex", "--only", "hermes",
        ])

        assert args.marker == self.MARKER
        assert args.since == 100
        assert args.only == ["codex", "hermes"]

    def test_cli_accepts_validate_delivery(self):
        from hive_mind.cli import _build_parser

        args = _build_parser().parse_args([
            "validate", "delivery", "--outbox-db", "capture.db", "--hive-db", "hive_mind.db", "--json",
        ])

        assert args.validate_command == "delivery"
        assert args.outbox_db == "capture.db"
        assert args.hive_db == "hive_mind.db"
        assert args.json is True
