"""M14 — recovering an observation's identity, and refusing to invent one.

Real SQLite throughout: the relation being tested is a declared foreign key
between two UNIQUE columns, and a fake would only prove the fake agreed with
itself.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from hive_mind.capture.identity_store import DeliveryState, IdentityStore
from hive_mind.capture.observation_identity import (
    Origin,
    content_session_id_for,
    health_counters,
    is_healthy,
    resolve_capture_identity_for_observation,
)

SID = "codex-session-42"
MEMORY_ID = "openrouter-codex-session-42-1784750259278"
ENVELOPE = {
    "project_id": "hive-mind",
    "project_name": "Hive-Mind",
    "resolution_method": "git_root",
    "provider": "codex",
    "surface": "cli",
}


@pytest.fixture
def claude_mem(tmp_path):
    """A Claude Mem store shaped like the real one (measured in M14-A)."""
    path = tmp_path / "claude-mem.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE sdk_sessions (
            id INTEGER PRIMARY KEY,
            content_session_id TEXT UNIQUE,
            memory_session_id  TEXT UNIQUE,
            project TEXT);
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT,
            prompt_number INTEGER,
            project TEXT,
            metadata TEXT,
            FOREIGN KEY(memory_session_id)
                REFERENCES sdk_sessions(memory_session_id));
    """)
    yield connection
    connection.close()


@pytest.fixture
def registry(tmp_path):
    with IdentityStore(tmp_path / "identities.db") as store:
        yield store


def link_session(claude_mem, sid=SID, memory_id=MEMORY_ID, project="Hive-Mind"):
    claude_mem.execute(
        "INSERT INTO sdk_sessions (content_session_id, memory_session_id, project)"
        " VALUES (?,?,?)", (sid, memory_id, project))
    claude_mem.commit()


def add_observation(claude_mem, memory_id=MEMORY_ID, project="Hive-Mind",
                    metadata=None):
    claude_mem.execute(
        "INSERT INTO observations (memory_session_id, prompt_number, project,"
        " metadata) VALUES (?,1,?,?)",
        (memory_id, project, json.dumps(metadata) if metadata else None))
    claude_mem.commit()


def record(registry, sid=SID, envelope=None, project_id=None):
    envelope = envelope or ENVELOPE
    return registry.record_pending(
        content_session_id=sid, provider="codex", surface="cli",
        project_id=project_id or envelope["project_id"],
        project_name=envelope["project_name"], identity=envelope,
        raw_project_label="rotulo-livre-que-nao-vale")


def resolve(claude_mem, registry, memory_id=MEMORY_ID, metadata=None, **kwargs):
    return resolve_capture_identity_for_observation(
        memory_session_id=memory_id, claude_mem=claude_mem,
        identity_store=registry, metadata=metadata, **kwargs)


class TestTheCorrelationPath:
    def test_the_foreign_key_leads_to_our_session_id(self, claude_mem):
        link_session(claude_mem)
        assert content_session_id_for(claude_mem, MEMORY_ID) == SID

    def test_an_unknown_memory_session_yields_nothing(self, claude_mem):
        assert content_session_id_for(claude_mem, "never-seen") is None

    def test_the_id_shape_is_never_parsed(self, claude_mem):
        """A memory id that does *not* contain the sid still resolves.

        Today the worker builds `memory_session_id` from the sid, so a
        substring reader would pass. This session id shares nothing with it,
        which is what a format change would look like.
        """
        link_session(claude_mem, sid="unrelated-sid",
                     memory_id="totally-different-shape")
        assert content_session_id_for(
            claude_mem, "totally-different-shape") == "unrelated-sid"


class TestRecoveringTheDecision:
    def test_the_recorded_decision_is_returned(self, claude_mem, registry):
        link_session(claude_mem)
        record(registry)
        add_observation(claude_mem)

        found = resolve(claude_mem, registry)
        assert found.origin is Origin.REGISTRY
        assert found.project_id == "hive-mind"
        assert found.project_name == "Hive-Mind"
        assert found.content_session_id == SID

    def test_it_marks_the_decision_observed(self, claude_mem, registry):
        link_session(claude_mem)
        record(registry)
        registry.mark_posted(SID)

        resolve(claude_mem, registry)
        assert registry.get(SID).delivery_state is DeliveryState.OBSERVED

    def test_marking_can_be_turned_off_for_a_read_only_pass(self, claude_mem,
                                                            registry):
        link_session(claude_mem)
        record(registry)
        registry.mark_posted(SID)

        resolve(claude_mem, registry, mark_observed=False)
        assert registry.get(SID).delivery_state is DeliveryState.POSTED

    def test_a_valid_envelope_alone_is_honoured(self, claude_mem, registry):
        link_session(claude_mem)
        found = resolve(claude_mem, registry,
                        metadata={"project_identity": ENVELOPE})
        assert found.origin is Origin.METADATA
        assert found.project_id == "hive-mind"

    def test_envelope_and_decision_agreeing(self, claude_mem, registry):
        link_session(claude_mem)
        record(registry)
        found = resolve(claude_mem, registry,
                        metadata={"project_identity": ENVELOPE})
        assert found.origin is Origin.METADATA_AND_REGISTRY
        assert found.usable


class TestDegradation:
    def test_a_missing_sdk_session(self, claude_mem, registry):
        found = resolve(claude_mem, registry, memory_id="orphan")
        assert found.origin is Origin.MISSING_SDK_SESSION
        assert not found.usable
        assert found.project_id is None

    def test_a_missing_decision(self, claude_mem, registry):
        link_session(claude_mem)
        found = resolve(claude_mem, registry)
        assert found.origin is Origin.MISSING_CAPTURE_IDENTITY
        assert not found.usable

    def test_a_tampered_decision(self, claude_mem, registry):
        link_session(claude_mem)
        record(registry)
        registry._connection.execute(
            "UPDATE capture_identity_decisions SET identity_json=?",
            (json.dumps({"project_id": "tampered", "project_name": "T"}),))
        found = resolve(claude_mem, registry)
        assert found.origin is Origin.INVALID_CAPTURE_IDENTITY
        assert not found.usable

    def test_a_contradiction_is_quarantined_and_refused(self, claude_mem,
                                                        registry):
        link_session(claude_mem)
        record(registry)
        other = {**ENVELOPE, "project_id": "some-other-project"}
        found = resolve(claude_mem, registry,
                        metadata={"project_identity": other})

        assert found.origin is Origin.CONFLICT
        assert not found.usable
        assert found.project_id is None
        assert registry.get(SID).delivery_state is DeliveryState.QUARANTINED

    def test_the_quarantine_survives_the_refusal(self, claude_mem, registry,
                                                 tmp_path):
        """Committed before returning, so a caller that crashes keeps it."""
        link_session(claude_mem)
        record(registry)
        resolve(claude_mem, registry,
                metadata={"project_identity": {**ENVELOPE, "project_id": "x"}})
        registry.close()

        with IdentityStore(tmp_path / "identities.db") as reopened:
            assert reopened.get(SID).delivery_state is DeliveryState.QUARANTINED

    @pytest.mark.parametrize("envelope", [
        None, "not an object", {}, {"project_id": "x"},
        {"project_id": "", "project_name": "n"},
    ])
    def test_an_unusable_envelope_is_ignored_not_trusted(self, claude_mem,
                                                         registry, envelope):
        link_session(claude_mem)
        found = resolve(claude_mem, registry,
                        metadata={"project_identity": envelope})
        assert found.origin is Origin.MISSING_CAPTURE_IDENTITY


class TestTheLabelIsNeverAuthority:
    def test_the_observation_project_is_not_used_when_nothing_is_recorded(
            self, claude_mem, registry):
        link_session(claude_mem, project="preciso-que-verifique")
        add_observation(claude_mem, project="preciso-que-verifique")

        found = resolve(claude_mem, registry)
        assert not found.usable
        assert found.project_id is None, "a label became an identity"

    def test_the_recorded_decision_wins_over_the_stored_label(self, claude_mem,
                                                              registry):
        link_session(claude_mem, project="rotulo-errado")
        record(registry)
        add_observation(claude_mem, project="rotulo-errado")

        found = resolve(claude_mem, registry)
        assert found.project_name == "Hive-Mind"
        assert found.project_id == "hive-mind"


class TestRealWorldShapes:
    def test_two_projects_sharing_a_name_stay_apart(self, claude_mem, registry):
        """Same `project_name`, different ids — the name is not the key."""
        link_session(claude_mem, sid="a", memory_id="mem-a")
        link_session(claude_mem, sid="b", memory_id="mem-b")
        record(registry, sid="a", envelope={**ENVELOPE, "project_id": "local/aaa"})
        record(registry, sid="b", envelope={**ENVELOPE, "project_id": "local/bbb"})

        assert resolve(claude_mem, registry, memory_id="mem-a").project_id == "local/aaa"
        assert resolve(claude_mem, registry, memory_id="mem-b").project_id == "local/bbb"

    def test_two_worktrees_of_one_project_agree(self, claude_mem, registry):
        link_session(claude_mem, sid="root", memory_id="mem-root")
        link_session(claude_mem, sid="tree", memory_id="mem-tree")
        record(registry, sid="root")
        record(registry, sid="tree")

        assert (resolve(claude_mem, registry, memory_id="mem-root").project_id
                == resolve(claude_mem, registry, memory_id="mem-tree").project_id)

    def test_unicode_survives(self, claude_mem, registry):
        link_session(claude_mem, sid="sessão-ção", memory_id="mem-ção")
        record(registry, sid="sessão-ção",
               envelope={**ENVELOPE, "project_name": "Cérebro Ação"})
        found = resolve(claude_mem, registry, memory_id="mem-ção")
        assert found.project_name == "Cérebro Ação"

    def test_the_store_survives_a_restart_between_post_and_lookup(
            self, claude_mem, registry, tmp_path):
        link_session(claude_mem)
        record(registry)
        registry.mark_posted(SID)
        registry.close()

        with IdentityStore(tmp_path / "identities.db") as reopened:
            found = resolve(claude_mem, reopened)
            assert found.project_id == "hive-mind"
            assert reopened.get(SID).delivery_state is DeliveryState.OBSERVED


class TestHealth:
    def test_counters_name_every_state(self, registry):
        record(registry)
        counters = health_counters(registry)
        assert counters["capture_identity_pending"] == 1
        assert set(counters) == {
            "capture_identity_pending", "capture_identity_posted",
            "capture_identity_observed", "capture_identity_bridged",
            "capture_identity_failed", "capture_identity_quarantined"}

    def test_a_clean_registry_is_healthy(self, registry):
        record(registry)
        assert is_healthy(health_counters(registry))

    @pytest.mark.parametrize("counter", [
        "capture_identity_quarantined", "capture_identity_failed",
        "capture_identity_conflicts", "capture_identity_missing_for_observation",
    ])
    def test_an_unresolved_problem_is_not_healthy(self, counter):
        """Green while a conflict sits unresolved is how it stays unresolved."""
        assert not is_healthy({counter: 1})
