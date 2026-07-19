# Delivery Ledger

APPEND-ONLY. Entregas passadas não são reescritas para parecer que
sempre estiveram corretas. Correções entram como novas entradas.

Template para novas entregas: [templates/DELIVERY-TEMPLATE.md](templates/DELIVERY-TEMPLATE.md).

---

## D000 — Baseline anterior (trabalho de d246f0c até b329e84)

- data: 2026-07-16 a 2026-07-19 (auditado em 2026-07-19)
- branch: `codex/control-plane-redesign`
- HEAD: `b329e84`
- objetivo: registrar o que os 40 commits anteriores a este sistema de
  documentação já entregaram, com classificação por commit.
- resultado: ver matriz abaixo. F1 do control plane concluída; identidade
  canônica implementada em `scripts/capture/`; bridge propagando
  `workspace_id=project_id`; outbox experimental isolada.
- problemas conhecidos:
  - Dream Cycle agrupa por `observations.project` (label livre) —
    `dream_cycle.py:71,812`;
  - frontmatter Markdown sem `project_id`;
  - `register-mcp.sh:357` ainda invoca `install-capture-hooks.py`
    (divergência com o `.ps1` corrigido);
  - 2 falhas pré-existentes em `test_windows_install_contract.py`
    (UnicodeDecodeError de stdout PowerShell);
  - saúde semântica degraded (observations_linked_pct 7.62%,
    discoveries_pending 942, orphan_vectors 7, milvus_sync_lag 568);
  - canários de captura são todos pré-correção de identidade.
- evidência: sessão de auditoria 2026-07-19 (FASE 0); 82 testes de
  identidade verdes; 10 testes de isolamento da outbox verdes.
- documentação atualizada: nenhuma à época (motivo da criação do D001).
- decisão: prosseguir com documentação viva antes de novo código.

### Matriz dos 40 commits (d246f0c..b329e84)

Ações: KEEP / PORT TO NATIVE / REWORK / REVERT AFTER PORT / UNKNOWN.

| Commit | Intenção | Nativa | Legado | Testado | Ação |
|---|---|:--:|:--:|:--:|---|
| `8bc78b4` | spec control plane v2 | ✅ | — | n/a | KEEP |
| `d984e83` | condições de aprovação F1 | ✅ | — | n/a | KEEP |
| `e215fd6` | pacote + entry points | ✅ | — | ✅ | KEEP |
| `60aa2af` | contratos pacote/root | ✅ | — | ✅ | KEEP |
| `a44540b` | fonte única de versão | ✅ | — | ✅ | KEEP |
| `6ac42f4` | excludes Hatch, build <5s | ✅ | — | ✅ | KEEP |
| `6f6dc64` | excluir .env/uv.lock do wheel | ✅ | — | ✅ | KEEP |
| `05d8900` | perfis local-full bootáveis | — | ✅ | ✅ | KEEP |
| `be2d9e5` | preservar vetores canônicos | — | ✅ | ✅ | KEEP |
| `7572756` | isolar Graphiti/LightRAG live | — | ✅ | ✅ | KEEP |
| `895316b` | encoding-safe Windows | — | ✅ | ✅ | KEEP |
| `c99a4df` | validar serviços live | — | ✅ | ✅ | KEEP |
| `e2ddd0b` | supervisor Node adota managed | ❌ | ✅ | ✅ | REVERT AFTER PORT (P4/P6) |
| `d5b60f0` | ler markdown legado | — | ✅ | ✅ | KEEP |
| `77046d2` | isolar writes de latência | — | ✅ | ✅ | KEEP |
| `c2df042` | normalizar newlines | — | ✅ | ✅ | KEEP |
| `c0caafe` | design identidade canônica | ✅ | — | n/a | KEEP |
| `1c2a18e` | plano de rollout identidade | ✅ | — | n/a | KEEP |
| `cb7e3bd` | restaurar entrega canônica direta | ⚠️ | ✅ | ✅ | KEEP |
| `f573459` | paridade parsers Windows | ⚠️ | ✅ | ✅ | KEEP |
| `4174519` | retry init de sessão | ⚠️ | ✅ | ✅ | KEEP |
| `63f1a04` | resolver canônico (765 L + aliases) | ⚠️ | ✅ | ✅ 472 L | PORT TO NATIVE (ADR-013) |
| `0b6b762` | remotes malformados | ⚠️ | ✅ | ✅ | PORT TO NATIVE |
| `4ac5434` | repo+worktree mesmo id (git real) | ⚠️ | ✅ | ✅ 173 L | PORT TO NATIVE |
| `47dd5ae` | propagar metadata canônica | ⚠️ | ✅ | ✅ 251 L | PORT TO NATIVE |
| `1352ba3` | cache identidade no hook | ❌ | ✅ | ✅ | REVERT AFTER PORT |
| `f4131d2` | isolar/reparar contexto do hook | ❌ | ✅ | ✅ | REVERT AFTER PORT |
| `01d64c7` | degradar sem context db (hook) | ❌ | ✅ | ✅ | REVERT AFTER PORT |
| `c0638ad` | fallback evidência inválida (hook) | ❌ | ✅ | ✅ | REVERT AFTER PORT |
| `921765a` | Hermes desktop Windows | ⚠️ | ✅ | ✅ 139 L | KEEP |
| `2e8d301` | cronologia Hermes | ⚠️ | ✅ | ✅ | KEEP |
| `01ca74b` | evidência de projeto Hermes | ⚠️ | ✅ | ✅ | PORT TO NATIVE |
| `416fb20` | encoding diagnóstico | ⚠️ | ✅ | ✅ | KEEP |
| `49eafb1` | normalizar evidência (6 parsers) | ⚠️ | ✅ | ✅ 229 L | KEEP |
| `814ebc5` | surface/workspace paths | ⚠️ | ✅ | ✅ | KEEP |
| `0f965c9` | workspace sem git | ⚠️ | ✅ | ✅ | PORT TO NATIVE |
| `b958e58` | identidade no bridge (workspace_id) | ⚠️ | ✅ | ✅ 91 L | PORT TO NATIVE |
| `465af94` | hardening do bridge | ⚠️ | ✅ | ✅ 118 L | KEEP |
| `8a4a41f` | `hive-mind projects audit` | ✅ | — | ✅ 127 L | KEEP (já nativo) |
| `b329e84` | isolar outbox deprecated | ❌ | ✅ | ✅ 120 L | TEMPORARY COMPATIBILITY SHIM — remover em P10/F11 (ADR-011) |

Legenda "Nativa": ✅ = pacote/spec nativo; ⚠️ = lógica correta em local
legado (`scripts/`), portável; ❌ = remendo em componente que a
arquitetura descarta.

---

## D001 — Establish living implementation documentation

- fase: P0
- estado: DONE
- aprovação humana: 2026-07-19 — MASTER-PLAN APROVADO; ADR-013
  (`hive_mind.agents`) APROVADO; conteúdo D001 APROVADO.
- escopo: criar `docs/implementation/` (README, MASTER-PLAN,
  CURRENT-STATE, ACCEPTANCE-MATRIX, DELIVERY-LEDGER,
  ARCHITECTURE-DECISIONS, DOCUMENTATION-MAP, templates/) e preencher
  baseline com o relatório auditado das Fases 0–1. Sem alteração de
  código funcional, runtime, banco ou serviços. Não corrige Dream
  Cycle. Não inicia F2.
- arquivos planejados:
  - docs/implementation/README.md
  - docs/implementation/MASTER-PLAN.md
  - docs/implementation/CURRENT-STATE.md
  - docs/implementation/ACCEPTANCE-MATRIX.md
  - docs/implementation/DELIVERY-LEDGER.md
  - docs/implementation/ARCHITECTURE-DECISIONS.md
  - docs/implementation/DOCUMENTATION-MAP.md
  - docs/implementation/templates/DELIVERY-TEMPLATE.md
- arquivos realmente alterados: os 8 acima (criação).
- testes planejados: nenhum (entrega só de documentação).
- testes executados: nenhum (n/a).
- evidência real: arquivos presentes no commit; baseline cruzado com
  auditoria de 2026-07-19 (git log, grep de código, sinapse_health).
- commits:
  - `ae32195` — `docs(implementation): establish living execution plan`
    (8 arquivos, +1120 linhas; trailer `Delivery: D001`)
  - `docs(implementation): close delivery D001` (este fechamento;
    trailer `Delivery: D001`)
- HEAD do commit 1: `ae32195a09db942fb1ccb88dbab5cc30edd045db`
- riscos: documentação divergir do código se as regras do README não
  forem seguidas nas próximas entregas.
- rollback: `git revert` dos dois commits desta entrega.
- documentação atualizada: este conjunto É a documentação.
- pendências: nenhuma (aprovações registradas em 2026-07-19).
- decisão final: **DONE** — 8 documentos criados, baseline preenchido
  com evidência auditada, MASTER-PLAN e ADR-013 aprovados. Nenhum
  código funcional, runtime, banco ou serviço alterado.

### Artefatos locais conhecidos (não fazem parte da entrega)

```
.tmp/
classificação: LOCAL TEST ARTIFACT
origin: Hermes canary 2026-07-18 / screenshots
tracked: no
required for product: no
cleanup: pending separate approval
```

16 arquivos. Não apagados, não movidos, não commitados. Se `.tmp/` não
estiver no `.gitignore`, isso vira uma entrega curta de higiene própria
— não é incluído silenciosamente aqui.

---

## D002 — Correct project-aware Dream Cycle

- fase: P1
- estado: PARTIAL
- HEAD inicial: `834e405`
- escopo executado: agrupamento do Dream Cycle por `project_id`
  canônico, frontmatter canônico nos neurônios, compatibilidade legacy,
  isolamento A/B, documentação de subsistema. NÃO tocou MCP, scheduler,
  supervisor nem F2.

### Alterações reais

| Arquivo | Mudança |
|---|---|
| `scripts/dream/dream_cycle.py` | `ObservationProject` + `resolve_observation_project()` + `_balanced_partition_sql()`; `fetch_balanced_observations` particiona por project_id; agrupamento do ciclo por project_id com log de projetos legados; `_route_and_persist_project(identity=...)`; frontmatter canônico |
| `tests/unit/test_dream_project_identity.py` | novo — 18 testes |
| `tests/integration/test_dream_project_isolation.py` | novo — 6 testes, SQLite real |
| `docs/dream-cycle.md` | novo |
| `docs/project-identity.md` | novo |

### Testes executados

| Comando | Resultado |
|---|---|
| `pytest tests/unit/test_dream_project_identity.py` | 18 passed |
| `pytest tests/integration/test_dream_project_isolation.py` | 6 passed |
| `pytest tests/unit/test_dream_*.py` (suítes existentes) | 47 passed (sem regressão) |
| `pytest tests/unit` (completo) | **993 passed, 20 skipped, 2 failed** |

As 2 falhas são pré-existentes e não relacionadas:
`test_windows_install_contract.py::test_install_powershell_accepts_a_non_mutating_dry_run`
e `::test_install_dry_run_reports_the_selected_versioned_profile`
(UnicodeDecodeError lendo stdout do PowerShell). Reproduzidas antes
desta entrega, com o diff em stash.

### Skips inventariados (20)

Todos por indisponibilidade de recurso externo ou por serem POSIX-only
no Windows — nenhum componente obrigatório habilitado foi skipped:
Ollama/nomic-embed-text (2), `register-mcp.sh` POSIX (3), Screenpipe
não rodando (3), systemd/procfs post-reboot (6), chmod POSIX (2),
comparação de unit systemd (1), demais (3).

### Decisão de design registrada

`daily_writer.py` **não foi alterado**: ele agrega por **dia**
(`cerebelo/diario/YYYY/MM/`), não por projeto — não há path por projeto
para corrigir nele. A identidade de projeto nos diários entra junto com
a validação operacional do ciclo (D005), se necessária.

### Evidência operacional

PENDENTE — nenhum canário real executado. Gates DC2–DC4 e DC8–DC9
seguem NOT_STARTED. É o motivo de esta entrega ser PARTIAL e não DONE.

- riscos: bancos legados sem coluna `workspace_id` — coberto por teste
  (`test_database_without_workspace_column_still_works`).
- rollback: `git revert` do commit desta entrega.
- documentação atualizada: `docs/dream-cycle.md`,
  `docs/project-identity.md`, CURRENT-STATE, ACCEPTANCE-MATRIX, este
  ledger.
- pendências: validação operacional do ciclo completo (D005).
- escopo planejado original:
  - Dream Cycle agrupando por `project_id`;
  - daily writer por `project_id`;
  - frontmatter canônico (project_id, project_name, workspace_root,
    repository_root, branch, worktree_name, provider, surface,
    source_session, source_observations, integrity_hash);
  - path `cerebro/cortex/temporal/<project_id>/<topic>/`;
  - compatibilidade com dados legacy (sem apagar; marcar
    legacy/unclassified);
  - testes unitários + integração SQLite real;
  - projetos A/B sintéticos com cleanup;
  - canário operacional;
  - atualização de: docs/dream-cycle.md (criar), docs/project-identity.md
    (criar), CURRENT-STATE.md, ACCEPTANCE-MATRIX.md (DC1–DC9),
    DELIVERY-LEDGER.md.

---

## DH-001 — Hygiene: `.tmp/` não está no `.gitignore` (REGISTRADA)

- fase: higiene (independente das fases P)
- estado: NOT_STARTED
- constatação: `.gitignore` não contém `.tmp/`; os 16 artefatos do
  canário Hermes aparecem como untracked em todo `git status`.
- classificação dos artefatos: LOCAL TEST ARTIFACT — não rastreados, não
  requeridos pelo produto, cleanup pendente de aprovação separada.
- escopo: adicionar `.tmp/` ao `.gitignore`. NÃO apagar, NÃO mover, NÃO
  commitar os arquivos existentes.
- motivo de ser entrega própria: não pode ser incluída silenciosamente em
  outra entrega.
