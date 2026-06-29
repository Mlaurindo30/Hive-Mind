## Last Update: 2026-06-29 09:14

---
tags: [memory, current-state]
status: active
created: 2026-05-22
updated: 2026-05-22
---

# Current State

## Última atualização: 2026-05-22

### O que foi feito
- **Deep research**: Comparativo de estruturas de vault Obsidian para agentes (obsidian-mind, PARA, Zettelkasten, Johnny Decimal, autograph, agent-second-brain, frozo-vault-mem)
- **Síntese aplicada**: obsidian-mind + Zettelkasten + PARA
- **atoms/** criado: notas atômicas Zettelkasten (1 ideia = 1 node no Graphify)
- **perf/ removido**: performance review corporativa não se aplica a founder
- **work/incidents/ + work/1-1/ removidos**: corporativo demais
- **Templates tipados**: Atom Note, Work Note (com project/quarter/domain), Decision Record (com owner/rationale/alternatives/reversibility)
- **AGENTS.md atualizado**: nova estrutura, filing rules com atoms/
- **Graphify reindexado**: 1141 nodes, 1210 edges, 100 comunidades (703KB)
- **Sinapse-memory paths**: validados (DECISIONS_DIR, MEMORY_FILE, PROJECTS_DIR, PATTERNS_FILE)

### Decisões tomadas
- **obsidian-mind como base, não como dogma**: Mantemos brain/work/org/templates/bases/thinking. Removemos perf/incidents/1-1. Adicionamos atoms/.
- **Zettelkasten para conhecimento denso**: atoms/ gera nodes mais limpos no Graphify que notas longas em brain/
- **Templates tipados**: schema validation implícito nos campos obrigatórios dos templates

### Estrutura final do vault
```
cerebro/
├── brain/          ← North Star, Patterns, Key Decisions, Gotchas, Current State
├── atoms/          ← Notas Zettelkasten (1 ideia = 1 node) 🆕
├── work/           ← active/, archive/, meetings/, pipeline/
├── org/            ← people/, teams/
├── reference/      ← business docs
├── templates/      ← Atom Note, Work Note, Decision Record, Thinking Note
├── bases/          ← 7 database views
├── thinking/       ← scratchpad
├── .claude/        ← 18 commands, 9 agents, 5 hooks
├── AGENTS.md       ← cross-agent guide
├── CLAUDE.md       ← Claude Code manual
└── GEMINI.md       ← Gemini CLI guide
```

### Stack
| Camada | Ferramenta | Status |
|--------|-----------|--------|
| Estrutural | Graphify | ✅ 1141 nodes |
| Temporal | claude-mem | ✅ worker ativo |
| Execução | RTK | ✅ plugin ativo |
| Vault | obsidian-mind + Zettelkasten | ✅ integrado |
| Agente | Thoth (Hermes) | ✅ WhatsApp |

### Próximos passos
1. **Fase 2: Hooks** — 5 lifecycle hooks como eventos Hermes
2. **Fase 3: sqlite-vec** — substituir Chroma no claude-mem
3. **Fase 4: Comandos** — adaptar slash commands como skills Hermes
4. **Popular atoms/** — migrar conhecimento do brain/ para átomos


## Session: 2026-05-23 13:55

### Decisions
- Nenhuma decisão registrada
### Learnings
- Nenhum aprendizado registrado
### Summary
Test session hook automation


## Session: 2026-05-24 22:04

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:04

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:04

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:05

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:06

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:06

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:06

### Decisions
- Nenhuma decisão registrada
### Learnings
- Nenhum aprendizado registrado
### Summary
Sessão remota via rede


## Session: 2026-05-24 22:06

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:06

### Decisions
- Nenhuma decisão registrada
### Learnings
- Nenhum aprendizado registrado
### Summary
Sessão remota via rede


## Session: 2026-05-24 22:08

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:08

### Decisions
- Nenhuma decisão registrada
### Learnings
- Nenhum aprendizado registrado
### Summary
Sessão remota via rede


## Session: 2026-05-24 22:08

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:08

### Decisions
- Nenhuma decisão registrada
### Learnings
- Nenhum aprendizado registrado
### Summary
Sessão remota via rede


## Session: 2026-05-24 22:08

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:08

### Decisions
- Nenhuma decisão registrada
### Learnings
- Nenhum aprendizado registrado
### Summary
Sessão remota via rede


## Session: 2026-05-24 22:37

### Decisions
- Decisão: [[decision1]]

### Learnings
- Aprendizado: [[learning1]]

### Summary
Resumo de teste da API


## Session: 2026-05-24 22:37

### Decisions
- Nenhuma decisão registrada
### Learnings
- Nenhum aprendizado registrado
### Summary
Sessão remota via rede


## Session: 2026-06-11 16:58

### Decisions
- Nenhuma decisão registrada
### Learnings
- Nenhum aprendizado registrado
### Summary
Push dos 10 commits locais para o repositório origin/main após auditoria e testes bem-sucedidos.


## Session: 2026-06-11 21:07

### Decisions
- Nenhuma decisão registrada
### Learnings
- Nenhum aprendizado registrado
### Summary
Corrigido erro de shape no modelo Ideogram 4 através de detecção dinâmica da dimensão llm_features_dim e ajuste na precedência de configuração de modelos no ComfyUI.


## Session: 2026-06-25 09:55

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Revisão arquitetural do roadmap reescrito pelo Kilo (Claude + 2 subagentes, verificado vs código). Acordo 5/5 com Kilo via CLI; 5 correções aplicadas (DuckDB 9→4 queries, fases 6→7, line numbers, testes 466→534, §2.6 5→7 read-backends + RTK reclassificado, tools→13, P5 re-escopado). Kilo aplicou ~70% (limitou em contexto 256k), meus 2 subagentes fecharam o resto. Commit 9ea63d6 nos 3 docs (roadmap, AGENTS.md, 01-architecture.md).


## Session: 2026-06-25 13:06

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Sessão 2026-06-25: P8 CR-SQLite implementado como vendor em integrations/crsqlite/. Roadmap corrigido (zero 'core/vendor/'), install.sh com etapa 13, client.py com load_extension real, 5 testes de integração passando sem mocks, README + .env.example + wrapper Python. Versão pinada v0.16.3 de vlcn-io/cr-sqlite.


## Session: 2026-06-25 19:30

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Re-passagem swarm P7+P8 em p8-crsqlite-sync: tester 30/30 testes OK; code reviewer 7 achados (1 bloqueante .gitignore pre-crr + 6 warnings). Apliquei 4 fixes (B1+W1+W2+W3), marquei P8 CONCLUÍDO no roadmap, commit ef39ac3, fast-forward merge para main, push origin (1ef138b..ef39ac3). P7 e P8 fechados. Débito técnico restante: W4/W5/W6 (não-bloqueante).


## Session: 2026-06-26 19:21

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Leitura do histórico do claude-mem sobre cadastro/configuração de modelos no Hive-Mind; identificada sessão 7ef20b38 e observações recentes 13333-13355 sobre setupbrain, providers/modelos, Ollama qwen3:8b e limites de CLI/OAuth.


## Session: 2026-06-26 19:35

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Corrigido fluxo de troca de modelo claude_mem: aplicado granite4.1:8b no worker real e setup-brain agora executa sync com saída, exit-code e confirmação via /api/settings.


## Session: 2026-06-26 19:59

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Auditoria tecnica ponta a ponta do Hive-Mind: anatomia do cerebro, integracoes, imports, MCP/API, Graphify e runtime systemd validados contra docs/01-architecture.md.


## Session: 2026-06-26 20:32

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Reorganizei os metadados de agentes do vault: movidos de cerebro/.claude/.codex/.gemini/.github/.openclaw/.roo/.claude-flow para cerebro/tronco/infra/agentes; mantidos .obsidian e .smart-env no topo; .trash migrada para tronco/infra/obsidian-trash com trashOption=system; scripts/docs/hooks atualizados para o novo caminho e exclusoes de indexacao ajustadas.


## Session: 2026-06-26 20:43

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Verifiquei checklist P0/P1/P2 Hive-Mind. P0 validate_after_reboot com mode=ro, busy_timeout e retry/backoff. P1 GRAPH_JSON canônico em core.paths/cortex/occipital/grafo e docs/runtime atualizados. P1 MCP/sinapse-write corrigidos para caminhos anatômicos. P2 exclusão/indexação e top-level do vault limpos. P2 imports reduzido com wrappers importáveis, inclusive sinapse_zettelkasten, mas ainda restam bootstraps sys.path/importlib em entrypoints legados.


## Session: 2026-06-27 14:10

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Leitura de contexto Hive-Mind: docs/01-architecture.md, AGENTS.md e Sinapse consultados. Última atividade identificada: 2026-06-27, fechamento funcional Graphiti/LightRAG, correção de NaN/retry e ajustes de modelo/setup.


## Session: 2026-06-27 14:15

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Correção de entendimento: consulta temporal exata no claude-mem localizou última frente Hive-Mind sobre modelos/setupbrain. Achados: setupbrain não persistia/recarregava claude-mem sem restart; em 2026-06-27 houve qwen2.5:3b, menu Graphiti/LightRAG e pull no install.


## Session: 2026-06-27 14:24

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Ajustadas descrições de busca Sinapse: prompt de agentes, MCP tool descriptions, sinapse.yaml e template MCP agora diferenciam sinapse_query hibrido de sinapse_temporal_search textual/timeline no claude-mem global.


## Session: 2026-06-27 14:33

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Auditadas descrições das tools Sinapse contra handlers reais e claude-mem instalado/upstream. Prompt agora inclui fluxo de busca e tabela de escolha rápida; MCP tools/list foi validado com descrições atualizadas.


## Session: 2026-06-27 14:45

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Corrigido MCP/prompt Sinapse para preservar fluxo claude-mem search -> timeline -> get_observations: adicionadas sinapse_temporal_timeline e sinapse_temporal_get_observations, docs atualizadas para 15 tools e validações unit/stdout passaram.


## Session: 2026-06-27 14:55

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Auditoria das tools Sinapse vs integrações reais: health agora separa 7 read_backends de components/RTK, docs ativas corrigidas para 15 tools e MCP único, Screenpipe aceita monitor. Graphiti aparece false por FalkorDB não responder como esperado.


## Session: 2026-06-27 14:58

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Entendido RTK: proxy/filtro hook-based de comandos shell, nao read-backend. Corrigido start-rtk.sh para plugin Hermes atual e adapter rtk-rewrite para usar scripts/services/sinapse-write.py. Testes RTK Hermes passaram.


## Session: 2026-06-27 15:03

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Corrigi RTK para ser transversal por agente/CLI: start-rtk.sh delega para rtk init por alvo, config remove RTK de hybrid_search.backends e docs/prompt explicam que nao e backend do sinapse_query; validado com dry-run Codex/Hermes e YAML.


## Session: 2026-06-27 21:12

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Apliquei snowflake-arctic-embed2:latest como default de embeddings em core, LightRAG, Graphiti e NeuralMemory; install/docs/migrador atualizados; reembed real da search_vec concluido 5404/5404 sem erros; watcher graphify religado.


## Session: 2026-06-27 22:19

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Documentada a cadencia hierarquica de escrita em docs/11; adicionados roles monthly/yearly no setup-brain/auth, paths canonicos mensal/anual e testes focados passaram.


## Session: 2026-06-27 22:30

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Criado docs/12 com plano K0-K10 de implementacao da arquitetura de conhecimento; linkado em docs/11/docs README/docs01 e corrigidas refs 384d para snowflake 1024d.


## Session: 2026-06-27 22:41

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Atualizei pyproject/uv.lock com ragflow-sdk, pymilvus, llama-index; registrei ragflow/milvus/llama_index no components.lock e no integrations-update; docs/12 ajustado.


## Session: 2026-06-28 09:52

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Revisao docs/11+docs/12 Frente K: concordei com correcoes do Claude (clone vs wrapper vs pip, K9 antes de fases, migracao CRR-safe). Testes locais passaram. Pontos pendentes: K1 aceite muito amplo via integrations-update, skip requires_service ainda nao generico, ensure_migrations engole erro estrutural, components.lock deve ser contrato negativo para Milvus/RAGFlow/LlamaIndex.


## Session: 2026-06-28 10:00

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Aplicados ajustes em docs/11 e docs/12: components.lock como contrato negativo, metadata vetorial obrigatoria, K1 com --no-components/wrappers-only, K9 skip por servico pendente, K0 strict migration health, auditoria final de alinhamento. Validado: workspace migration 9 passed, real knowledge 3 passed, json/bash/py_compile OK.


## Session: 2026-06-28 10:28

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Implementado recorte Frente K: service registry requires_service, --no-components/--wrappers-only no integrations-update, HIVE_STRICT_MIGRATIONS=1, docs/11/12 atualizados, testes Graphiti/hybrid ajustados. Validacao final: tests/run_all.sh verde (Smoke 19, Unit 473/3 skipped, Integration 104/4 skipped, E2E 22).


## Session: 2026-06-28 10:33

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Corrigido contrato K0: migracao workspace/federacao agora falha fechado por padrao; removido HIVE_STRICT_MIGRATIONS. Bypass somente HIVE_ALLOW_DEFERRED_MIGRATIONS=1 para diagnostico legado. Docs atualizados. Validacao: workspace_migration + database 31 passed.


## Session: 2026-06-28 10:41

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Auditoria final K0/K1/K9: ADD COLUMN legado tornado CRR-safe, docs 11/12 alinhados, update flags validados e run_all verde.


## Session: 2026-06-28 11:09

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
K1 importações/wrappers e K2 VectorBackend sqlite+Milvus implementados e verificados com testes reais; sync/backfill K2 ainda pendentes.


## Session: 2026-06-28 16:27

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
K2 avançou: sync/backfill memory_vectors SQLite->Milvus com idempotência/hash, falha por linha reportada, testes reais 15 passed e run_all verde.


## Session: 2026-06-28 16:44

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
K2 alinhado para observation_vectors: SQLiteVecBackend consulta claude-mem.db read-only, sync_observation_vectors_to_milvus exporta para Milvus com idempotencia. Testes: observation 2 passed, K1/K2 14 passed, run_real_knowledge 17 passed, run_all verde.


## Session: 2026-06-28 16:58

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Continuacao K1/K2: adicionado E2E live bounded para sync memory/observation vectors com bancos reais read-only e Milvus temporario. core/vector_sync limit opcional. Testes: K1/K2 15 passed, run_real_knowledge 18 passed, run_all verde.


## Session: 2026-06-28 17:08

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
K1 reforcado: verify_wrappers.py valida compose/digest Milvus/RAGFlow; install.sh e integrations-update.sh chamam o gate. Testes: K1 wrappers 7 passed, run_real_knowledge 21 passed, run_all verde.


## Session: 2026-06-28 22:01

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
K2 reforcado com CLI operacional vector-sync.py + E2E real por subprocesso; docs atualizadas. Verificacoes: CLI test 1 passed, K2 real agregado 12 passed, run_real_knowledge 21 passed/1 skipped; run_all bloqueado por falhas externas a K2 em Ollama/Graphiti/sinapse-write.


## Session: 2026-06-28 22:39

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
K2 finalizado: 7 colecoes VectorBackend vivas, backfill auxiliar, sync Milvus idempotente, CLI completo, docs 11/12 atualizadas. Verificacao: K2 real 14 passed, run_real_knowledge 24 passed, run_all 4 suites verdes.


## Session: 2026-06-29 09:14

### Decisions
- Nenhuma decisão registrada### Learnings
- Nenhum aprendizado registrado### Summary
Corrigido provider Antigravity/agy para usar HOME real por padrao e herdar auth do CLI; AGY_BIN agora resolve via env/PATH/fallback. Validado agy direto, dreamer antigravity/gemini-3.5-flash, fallback gemini-cli e dream_cycle real ok sem auth errors.
