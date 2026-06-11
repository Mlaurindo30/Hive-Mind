# 06 — Análise de Gaps e Status de Auditoria

> **Hive-Mind v2.0.0** — Auditoria técnica, gaps do instalador e status de correções.
> **Última atualização:** 2026-06-10 | **Total de testes:** 116

---

## 1. Auditoria Técnica — 2026-06-10

A auditoria técnica completa identificou 5 achados (C1-C5). Todos tratados.

| ID | Severidade | Achado | Status |
|----|-----------|--------|--------|
| C1 | 🔴 CRÍTICA | `archived` col filter usava `LIKE` em JSON metadata (falso positivo/negativo no Dream Cycle) | ✅ CORRIGIDO — colunas `archived INTEGER` real com INDEX |
| C2 | 🔴 CRÍTICA | `GOOGLE_OAUTH_CLIENT_SECRET` estava hardcoded como `GOCSPX-...` em `core/auth.py` | ✅ CORRIGIDO — agora `_env("GOOGLE_OAUTH_CLIENT_SECRET")`; **⚠️ rotacionar no Google Cloud Console** |
| C3 | 🟡 ALTA | Bug de metadata em `document_ingest.py` — campo `author` não passava para INSERT | ✅ CORRIGIDO — metadata preservado no INSERT |
| C4 | 🟡 ALTA | `install.sh` não incluía `pypdf`, `python-docx`, `PyMuPDF`, `mss` | ✅ CORRIGIDO — `requirements.txt` atualizado + etapa no `install.sh` |
| C5 | 🟢 MÉDIA | `dream_cycle.py` não usava modelo configurado em `HIVE_DREAMER_MODEL` para etapa Vision | ✅ CORRIGIDO — obedece `HIVE_DREAMER_PROVIDER/MODEL` sem exceção |

---

## 2. Análise de Gaps do install.sh — Histórico (2026-05-23)

O `install.sh` (10 passos, 625 linhas) foi auditado contra a implementação real.

### Gap #1: Passo 3 sem conteúdo real

**Declarado:** `[3/9] Registrando skills nos agentes...`
**Problema:** passo 3 era continuação do Graphify; skills não eram copiadas.
**Severidade:** 🔴 ALTA | **Status:** ✅ CORRIGIDO — skills copiadas para `~/.hermes/skills/`, `~/.claude/skills/`

---

### Gap #2: MCP configurado apenas para Hermes

**Declarado:** `[7/9] Configurando servidores MCP...`
**Problema:** verificava apenas `command -v hermes`; Claude Code e Codex não recebiam config MCP.
**Severidade:** 🔴 ALTA | **Status:** ✅ CORRIGIDO — passo 10 configura Claude Code, Codex, OpenClaw, Gemini CLI

---

### Gap #3: Header vs execução — numeração inconsistente

**Problema:** Header declarava 9 passos, execução tinha 10; passo [3/9] era na realidade Graphify.
**Severidade:** 🟡 MÉDIA | **Status:** ✅ CORRIGIDO — header atualizado para 10 passos

---

### Gap #4: Paths hardcoded em plugin.yaml

**Problema:** `~/Documentos/Projects/sinapse_agent/cerebro/` hardcoded ignorava `SINAPSE_HOME`.
**Severidade:** 🟡 MÉDIA | **Status:** ✅ CORRIGIDO — `$PROJECT_ROOT/cerebro/` usado

---

### Gap #5: Sem health check pós-instalação

**Problema:** instalação podia parecer bem-sucedida com backends quebrados.
**Severidade:** 🟡 MÉDIA | **Status:** ✅ CORRIGIDO — `sinapse-write.py health` executado antes do banner final

---

### Gap #6: Hooks não verificados

**Problema:** `sinapse-hook.py` poderia não estar executável.
**Severidade:** 🟢 BAIXA | **Status:** ✅ CORRIGIDO — `settings.json`/`hooks.json` atualizados

---

### Gap #7: MCP para demais agentes

**Problema:** OpenClaw e Gemini CLI sem auto-config.
**Severidade:** 🟢 BAIXA | **Status:** ✅ CORRIGIDO — detectores adicionados no passo 10

---

### Gap #8: pyyaml não instalado explicitamente

**Problema:** `_load_config()` falhava silenciosamente sem pyyaml.
**Severidade:** 🟢 BAIXA | **Status:** ✅ CORRIGIDO — `pip install pyyaml` adicionado

---

### Gap #9: recover.sh não mencionado

**Severidade:** 🟢 BAIXA | **Status:** ✅ CORRIGIDO — menção adicionada no banner pós-instalação

---

### Gap #10: Permissões de execução

**Problema:** apenas `sinapse-write.py` e `sinapse-mcp.py` recebiam `chmod +x`.
**Severidade:** 🟢 BAIXA | **Status:** ✅ CORRIGIDO — `chmod +x scripts/*.sh scripts/*.py`

---

### Gap #11: Cron com path absoluto hardcoded

**Problema:** `$PROJECT_ROOT` no cron quebrava se projeto fosse movido.
**Severidade:** 🟢 BAIXA | **Status:** ✅ CORRIGIDO — `SINAPSE_HOME` usado

---

### Gap #12: Agentes sem install_method no sinapse.yaml

**Problema:** Kilocode, Cursor, OpenCode listados no sinapse.yaml mas sem autoconfig.
**Severidade:** 🟡 MÉDIA | **Status:** ✅ CORRIGIDO — detectores para Kilo Code, OpenCode, Cursor no passo 10

---

### Gap #13: Testes não executados na instalação

**Problema:** instalação não validava a própria instalação com testes.
**Severidade:** 🟢 BAIXA | **Status:** ✅ CORRIGIDO — flag `--with-tests` adicionada

---

### Gap #14: ~~Docker support~~

**Status:** ❌ REMOVIDO — gap inválido. Docker nunca fez parte do projeto.

---

### Gap #15: Sem validação da versão do Python

**Problema:** versão detectada mas não validada (Python 3.8 passava e quebrava depois).
**Severidade:** 🟡 MÉDIA | **Status:** ✅ CORRIGIDO — `if` com `exit 1` se < 3.10

---

## 3. Sumário de Gaps

| Severidade | Quantidade | Status |
|-----------|-----------|--------|
| 🔴 ALTA | 2 | Todos corrigidos |
| 🟡 MÉDIA | 5 | Todos corrigidos |
| 🟢 BAIXA | 7 | Todos corrigidos |

**Status geral:** 14/15 corrigidos, 1 removido (gap inválido), 0 pendentes.

---

## 4. Métricas de Qualidade (2026-06-10)

| Métrica | Valor |
|---------|-------|
| Total de testes | **116** |
| Smoke tests | 8 |
| Testes unitários | 72 |
| Testes de integração | 28 |
| Testes e2e | 8 |
| Cobertura (estimada) | ~78% |
| Testes que chamam LLM real | **0** (apenas `test_synthesis.py` de integração, com flag explícita) |
| Testes que usam `hive_mind.db` real | **0** (in-memory SQLite) |

### 4.1 Suítes de Teste

| Arquivo / Diretório | Tipo | Foco / Detalhes |
|----------------------|------|-----------------|
| `tests/smoke/` | smoke | Testes de fumaça de binários, imports e inicialização rápida do daemon. |
| `tests/unit/test_backend_claude_mem.py` | unit | Testes unitários para o backend de busca temporal claude-mem. |
| `tests/unit/test_backend_graphify.py` | unit | Testes unitários para o backend de busca estrutural graphify. |
| `tests/unit/test_backend_nmem.py` | unit | Testes unitários para o backend de busca associativo nmem. |
| `tests/unit/test_dream_queue.py` | unit | Fila de consolidação de fatos e status `archived` (Regressão C1). |
| `tests/unit/test_format_context.py` | unit | Formatação e fusão de contexto semântico e estrutural. |
| `tests/unit/test_query_engine.py` | unit | Motor de busca híbrido paralela, circuit breaker e orquestração. |
| `tests/unit/test_sinapse_mcp.py` | unit | Validação do protocolo do servidor MCP de memória. |
| `tests/unit/test_sinapse_write_cli.py` | unit | Validação do utilitário CLI standalone de escrita. |
| `tests/unit/test_sinapse_zettelkasten.py` | unit | Testes de particionamento Zettelkasten para notas atômicas. |
| `tests/unit/test_write_helpers.py` | unit | Escrita atômica via `os.replace`, higienização de slugs e frontmatter YAML. |
| `tests/integration/` | integration | Testes de integração de APIs, cron jobs, banco SQLite UMC e fluxos híbridos. |
| `tests/test_synthesis.py` | integration | Validação do motor de síntese (Dream Cycle) com LLM real (opt-in). |
| `tests/test_portal_generator.py` | integration | Geração do canvas e portal Obsidian. |
| `tests/e2e/` | e2e | Testes de ponta a ponta (concorrência, degradação graciosa, tolerância a falhas). |

### 4.2 Política de Testes

- **Testes unitários** nunca chamam LLM real nem dependem de `hive_mind.db` em disco
- **Testes de integração** podem chamar LLM se `HIVE_DREAMER_PROVIDER` estiver no `.env` e `--integration` flag passada
- **Nomes de modelos nunca são hardcoded** nos testes — lidos de variável de ambiente
- A suíte completa deve passar em qualquer máquina sem API keys

---

## 5. Próximas Melhorias (Backlog)

| Prioridade | Item |
|-----------|------|
| 🟡 MÉDIA | Adicionar `--with-tests` ao CI/CD pipeline |
| 🟡 MÉDIA | Cobertura de testes para `semantic_diff.py` (Phase 9) |
| 🟢 BAIXA | Teste e2e para fluxo P2P completo (Syncthing → audit → merge) |
| 🟢 BAIXA | Benchmark de performance (KNN 10k vetores, FTS5 100k docs) |
| 🟢 BAIXA | Test fixtures compartilhadas em `tests/conftest.py` |
