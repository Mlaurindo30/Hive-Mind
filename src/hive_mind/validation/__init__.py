"""Validation harnesses for the Hive-Mind pipeline (D004-R1).

Native home for the multiagent canary previously living in
`scripts/health/canary_multiagent_runner.py`.

**What this validates, precisely:** the wiring of
`attach_project_identity -> Claude Mem row -> bridge -> workspace_id`,
driven by a *synthetic* session against *temporary* databases. It is a
sandboxed pipeline check, not proof that a real provider was captured.
Real capture from a live provider source is a separate, operational gate.
"""

from hive_mind.validation.models import CanaryResult, CanaryStatus, CanaryReport

__all__ = ["CanaryResult", "CanaryStatus", "CanaryReport"]
