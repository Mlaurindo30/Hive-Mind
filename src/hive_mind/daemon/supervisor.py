"""Shadow supervisor (spec F3 / Anexo D.4).

`ShadowSupervisor` observes the manifest and reports what a managed daemon
*would* do, without doing any of it. It is absolutely passive:

  - it never starts a process;
  - it never writes `runtime.yaml`;
  - it writes exactly one state file, `state_dir/services.shadow.json`;
  - it never triggers a job or performs a cutover.

Readiness is computed by an injected `prober` (a read-only probe of the
legacy service). With no prober, readiness is reported as ``unknown`` rather
than assumed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Optional

from hive_mind.daemon.manifest import RuntimeManifest, ServiceSpec

Prober = Callable[[ServiceSpec], bool]

SHADOW_STATE_FILENAME = "services.shadow.json"


class ShadowSupervisor:
    """Passive observer of the runtime manifest."""

    ownership = "shadow"

    def __init__(self, manifest: RuntimeManifest, state_dir: Path | str) -> None:
        self.manifest = manifest
        self.state_dir = Path(state_dir)

    def _active_services(self) -> list[ServiceSpec]:
        profile = self.manifest.profile
        services = [
            s
            for s in self.manifest.services
            if s.enabled and profile in s.profiles
        ]
        return sorted(services, key=lambda s: (s.startup_order, s.name))

    @staticmethod
    def _readiness(spec: ServiceSpec, prober: Optional[Prober]) -> str:
        if prober is None:
            return "unknown"
        try:
            return "ready" if prober(spec) else "not_ready"
        except Exception:  # noqa: BLE001 - a failed probe is "not ready", never fatal
            return "not_ready"

    def observe(self, prober: Optional[Prober] = None) -> dict:
        """Compute the shadow view and persist it. Returns the summary."""
        services = []
        required_ready = True
        for spec in self._active_services():
            readiness = self._readiness(spec, prober)
            record = {
                "name": spec.name,
                "ownership": spec.ownership,
                "required": spec.required,
                "dependencies": list(spec.dependencies),
                "startup_order": spec.startup_order,
                "category": spec.category,
                "readiness": readiness,
                "readiness_probe": spec.readiness.type if spec.readiness else None,
                "would_start": True,
            }
            services.append(record)
            if spec.required and readiness != "ready":
                required_ready = False

        summary = {
            "mode": "shadow",
            "profile": self.manifest.profile,
            "service_count": len(services),
            "ready": required_ready,
            "services": services,
        }
        self._write_shadow_state(summary)
        return summary

    def _write_shadow_state(self, summary: dict) -> None:
        """Atomic write of the single shadow state file. No other file touched."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        target = self.state_dir / SHADOW_STATE_FILENAME
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, target)
