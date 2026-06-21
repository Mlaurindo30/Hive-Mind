# Auditoria Tecnica E2E do Hive-Mind

Data: 2026-06-19  
Repositorio: `/home/michel/Documentos/Projects/Hive-Mind`  
Escopo: arquitetura, fluxos de dados, integracoes, interface, runtime instalado, testes unitarios, integracao, E2E, seguranca e estresse.

## 1. Resumo executivo

O Hive-Mind esta operacional em partes, mas nao esta pronto para producao. O UMC (`hive_mind.db`), a API REST em `37702`, o MCP `sinapse-memory`, Graphify, RTK e a `.venv` local existem e respondem. A suite unitaria e a E2E passam.

O bloqueador principal e o pipeline temporal do `claude-mem`: a instalacao real nao esta project-local. O diretorio `Hive-Mind/claude-mem` contem apenas dados; nao contem checkout/plugin local, `worker-service.cjs`, `mcp-server.cjs`, `package.json` ou lockfile. O worker ativo em `127.0.0.1:37700`, o sqlite-vec em `37701`, os scripts de captura e a ponte para o UMC ainda usam `~/.claude-mem` ou o plugin/cache global.

Isso quebra o requisito central de isolamento: uma instalacao do zero pelo `install.sh` reproduz o runtime global, nao um runtime autocontido no projeto.

Classificacao final: **pre-producao com bloqueadores P0**. O sistema tem componentes maduros, mas o fluxo de captura e memoria temporal nao e confiavel nem isolado.

## 2. Fontes e metodologia

Foram usadas evidencias por comando, codigo e teste real:

- leitura de `docs/01-architecture.md`, `docs/04-infrastructure.md`, `docs/05-blueprints.md`, `docs/06-gap-analysis.md`, `install.sh`, `scripts/register-mcp.sh`, `scripts/install_services.py`;
- inventario de systemd user units, processos, portas, bancos SQLite, MCPs e hooks Codex/Claude;
- execucao real de smoke, unit, integration, E2E, benchmark operacional, API auth, MCP stdio e escrita no worker `37700`;
- consulta externa pontual da documentacao oficial do `claude-mem`: `npx claude-mem install` e marketplace sao os caminhos de instalacao funcional; `npm install -g` instala apenas biblioteca/SDK e nao registra hooks/worker; o diretorio padrao e `~/.claude-mem`, com override por `CLAUDE_MEM_DATA_DIR` ([docs](https://docs.claude-mem.ai/installation), [GitHub](https://github.com/thedotmack/claude-mem)).

## 3. Objetivo do produto

O Hive-Mind pretende ser uma infraestrutura local-first de memoria persistente e multimodal para agentes. O desenho documentado combina:

- Atlas/Vault Obsidian em `cerebro/` como fonte canonica em Markdown;
- UMC SQLite (`hive_mind.db`) com FTS5, vetores, grafo, observacoes e auditabilidade;
- `claude-mem` para captura temporal de sessoes, prompts, observacoes e sumarizacao;
- Graphify para grafo de conhecimento do vault;
- NeuralMemory e RTK como backends auxiliares;
- MCP, CLI, REST, hooks e plugins para entrada/consulta por varios agentes.

## 4. Stakeholders

| Stakeholder | Interesse operacional |
|---|---|
| Usuario operador | Captura automatica real entre Codex, Claude, Gemini, OpenClaw e demais ferramentas, sem depender de memoria global. |
| Agentes de codigo | Contexto recuperavel por MCP/hooks, baixa latencia e sem duplicacao de instancias. |
| Instalador do produto | Instalar do zero de forma reproduzivel, idempotente e isolada dentro do projeto. |
| Vault/Obsidian | Ser fonte canonica legivel e sincronizavel. |
| Runtime local/systemd | Manter worker, API, watcher, sqlite-vec e timers sem loops nem portas duplicadas. |
| Segurança/privacidade | Evitar vazamento de tokens, abertura de API fora de loopback e dependencia global nao auditavel. |

## 5. Requisitos extraidos

### Funcionais

- Capturar prompts, sessoes, observacoes e resumos automaticamente.
- Injetar contexto relevante no inicio de sessao e sob demanda via MCP.
- Consultar UMC, vault, Graphify, NeuralMemory, RTK e memoria temporal.
- Consolidar observacoes em conhecimento persistente via Dream Cycle.
- Expor REST autenticado em `127.0.0.1:37702`.
- Manter watcher Graphify/Obsidian em tempo real.

### Tecnicos

- Runtime Python por `.venv` ou `uv run`, nunca Python global.
- Dependencias Python em `uv.lock`.
- Servicos systemd com `PATH` restrito.
- `claude-mem` project-local, com dados em `claude-mem/data`.
- `sqlite-vec` apontando para o banco ativo correto.
- Instalador idempotente e valido para maquina nova.

### Operacionais

- Uma unica instancia do worker `claude-mem` em `37700`.
- Sem referencias runtime a `~/.claude-mem` se o produto exigir isolamento.
- Testes reais falhando quando integracao for ignorada ou roteada para alvo errado.
- Restart e pos-reboot validados.

### Segurança

- API fail-closed quando `HIVE_MIND_API_KEY` nao existe.
- Bearer token em comparacao constante.
- CORS restrito.
- Segredos redigidos/encriptados no vault.
- Nenhum segredo ou banco pessoal versionado.

## 6. Arquitetura esperada

Fluxo esperado:

1. Agente dispara hooks de ciclo de vida.
2. Hooks chamam `claude-mem` para `context`, `session-init`, `observation`, `summarize`.
3. Worker `37700` grava sessoes/prompts/observacoes no banco do projeto.
4. sqlite-vec `37701` indexa esse mesmo banco.
5. Ponte `claude_mem_bridge.py` importa observacoes para `hive_mind.db`.
6. Dream Cycle consolida observacoes em neuronios/atlas.
7. MCP/API/CLI consultam memoria consolidada e temporal.

## 7. Estado observado

### 7.1 Portas e processos

| Porta | Estado observado | Processo | Avaliacao |
|---|---:|---|---|
| `37700` | aberta em `127.0.0.1` | `bun` | Vivo, mas usando `~/.claude-mem`. |
| `37701` | aberta em `127.0.0.1` | `.venv/bin/python plugins/sqlite-vec-worker/worker.py` | Vivo, mas indexando `~/.claude-mem/claude-mem.db`. |
| `37702` | aberta em `127.0.0.1` | `.venv/bin/python scripts/sinapse-api.py` | Vivo, loopback e autenticado. |
| `11434` | aberta em `127.0.0.1` | Ollama | Disponivel para modelos locais. |

`lsof` mostrou apenas o banco global aberto por `bun` e pelo sqlite-vec:

- `/home/michel/.claude-mem/claude-mem.db` aberto por `bun` e `python`;
- `Hive-Mind/claude-mem/data/claude-mem.db` nao estava aberto por processo ativo.

### 7.2 Bancos

| Banco | Integridade | Contagens relevantes |
|---|---|---|
| `hive_mind.db` | `PRAGMA integrity_check = ok` | `3339` neurons, `3117` synapses, `4692` observations, `3339` FTS, `3341` vector rowids. |
| `claude-mem/data/claude-mem.db` | `ok` | `10` prompts, `29` observations, `7` sdk_sessions, `4` summaries. |
| `~/.claude-mem/claude-mem.db` | operacional | `1013+` prompts, `4169+` observations, `756+` sdk_sessions, `496+` summaries antes do teste de escrita. |

O delta de volume prova que o banco do projeto nao e o banco vivo.

### 7.3 Servicos systemd

`sinapse-api.service` esta correto em termos de `.venv` e loopback.

`sinapse-claude-mem.service` esta definido como global:

- `Description=Sinapse Agent - claude-mem Worker (global)`;
- `WorkingDirectory=%h/.claude-mem`;
- `ExecStart=.../scripts/claude-mem-local.sh`.

`sinapse-sqlite-vec.service` aponta explicitamente para global:

- `Environment=CLAUDE_MEM_DB=%h/.claude-mem/claude-mem.db`;
- `Environment=FASTEMBED_CACHE_PATH=%h/.claude-mem/models`.

`sinapse-capture-realtime.service` nao define `CLAUDE_MEM_DATA_DIR`; `scripts/capture_core.py` cai no default `Path.home() / ".claude-mem"`.

### 7.4 Instalador

O `install.sh` contradiz o requisito project-local:

- `install.sh:13` declara "Instala claude-mem global";
- `install.sh:271-383` executa `npx -y claude-mem@13.6 install`, migra banco local para `~/.claude-mem` e declara sucesso com dados globais;
- `scripts/claude-mem-local.sh:6-8` afirma que os dados vivem em `~/.claude-mem` e o plugin vem de `~/.claude/plugins/marketplaces/thedotmack`;
- `scripts/install_services.py:21-35` gera unit global;
- `scripts/install_services.py:52-53` gera sqlite-vec global;
- `scripts/install_services.py:194` gera bridge global;
- `scripts/register-mcp.sh:93-97` e `154-158` registram `claude-mem-local` como `npx -y claude-mem@13.6 mcp-server` em alguns alvos, nao como checkout local fixado.

### 7.5 Claude-mem dentro do projeto

O diretorio `Hive-Mind/claude-mem` contem somente `data/`. Nao existem:

- `claude-mem/plugin/scripts/worker-service.cjs`;
- `claude-mem/plugin/scripts/mcp-server.cjs`;
- `claude-mem/package.json`;
- `claude-mem/bun.lock` ou `package-lock.json`.

Conclusao: **o claude-mem nao esta instalado como runtime completo dentro do repositorio**. Existe apenas uma pasta de dados local.

### 7.6 Codex, MCP e hooks

`codex mcp list` mostrou `sinapse-memory`, `claude-mem-local` e `neural-memory-local` registrados.

`sinapse-memory` por stdio inicializou e listou 11 tools, incluindo:

- `sinapse_query`;
- `sinapse_save_decision`;
- `sinapse_save_learning`;
- `sinapse_health`;
- `sinapse_temporal_search`;
- `sinapse_temporal_save`;
- `search_memories`.

Os hooks Codex existem em `.codex/hooks.json` e `~/.codex/hooks.json` e chamam:

- `hook codex context`;
- `hook codex session-init`;
- `hook codex observation`;
- `hook codex summarize`.

Porem os hooks resolvem plugin por fallback amplo: `CLAUDE_PLUGIN_ROOT`, cache Codex, cache Claude e marketplace Claude. Como nao existe plugin local em `Hive-Mind/claude-mem/plugin`, a resolucao tende a cache/global.

### 7.7 API REST

API em `37702`:

- `/api/v1/health` respondeu `{"status":"online","engine":"Hive-Mind Vault Ready"}`;
- POST sem Bearer em `/api/v1/query` retornou `401`;
- `scripts/sinapse-api.py:149-160` implementa fail-closed e comparacao constante;
- `scripts/sinapse-api.py:443-447` valida chave antes de subir e usa host/porta por env, default `127.0.0.1:37702`.

### 7.8 Pos-reboot

`sinapse-post-reboot-validation.service` esta `failed`. Logs recentes:

- `claude_mem_integrity: false`;
- `claude_mem_vectors_complete: true`;
- `global_claude_mem_worker_running: true`;
- `smoke_passed: true`.

O proprio validador foi alterado para esperar global (`scripts/validate_after_reboot.py:123-131`) e ainda assim falha por integridade/global worker.

## 8. Testes executados

| Area | Comando | Resultado |
|---|---|---|
| Suite completa | `./tests/run_all.sh` | Falhou: 3 suites passaram, 1 falhou. |
| Smoke | via runner | PASS: 16 passed, 0 failed. |
| Unit | via runner | PASS: 410 passed, 1 warning. |
| Unit via uv | `uv run pytest tests/unit/ -q` | PASS: 410 passed, 1 warning. |
| Integration | `HIVE_RUN_INTEGRATION=1 ... tests/integration/` | FAIL: 34 passed, 1 skipped, 1 failed. |
| Integration alvo | `HIVE_RUN_INTEGRATION=1 uv run pytest tests/integration/vision/test_chain_real.py::test_c4...` | FAIL: `DID NOT RAISE LLMChainFailure`. |
| E2E | via runner | PASS: 22 passed. |
| E2E via uv | `uv run pytest tests/e2e/ -q` | PASS: 22 passed. |
| MCP stdio | initialize + `tools/list` em `scripts/sinapse-mcp.py` | PASS: MCP respondeu e listou tools. |
| API sem auth | POST `/api/v1/query` sem Bearer | PASS: `401`. |
| Benchmark operacional | `.venv/bin/python scripts/operational_benchmark.py --iterations 5 --timeout 10 --no-fail` | FAIL: `ModuleNotFoundError: No module named 'sinapse_memory'`. |
| Security scan basico | `rg` para padroes de segredo excluindo bancos/caches | Sem segredo real exposto; apenas exemplos/docs/codigo de redactor. |
| Security tools | `pip_audit`, `bandit`, `safety` via `.venv` | Indisponiveis na `.venv`; nao executados. |
| Escrita real no worker | POST `37700/api/sessions/init`, `observations`, `summarize` com marcador | Sessao/prompt gravados no banco global; banco local permaneceu inalterado; observation/summary nao materializaram em 20s. |

## 9. Achados principais

### P0-1. Claude-mem vivo usa global, nao o projeto

**Descricao:** o worker `37700` esta vivo, mas abre `/home/michel/.claude-mem/claude-mem.db`. O banco local `Hive-Mind/claude-mem/data/claude-mem.db` nao recebe escrita.

**Impacto:** o produto nao atende isolamento. Dados entram no lugar errado; reinstalacao do produto do zero nao reproduz o estado esperado; Codex/Claude podem consultar memoria fora do escopo do projeto.

**Causa raiz provavel:** instalador e units foram orientados a global: `install.sh`, `scripts/claude-mem-local.sh`, `scripts/install_services.py`, `scripts/register-mcp.sh` e hooks com fallback global.

**Recomendacao:** reinstalar `claude-mem` como runtime project-local. Ha duas alternativas tecnicamente validas:

1. **npx com data dir local:** usar `npx claude-mem install` para registrar hooks, mas executar worker com `CLAUDE_MEM_DATA_DIR=$PROJECT/claude-mem/data` e `CLAUDE_PLUGIN_ROOT` controlado; validar que nenhum processo abre `~/.claude-mem`.
2. **clone/vendor local:** clonar/buildar `thedotmack/claude-mem` dentro do projeto, instalar dependencias Node/Bun localmente, apontar hooks/MCP/systemd para `Hive-Mind/claude-mem/plugin`, e fixar versao/lockfile.

Como requisito do produto e isolamento e reprodutibilidade, a opcao 2 e mais robusta; a opcao 1 e mais alinhada ao instalador oficial, mas precisa de guardrails fortes para nao cair no default global.

### P0-2. Nao existe runtime `claude-mem` dentro do repo

**Descricao:** `Hive-Mind/claude-mem` contem `data/` e nenhum plugin/worker/package.

**Impacto:** qualquer script que promete "local" precisa buscar codigo em cache/global. Se global for apagado, o `claude-mem` para.

**Causa raiz provavel:** migrou-se dados, mas nao se instalou o pacote/plugin dentro do repositorio.

**Recomendacao:** instalar o codigo real do `claude-mem` no projeto ou transformar o instalador em wrapper oficial com `CLAUDE_MEM_DATA_DIR` e plugin root explicitamente auditados.

### P0-3. sqlite-vec indexa o banco errado

**Descricao:** `37701/health` retornou `db=/home/michel/.claude-mem/claude-mem.db`. A unit tambem define `CLAUDE_MEM_DB=%h/.claude-mem/claude-mem.db`.

**Impacto:** busca semantica temporal retorna dados globais, nao dados do Hive local. Backfills/embeddings do projeto ficam fora do fluxo.

**Causa raiz provavel:** unit gerada por `scripts/install_services.py` usa global.

**Recomendacao:** apontar para `Hive-Mind/claude-mem/data/claude-mem.db`, usar cache de modelos local ou explicitamente documentado, e fazer o health falhar se o path nao for o esperado.

### P0-4. Captura real grava no global e nao gera observation no intervalo testado

**Descricao:** teste real com marcador `HIVE_AUDIT_WRITE_4ab819eb94c8` criou `sdk_session` e `user_prompt` no global. O banco local continuou com as mesmas contagens. A observation retornou `queued`, mas nao apareceu em `observations` nem em `session_summaries` apos 20s.

**Impacto:** mesmo quando o worker aceita entrada, a memoria util pode nao ser materializada. Isso explica sintomas de "nada esta sendo capturado" quando o usuario espera ver observacoes.

**Causa raiz provavel:** worker global + pipeline assincrono dependente de parser/LLM. Logs mostram historico de `OpenRouter returned non-XML... ignoring queued batch` e `database is locked`.

**Recomendacao:** corrigir isolamento primeiro; depois criar teste E2E que verifica `sdk_sessions`, `user_prompts`, `pending_messages`, `observations`, `session_summaries` e logs. O teste deve falhar se `queued` nao materializar dentro de timeout configurado.

### P1-5. Smoke tests aceitam falso positivo

**Descricao:** `tests/smoke/test_smoke.sh:47-50` valida apenas `37700/health`. Nao valida PID, cwd, banco aberto ou `CLAUDE_MEM_DATA_DIR`.

**Impacto:** smoke passa mesmo com worker global.

**Causa raiz provavel:** teste de disponibilidade substituiu teste de invariante operacional.

**Recomendacao:** adicionar assercoes:

- `lsof`/`proc` mostra `claude-mem/data/claude-mem.db`;
- `37701/health.db` e igual ao path local;
- nenhum processo abre `~/.claude-mem`;
- `claude-mem/plugin/scripts/worker-service.cjs` existe ou o modo `npx` esta explicitamente declarado.

### P1-6. Suite de integracao tem fallback silencioso indevido

**Descricao:** `test_c4_both_targets_dead_raises_chain_failure_with_both_exceptions` espera falha em dois alvos fake, mas a execucao tenta terceiro fallback real: `omniroute/oc/deepseek-v4-flash-free`. O teste falha porque nao levanta `LLMChainFailure`.

**Impacto:** a suite nao prova comportamento fail-closed da cadeia de LLM. Um fallback real pode mascarar erro de configuracao e usar provedor inesperado.

**Causa raiz provavel:** `core/auth.py:443-456` herda `HIVE_DREAMER_FALLBACK2_*`; `core/llm_client.py:321-327` adiciona `fallback2` na cadeia. O teste limpa apenas o fallback 1.

**Recomendacao:** no teste, limpar `HIVE_DREAMER_FALLBACK2_PROVIDER/MODEL`; no runtime, exigir opt-in explicito e registrar fallback2 no relatorio de decisao. A documentacao de `docs/01-architecture.md:848` diz que cascata automatica foi rejeitada; o comportamento atual contradiz essa regra.

### P1-7. Benchmark operacional nao roda

**Descricao:** `scripts/operational_benchmark.py` falha com `ModuleNotFoundError: No module named 'sinapse_memory'`.

**Impacto:** SLO de latencia e write-to-index nao e mensuravel; nao ha prova de performance/estresse operacional.

**Causa raiz provavel:** o benchmark importa `from sinapse_memory import _query_vault_knowledge`, mas o codigo real esta em `plugins/hermes/sinapse-memory.py`, com nome de arquivo que nao e modulo Python importavel diretamente.

**Recomendacao:** mover backend compartilhado para modulo importavel (`core/sinapse_memory_backend.py`) ou carregar o plugin via `importlib` como outros scripts/testes fazem. Depois rodar benchmark em CI e pos-install.

### P1-8. Pos-reboot falha e a logica do validador esta divergente do requisito

**Descricao:** `sinapse-post-reboot-validation.service` esta failed. O validador atual escolhe global se existir (`scripts/validate_after_reboot.py:126-131`) e reporta `global_claude_mem_worker_running`.

**Impacto:** sobrevivencia a reboot nao esta comprovada; o validador foi adaptado para uma arquitetura global que o produto agora rejeita.

**Causa raiz provavel:** cutover incompleto e mudancas contraditorias entre "global esperado" e "project-local requerido".

**Recomendacao:** reescrever validacao pos-reboot para exigir project-local e falhar com mensagem clara quando `~/.claude-mem` aparecer em cwd, fd ou cmdline.

### P1-9. Bridge para UMC le global por default

**Descricao:** `scripts/claude_mem_bridge.py:40-41` usa `~/.claude-mem/claude-mem.db` se `CLAUDE_MEM_DB` nao for definido. A unit define global.

**Impacto:** Dream Cycle recebe dados da memoria global, nao do banco local esperado.

**Causa raiz provavel:** default historico global.

**Recomendacao:** default deve ser `ROOT/claude-mem/data/claude-mem.db`; global deve exigir flag explicita de migracao/auditoria.

### P1-10. MCP `claude-mem-local` ainda tem ambiguidade de origem

**Descricao:** no Codex aparecem processos MCP do cache Claude (`~/.claude/plugins/cache/.../13.6.2`) e do cache Codex (`~/.codex/plugins/cache/.../13.6.0`). `scripts/claude-mem-local.sh` busca marketplace global.

**Impacto:** duas versoes podem coexistir e responder diferentemente; dificil auditar captura e busca.

**Causa raiz provavel:** wrappers de compatibilidade com fallback amplo.

**Recomendacao:** registrar MCP com um unico comando local deterministico. Se nao houver plugin local, o registro deve falhar, nao cair em global.

### P1-11. Chroma/uvx global ainda roda

**Descricao:** ha processo `uv tool uvx ... chroma-mcp ... --data-dir /home/michel/.claude-mem/chroma`.

**Impacto:** runtime depende de cache global e armazenamento global, contrariando isolamento.

**Causa raiz provavel:** worker/plugin global do `claude-mem` ainda habilitou componentes historicos.

**Recomendacao:** desativar Chroma se sqlite-vec for backend oficial, ou mover Chroma para diretorio local e lockado. Nao usar `uvx` como dependencia de runtime do produto.

### P2-12. Documentacao e metricas estao defasadas

**Descricao:** docs antigas falam em 191 testes; a suite unitaria atual tem 410 testes. Relatorios anteriores dizem que global nao e usado; runtime atual usa global.

**Impacto:** operadores e agentes tomam decisoes erradas.

**Causa raiz provavel:** atualizacao documental acompanhou intencao/plano, nao runtime verificado.

**Recomendacao:** docs de arquitetura e status devem ter secao "estado observado" separada de "estado alvo". Nao declarar pronto sem comando de evidencia.

### P2-13. Ferramentas de seguranca de dependencia nao estao instaladas

**Descricao:** `pip_audit`, `bandit` e `safety` nao existem na `.venv`.

**Impacto:** nao ha auditoria automatica de CVE/padroes Python na instalacao atual.

**Causa raiz provavel:** dependencias dev nao incluem scanners.

**Recomendacao:** adicionar grupo `security` no `pyproject.toml` com `pip-audit` e `bandit`, e job local/CI sem rede obrigatoria para regras estaticas.

## 10. Fluxos avaliados

### Codex -> hooks -> claude-mem

Estado: **parcial/quebrado para isolamento**.

- Hooks existem e chamam os nomes certos.
- Nao existe plugin local no repo.
- Worker vivo usa banco global.
- Escrita real no worker gravou sessao/prompt no global.

### claude-mem -> sqlite-vec

Estado: **funcional no alvo errado**.

- `37701` responde.
- Health mostra DB global.
- Busca semantica retorna dados globais.

### claude-mem -> bridge -> UMC

Estado: **conceitualmente implementado, operacionalmente desalinhado**.

- Bridge existe e preserva `project`.
- Default e unit usam global.
- Nao foi validado delta local porque worker local nao existe.

### Obsidian/vault -> Graphify -> UMC

Estado: **ativo, com alerta de sujeira operacional**.

- Graphify watch esta ativo via `.venv`.
- UMC tem FTS/vetores e integridade ok.
- Benchmark write-to-index nao executa por falha de import.

### REST

Estado: **bom para loopback e auth basica**.

- API esta em `127.0.0.1`.
- Health responde.
- Endpoint protegido nega sem token.

### MCP

Estado: **sinapse-memory funcional; claude-mem ambiguo**.

- MCP `sinapse-memory` responde por stdio.
- `claude-mem-local` esta registrado, mas sua origem real depende de wrappers/cache/global.

## 11. Dependencias e inventario

### Python

- `.venv` existe e `uv run` usa `/home/michel/Documentos/Projects/Hive-Mind/.venv/bin/python3`.
- `uv.lock` existe.
- `pyproject.toml` usa `graphifyy` e `neural-memory` por path local.

### Node/Bun

- Node `v22.22.3`.
- Bun local em `.tools/bin/bun`.
- Nao ha `package.json`/lockfile de `claude-mem` dentro de `Hive-Mind/claude-mem`.

### Globais remanescentes observados

- `/home/michel/.claude-mem/claude-mem.db`;
- `/home/michel/.claude-mem/chroma`;
- `/home/michel/.claude/plugins/marketplaces/thedotmack/plugin`;
- `/home/michel/.claude/plugins/cache/thedotmack/claude-mem/13.6.2`;
- `/home/michel/.codex/plugins/cache/claude-mem-local/claude-mem/13.6.0`;
- `uv tool uvx chroma-mcp` em runtime.

## 12. Riscos

| Risco | Severidade | Probabilidade | Impacto | Mitigacao |
|---|---:|---:|---|---|
| Captura grava no banco global | P0 | Alta | Perda de isolamento e confusao de memoria entre projetos | Reinstalar project-local e adicionar health invariant. |
| Apagar global quebra runtime | P0 | Alta | Worker/MCP param se global for removido | Instalar plugin/codigo dentro do projeto antes de remover global. |
| Testes aprovam alvo errado | P1 | Alta | Falso positivo de producao | Smoke/E2E devem verificar paths, fds e DB ativo. |
| Observation enfileirada nao materializa | P1 | Media/Alta | Memoria nao aparece para agentes | Teste com timeout e inspecao de `pending_messages`/logs. |
| Fallback LLM silencioso | P1 | Media | Uso de provedor inesperado e mascaramento de falhas | Remover fallback2 automatico em testes; exigir opt-in explicito. |
| Pos-reboot failed | P1 | Alta | Continuidade operacional nao comprovada | Corrigir validacao e rerodar apos restart/reboot real. |
| Benchmark/SLO quebrado | P1 | Alta | Sem medicao de performance | Tornar backend importavel e incluir benchmark no runner. |
| Dependencias de seguranca ausentes | P2 | Media | CVEs e padroes inseguros nao detectados | Adicionar `pip-audit`/`bandit` em grupo dev/security. |

## 13. Cronograma e marcos recomendados

### Marco 1 - Auditoria e congelamento do alvo

- Definir oficialmente se `claude-mem` sera clone/vendor ou `npx` com data dir local.
- Proibir runtime global em criterios de aceite.
- Criar backup auditavel dos bancos antes do cutover.

### Marco 2 - Reinstalacao local do claude-mem

- Instalar codigo/plugin real no projeto ou criar wrapper `npx` com envs obrigatorios.
- Systemd deve usar `WorkingDirectory=$PROJECT` e `CLAUDE_MEM_DATA_DIR=$PROJECT/claude-mem/data`.
- `sqlite-vec`, capture realtime, bridge e MCP devem apontar para o mesmo banco.

### Marco 3 - Testes de invariantes

- Adicionar smoke para DB path, fd path, cwd, PID e ausencia de `~/.claude-mem`.
- Teste E2E com marcador: prompt, session, observation, summary, FTS e semantic.
- Teste Codex/Claude real apos reiniciar agente.

### Marco 4 - Recovery e reboot

- Corrigir `validate_after_reboot.py`.
- Executar restart de servicos e reboot real.
- Anexar evidencia antes/depois.

### Marco 5 - Performance e seguranca

- Corrigir benchmark operacional.
- Adicionar scanners de dependencia/seguranca.
- Definir SLOs e executar carga controlada.

## 14. Criterios de aceite corrigidos

O sistema so deve ser considerado pronto quando todos estes itens passarem:

- `lsof` mostra que `37700` e `37701` abrem `Hive-Mind/claude-mem/data/claude-mem.db`.
- Nenhum processo em runtime referencia `~/.claude-mem`.
- `Hive-Mind/claude-mem` contem plugin/worker real ou wrapper oficial com envs travados e testados.
- Teste marcador cria `sdk_sessions`, `user_prompts`, `observations`, `session_summaries`, FTS e vetor no banco local.
- `tests/run_all.sh` passa integralmente.
- `scripts/operational_benchmark.py` passa e grava relatorio SLO.
- `sinapse-post-reboot-validation.service` passa apos reboot real.
- MCP `claude-mem-local` e hooks usam caminho local deterministico.
- `register-mcp.sh --check` valida nao apenas presenca, mas origem dos comandos.
- Docs declaram separadamente estado alvo e estado observado.

## 15. Conclusao

O Hive-Mind tem base tecnica boa no UMC, API, MCP `sinapse-memory`, testes unitarios e E2E. O problema nao e falta de componentes; e acoplamento operacional errado entre instalador, systemd, hooks e `claude-mem`.

A causa raiz mais provavel e uma decisao/alteracao anterior que transformou o `claude-mem` em instalacao global, enquanto o requisito do produto exige runtime project-local. O resultado e um sistema que "parece verde" em smoke/health, mas grava e busca a memoria temporal no lugar errado.

A proxima acao correta nao e apagar global primeiro. A sequencia segura e:

1. instalar o runtime real do `claude-mem` dentro do Hive-Mind ou configurar `npx` com `CLAUDE_MEM_DATA_DIR` local obrigatorio;
2. migrar/sincronizar dados;
3. trocar systemd/hooks/MCP/sqlite-vec/bridge para o banco local;
4. provar por teste marcador e `lsof`;
5. so entao remover/desabilitar o global.

Sem isso, uma instalacao nova continuara reproduzindo o problema.
