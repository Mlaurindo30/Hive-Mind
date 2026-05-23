# Gotchas

Things that have gone wrong and why. Lessons learned the hard way.

## Hermes Agent

- **claude-mem worker offline (silent failure):** Worker not running = agent operates without external memory, no logs or alerts. Verify: `curl -s http://127.0.0.1:37700/health`
- **graph.json missing (silent failure):** sinapse-memory plugin returns None without logging. Agent operates without structural context. Verify: `ls cerebro/graphify-out/graph.json`
- **Plugin offline = zero context:** If sinapse-memory plugin is disabled, SOUL.md conventions still load (embedded in system prompt). Vault context is lost. Verify: `hermes plugins list | grep sinapse`

## Install

- **Never pip/npm install external tools directly.** Always clone repo and build from source (`pip install -e .`, `npm install && npm run build`). Graphify, claude-mem, RTK are all in-repo.
- **Graphify output location:** `graphify update cerebro/` outputs to `cerebro/graphify-out/`, NOT to `graphify/graphify-out/`. MCP server must point to correct path.
