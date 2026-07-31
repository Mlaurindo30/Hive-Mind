"""M14 — the identity decision store (ADR-014).

The store exists so a delivered event always has a recoverable identity. Two
of its properties are the ones worth breaking on purpose:

  - a decision is written before the post, so nothing is delivered without one;
  - the same session arriving with a *different* identity is quarantined, not
    overwritten — guessing which answer was right is how the free-label era
    started.
"""
from __future__ import annotations

import json
import sqlite3
import threading

import pytest

from hive_mind.capture.identity_store import (
    DeliveryState,
    IdentityConflict,
    IdentityStore,
    IdentityStoreError,
    InvalidTransition,
    canonical_json,
    default_path,
    identity_hash,
)

ENVELOPE = {
    "project_id": "hive-mind",
    "project_name": "Hive-Mind",
    "resolution_method": "git_root",
    "provider": "codex",
    "surface": "cli",
}


@pytest.fixture
def store(tmp_path):
    with IdentityStore(tmp_path / "identities.db") as opened:
        yield opened


def record(store, sid="session-1", envelope=None, **kwargs):
    envelope = envelope or ENVELOPE
    return store.record_pending(
        content_session_id=sid,
        provider=envelope.get("provider", "codex"),
        surface=envelope.get("surface", "cli"),
        project_id=envelope["project_id"],
        project_name=envelope["project_name"],
        identity=envelope,
        **kwargs,
    )


class TestSchemaAndLifecycle:
    def test_it_creates_its_schema(self, tmp_path):
        path = tmp_path / "new.db"
        with IdentityStore(path):
            pass
        with sqlite3.connect(path) as connection:
            tables = {r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"capture_identity_decisions", "schema_version"} <= tables

    def test_it_uses_wal(self, store):
        mode = store._connection.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_reopening_keeps_the_data(self, tmp_path):
        path = tmp_path / "reopen.db"
        with IdentityStore(path) as first:
            record(first)
        with IdentityStore(path) as second:
            assert second.get("session-1") is not None

    def test_a_newer_schema_is_refused(self, tmp_path):
        path = tmp_path / "future.db"
        with IdentityStore(path):
            pass
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE schema_version SET version=99")
        with pytest.raises(IdentityStoreError):
            IdentityStore(path)

    def test_a_path_with_spaces_and_unicode(self, tmp_path):
        path = tmp_path / "cérebro ação" / "identities.db"
        with IdentityStore(path) as opened:
            record(opened)
            assert opened.get("session-1").project_id == "hive-mind"

    def test_the_default_path_is_not_inside_claude_mem(self):
        """This database belongs to Hive-Mind and lives with Hive-Mind's state."""
        assert ".claude-mem" not in default_path().as_posix()


class TestRecordingADecision:
    def test_a_new_decision_starts_pending(self, store):
        decision = record(store)
        assert decision.delivery_state is DeliveryState.PENDING
        assert decision.project_id == "hive-mind"
        assert decision.identity_hash == identity_hash(ENVELOPE)

    def test_recording_twice_is_idempotent(self, store):
        first = record(store)
        second = record(store)
        assert second.created_at == first.created_at
        assert store._connection.execute(
            "SELECT COUNT(*) FROM capture_identity_decisions").fetchone()[0] == 1

    def test_a_different_identity_for_the_same_session_is_quarantined(self, store):
        record(store)
        other = {**ENVELOPE, "project_id": "some-other", "project_name": "Other"}
        with pytest.raises(IdentityConflict):
            record(store, envelope=other)
        assert store.get("session-1").delivery_state is DeliveryState.QUARANTINED

    def test_a_conflict_does_not_overwrite_the_stored_identity(self, store):
        record(store)
        with pytest.raises(IdentityConflict):
            record(store, envelope={**ENVELOPE, "project_id": "x",
                                    "project_name": "X"})
        assert store.get("session-1").project_id == "hive-mind"

    def test_comparison_is_not_by_project_name_alone(self, store):
        """Same name, different id, is still a conflict."""
        record(store)
        with pytest.raises(IdentityConflict):
            record(store, envelope={**ENVELOPE, "project_id": "different"})

    def test_a_changed_envelope_field_is_a_conflict(self, store):
        """The hash covers the whole envelope, not just the id."""
        record(store)
        with pytest.raises(IdentityConflict):
            record(store, envelope={**ENVELOPE, "resolution_method": "guessing"})

    def test_a_matching_replay_reopens_a_conflict_quarantine(self, store):
        record(store)
        with pytest.raises(IdentityConflict):
            record(store, envelope={**ENVELOPE, "project_id": "different"})

        replayed = record(store)

        assert replayed.delivery_state is DeliveryState.PENDING
        assert replayed.last_error is None

    def test_a_classified_replay_replaces_an_old_unclassified_fallback(self, store):
        degraded = {
            "project_id": "unclassified/antigravity",
            "project_name": "Unclassified (antigravity)",
            "resolution_method": "unclassified_provider",
            "provider": "antigravity",
            "surface": "cli",
        }
        improved = {
            **degraded,
            "project_id": "local/75a99723f2d2",
            "project_name": "Raju Trader",
            "resolution_method": "official_workspace",
            "workspace_root": r"D:\Raju Trader\Docs\impement",
            "repository_root": r"D:\Raju Trader",
        }

        first = record(store, sid="session-upgrade", envelope=degraded)
        assert first.project_id == "unclassified/antigravity"

        upgraded = record(store, sid="session-upgrade", envelope=improved)

        assert upgraded.delivery_state is DeliveryState.PENDING
        assert upgraded.project_id == "local/75a99723f2d2"
        assert upgraded.project_name == "Raju Trader"
        assert upgraded.identity["resolution_method"] == "official_workspace"
        assert upgraded.last_error is None

    def test_same_project_id_replay_does_not_quarantine_when_envelope_gets_richer(self, store):
        transcript_only = {
            "project_id": "unclassified/antigravity",
            "project_name": "Unclassified (antigravity)",
            "resolution_method": "unclassified_provider",
            "provider": "antigravity",
            "surface": "cli",
        }
        sqlite_replay = {
            **transcript_only,
            "workspace_root": r"C:\Users\miche\AppData\Local\Comfy-Desktop\ComfyUI-Installs\ComfyUI",
            "provider": "antigravity",
            "surface": "ide",
        }

        first = record(store, sid="session-same-project", envelope=transcript_only)
        assert first.delivery_state is DeliveryState.PENDING

        replayed = record(store, sid="session-same-project", envelope=sqlite_replay)

        assert replayed.delivery_state is DeliveryState.PENDING
        assert replayed.project_id == "unclassified/antigravity"
        assert replayed.identity["workspace_root"].endswith("ComfyUI")
        assert replayed.surface == "ide"
        assert replayed.last_error is None

    def test_an_empty_session_id_is_refused(self, store):
        with pytest.raises(IdentityStoreError):
            record(store, sid="")

    def test_the_raw_label_is_kept_for_audit(self, store):
        decision = record(store, raw_project_label="preciso-que-verifique")
        assert decision.raw_project_label == "preciso-que-verifique"
        assert decision.project_name == "Hive-Mind"


class TestTheStateMachine:
    def test_the_happy_path(self, store):
        record(store)
        assert store.mark_posted("session-1").delivery_state is DeliveryState.POSTED
        assert store.mark_observed("session-1").delivery_state is DeliveryState.OBSERVED
        assert store.mark_bridged("session-1").delivery_state is DeliveryState.BRIDGED

    def test_timestamps_are_set_as_it_advances(self, store):
        record(store)
        store.mark_posted("session-1")
        store.mark_observed("session-1")
        final = store.mark_bridged("session-1")
        assert final.posted_at and final.observed_at and final.bridged_at

    def test_a_repeated_transition_is_idempotent(self, store):
        record(store)
        first = store.mark_posted("session-1")
        again = store.mark_posted("session-1")
        assert again.posted_at == first.posted_at

    @pytest.mark.parametrize("path,target", [
        (("mark_bridged",), DeliveryState.BRIDGED),
        (("mark_observed",), DeliveryState.OBSERVED),
    ])
    def test_skipping_a_step_is_refused(self, store, path, target):
        record(store)
        with pytest.raises(InvalidTransition):
            getattr(store, path[0])("session-1")

    def test_bridged_cannot_go_back_to_pending(self, store):
        record(store)
        store.mark_posted("session-1")
        store.mark_observed("session-1")
        store.mark_bridged("session-1")
        replayed = store.mark_posted("session-1")
        assert replayed.delivery_state is DeliveryState.BRIDGED

    def test_observed_replay_does_not_reopen_a_bridged_session(self, store):
        record(store)
        store.mark_posted("session-1")
        store.mark_observed("session-1")
        store.mark_bridged("session-1")

        replayed = store.mark_observed("session-1")
        assert replayed.delivery_state is DeliveryState.BRIDGED

    def test_quarantined_is_terminal(self, store):
        record(store)
        store.quarantine("session-1", "conflict")
        with pytest.raises(InvalidTransition):
            store.mark_posted("session-1")

    def test_a_failed_post_can_be_retried(self, store):
        record(store)
        store.mark_failed("session-1", "worker offline")
        retried = store.mark_posted("session-1")
        assert retried.delivery_state is DeliveryState.POSTED
        assert retried.post_attempts >= 2

    def test_advancing_an_unknown_session_is_refused(self, store):
        with pytest.raises(IdentityStoreError):
            store.mark_posted("never-recorded")


class TestSafety:
    def test_no_secret_is_stored_in_an_error(self, store):
        record(store)
        store.mark_failed("session-1",
                          "POST failed: authorization: Bearer sk-abc123secret")
        stored = store.get("session-1").last_error
        assert "sk-abc123secret" not in stored
        assert "<redacted>" in stored

    def test_no_prompt_or_response_column_exists(self, store):
        columns = {row[1] for row in store._connection.execute(
            "PRAGMA table_info(capture_identity_decisions)")}
        for forbidden in ("prompt", "prompt_text", "response", "tool_response",
                          "content", "text"):
            assert forbidden not in columns

    def test_verify_passes_on_a_sound_store(self, store):
        record(store)
        assert store.verify() == []

    def test_verify_catches_a_tampered_envelope(self, store, tmp_path):
        record(store)
        store._connection.execute(
            "UPDATE capture_identity_decisions SET identity_json=?",
            (json.dumps({"project_id": "tampered"}),))
        problems = store.verify()
        assert any("hash mismatch" in problem for problem in problems)

    def test_the_canonical_json_is_order_independent(self):
        assert (identity_hash({"a": 1, "b": 2})
                == identity_hash({"b": 2, "a": 1}))
        assert canonical_json({"b": 2, "a": 1}).startswith('{"a"')

    def test_counts_report_every_state(self, store):
        record(store)
        counted = store.counts()
        assert set(counted) == {state.value for state in DeliveryState}
        assert counted["PENDING"] == 1


class TestConcurrency:
    def test_one_store_serializes_transactions_across_provider_threads(self, tmp_path):
        """One daemon shares this store across provider workers."""
        path = tmp_path / "shared-connection.db"
        errors: list[Exception] = []
        start = threading.Barrier(12)

        with IdentityStore(path) as opened:
            def writer(index: int):
                try:
                    start.wait()
                    for attempt in range(20):
                        sid = f"provider-{index}-session-{attempt}"
                        record(opened, sid=sid)
                        opened.mark_posted(sid)
                except Exception as caught:  # noqa: BLE001 - reported below
                    errors.append(caught)

            threads = [
                threading.Thread(target=writer, args=(index,))
                for index in range(12)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            assert errors == [], errors
            assert opened._connection.execute(
                "SELECT COUNT(*) FROM capture_identity_decisions"
            ).fetchone()[0] == 240

    def test_two_writers_do_not_create_two_rows(self, tmp_path):
        path = tmp_path / "concurrent.db"
        with IdentityStore(path):
            pass  # create the schema once, then race the writes

        errors: list[Exception] = []

        def writer():
            try:
                with IdentityStore(path) as opened:
                    record(opened)
            except Exception as caught:  # noqa: BLE001 - reported below
                errors.append(caught)

        threads = [threading.Thread(target=writer) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == [], errors
        with sqlite3.connect(path) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM capture_identity_decisions").fetchone()[0] == 1
