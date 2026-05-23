# Graph Report - cerebro  (2026-05-23)

## Corpus Check
- 130 files · ~69,871 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1131 nodes · 1199 edges · 100 communities (93 shown, 7 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a6106280`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]

## God Nodes (most connected - your core abstractions)
1. `compilerOptions` - 15 edges
2. `Sinapse Agent — Vault (CLAUDE.md)` - 15 edges
3. `Obsidian Bases Skill` - 14 edges
4. `Obsidian Flavored Markdown Skill` - 14 edges
5. `Functions Reference` - 13 edges
6. `Workflow` - 13 edges
7. `Sinapse Agent — Vault (AGENTS.md)` - 12 edges
8. `JSON Canvas Skill` - 11 edges
9. `debug()` - 10 edges
10. `Session Workflow` - 10 edges

## Surprising Connections (you probably didn't know these)
- `composeWorkerInvocations()` --calls--> `buildQmdCommand()`  [EXTRACTED]
  .claude/scripts/lib/qmd-refresh.ts → .claude/scripts/lib/qmd.ts
- `extractFrontmatterField()` --calls--> `escapeRegex()`  [EXTRACTED]
  .claude/scripts/lib/session-start.ts → .claude/scripts/lib/regex.ts
- `northStar()` --calls--> `take()`  [EXTRACTED]
  .claude/scripts/session-start.ts → .claude/scripts/lib/session-start.ts
- `recentChanges()` --calls--> `formatRecentChanges()`  [EXTRACTED]
  .claude/scripts/session-start.ts → .claude/scripts/lib/session-start.ts
- `listMarkdownSources()` --calls--> `isMarkdownFilename()`  [EXTRACTED]
  .claude/scripts/session-start.ts → .claude/scripts/lib/session-start.ts

## Communities (100 total, 7 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (37): isMainModule(), backupDir, dest, formatTimestamp(), HookInput, input, listBackups(), pruneBackups() (+29 more)

### Community 1 - "Community 1"
Cohesion: 0.04
Nodes (48): Cards View, code:yaml (# Global filters apply to ALL views in the base), code:yaml (filters:), code:yaml (filters:), code:yaml (filters:), code:markdown (![[MyBase.base]]), code:yaml (# WRONG - colon in unquoted string), code:yaml (# WRONG - double quotes inside double quotes) (+40 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (39): collectOpenTasks(), extractFrontmatterField(), findFrontmatterEnd(), formatActiveWork(), formatBrainIndex(), formatDateHeader(), formatRecentChanges(), hasBrainContent() (+31 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (38): frontmatter_required, 1-1, global, incident, person, team, work-note, infrastructure (+30 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (32): warn(), buildCollectionAddArgs(), isContextRemoveBenign(), makeCollectionAddBenignMatcher(), IGNORE_BLOCK_RE, qmdConfigPath(), readObsidianIgnore(), translateToGlob() (+24 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (31): anyWordMatch(), classify(), compileMatcher(), SIGNAL_MATCHERS, Signal, SIGNALS, CJK_CASES, CJKCase (+23 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (32): Agent Guidelines, code:bash (ls graphify-out/graph.json                          # graph ), code:bash (obsidian read file="Note Name"                    # Read a n), Creating Notes, Custom Slash Commands, Decision Records, Don't Mix Contexts, Ending a Substantial Session (+24 more)

### Community 7 - "Community 7"
Cohesion: 0.07
Nodes (28): Callouts, code:markdown ([[Note Name]]                          Link to note), code:markdown (Inline: $e^{i\pi} + 1 = 0$), code:`markdown, code:block12, code:markdown (Text with a footnote[^1].), code:`markdown (---), code:markdown (This paragraph can be linked to. ^my-block-id) (+20 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (27): 1. Create a New Canvas, 2. Add a Node to an Existing Canvas, 3. Connect Two Nodes, 4. Edit an Existing Canvas, code:json ({), code:json ({), code:json ({), code:json ({) (+19 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (26): 0. Idioma, 10. Frontmatter obrigatório, 1. O que é este vault, 2. Estrutura do vault, 3. Como cada agente usa este vault, 4. Hooks (5 lifecycle hooks), 5. Comandos (18 slash commands), 6. Subagentes (9 agentes especializados) (+18 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (20): debug(), composeWorkerInvocations(), isDebounced(), QmdInvocation, readSentinelMtime(), resolveVaultRoot(), shouldRefreshForPath(), SKIP_SEGMENTS (+12 more)

### Community 11 - "Community 11"
Cohesion: 0.09
Nodes (21): Classification Heuristics, code:yaml (---), Execution Process, Important, Mode A: Classification, Mode B: Execution, Modes, Step 1: Build Context (+13 more)

### Community 12 - "Community 12"
Cohesion: 0.10
Nodes (20): Additional developer commands, code:bash (obsidian create name="My Note" content="Hello world"), code:bash (obsidian dev:css selector=".workspace-leaf" prop=background-), code:bash (obsidian dev:mobile on), code:bash (obsidian create name="My Note" silent overwrite), code:bash (obsidian vault="My Vault" search query="test"), code:bash (obsidian read file="My Note"), code:bash (obsidian plugin:reload id=my-plugin) (+12 more)

### Community 13 - "Community 13"
Cohesion: 0.11
Nodes (18): 10. Check for Mixed Context, 11. Check Claude Config, 12. Fix and Report, 1. Check Folder Structure, 2. Check Indexes, 3. Check Frontmatter Completeness, 4. Check for Duplicate Tags, 5. Check Status/Folder Alignment (+10 more)

### Community 14 - "Community 14"
Cohesion: 0.11
Nodes (17): code:markdown (![[Note Name]]), code:markdown (![[image.png]]), code:markdown (![Alt text](https://example.com/image.png)), code:markdown (![[audio.mp3]]), code:markdown (![[document.pdf]]), code:markdown (![[Note#^list-id]]), code:markdown (- Item 1), code:`markdown (+9 more)

### Community 15 - "Community 15"
Cohesion: 0.11
Nodes (17): compilerOptions, allowImportingTsExtensions, exactOptionalPropertyTypes, isolatedModules, lib, module, moduleResolution, noEmit (+9 more)

### Community 16 - "Community 16"
Cohesion: 0.19
Nodes (15): buildLaunchCommand(), readManifestRaw(), readQmdIndex(), require, resolveIndexSqlitePath(), resolveQmdEntry(), resolveVaultRoot(), runAsMcp() (+7 more)

### Community 17 - "Community 17"
Cohesion: 0.15
Nodes (12): buildQmdCommand(), require, resolveQmdEntry(), invocations, MANIFEST_PATH, qmdIndex, result, SCRIPT_DIR (+4 more)

### Community 18 - "Community 18"
Cohesion: 0.12
Nodes (15): 1. Gather Raw Data, 2. Identify People, 3. Build the Timeline, 4. Create the Work Note, 5. Create/Update People Notes, 6. Update Indexes, 7. Prepare Incident Report Draft (if applicable), 8. Offer Next Steps (+7 more)

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (15): 1. Validate & Detect, 2. Inventory & Classify, 3. Present Migration Plan, 4. Execute Migration, 5. Validate, code:block1 (/om-vault-upgrade <path-to-source-vault>), code:block2 (Source: ~/my-vault (obsidian-mind v2)), code:block3 (| # | Source | Target | Action | Transforms |) (+7 more)

### Community 20 - "Community 20"
Cohesion: 0.12
Nodes (15): Any Type Functions, code:yaml (# CORRECT: Calculate days between dates), code:yaml (# Duration units: y/year/years, M/month/months, d/day/days,), Date Arithmetic, Date Functions & Fields, Duration Type, File Functions, Functions Reference (+7 more)

### Community 21 - "Community 21"
Cohesion: 0.13
Nodes (14): Daily Workflow, Editing & Synthesis, Hooks, Meeting Prep & Capture, Performance & Review, Semantic Search (QMD), Skills, Slash Commands (+6 more)

### Community 22 - "Community 22"
Cohesion: 0.13
Nodes (14): 1. Scan the Inbox, 2. Identify Meeting Type, 3. Search for Related Vault Context, 4. Route Content, 5. Cross-Link, 6. Clear the Inbox, code:block1 (/om-intake), code:markdown (---) (+6 more)

### Community 23 - "Community 23"
Cohesion: 0.13
Nodes (14): 1. Load Context, 2. Draft Projects, 3. Draft Competencies, 4. Draft Principles, 5. Strategic Calibration, 6. Quality Checks, 7. Fact-Check Pass, 8. Save (+6 more)

### Community 24 - "Community 24"
Cohesion: 0.13
Nodes (14): 1. Review What Was Done, 2. Verify Note Quality, 3. Check Index Consistency, 4. Check for Orphans, 5. Archive Check, 6. Ways of Working Review, 7. Suggest Improvements, 8. Report (+6 more)

### Community 25 - "Community 25"
Cohesion: 0.18
Nodes (9): readStdinJson(), writeHookOutput(), fields, input, values, hints, HookInput, input (+1 more)

### Community 26 - "Community 26"
Cohesion: 0.20
Nodes (11): ROOT_FILES, shouldSkipFile(), SKIP_PATH_SEGMENTS, validateContent(), validateFile(), base, hintList, HookInput (+3 more)

### Community 27 - "Community 27"
Cohesion: 0.14
Nodes (13): added, addedIdx, changedIdx, fixedIdx, FIXTURE, fp, GLOBS, once (+5 more)

### Community 28 - "Community 28"
Cohesion: 0.15
Nodes (12): 1. Gather Evidence, 2. Assess Visibility, 3. Draft, 4. Quality Checks, 5. Fact-Check, 6. Save, code:block1 (/om-review-peer <Name>), Context: Review System (+4 more)

### Community 29 - "Community 29"
Cohesion: 0.15
Nodes (12): After Bulk Changes, Bootstrap (Fresh Clone), code:bash (INDEX=$(node -e '), code:bash (node --experimental-strip-types scripts/qmd-bootstrap.ts), Commands, Index Management (CLI only — MCP exposes read surfaces), Named Index (This Vault), QMD — Vault Semantic Search (+4 more)

### Community 30 - "Community 30"
Cohesion: 0.15
Nodes (12): Active Projects, Archive, Completed, Current Quarter, Decisions Log, Incidents, Open Questions, Previous Quarters (+4 more)

### Community 31 - "Community 31"
Cohesion: 0.17
Nodes (11): 1. Find the Note, 2. Update Frontmatter, 3. Move the File, 4. Update Indexes, 5. Verify, code:block1 (/om-project-archive <project name>), code:bash (git mv "work/active/<Note>.md" "work/archive/YYYY/"), Important (+3 more)

### Community 32 - "Community 32"
Cohesion: 0.17
Nodes (7): after, before, SCRIPT, SCRIPT_DIR, { stdout, code }, { stdout, stderr, code }, VAULT_ROOT

### Community 33 - "Community 33"
Cohesion: 0.18
Nodes (10): 1. Fetch Profiles, 2. Check Vault, 3. Create Missing Notes, 4. Update Stale Notes, 5. Update People & Context Index, 6. Check Team Notes, code:yaml (---), Input (+2 more)

### Community 34 - "Community 34"
Cohesion: 0.25
Nodes (8): CountArgs, countSection(), FormatResult, content, count, result, d, doc

### Community 35 - "Community 35"
Cohesion: 0.18
Nodes (10): Basic Callout, Callouts Reference, code:markdown (> [!note]), code:markdown (> [!faq]- Collapsed by default), code:markdown (> [!question] Outer callout), code:css (.callout[data-callout="custom-type"] {), Custom Callouts (CSS), Foldable Callouts (+2 more)

### Community 36 - "Community 36"
Cohesion: 0.18
Nodes (10): 1. Gather Data, 2. Generate Content, 3. Create Files, 4. Verify, code:block1 (/om-review-brief <audience> [period]), Generate Review Brief, Important, Subagent (+2 more)

### Community 37 - "Community 37"
Cohesion: 0.18
Nodes (10): 1. Gather Week's Activity, 2. North Star Alignment, 3. Cross-Day Patterns, 4. Uncaptured Win Detection, 5. Competency Signal Mapping, 6. Forward Look, 7. Present Synthesis, Important (+2 more)

### Community 38 - "Community 38"
Cohesion: 0.20
Nodes (9): 1. Semantic Search, 2. Direct Note Lookup, 3. Gather Backlinks, 4. Gather Mentions, 5. Build Timeline, 6. Synthesize, Input, Output (+1 more)

### Community 39 - "Community 39"
Cohesion: 0.20
Nodes (9): 1. Read Every Message, 2. Profile Every Person, 3. Build the Timeline, 4. Identify Key Moments, 5. Produce People Summary, code:yaml (---), Input, Output (+1 more)

### Community 40 - "Community 40"
Cohesion: 0.20
Nodes (9): brain-first.md, builder-ethos.md, filing-rules.md, output-rules.md, padroes-system-prompts.md, Patterns & Conventions, quality.md, RESOLVER (skill dispatcher) (+1 more)

### Community 41 - "Community 41"
Cohesion: 0.20
Nodes (9): code:toml (project_doc_fallback_filenames = ["CLAUDE.md"]), code:json ({ "context": { "fileName": ["GEMINI.md", "CLAUDE.md"] } }), Commands, Hooks, Memory, Setup, Sinapse Agent — Vault (Gemini CLI), Subagents (+1 more)

### Community 42 - "Community 42"
Cohesion: 0.20
Nodes (7): bareRelative, cfg, commands, configs, envPrefixed, HookConfig, repoRoot

### Community 43 - "Community 43"
Cohesion: 0.20
Nodes (9): code:json ({), code:json ({), code:json ({), code:json ({), Flowchart, JSON Canvas Complete Examples, Project Board with Groups, Research Canvas with Files and Links (+1 more)

### Community 44 - "Community 44"
Cohesion: 0.20
Nodes (9): Agent Identity, Architect Mode, Ask Mode, Code Mode (default), Debug Mode, Memory Stack, Mode Behavior, Roo Code — Instructions (+1 more)

### Community 45 - "Community 45"
Cohesion: 0.22
Nodes (8): Alternatives Considered, Consequences, Context, Decision, Decision: Síntese obsidian-mind + Zettelkasten + PARA, Rationale, Related, Reversibility

### Community 46 - "Community 46"
Cohesion: 0.22
Nodes (8): code:block1 (cerebro/), Current State, Decisões tomadas, Estrutura final do vault, O que foi feito, Próximos passos, Stack, Última atualização: 2026-05-22

### Community 47 - "Community 47"
Cohesion: 0.22
Nodes (8): 1. Build the Link Targets, 2. Scan for Missing Links, 3. Check Bidirectional Links, 4. Check Orphans, 5. Check Related Sections, Input, Output, Process

### Community 48 - "Community 48"
Cohesion: 0.22
Nodes (8): 1. Load Voice Samples, 2. Read Target Note, 3. Edit In-Place, 4. Summarize Changes, code:block1 (/om-humanize <file path or note name>), Important, Usage, Workflow

### Community 49 - "Community 49"
Cohesion: 0.22
Nodes (8): code:block1 (/om-peer-scan <name> <github-username> <repo> [period]), code:block2 (gh pr list --repo <org>/<repo> --author <username> --state a), code:block3 (gh pr view <number> --repo <org>/<repo> --json body,reviews,), code:yaml (---), Important, Peer PR Deep Scan, Usage, Workflow

### Community 50 - "Community 50"
Cohesion: 0.22
Nodes (8): Manager Timeline, People, People & Context, Performance Reviews, Recurring Growth Themes, Review Goals, Role & Org, Teams

### Community 51 - "Community 51"
Cohesion: 0.22
Nodes (8): Alternatives Considered, Consequences, Context, Decision, Decision: {{title}}, Rationale, Related, Reversibility

### Community 52 - "Community 52"
Cohesion: 0.25
Nodes (7): 1. Determine Current Quarter, 2. Read Current Brag State, 3. Scan for Uncaptured Wins, 4. Check Competency Coverage, 5. Evaluate Each Find, Output, Process

### Community 53 - "Community 53"
Cohesion: 0.25
Nodes (7): code:block1 (/om-slack-scan <target> [channels...] [date-range]), code:block2 (mcp slack_read_channel channel_id=<id> limit=100), code:block3 (mcp slack_search_public_and_private query="from:<@USER_ID> a), Important, Slack Deep Scan, Usage, Workflow

### Community 54 - "Community 54"
Cohesion: 0.25
Nodes (7): code:yaml (---), code:markdown (#tag), code:yaml (---), Default Properties, Properties (Frontmatter) Reference, Property Types, Tags

### Community 55 - "Community 55"
Cohesion: 0.25
Nodes (7): Competencies -- "How knowledge and skills were applied", Growth Plan, Impact -- "What was delivered?", Perf Review -- {{period}}, Principles -- "How delivery happened", Related, Summary

### Community 56 - "Community 56"
Cohesion: 0.29
Nodes (6): Atoms — Zettelkasten Notes, code:yaml (---), Exemplos de bons átomos, Exemplos de notas que DEVEM SER SPLIT, Regras, Template

### Community 57 - "Community 57"
Cohesion: 0.29
Nodes (6): Capture 1:1 Meeting, code:block1 (/om-capture-1on1 <participant>), code:yaml (---), Important, Usage, Workflow

### Community 58 - "Community 58"
Cohesion: 0.29
Nodes (6): hooks, PostToolUse, PreCompact, SessionStart, Stop, UserPromptSubmit

### Community 59 - "Community 59"
Cohesion: 0.29
Nodes (6): After the Meeting, code:block1 (/om-meeting <topic>), Important, Meeting Prep, Usage, Workflow

### Community 60 - "Community 60"
Cohesion: 0.29
Nodes (6): After the Meeting, code:block1 (/om-prep-1on1 <person>), Important, Prep for 1:1, Usage, Workflow

### Community 61 - "Community 61"
Cohesion: 0.29
Nodes (6): code:bash (defuddle parse <url> --md), code:bash (defuddle parse <url> --md -o content.md), code:bash (defuddle parse <url> -p title), Defuddle, Output formats, Usage

### Community 62 - "Community 62"
Cohesion: 0.29
Nodes (6): hooks, AfterTool, BeforeAgent, PreCompress, SessionEnd, SessionStart

### Community 63 - "Community 63"
Cohesion: 0.29
Nodes (6): description, private, scripts, test, typecheck, type

### Community 64 - "Community 64"
Cohesion: 0.29
Nodes (6): Analysis, Conclusions, Feeds Into, Next Steps, Question / Problem, {{title}}

### Community 65 - "Community 65"
Cohesion: 0.29
Nodes (6): Context, Decisions, Related, {{title}}, What, Why

### Community 66 - "Community 66"
Cohesion: 0.33
Nodes (5): code:block1 (## Verified (X claims)), Input, Output, Process, Review Fact-Checker

### Community 67 - "Community 67"
Cohesion: 0.33
Nodes (5): checklist, HookInput, input, SCRIPT_DIR, WORKER_PATH

### Community 68 - "Community 68"
Cohesion: 0.33
Nodes (5): hooks, PostToolUse, SessionStart, Stop, UserPromptSubmit

### Community 69 - "Community 69"
Cohesion: 0.33
Nodes (5): Agent identity, Codex CLI — Instructions, Hooks, Memory stack, Vault conventions

### Community 70 - "Community 70"
Cohesion: 0.33
Nodes (5): Conventions, GitHub Copilot Instructions — Sinapse Agent Vault, Quick Rules, When to act vs ask, Where to put things

### Community 71 - "Community 71"
Cohesion: 0.33
Nodes (5): Identity, Memory, OpenClaw — Instructions, Rules, Vault conventions

### Community 72 - "Community 72"
Cohesion: 0.33
Nodes (5): Definition, Growth Notes, Proficiency Levels, Related, {{title}}

### Community 73 - "Community 73"
Cohesion: 0.40
Nodes (4): Auto Memory, Rule: Vault-First Memories, Setup, Where to Find Things

### Community 75 - "Community 75"
Cohesion: 0.40
Nodes (4): mcpServers, qmd, args, command

### Community 76 - "Community 76"
Cohesion: 0.40
Nodes (4): How This Works, Linking Convention, Thinking Space, When to Use

### Community 77 - "Community 77"
Cohesion: 0.50
Nodes (3): code:yaml (---), Data Sources to Scan, Output

### Community 78 - "Community 78"
Cohesion: 0.50
Nodes (3): Gotchas, Hermes Agent, Install

## Knowledge Gaps
- **706 isolated node(s):** `template`, `version`, `released`, `qmd_index`, `qmd_context` (+701 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `escapeRegex()` connect `Community 4` to `Community 2`, `Community 5`?**
  _High betweenness centrality (0.008) - this node is a cross-community bridge._
- **Why does `resolveQmdEntry()` connect `Community 17` to `Community 32`, `Community 2`, `Community 10`?**
  _High betweenness centrality (0.004) - this node is a cross-community bridge._
- **Why does `runScript()` connect `Community 0` to `Community 32`, `Community 5`?**
  _High betweenness centrality (0.003) - this node is a cross-community bridge._
- **What connects `template`, `version`, `released` to the rest of the system?**
  _706 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.050170068027210885 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.04081632653061224 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.08879492600422834 - nodes in this community are weakly interconnected._