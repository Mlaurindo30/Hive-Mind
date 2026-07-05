"""Shared fixtures for the Model Gateway unification test suite.

All tests in `tests/model_gateway/` are hermetic: they use
`monkeypatch.setenv` to inject a controlled env, restore it via the
`clean_env` autouse fixture, and never touch the real `.env` or any
external service. The single exception is `test_openai_compat_real.py`
which hits a real local backend (ollama/lmstudio) and is skipped if
nothing is listening.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Strip the gateway-relevant env vars before each test so the
    previous test can't leak state into the next.

    The legacy `HIVE_*_PROVIDER` / `HIVE_*_MODEL` keys are also cleared
    for every role that `setup-brain.py` knows about. This guards
    against the real-model-gateway test (which calls `load_env()` and
    populates `os.environ` via `os.environ.setdefault` in
    `core/auth.py`) polluting subsequent tests.
    """
    keys = [
        "MODEL_GATEWAY_MODE", "MODEL_GATEWAY_ENABLED",
        "HIVE_FORCE_LEGACY_LLM", "MODEL_GATEWAY_CONFIG",
    ]
    # Roles that setup-brain configures — clear primary/fallback/fallback2
    # for each so the legacy `from_legacy_roles` does not pick up
    # artifacts from previous tests' `load_env()`.
    role_keys = [
        "DREAMER", "GRAPHIFY", "VISION", "SYNTHESIS", "CLAUDE_MEM",
        "WEEKLY_SYNTHESIZER", "MONTHLY_SYNTHESIZER", "YEARLY_SYNTHESIZER",
        "ALIAS_MINER", "SECTOR_CLASSIFIER", "TOPIC_ROUTER",
        "PATTERN_DISTILLER", "CONFLICT_DETECTOR", "SESSION_SUMMARIZER",
        "DAILY_WRITER",
    ]
    for role in role_keys:
        for suffix in ("PROVIDER", "MODEL", "FALLBACK_PROVIDER",
                       "FALLBACK_MODEL", "FALLBACK2_PROVIDER",
                       "FALLBACK2_MODEL"):
            keys.append(f"HIVE_{role}_{suffix}")
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def dreamer_env(monkeypatch):
    """Set up a three-level legacy env for the `dreamer` role."""
    env = {
        "HIVE_DREAMER_PROVIDER": "ollama",
        "HIVE_DREAMER_MODEL": "qwen3:14b",
        "HIVE_DREAMER_FALLBACK_PROVIDER": "openrouter",
        "HIVE_DREAMER_FALLBACK_MODEL": "qwen/qwen3-32b",
        "HIVE_DREAMER_FALLBACK2_PROVIDER": "openai",
        "HIVE_DREAMER_FALLBACK2_MODEL": "gpt-4o-mini",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return env


@pytest.fixture
def all_legacy_providers_env(monkeypatch):
    """Set HIVE_DREAMER_* for every provider in PROVIDERS_CONFIG so the
    test can assert each one resolves via `build_profile_from_provider`.
    """
    from core.auth import PROVIDERS_CONFIG
    seen = set()
    for i, p in enumerate(PROVIDERS_CONFIG.keys()):
        seen.add(p)
        monkeypatch.setenv(f"HIVE_DREAMER_PROVIDER", p)
        monkeypatch.setenv(f"HIVE_DREAMER_MODEL", f"test-model-{i}")
    return list(seen)
