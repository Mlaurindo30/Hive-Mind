"""R1.2 — RTK hook compile guard.

Spec: specs/post-audit-stabilization.md R1.2.

Fails when the audit is opened; passes after the SyntaxError is fixed.
Body MUST be a `py_compile.compile(..., doraise=True)` sweep over every
`*.py` under `integrations/rtk/hooks`.
"""

from __future__ import annotations

import py_compile
from pathlib import Path


HOOKS_ROOT = Path("integrations/rtk/hooks")


def test_rtk_hooks_compile():
    assert HOOKS_ROOT.exists(), f"hooks root missing: {HOOKS_ROOT}"
    files = sorted(HOOKS_ROOT.rglob("*.py"))
    assert files, f"no Python files under {HOOKS_ROOT}"
    for file in files:
        py_compile.compile(str(file), doraise=True)
