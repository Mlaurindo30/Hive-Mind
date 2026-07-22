"""Build a worker environment instead of inheriting one (D004-R2W).

The first isolated-worker run passed `dict(os.environ)` through. It happened
to be safe — this machine had no credential variables at all — but that is
luck, not design. A host with `OPENROUTER_API_KEY` exported would have handed
it to a test process, and the test would have passed while quietly spending
someone's quota.

So the environment is constructed from an allowlist. Nothing reaches the
worker unless it is named here or passed explicitly, and the credential names
are additionally subtracted afterwards, so a future edit that widens the
allowlist cannot silently re-admit them.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping, Optional

# Variables a process genuinely cannot run without on Windows or POSIX.
BASE_ALLOWLIST = (
    "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "PATHEXT", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "OS", "LANG", "LC_ALL", "TZ", "SHELL", "TERM",
)

# Names that must never reach an isolated worker, even if an allowlist grows.
DENIED_EXACT = frozenset({
    "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "MISTRAL_API_KEY", "COHERE_API_KEY", "AZURE_OPENAI_API_KEY",
    "GROQ_API_KEY", "DEEPSEEK_API_KEY", "TOGETHER_API_KEY",
    "HUGGINGFACE_API_KEY", "HF_TOKEN", "REPLICATE_API_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_MEM_OPENROUTER_API_KEY",
    "CLAUDE_MEM_GEMINI_API_KEY", "CLAUDE_MEM_CHROMA_API_KEY",
    "CLAUDE_MEM_CLOUD_SYNC_TOKEN", "GITHUB_TOKEN", "GH_TOKEN",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
})

# And anything that merely looks like one. Belt and braces, because the list
# above can only name providers that existed when it was written.
DENIED_PATTERN = re.compile(
    r"(API_KEY|APIKEY|_TOKEN|TOKEN_|SECRET|PASSWORD|PASSWD|CREDENTIAL|"
    r"PRIVATE_KEY|ACCESS_KEY|AUTH)",
    re.IGNORECASE,
)


def is_denied(name: str) -> bool:
    """Whether a variable must be kept out of an isolated worker."""
    return name.upper() in DENIED_EXACT or bool(DENIED_PATTERN.search(name))


def isolated_home(base: Path) -> dict[str, str]:
    """Point every per-user directory a process might read at a temporary one.

    Without this the worker still finds the real `~/.claude`, which is where
    its SDK looks for authentication. Redirecting HOME alone is not enough on
    Windows, where USERPROFILE, APPDATA and LOCALAPPDATA are consulted
    independently.
    """
    base = Path(base)
    home = base / "home"
    appdata = home / "AppData" / "Roaming"
    local = home / "AppData" / "Local"
    temp = base / "temp"
    for path in (home, appdata, local, temp):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "HOMEDRIVE": home.drive or "",
        "HOMEPATH": str(home),
        "APPDATA": str(appdata),
        "LOCALAPPDATA": str(local),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "TEMP": str(temp),
        "TMP": str(temp),
        "TMPDIR": str(temp),
        "CLAUDE_CONFIG_DIR": str(home / ".claude"),
    }


def build_environment(
    *,
    base: Path,
    extra: Optional[Mapping[str, str]] = None,
    allowlist: tuple[str, ...] = BASE_ALLOWLIST,
    source: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """The environment an isolated worker runs with.

    `extra` is for the test's own settings (data dir, port). It is applied
    after the allowlist, and is still filtered — a caller that tries to pass a
    credential through this door does not get one.
    """
    source = os.environ if source is None else source
    env: dict[str, str] = {}
    for name in allowlist:
        value = source.get(name)
        if value is not None and not is_denied(name):
            env[name] = value

    env.update(isolated_home(base))
    for name, value in (extra or {}).items():
        if is_denied(name):
            continue
        env[name] = value

    # Final subtraction: whatever route a name took, it does not survive this.
    return {name: value for name, value in env.items() if not is_denied(name)}


def leaked_names(env: Mapping[str, str]) -> list[str]:
    """Credential-shaped names present in an environment. For assertions."""
    return sorted(name for name in env if is_denied(name))
