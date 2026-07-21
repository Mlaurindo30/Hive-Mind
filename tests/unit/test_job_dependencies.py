"""D008-R1V — job ordering must be a declared dependency, not a clock gap.

The Linux units encode "the bridge feeds the dream" as 02:45 vs 03:00. That is
not a contract: a slow bridge, a reboot between the two, or a misfire silently
breaks it. The manifest must declare the dependency so the scheduler can
enforce it once it starts firing jobs (F7).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hive_mind.daemon.manifest import RuntimeManifest, load_manifest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "runtime.yaml"


def _job_model(**overrides) -> dict:
    base = {
        "name": "j",
        "command": ["python", "x.py"],
        "schedule": {"type": "cron", "expression": "0 3 * * *"},
    }
    base.update(overrides)
    return base


def _manifest(jobs) -> dict:
    return {"schema_version": 3, "profile": "local-min", "jobs": jobs}


class TestSchemaSupportsJobDependencies:
    def test_job_accepts_depends_on(self):
        manifest = RuntimeManifest.model_validate(
            _manifest([
                _job_model(name="a"),
                _job_model(name="b", depends_on=["a"]),
            ])
        )
        b = next(j for j in manifest.jobs if j.name == "b")
        assert b.depends_on == ["a"]

    def test_job_accepts_dependency_policy(self):
        manifest = RuntimeManifest.model_validate(
            _manifest([
                _job_model(name="a"),
                _job_model(
                    name="b",
                    depends_on=["a"],
                    dependency_policy={"require_success_since_last_run": True},
                ),
            ])
        )
        b = next(j for j in manifest.jobs if j.name == "b")
        assert b.dependency_policy.require_success_since_last_run is True

    def test_default_is_no_dependency(self):
        manifest = RuntimeManifest.model_validate(_manifest([_job_model()]))
        assert manifest.jobs[0].depends_on == []

    def test_unknown_job_dependency_is_rejected(self):
        with pytest.raises(ValidationError):
            RuntimeManifest.model_validate(
                _manifest([_job_model(name="b", depends_on=["ghost"])])
            )

    def test_job_cannot_depend_on_itself(self):
        with pytest.raises(ValidationError):
            RuntimeManifest.model_validate(
                _manifest([_job_model(name="a", depends_on=["a"])])
            )

    def test_dependency_cycle_is_rejected(self):
        with pytest.raises(ValidationError):
            RuntimeManifest.model_validate(
                _manifest([
                    _job_model(name="a", depends_on=["b"]),
                    _job_model(name="b", depends_on=["a"]),
                ])
            )


class TestShippedManifestDeclaresTheOrdering:
    def test_dream_cycle_declares_its_dependency_on_the_bridge(self):
        manifest = load_manifest(MANIFEST)
        dream = next(j for j in manifest.jobs if j.name == "dream-cycle")
        assert "claude-mem-bridge" in dream.depends_on, (
            "the dream cycle must declare that the bridge feeds it, not rely "
            "on a 15-minute clock gap"
        )

    def test_the_declared_dependency_also_holds_on_the_clock(self):
        """Belt and braces: the declaration must not contradict the schedule."""
        manifest = load_manifest(MANIFEST)
        jobs = {j.name: j for j in manifest.jobs}
        dream = jobs["dream-cycle"]
        for dep in dream.depends_on:
            expr = jobs[dep].schedule.expression
            if not expr:
                continue
            minute, hour = expr.split()[0], expr.split()[1]
            dep_minutes = int(hour) * 60 + int(minute)
            d_min, d_hour = (
                dream.schedule.expression.split()[0],
                dream.schedule.expression.split()[1],
            )
            assert dep_minutes < int(d_hour) * 60 + int(d_min)


class TestNoDeadJobsInTheManifest:
    def test_every_job_command_points_at_existing_code(self):
        """A job whose script does not exist would fail on a clean install."""
        manifest = load_manifest(MANIFEST)
        missing = []
        for job in manifest.jobs:
            for part in job.command:
                if part.endswith(".py") and not (ROOT / part).is_file():
                    missing.append(f"{job.name} -> {part}")
        assert missing == [], f"manifest schedules non-existent scripts: {missing}"
