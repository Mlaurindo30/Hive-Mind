# Relatório de Auditoria Técnica — Hive-Mind

> **Tipo:** Auditoria de Projeto e Arquitetura de Software
> **Data:** 2026-06-10
> **Auditor:** Claude Code (Fable 5) — análise exaustiva de documentação, código-fonte, cronograma e fases
> **Escopo:** `scripts/`, `core/`, `plugins/`, `tests/`, `install.sh`, documentação de status e planejamento de fases

---

**TL;DR:** O projeto está conceitualmente maduro (Fase 10 de 12), mas há um descompasso grave entre o que a documentação declara como "CONCLUÍDO" e o estado real do código: a ingestão de documentos (pendência nº 1 da Fase 10) **quebra com `NameError` na primeira execução**, o Dream Cycle tem um bug de SQL que **ignora silenciosamente observações sem metadata**, há um **client_secret OAuth hardcoded** prestes a ser commitado, e praticamente todo o código das Fases 7–10 está **não-commitado no git**. A suíte de testes tem 1 falha unitária e 2 módulos de integração que nem coletam.

---

## 1. Diagnóstico de Status

**Maturidade declarada:** Fase 10 ("Deep Portal", multimodal) em finalização, com Fases 1–9 concluídas (UMC SQLite, busca híbrida, watcher real-time, Dream Cycle, P2P/UUID, Síntese Dialética).

**Maturidade real observada:**

| Dimensão | Estado |
|---|---|
| Arquitetura conceitual | Sólida e bem pensada (vault como fonte de verdade, UMC unificado, pipeline Distiller→Validator→Router com Pydantic) |
| Código das Fases 7–10 | Escrito, mas **~25 arquivos novos não-commitados** (`dream_cycle.py`, `core/auth.py`, `audit_memory.py`, `document_ingest.py`, `semantic_diff.py`, `core/schemas/`...) — o último commit é da tabela `visual_memories` |
| Pendências da Fase 10 | `document_ingest.py` existe mas **não funciona** (bug fatal); `install.sh` e `requirements.txt` **não foram atualizados** com nenhuma dependência das fases 7–10 |
| Testes | 70/71 unitários passam; 1 falha (tools_list desatualizado); 2 módulos de integração com erro de coleta; doc afirma "103 testes", há 110 coletáveis |
| Governança | Repo sendo modificado por múltiplos agentes simultaneamente — o `ARCHITECTURE.md` da raiz foi movido para `docs/` *durante esta auditoria* |

**Veredito:** o projeto está entre a Fase 9 e 10 *de fato*, não "Fase 10 em finalização". A velocidade de feature está superando a capacidade de consolidação (commits, testes, instalador, docs) — padrão clássico de dívida acumulando em projeto dirigido por agentes de IA.

---

## 2. Auditoria Técnica e de Código

### 🔴 Críticos (quebram funcionalidade ou expõem segredos)

**C1. `scripts/document_ingest.py:92` — variável usada antes de definir.** `json.dumps(metadata)` é chamado na linha 92, mas `metadata` só é definida na linha 97. Todo documento PDF/DOCX dispara `NameError`; o erro é engolido pelo `try/except` genérico do `dream_cycle.py:398-402`, então a falha é invisível. A entrega central da Fase 10 está inoperante.

**C2. `core/auth.py:28` — Google OAuth `client_secret` hardcoded** (`GOCSPX-...`), além de um `client_id` de produção. O arquivo está untracked mas **não está no `.gitignore`** — o próximo `git add -A` publica o segredo. Agravantes: tokens de acesso/refresh são persistidos em plaintext no `.env` (que já tem 26KB), e os loops de polling OAuth (`poll_oauth_token`) não têm timeout — podem travar para sempre.

**C3. `scripts/dream_cycle.py:409` — observações com metadata NULL nunca são processadas.** Em SQLite, `NULL NOT LIKE '%...%'` resulta em NULL (falso). Como `add_observation()` e `_umc_save_observation()` gravam `metadata = NULL` quando não há metadata, **essas observações são invisíveis para o Dream Cycle para sempre** — e se passassem, `json.loads(o['metadata'])` na linha 431 quebraria com NULL.

**C4. `dream_cycle.py:431-435` — arquivamento antes da validação.** As observações são marcadas `archived: true` e commitadas *antes* de o pipeline Distiller/Validator rodar. Se a LLM falhar nas 3 tentativas, os dados são dados como processados e a "quarentena" mencionada no log **não existe no código** — perda silenciosa de consolidação.

**C5. `scripts/sinapse-api.py` — postura de segurança frágil para uma API "Cloud/VPS":**
- API key default `"hive_mind_default_secret"` (linha 136) — quem não configurar `HIVE_MIND_API_KEY` sobe uma API autenticável com segredo público, em `0.0.0.0`.
- `CORS allow_origins=["*"]` com `allow_credentials=True`.
- Comparação de token com `!=` (vazamento por timing; usar `secrets.compare_digest`).
- **Defaults incompatíveis:** o plugin cliente usa default `"sinapse_default_secret_key"` (`sinapse-memory.py:170`) e URL `localhost:8000`, enquanto a API usa `"hive_mind_default_secret"` e porta `37702`. O README ainda instrui porta 8000. Na configuração padrão, cliente e servidor **nunca se autenticam**.

**C6. Bancos de dados pessoais sem proteção no git.** `hive_mind.db` (4.9MB de memória pessoal), `hive_mind.db.bak` e `banco.db` (0 bytes, lixo) **não estão no `.gitignore`** — `git check-ignore` confirma. Um `git add -A` publica sua memória inteira.

### 🟠 Altos (lógica incorreta ou comportamento enganoso)

**A1. `sinapse-memory.py:42 vs 53` — dois defaults de `SINAPSE_HOME` no mesmo arquivo:** o import do core usa `~/Documentos/Projects/Hive-Mind`, mas os paths do vault usam `~/Documentos/Projects/sinapse_agent`. Sem a env var, o plugin lê o UMC de um projeto e escreve notas em outro. Os tracebacks do pytest apontando para `sinapse_agent/` sugerem que essa contaminação já ocorre.

**A2. Circuit breaker pune "sem resultados" como falha** (`_query_vault_knowledge:800-802`). Backend que legitimamente não tem hits para 3 queries é desligado por 30s — em vault pequeno, isso desliga backends saudáveis o tempo todo. Falha de rede e resultado vazio precisam ser sinais distintos.

**A3. `sinapse-mcp.py:_session_end` zera os buffers antes de gravar** (`sm._session_decisions = []` e depois `_update_current_state([], [], summary)`). O `Current State.md` sempre registra "Nenhuma decisão registrada", descartando o histórico real da sessão. Mesmo padrão em `sinapse-write.py:76-78`.

**A4. `run_synthesis_cycle` (dream_cycle.py:261) — join de path inconsistente:** monta `cerebro/atlas / neuron['source_file']`, mas `audit_memory.reindex_neuron` grava `source_file` como **caminho absoluto** (`str(file_path)`). `Path` com segundo argumento absoluto descarta o prefixo — funciona por acidente hoje e quebra se a origem gravar caminho relativo. Além disso, a síntese **sobrescreve o arquivo perdendo o frontmatter original** (admitido em comentário no código).

**A5. Vault de segredos sem caminho de volta:** `encrypt_and_vault` criptografa com Fernet e grava na tabela `vault`, mas **não existe endpoint nem função de decriptação/recuperação** — os segredos viram órfãos permanentes. Os regex estão desatualizados (não cobrem `sk-proj-...` da OpenAI, por exemplo) e, se o banco falhar, o fallback redige destrutivamente sem guardar nada.

**A6. Concorrência SQLite sem `busy_timeout`:** watcher, Dream Cycle, API REST e MCP escrevem no mesmo `hive_mind.db`. WAL ajuda leitores, mas `get_connection()` não define `timeout`/`busy_timeout` — `database is locked` esporádico é questão de tempo.

**A7. `core/auth.py:312-319` — modelos fictícios injetados incondicionalmente:** a lista "Codex elites" (`gpt-5.5`, `gpt-5.4-pro`...) é adicionada à descoberta de modelos mesmo que a conta não tenha acesso, e `discover_models_realtime` usa `except: pass` silencioso em todo o loop. O usuário pode selecionar um modelo inexistente e só descobrir quando o Dream Cycle falhar à noite.

### 🟡 Médios (dívida técnica)

- **`execute_insert` interpola nomes de tabela/coluna em f-string** (`core/database.py:66`) — hoje os chamadores são internos, mas é um footgun de SQL injection se algum dia receber chaves vindas de payload.
- **`_save_learning` deduplica por substring do título** — títulos curtos ("fix", "bug") causam falsos positivos e aprendizados descartados.
- **`sync_claude_mem_to_vault` grava observações genéricas como *decisões*** em `work/active/` — polui a categoria mais nobre do vault.
- **`_FS_CACHE` cresce sem limite** (uma entrada por query única, nunca podada).
- **`health_check` exige TODOS os backends saudáveis** para `healthy: true` — RTK ausente torna o sistema inteiro "doente", banalizando o sinal.
- **upsert em `search_vec` (vec0)** pode não suportar `ON CONFLICT` dependendo da versão do sqlite-vec; a exceção é apenas printada, deixando embeddings dessincronizados em silêncio.
- **Fase visual só processa `*.png`** — JPG/WebP ficam na inbox para sempre, sem aviso.

---

## 3. Análise de Lacunas (Gaps) e Estrutura

**G1. Trabalho das Fases 7–10 inteiro fora do git.** Não há um único commit de `dream_cycle.py`, `core/auth.py`, `core/schemas/`, `audit_memory.py`, `semantic_diff.py` etc. Para um projeto cuja tese é "memória persistente e P2P sync", o próprio código não tem persistência versionada. Qualquer `git clean` ou sync mal configurado do Syncthing destrói semanas de trabalho.

**G2. Documentação tripla e contraditória.** `PROJECT_STATUS.md` diz Fases 9 e 10 concluídas/em finalização; `IMPLEMENTATION.md` lista as mesmas fases como "Próximas Fases" e tem entregas fora de ordem (Entrega 13 de 09/06 antes da Entrega 12 de 10/06); o `README.md` ainda descreve a Camada 2 como "SQLite + Chroma" (substituído pelo sqlite-vec) e mostra contagens de grafo divergentes na mesma página (491 vs 1328 nodes). Não há fonte única de verdade sobre o estado do projeto — irônico, dado o lema do vault.

**G3. ~~`docs/ARCHITECTURE.md` corrompido por automação~~ — ERRATA (10/06):** falso positivo. Verificação com consciência de code fences mostrou que os blocos `## Last Update:`/`## Session:` estão dentro de um fence ```` ```markdown ```` na seção 3 (exemplo documentado do formato de `current-state.md`) e de um heredoc bash na seção 6. O documento está íntegro. Permanece válida apenas a observação da movimentação raiz→`docs/` sem atualização de referências.

**G4. Instalador e dependências desatualizados em 3 fases.** `requirements.txt` tem só 4 pacotes (stack FastAPI); faltam `requests`, `pyyaml`, `pydantic`, `numpy`, `fastembed`, `sqlite-vec`, `cryptography`, `slowapi`, `python-dotenv`, `mss`, `watchdog`, `PyMuPDF`, `python-docx`. O `install.sh` (10 etapas) não menciona nenhum deles. Um clone limpo + `./install.sh` produz um sistema onde Dream Cycle, API e captura de tela simplesmente não importam.

**G5. Dois sistemas de numeração de fases coexistem** em `cerebro/work/active/`: as Fases 1–12 do Hive-Mind e as "PHASE-33/34" (TTS do Thoth). Sem namespace, o planejamento fica ambíguo para humanos e para os próprios agentes que consultam o vault.

**G6. Testes não acompanharam as fases.** Os 110 testes cobrem o plugin e o MCP (Fases 1–5). **Zero testes** para `dream_cycle`, `semantic_diff`, `audit_memory`, `document_ingest`, `core/auth`, `core/database` — exatamente o código mais novo e mais frágil (vide C1/C3). O CI (`.github/workflows/test.yml`) está vermelho pela falha do `test_tools_list`. O excelente `docs/06-gap-analysis.md` (23/05) nunca foi revisitado.

**G7. Monorepo com 4 sub-repos vendorizados** (`claude-mem`, `neural-memory`, `rtk`, `graphify`) ignorados no `.gitignore` mas presentes no disco — sem submodules, sem pinning de versão, sem estratégia de atualização documentada. Reprodutibilidade do ambiente depende do estado do disco de uma máquina.

**G8. `sinapse-memory.py` com 1536 linhas** viola o padrão "Files under 500 lines" do próprio `CLAUDE.md` do projeto. Ele acumula 5 backends, circuit breaker, fusão de contexto, hooks, escrita no vault e health check num único módulo importado por 3 entry points distintos via `importlib` manual.

---

## 4. Plano de Ação e Melhorias

### P0 — Esta semana (segurança e perda de dados)

1. **Revogar e rotacionar o OAuth client do Google** exposto em `core/auth.py`; mover `client_id`/`client_secret` para o `.env` e adicionar `core/auth.py` a uma revisão antes do primeiro commit. Adicionar ao `.gitignore`: `hive_mind.db*`, `banco.db`, `*.db.bak`.
2. **Corrigir `document_ingest.py`**: mover a definição de `metadata` (linhas 97–102) para antes do INSERT em `document_memories`, com metadata próprio para o documento. Adicionar um teste unitário com um DOCX mínimo de fixture.
3. **Corrigir a query do Dream Cycle**: trocar o filtro por uma coluna real — `ALTER TABLE observations ADD COLUMN archived INTEGER DEFAULT 0` + índice — e usar `WHERE archived = 0 ORDER BY created_at LIMIT 30`. Filtro por `LIKE` em JSON é frágil e não usa índice.
4. **Arquivar só após sucesso**: mover o `UPDATE ... archived` para depois do `agent_route` retornar; em falha, marcar `status='quarantine'` (implementando a quarentena prometida).
5. **Commitar as Fases 7–10** em commits temáticos (após os fixes 1–4), restaurando o CI verde: atualizar `test_tools_list` com `sinapse_capture_screen` e consertar os 2 módulos de integração que apontam para `sinapse_agent/`.
6. **Remover defaults de API key**: a API deve **recusar iniciar** sem `HIVE_MIND_API_KEY`; o plugin deve falhar explicitamente sem `SINAPSE_API_KEY`. Unificar a porta (decidir 8000 ou 37702) em README, plugin e API. Usar `secrets.compare_digest` e restringir CORS a origens configuráveis.

### P1 — Próximas 2 semanas (correção de lógica)

7. **Unificar `SINAPSE_HOME`** numa única constante resolvida uma vez (default = raiz do repo via `Path(__file__)`), eliminando o path fantasma `sinapse_agent`.
8. **Circuit breaker**: registrar falha somente em exceção/timeout; resultado vazio é sucesso operacional.
9. **Sessões MCP/CLI**: capturar `_session_decisions`/`_session_learnings` *antes* de zerar e passá-los a `_update_current_state`.
10. **Normalizar `source_file`** como caminho **relativo ao vault** em todos os escritores (`audit_memory`, graphify export, síntese) e fazer a síntese preservar frontmatter (ler, atualizar campos, reescrever).
11. **SQLite multi-escritor**: `sqlite3.connect(DB_PATH, timeout=10)` + `PRAGMA busy_timeout=5000` em `get_connection()`.
12. **Vault de segredos**: criar endpoint autenticado de recuperação (ou remover a feature e fazer redaction pura — meio-termo atual é o pior dos mundos); atualizar os regex de segredos.
13. **Dependências**: gerar `requirements.txt` completo (ou migrar para `pyproject.toml` com extras `[api]`, `[dreamer]`, `[vision]`, `[docs]`) e adicionar a etapa de instalação no `install.sh` — fecha a pendência nº 4 da Fase 10.

### P2 — Próximo mês (escalabilidade e qualidade)

14. **Quebrar `sinapse-memory.py`** em pacote (`backends/`, `writers/`, `hooks.py`, `config.py`) instalável (`pip install -e .`), eliminando os 3 carregamentos via `importlib` manual — isso também elimina a classe de bugs do path duplo.
15. **Cobertura de testes para o núcleo novo**: `dream_cycle` (com LLM mockada), `document_ingest`, `audit_memory`, `core/database` — os testes de C1/C3 teriam pego ambos os bugs antes do "CONCLUÍDO".
16. **Consolidar a documentação de status**: eleger `PROJECT_STATUS.md` como única fonte (gerável a partir do vault, já que o projeto é um sistema de memória), reduzir `IMPLEMENTATION.md` a changelog e regenerar o README (camadas reais, portas reais, contagens reais). Limpar os blocos de sessão injetados no `ARCHITECTURE.md`.
17. **Performance da busca híbrida**: `query_hybrid` hidrata neurônios com N queries individuais (`SELECT ... WHERE id = ?` em loop) — trocar por um único `IN (...)`; implementar RRF de verdade (o comentário promete, o código só concatena). O `_backend_filesystem` lê todos os `.md` do vault a cada query fora do TTL de 30s — com vault crescendo, isso vira o gargalo; considerar delegar ao FTS5 que já existe no UMC.
18. **Governança multi-agente**: definir convenção de fases com namespace (`HM-10`, `THOTH-34`), e regra de que nenhum agente marca fase como concluída sem (a) commit, (b) teste cobrindo a entrega, (c) CI verde — exatamente o gap que esta auditoria encontrou entre o declarado e o real.

---

## Síntese Final

A arquitetura do Hive-Mind é ambiciosa e o desenho (UMC + vault + pipeline validado por Pydantic) é genuinamente bom. O risco do projeto hoje não é arquitetural — é **operacional**: código crítico não versionado, entregas declaradas prontas sem execução real, e três vetores de vazamento de segredo a um `git add` de distância. As 6 ações P0 cabem em poucos dias de trabalho e eliminam todo o risco de classe crítica.

---

## Status de Implementação (atualizado 2026-06-10, mesma data)

Plano executado por 3 agentes paralelos + orquestrador. Commits: `eff2e8f` (gitignore), `dd87e4c` (fases 7–10 + fixes), `d0b8cd1` (testes), `e3cbe05` (docs/instalador).

| Item | Status | Observação |
|---|---|---|
| P0-1 Segredo OAuth | ✅ Código limpo; credenciais migradas para `.env`; dbs no `.gitignore` | ⚠️ **Rotação do client_secret no Google Cloud Console é manual e ainda pendente** |
| P0-2 document_ingest | ✅ | `doc_metadata` definido antes do INSERT + teste de regressão AST |
| P0-3 Fila Dream Cycle | ✅ | Coluna `archived` + índice + migração aplicada ao banco real (19 observações represadas destravadas) |
| P0-4 Quarentena | ✅ | `archived=2` em falha de pipeline/router; arquivamento só pós-sucesso |
| P0-5 Commits + CI verde | ✅ | 74 unit passed, 116 coletados sem erro |
| P0-6 API keys/CORS | ✅ | Fail-closed, `compare_digest`, CORS configurável, porta unificada 37702 |
| P1-7 SINAPSE_HOME | ✅ | Constante única; path fantasma `sinapse_agent` eliminado |
| P1-8 Circuit breaker | ✅ | Só exceção/timeout conta como falha |
| P1-9 Session-end | ✅ | Buffers capturados antes de zerar (MCP + CLI) |
| P1-10 source_file relativo | ✅ | `audit_memory` grava relpath; síntese normaliza e preserva frontmatter |
| P1-11 busy_timeout | ✅ | `timeout=10` + `PRAGMA busy_timeout=5000` |
| P1-12 Vault recovery | ✅ | `GET /api/v1/vault/{id}` autenticado + regexes atualizados (`sk-proj-`) |
| P1-13 Dependências | ✅ | `requirements.txt` completo + etapa [2/12] no `install.sh` |
| P2-14 Quebrar plugin em pacote | ⏳ Pendente | Mês — exige refactor dos 3 entry points |
| P2-15 Testes do núcleo novo | 🟡 Parcial | Regressões C1/C3 criadas; `dream_cycle` com LLM mockada pendente |
| P2-16 Consolidar docs | 🟡 Parcial | README/IMPLEMENTATION/PROJECT_STATUS alinhados; G3 era falso positivo (errata acima) |
| P2-17 Performance busca | 🟡 Parcial | Hidratação em SELECT IN feita; RRF real e delegação do FS-backend ao FTS5 pendentes |
| P2-18 Governança de fases | ⏳ Pendente | Convenção de namespace HM-/THOTH- a definir com o time |
