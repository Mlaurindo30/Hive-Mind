# Clean Install Retrieval Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Ensure a clean Windows local-full install can write and retrieve a hyphenated decision through the unified query path; local Ollama is provisioned only for explicitly requested local tests.

**Architecture:** Normalize FTS input at the SQLite boundary, make the retrieval router preserve a fast UMC/filesystem result when slower federated backends time out, and materialize a non-empty graph from indexed vault neurons when AST Graphify finds no code files. Ollama model pulls are isolated to a test-only switch.

**Tech Stack:** Python 3.12, SQLite FTS5/sqlite-vec, Ollama, PowerShell, pytest, Docker services.

## Global Constraints

- The default clean-install profile does not require Ollama or pull local models.`r`n- Ollama model provisioning is enabled only by an explicit local-test switch.
- Do not alter or delete existing vault notes, UMC data, or `.env` secrets.
- User query strings are data, never raw FTS5 syntax.
- A slow optional backend must not erase a successful UMC/filesystem result.
- Graph output must always use `nodes` and `links` lists.

### Task 1: Literal FTS5 query contract

**Files:**
- Modify: `core/database.py`
- Modify: `tests/unit/test_database.py`

- [ ] Add a failing test that indexes `AUDIT-E2E-test`, calls `query_hybrid`, and asserts it returns `n1` without an FTS error.
- [ ] Run `python -m pytest tests/unit/test_database.py::test_query_hybrid_treats_hyphenated_terms_as_literal_fts_text -q`; expect failure with `no such column: E2E`.
- [ ] Add `_fts_literal_query(text)` which double-quotes escaped text and pass it as the FTS MATCH parameter.
- [ ] Re-run the focused test; expect pass.

### Task 2: Retrieval timeout fallback

**Files:**
- Modify: `core/retrieval/router.py`
- Modify: `tests/unit/test_retrieval_router.py` or the existing router test module

- [ ] Add a failing test where UMC produces a citation before an optional backend times out; assert the response retains the citation and reports the timeout only in `retrieval_path`.
- [ ] Run the focused test; expect failure because context fusion currently returns a miss.
- [ ] Make the router return usable UMC/filesystem results without waiting for exhausted optional backends.
- [ ] Re-run the focused test; expect pass.

### Task 3: Vault graph fallback

**Files:**
- Create: `scripts/graph/materialize_vault_graph.py`
- Modify: `scripts/graph/build-graph.ps1`
- Test: `tests/unit/test_materialize_vault_graph.py`

- [ ] Add a failing fixture test with one Markdown neuron; assert generated graph contains one node with id, label, source_file and `links` list.
- [ ] Run the focused test; expect missing module.
- [ ] Materialize graph nodes from Markdown files whenever Graphify AST leaves `nodes` empty; write atomically to `graph.json`.
- [ ] Run focused test and `build-graph.ps1`; expect valid non-empty graph when vault contains notes.

### Task 4: Clean-install acceptance test and Superpowers ledger

**Files:**
- Modify: `tests/e2e/test_decision_write_index_query.py`
- Modify: `.superpowers/sdd/progress.md`

- [ ] Keep the test portable via `sys.executable`, then assert a hyphenated decision is cited through the CLI query path.
- [ ] Run the focused E2E after Tasks 1–3; expect pass.
- [ ] Replace the stale Universal Provider Capture ledger header with the active clean-install/retrieval hardening plan and record completed bootstrap work without inventing commits.
- [ ] Run `tests/run_all.ps1` and `sinapse-write.py health`; expect green tests and seven healthy backends.
