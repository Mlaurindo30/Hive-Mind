"""Structured results for validation runs (no I/O, no side effects)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class CanaryStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class CanaryResult:
    provider: str
    status: CanaryStatus
    project_id: Optional[str] = None
    inserted: int = 0
    idempotent: Optional[bool] = None
    reason: Optional[str] = None
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status is CanaryStatus.PASSED

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class CanaryReport:
    results: tuple[CanaryResult, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> tuple[CanaryResult, ...]:
        return tuple(r for r in self.results if r.status is CanaryStatus.PASSED)

    @property
    def failed(self) -> tuple[CanaryResult, ...]:
        return tuple(
            r for r in self.results if r.status in (CanaryStatus.FAILED, CanaryStatus.ERROR)
        )

    @property
    def ok(self) -> bool:
        return bool(self.results) and not self.failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "total": len(self.results),
            "passed": len(self.passed),
            "failed": len(self.failed),
            "results": [r.to_dict() for r in self.results],
        }
