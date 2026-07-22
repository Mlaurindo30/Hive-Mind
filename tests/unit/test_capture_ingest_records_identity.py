"""M14 — the ingest contract: decide, record, then post.

The order is the whole point. The worker drops our metadata, so a decision
recorded *after* delivery would be missing for exactly the events that crashed
in between — the ones whose identity nobody could reconstruct afterwards.

These use a fake transport because they are about ordering and refusal, not
about delivery. The operational proof runs the real worker.
"""
from __future__ import annotations

import pytest

from hive_mind.capture.identity_store import (
    DeliveryState,
    IdentityConflict,
    IdentityStore,
)
from hive_mind.capture.ingest import ingest
from hive_mind.projects.identity import ProjectIdentityResolver

SID = "session-under-test"


@pytest.fixture(scope="module")
def resolver():
    return ProjectIdentityResolver()


@pytest.fixture
def registry(tmp_path):
    with IdentityStore(tmp_path / "identities.db") as opened:
        yield opened


@pytest.fixture
def seen(tmp_path):
    from hive_mind.capture import engine

    store = engine.SeenStore(tmp_path / "seen.db")
    yield store
    store.close()


def _session(root, sid=SID, raw_label="rotulo-livre"):
    return {
        "sid": sid,
        "cwd": str(root),
        "surface": "cli",
        "prompt": "do the thing",
        "project": raw_label,
        "turns": [{"tool_name": "Message", "tool_input": {},
                   "tool_response": "done"}],
        "last": "done",
    }


@pytest.fixture
def project(tmp_path):
    import subprocess

    path = tmp_path / "acme"
    path.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"),
                 ("config", "user.name", "t")):
        subprocess.run(["git", "-C", str(path), *args], check=True,
                       capture_output=True)
    (path / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"],
                   check=True, capture_output=True)
    return path


class TestTheDecisionIsWrittenBeforeThePost:
    def test_the_store_already_holds_the_decision_when_the_post_runs(
            self, monkeypatch, registry, seen, project, resolver):
        """Asserted from inside the transport, which is the only honest place.

        Checking afterwards cannot tell the two orders apart: both end with a
        decision and a delivery. What distinguishes them is what the store
        knows at the moment the post happens.
        """
        from hive_mind.capture import engine

        seen_during_post = {}

        def spy(path, payload):
            decision = registry.get(SID)
            seen_during_post["state"] = decision.delivery_state if decision else None
            seen_during_post["project_id"] = decision.project_id if decision else None
            return {"stored": True}

        monkeypatch.setattr(engine, "_post", spy)
        ingest("codex", _session(project), seen, resolver=resolver,
               identity_store=registry)

        assert seen_during_post["state"] is DeliveryState.PENDING
        # A local repository with no remote is identified by its git common
        # dir, not by its directory name — the name is `acme`, the id is not.
        assert seen_during_post["project_id"].startswith("local/")

    def test_nothing_is_posted_when_the_decision_cannot_be_recorded(
            self, monkeypatch, registry, seen, project, resolver):
        from hive_mind.capture import engine

        posted = []
        monkeypatch.setattr(engine, "_post",
                            lambda p, payload: posted.append(p) or {"stored": True})

        # A session already decided as something else: recording refuses.
        registry.record_pending(
            content_session_id=SID, provider="codex", surface="cli",
            project_id="some-other", project_name="Other",
            identity={"project_id": "some-other", "project_name": "Other"},
        )
        conflicts = []
        emitted = ingest("codex", _session(project), seen, resolver=resolver,
                         identity_store=registry, on_conflict=conflicts.append)

        assert emitted == 0
        assert posted == [], "an event was delivered with no recoverable identity"
        assert conflicts and isinstance(conflicts[0], IdentityConflict)

    def test_a_conflict_leaves_the_session_quarantined(
            self, monkeypatch, registry, seen, project, resolver):
        from hive_mind.capture import engine

        monkeypatch.setattr(engine, "_post", lambda p, payload: {"stored": True})
        registry.record_pending(
            content_session_id=SID, provider="codex", surface="cli",
            project_id="some-other", project_name="Other",
            identity={"project_id": "some-other", "project_name": "Other"},
        )
        ingest("codex", _session(project), seen, resolver=resolver,
               identity_store=registry, on_conflict=lambda _: None)
        assert registry.get(SID).delivery_state is DeliveryState.QUARANTINED


class TestAfterThePost:
    def test_an_accepted_post_marks_posted(self, monkeypatch, registry, seen,
                                           project, resolver):
        from hive_mind.capture import engine

        monkeypatch.setattr(engine, "_post", lambda p, payload: {"stored": True})
        ingest("codex", _session(project), seen, resolver=resolver,
               identity_store=registry)
        assert registry.get(SID).delivery_state is DeliveryState.POSTED

    def test_a_transport_failure_marks_failed_and_keeps_the_decision(
            self, monkeypatch, registry, seen, project, resolver):
        from hive_mind.capture import engine

        def explode(path, payload):
            raise ConnectionError("worker offline")

        monkeypatch.setattr(engine, "_post", explode)
        with pytest.raises(ConnectionError):
            ingest("codex", _session(project), seen, resolver=resolver,
                   identity_store=registry)

        decision = registry.get(SID)
        assert decision is not None, "the decision was lost on failure"
        assert decision.delivery_state is DeliveryState.FAILED
        assert decision.project_name == "acme"

    def test_a_retry_reuses_the_same_session_and_decision(
            self, monkeypatch, registry, seen, project, resolver):
        from hive_mind.capture import engine

        def explode(path, payload):
            raise ConnectionError("worker offline")

        monkeypatch.setattr(engine, "_post", explode)
        with pytest.raises(ConnectionError):
            ingest("codex", _session(project), seen, resolver=resolver,
                   identity_store=registry)
        first = registry.get(SID)

        monkeypatch.setattr(engine, "_post", lambda p, payload: {"stored": True})
        ingest("codex", _session(project), seen, resolver=resolver,
               identity_store=registry)
        retried = registry.get(SID)

        assert retried.created_at == first.created_at, "a second decision was made"
        assert retried.delivery_state is DeliveryState.POSTED


class TestWhatIsRecorded:
    def test_the_canonical_identity_is_what_is_stored(self, monkeypatch, registry,
                                                      seen, project, resolver):
        from hive_mind.capture import engine

        monkeypatch.setattr(engine, "_post", lambda p, payload: {"stored": True})
        ingest("codex", _session(project), seen, resolver=resolver,
               identity_store=registry)

        decision = registry.get(SID)
        assert decision.project_name == "acme"
        # The id is derived from the repository, never from the label or the
        # directory name; only the *name* is human-facing.
        assert decision.project_id.startswith("local/")
        assert decision.project_id != decision.project_name

    def test_the_raw_label_is_recorded_only_as_audit(self, monkeypatch, registry,
                                                    seen, project, resolver):
        from hive_mind.capture import engine

        monkeypatch.setattr(engine, "_post", lambda p, payload: {"stored": True})
        ingest("codex", _session(project, raw_label="preciso-que-verifique"),
               seen, resolver=resolver, identity_store=registry)

        decision = registry.get(SID)
        assert decision.raw_project_label == "preciso-que-verifique"
        assert decision.project_id != "preciso-que-verifique"
        assert decision.project_name != "preciso-que-verifique"

    def test_the_key_is_the_session_id_the_worker_preserves(
            self, monkeypatch, registry, seen, project, resolver):
        """M14-A measured `contentSessionId` surviving; it is `sess["sid"]`."""
        from hive_mind.capture import engine

        posted = {}

        def spy(path, payload):
            posted.setdefault("id", payload.get("contentSessionId"))
            return {"stored": True}

        monkeypatch.setattr(engine, "_post", spy)
        ingest("codex", _session(project), seen, resolver=resolver,
               identity_store=registry)

        assert posted["id"] == SID
        assert registry.get(SID) is not None


class TestDeliveryIsNotTheSameAsNovelty:
    """`emit` counts new content; POSTED means the session was delivered.

    A real Codex session in D004-M emitted zero — every record already seen —
    and the observation still arrived. Gating `mark_posted` on the count left
    that session PENDING forever, so the bridge could never advance it.
    """

    def test_a_session_with_no_new_content_is_still_marked_posted(
            self, monkeypatch, registry, seen, project, resolver):
        from hive_mind.capture import engine

        monkeypatch.setattr(engine, "_post", lambda p, payload: {"stored": True})
        monkeypatch.setattr(engine, "emit", lambda *a, **k: 0)

        emitted = ingest("codex", _session(project), seen, resolver=resolver,
                         identity_store=registry)
        assert emitted == 0
        assert registry.get(SID).delivery_state is DeliveryState.POSTED

    def test_it_can_then_reach_bridged(self, monkeypatch, registry, seen,
                                       project, resolver):
        from hive_mind.capture import engine

        monkeypatch.setattr(engine, "_post", lambda p, payload: {"stored": True})
        monkeypatch.setattr(engine, "emit", lambda *a, **k: 0)
        ingest("codex", _session(project), seen, resolver=resolver,
               identity_store=registry)

        registry.mark_observed(SID)
        assert registry.mark_bridged(SID).delivery_state is DeliveryState.BRIDGED
