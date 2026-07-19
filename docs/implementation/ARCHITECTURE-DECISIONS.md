# Architecture Decision Records

| ADR | Título | Estado | Data | Entrega |
|---|---|---|---|---|
| ADR-001 | Native control plane | ACCEPTED | 2026-07-16 | D000 |
| ADR-002 | One owner per service/job/provider | ACCEPTED | 2026-07-16 | D000 |
| ADR-003 | PowerShell/Bash as thin wrappers | ACCEPTED | 2026-07-16 | D000 |
| ADR-004 | Canonical capture path through capture_core.ingest | ACCEPTED | 2026-07-18 | D000 |
| ADR-005 | Preserve native Claude Mem capture | ACCEPTED | 2026-07-16 | D000 |
| ADR-006 | Canonical project identity | ACCEPTED | 2026-07-17 | D000 |
| ADR-007 | Dream Cycle grouped by project_id | ACCEPTED (não implementado) | 2026-07-19 | D002 |
| ADR-008 | Docker boundary | ACCEPTED | 2026-07-16 | D000 |
| ADR-009 | Windows user-session default runtime | ACCEPTED | 2026-07-16 | D000 |
| ADR-010 | Disposable Windows before root update | ACCEPTED | 2026-07-19 | D012 |
| ADR-011 | Legacy outbox preserved but inactive | ACCEPTED | 2026-07-19 | D000 |
| ADR-012 | No historical migration without dry-run and rollback | ACCEPTED | 2026-07-19 | D000 |
| ADR-013 | Agents namespace: `hive_mind.agents` (não `integrations`) | PROPOSED | 2026-07-19 | D009 |

Estados: PROPOSED / ACCEPTED / SUPERSEDED / DEPRECATED.

---

## ADR-001 — Native control plane

- **Contexto:** o runtime Windows acumulou lógica de produto em
  PowerShell (`register-mcp.ps1`), Bash (`register-mcp.sh`), Node
  (`npm/lib/supervisor.js`) e Task Scheduler, sem dono único.
- **Decisão:** o control plane é um pacote Python instalável com CLI
  `hive-mind` e daemon foreground `hive-mindd run`, guiado por um único
  manifesto declarativo (`config/runtime.yaml`, F2). Fonte:
  `specs/control-plane-redesign-v2.md`.
- **Alternativas rejeitadas:** manter supervisor Node (sem paridade
  Linux, segundo owner); orquestrar via Task Scheduler puro (sem
  dependency graph nem readiness); reescrever em Rust (custo sem
  benefício imediato).
- **Consequências:** F1 entregue (`src/hive_mind/`); F2+ pendentes;
  scripts atuais viram wrappers e depois são removidos (F10/F11).
- **Arquivos afetados:** `pyproject.toml`, `src/hive_mind/**`.
- **Testes:** `tests/unit/test_f1_package.py`, `test_f1_project_root.py`.
- **Rollback:** `git revert` dos commits F1 (sem deploy ainda).
- **Status:** ACCEPTED.

## ADR-002 — One owner per service/job/provider

- **Contexto:** dupla execução real observada: capture com dois donos
  (tailer/realtime vs hook/outbox), scheduler triplo (systemd, Task
  Scheduler, Node).
- **Decisão:** cada serviço, job e provider tem exatamente um owner,
  declarado no manifesto; ownership transita por cutover explícito
  legacy → shadow → managed com rollback automático (spec §9, §16.2).
- **Alternativas rejeitadas:** coexistência "temporária" de dois donos
  (foi a causa da outbox órfã); feature flags por ambiente.
- **Consequências:** `capture_adapters.py` declara `owner` por provider
  (realtime/timer); teste `test_every_provider_has_exactly_one_delivery_owner`.
- **Arquivos afetados:** `scripts/capture/capture_adapters.py`, futuro
  `config/runtime.yaml`.
- **Testes:** `tests/unit/test_outbox_delivery_isolated.py`.
- **Rollback:** n/a (princípio).
- **Status:** ACCEPTED.

## ADR-003 — PowerShell/Bash as thin wrappers

- **Contexto:** `register-mcp.ps1` (~430 L) e `.sh` (~360 L) contêm
  detecção de providers, edição de configs e instalação de hooks.
- **Decisão:** PS1/SH podem apenas localizar o executável `hive-mind`,
  repassar argumentos e devolver o exit code. Nenhuma detecção, regra
  de provider, edição de config ou decisão de owner. Alvo final: <100
  LOC (spec §16.1 F10) e remoção em F11.
- **Alternativas rejeitadas:** manter a lógica em PS1 com paridade
  manual no SH (já divergiu: hook removido do `.ps1` em `b329e84`,
  ainda presente no `.sh:357`).
- **Consequências:** nenhuma lógica nova entra nos scripts; a migração
  acontece em P5/D009.
- **Arquivos afetados:** `scripts/setup/register-mcp.{ps1,sh}`,
  `install.{ps1,sh}`.
- **Testes:** `tests/unit/test_outbox_delivery_isolated.py` (guarda o
  `.ps1`); teste equivalente para `.sh` entra em D009.
- **Rollback:** git revert por script.
- **Status:** ACCEPTED.

## ADR-004 — Canonical capture path through capture_core.ingest

- **Contexto:** dois pipelines concorrentes: (a)
  parser → sessão normalizada → `capture_core.ingest()` → Claude Mem
  (funcional no Linux); (b) `ProviderEvent → CaptureQueue → outbox`
  experimental, sem drainer.
- **Decisão:** (a) é o único caminho de entrega para todos os 12
  providers. (b) não participa do runtime. Não implementar OutboxDrainer.
- **Alternativas rejeitadas:** terminar o outbox (segundo dono;
  contraria ADR-002); drenar a fila histórica (proibido sem autorização
  — ADR-012).
- **Consequências:** commits `cb7e3bd` (desabilita internamente) e
  `b329e84` (remove wiring do `.ps1`); `register-mcp.sh` pendente
  (D009).
- **Arquivos afetados:** `scripts/capture/capture-realtime.py`,
  `capture-tailer.py`, `capture_core.py`, `capture_adapters.py`.
- **Testes:** `test_outbox_delivery_isolated.py`,
  `test_capture_realtime.py`, `test_capture_tailer.py`.
- **Rollback:** git revert de `b329e84`.
- **Status:** ACCEPTED.

## ADR-005 — Preserve native Claude Mem capture

- **Contexto:** o Claude Code tem plugin de captura próprio, funcional.
- **Decisão:** não modificar, não duplicar, não registrar adapter
  Hive-Mind para Claude Code (spec §14.4).
- **Alternativas rejeitadas:** unificar a captura do Claude no pipeline
  Hive-Mind (duplicaria sessões).
- **Consequências:** `ADAPTERS` não contém `claude`/`claude-code`;
  teste `test_native_claude_code_capture_is_not_duplicated`.
- **Arquivos afetados:** nenhum (proibição).
- **Testes:** `tests/unit/test_outbox_delivery_isolated.py`.
- **Rollback:** n/a.
- **Status:** ACCEPTED.

## ADR-006 — Canonical project identity

- **Contexto:** projeto derivado de `Path(cwd).name` gerava identidades
  falsas (Qwen, miche, Microsoft VS Code, app, hermes,
  hive-mind-windows-zero-install) fragmentando Claude Mem, UMC, Dream
  Cycle, vetores e grafos.
- **Decisão:** um único `ProjectIdentityResolver`
  (`scripts/capture/project_identity.py`) com ordem de resolução:
  explícito → env → workspace do app → git root → git common dir →
  remote normalizado → aliases (`config/project-aliases.yaml`) →
  markers → `unclassified/<provider>`. Worktree, branch, surface e
  profile são metadados, nunca identidade. Raiz e worktrees do mesmo
  `git-common-dir` compartilham `project_id`.
- **Alternativas rejeitadas:** resolução por parser (divergência
  garantida); heurística semântica silenciosa (permitida apenas com
  política habilitada, threshold e método `semantic_reference`
  auditável).
- **Consequências:** contrato de 13 campos anexado às sessões; bridge
  usa `workspace_id = project_id`.
- **Arquivos afetados:** `scripts/capture/project_identity.py`,
  `session_events.py`, parsers, `config/project-aliases.yaml`.
- **Testes:** `test_project_identity.py` (500+ L),
  `test_capture_project_identity.py`,
  `test_provider_parser_identity_contract.py`,
  `tests/integration/test_project_identity_git.py`.
- **Rollback:** git revert da série `63f1a04`..`465af94`.
- **Status:** ACCEPTED.

## ADR-007 — Dream Cycle grouped by project_id

- **Contexto:** `dream_cycle.py:71` particiona por
  `COALESCE(project, '_sem_projeto')` e `:812` lê `o["project"]` (label
  livre). O `project_id` gravado pelo bridge é ignorado. Markdown vai
  para diretórios por label, fragmentando o cérebro.
- **Decisão:** Dream Cycle e daily writer agrupam por `project_id`;
  Markdown em `cerebro/cortex/temporal/<project_id>/<topic>/`;
  frontmatter canônico com project_id, project_name, workspace_root,
  repository_root, branch, worktree_name, provider, surface,
  source_session, source_observations, integrity_hash. Dados legacy sem
  project_id não são apagados: caem em legacy/unclassified com leitura
  retrocompatível.
- **Alternativas rejeitadas:** normalizar labels por regex (mantém
  fonte não canônica); migrar histórico junto (viola ADR-012).
- **Consequências:** entrega D002; gates DC1–DC9 na matriz.
- **Arquivos afetados:** `scripts/dream/dream_cycle.py`,
  `scripts/dream/daily_writer.py`, testes de segregação.
- **Testes:** novos em D002 (unit + integração SQLite real + A/B).
- **Rollback:** git revert da D002.
- **Status:** ACCEPTED (decisão firmada; implementação NOT_STARTED).

## ADR-008 — Docker boundary

- **Contexto:** tentação recorrente de dockerizar componentes locais.
- **Decisão:** Docker somente para infraestrutura naturalmente
  server-side (Milvus, FalkorDB, RAGFlow etc.). Componentes de sessão
  de usuário e captura rodam nativos. "Container running" não conta
  como healthy — health é verificado no serviço (spec §12).
- **Alternativas rejeitadas:** compose para todo o runtime.
- **Consequências:** daemon apenas orquestra compose projects
  declarados no manifesto.
- **Arquivos afetados:** `integrations/*/docker-compose.yml`, futuro
  manifesto.
- **Testes:** F2+.
- **Rollback:** n/a.
- **Status:** ACCEPTED.

## ADR-009 — Windows user-session default runtime

- **Contexto:** captura e MCPs precisam do contexto da sessão do
  usuário; Windows Service roda em session 0.
- **Decisão:** runtime padrão na sessão do usuário (autostart);
  Windows Service é opcional (spec Anexo D.1).
- **Alternativas rejeitadas:** service-only (quebra captura de apps
  desktop).
- **Consequências:** `hive-mindd` inicia com o logon; lifecycle W1–W8
  testado nessa modalidade primeiro.
- **Arquivos afetados:** installer (P7).
- **Testes:** P8.
- **Rollback:** n/a.
- **Status:** ACCEPTED.

## ADR-010 — Disposable Windows before root update

- **Contexto:** `D:\Hive-Mind` é o runtime de produção do usuário.
- **Decisão:** toda instalação/upgrade corrigido é validado primeiro em
  ambiente Windows descartável (P8/D012). Só depois, com snapshot,
  backup e plano de rollback, atualiza-se a raiz (P9/D013), com
  autorização humana explícita.
- **Alternativas rejeitadas:** testar na máquina ativa.
- **Consequências:** sequência D012 → D013 obrigatória.
- **Rollback:** por definição, cada etapa tem rollback próprio.
- **Status:** ACCEPTED.

## ADR-011 — Legacy outbox preserved but inactive

- **Contexto:** `capture-hook.py`/`capture_queue.py` alimentaram
  `D:\Hive-Mind\logs\capture-outbox.db` (3.9 MB) e
  `C:\Users\miche\.claude-mem\capture.db` sem drainer.
- **Decisão:** arquivos permanecem no disco para auditoria histórica;
  nenhum wiring no runtime novo; bancos históricos não são drenados,
  mesclados, reprocessados ou limpos sem autorização separada. O
  runtime antigo (`D:\Hive-Mind`) continua escrevendo neles até P9 —
  comportamento esperado, não defeito do incremento.
- **Alternativas rejeitadas:** apagar os arquivos (perde histórico);
  drenar a fila (mexe em banco histórico sem autorização).
- **Consequências:** commit `b329e84` é TEMPORARY COMPATIBILITY SHIM,
  removido em P10 junto com os scripts (F11).
- **Testes:** `test_outbox_delivery_isolated.py`.
- **Rollback:** git revert de `b329e84`.
- **Status:** ACCEPTED.

## ADR-012 — No historical migration without dry-run and rollback

- **Contexto:** dados históricos com labels legados (Hive-Mind,
  hive-mind-windows-zero-install, Qwen, miche, Microsoft VS Code, app,
  hermes) em sessões, observations, vetores e Markdown.
- **Decisão:** nenhuma reescrita histórica sem: dry-run
  (`hive-mind projects audit` — já existe, `8a4a41f`), classificação
  CANONICAL/ALIAS/SURFACE/PROFILE/UNCLASSIFIED/AMBIGUOUS, backup, plano
  transacional com rollback, e autorização humana explícita.
- **Alternativas rejeitadas:** migração oportunista durante D002.
- **Consequências:** leitura retrocompatível obrigatória em todo o
  pipeline até a migração autorizada.
- **Testes:** `test_projects_audit.py`,
  `tests/integration/test_projects_audit_readonly.py`.
- **Rollback:** n/a (proibição).
- **Status:** ACCEPTED.

## ADR-013 — Agents namespace: `hive_mind.agents`

- **Contexto:** divergência real entre instruções de execução
  (`src/hive_mind/integrations/` com comando
  `hive-mind integrations register`) e a spec aprovada
  (`specs/control-plane-redesign-v2.md:1233`, que remove
  `register-mcp.sh` "substituído por `hive_mind.agents.register`").
  Criar os dois violaria a proibição de registries concorrentes.
- **Decisão (proposta):** namespace único `hive_mind.agents`, conforme
  a spec aprovada. Comandos públicos do CLI:
  `hive-mind agents detect|list|register|unregister|doctor` e
  `hive-mind capture detect|install|uninstall|status|doctor`. O termo
  "integrations/" continua reservado ao diretório existente de
  infraestrutura Docker (`integrations/milvus`, `integrations/ragflow`
  etc.), o que é mais um motivo para não reutilizá-lo como namespace
  Python de registro de agentes.
- **Alternativas rejeitadas:** `hive_mind.integrations` (colide com o
  diretório `integrations/` de compose projects; contraria a spec);
  criar ambos com um deprecado (dois registries).
- **Consequências:** D009 implementa sob `hive_mind.agents`; wrappers
  PS1/SH delegam para `hive-mind agents register`.
- **Arquivos afetados:** futuros `src/hive_mind/agents/**`,
  `src/hive_mind/capture/**`.
- **Testes:** D009.
- **Rollback:** rename mecânico antes do primeiro release público.
- **Status:** PROPOSED (aguardando aprovação humana do MASTER-PLAN).
