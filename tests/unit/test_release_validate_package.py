from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "release" / "validate_package.py"


def test_release_validator_accepts_the_repository_version_contract():
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--source-root", str(ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "version contract OK" in result.stdout
