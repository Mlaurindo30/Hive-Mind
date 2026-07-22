"""Where the register-mcp.sh unit tests went (D009-R6).

This file used to drive `register-mcp.sh` directly, under a symlinked PATH,
and assert on what it wrote: that only `sinapse-memory` is registered, that
VS Code gets `servers` with `type: stdio`, that a third-party entry survives
the merge. Those were tests of the script's internals, and the script no
longer has internals — it is a wrapper.

The behaviour is still tested, in the places that now own it:

| what it asserted | where it is asserted now |
|---|---|
| only `sinapse-memory`, legacy raw backends removed | `tests/unit/test_agents_mcp_config.py` and, end to end, `tests/integration/test_registration_through_wrappers.py::test_apply_registers_and_keeps_third_parties` |
| VS Code uses `servers` + `type: stdio` | `tests/unit/test_agents_register.py::test_vscode_uses_servers_root_key_and_stdio_type` and `...::test_vscode_root_key_is_respected` |
| third-party entries survive the merge | `tests/unit/test_agents_mcp_config.py` and `...::test_apply_registers_and_keeps_third_parties` |
| the script runs and exits 0 | `tests/unit/test_registration_wrappers.py` (forwarding, streams, exit codes) |

One behaviour is deliberately *not* carried over: the old script shelled out
to the `codex` CLI (`codex mcp add ...`). The native path writes
`~/.codex/config.toml` directly (D009-R4), which is the file that CLI edits.
Depending on an agent's own CLI made registration fail whenever that CLI
changed its argument grammar — which is exactly what broke
`test_register_mcp_check` before this delivery.

The file is kept as this note rather than deleted, so the mapping is visible
where someone would look for the missing tests.
"""
