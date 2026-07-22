"""The legacy registrar command line, understood in one place (D009-R6).

`register-mcp.ps1` and `register-mcp.sh` grew their own option vocabulary over
time. Reducing them to wrappers means the vocabulary has to survive somewhere,
because real callers still speak it: `install.ps1`, `install.sh`,
`npm/bin/hive-mind.js`, the integration test, and the documented
`--check` contract in `specs/post-audit-stabilization.md`.

It survives here, not in the wrappers. A wrapper that translated its own
arguments would be reinterpreting them — which is exactly the product logic
D009-R6 removes. The wrapper forwards bytes; this module decides what they mean.

Two legacy behaviours deserve naming, because a silent pass-through would
change them:

- **the legacy scripts write by default.** `hive-mind agents register` is
  dry-run by default, on purpose. So the callers that relied on the old
  default are updated to say `--apply` explicitly, rather than the wrapper
  inserting it behind their back.
- **the legacy scripts inject instructions by default.** The native default
  is not to. `--no-instructions` and `HIVE_SKIP_PROMPT` are honoured, and the
  callers that want injection ask for it.
"""
from __future__ import annotations

import os

# The legacy scripts each carried this list. It must match the registry, or a
# provider would be registrable by one path and rejected by the other.
LEGACY_AGENT_KEYS = (
    "claude", "codex", "gemini", "qwen", "kimi", "kiro", "kilo", "roo",
    "vscode", "cursor", "opencode", "openclaw", "swarmclaw",
)

# The legacy scripts exit 2 for an unknown agent key. Callers branch on it.
EX_UNKNOWN_AGENT = 2


def instructions_requested(args) -> bool:
    """Resolve the instruction flags into one answer.

    Precedence, most explicit first: `--instructions`, then
    `--no-instructions`, then `HIVE_SKIP_PROMPT` (which the shell script read
    from the environment), then the native default of not touching prompt
    files.
    """
    if getattr(args, "instructions", False):
        return True
    if getattr(args, "no_instructions", False):
        return False
    if os.environ.get("HIVE_SKIP_PROMPT"):
        return False
    return False


def selected_provider(args) -> "str | None":
    """The single provider a caller asked for, in any spelling it may use.

    `--only`, `--self` and `--agent` are the same option under three names;
    `-CodexOnly` / `-ClaudeOnly` are the two PowerShell-only shortcuts; and a
    bare agent name was accepted positionally.
    """
    if getattr(args, "codex_only", False):
        return "codex"
    if getattr(args, "claude_only", False):
        return "claude"
    return getattr(args, "only", None) or getattr(args, "provider", None)


def validate_provider(provider: "str | None") -> "str | None":
    """Return an error message for an unknown key, or None when it is fine."""
    if provider is None or provider in LEGACY_AGENT_KEYS:
        return None
    return (
        f"unknown agent: {provider!r}\n"
        f"  valid: {' '.join(LEGACY_AGENT_KEYS)}"
    )
