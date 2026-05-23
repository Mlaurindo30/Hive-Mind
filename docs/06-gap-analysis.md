# 06 — Análise de Gaps: install.sh vs Implementação Real

> **Sinapse Agent v1.1.0** — Auditoria do script de instalação.
> **Data:** 2026-05-23 | **Total de gaps:** 15

---

## 1. Metodologia

O `install.sh` (625 linhas, 10 passos declarados) foi comparado contra:
1. Código real implementado (plugin 984 linhas, scripts, configs)
2. Configurações de hooks (`.claude/settings.json`, `.codex/hooks.json`)
3. Documentação (`sinapse.yaml`, `ARCHITECTURE.md`)
4. Testes (103 testes em 3 níveis)

---

## 2. Matriz de Gaps

### Gap #1: Passo 3 declara "Registra skills nos agentes" mas está vazio

**Arquivo:** `install.sh`, linha 114
**Declarado:** `[3/9] Registrando skills nos agentes...`
**Implementado:** O passo 3 existe no header (`#   3. Registra skills...`) mas no corpo do script o passo 3 foi **fundido com o passo 2**. A label `[3/9]` aparece mas o conteúdo não é sobre skills — é sobre Graphify.

**Impacto:** Skills (como `skills/sinapse-consulta.md`) NÃO são copiadas para os agentes.
**Severidade:** 🔴 ALTA
**Correção:** Criar passo 3 separado que copia `skills/sinapse-consulta.md` para `~/.hermes/skills/`, `~/.claude/skills/`, etc.

---

### Gap #2: Passo 7 só configura MCP para Hermes

**Arquivo:** `install.sh`, linha 394
**Declarado:** `[7/9] Configurando servidores MCP...`
**Implementado:** Só verifica `command -v hermes`. Se Hermes não detectado, pula toda a config MCP. Claude Code, Codex CLI, Kilo Code, OpenClaw NÃO recebem config MCP no passo 7.

**Impacto:** Agentes não-Hermes não recebem MCP config automaticamente.
**Severidade:** 🔴 ALTA (parcialmente mitigado pelo passo 10)
**Correção:** Parcialmente resolvido pelo passo 10 (implementado em 2026-05-23). O passo 7 deveria ser renomeado para "Configurando MCP para Hermes" e o passo 10 cobre os demais.

---

### Gap #3: Passo 3 (header) vs Passo 3 (execução) — numeração inconsistente

**Arquivo:** `install.sh`
**Header declara:**
```
#   1. Verifica dependências
#   2. Instala Graphify
#   3. Configura claude-mem
#   4. Instala NeuralMemory
#   5. Configura RTK plugin
#   6. Registra skills
#   7. Configura MCP servers
#   8. Instala cron job
#   9. Instala/atualiza plugin sinapse-memory
```

**Execução real:**
```
[1/9] Verificando dependências...
[2/9] Instalando Graphify...
[3/9] Registrando skills...  ← na verdade é continuação do Graphify
[4/9] Configurando claude-mem...
[5/9] Instalando NeuralMemory...
[6/9] Compilando RTK...
[7/9] Configurando servidores MCP...
[8/9] Configurando cron...
[9/9] Instalando plugin sinapse-memory...
[10/10] Configurando agentes externos... ← adicionado, não está no header
```

**Severidade:** 🟡 MÉDIA
**Correção:** Atualizar header para refletir 10 passos reais e adicionar passo "Registrar skills" como passo real.

---

### Gap #4: Passo 9 (plugin sinapse-memory) — paths hardcoded no plugin.yaml

**Arquivo:** `install.sh`, linha 499
**Código:**
```yaml
graph_json: "~/Documentos/Projects/sinapse_agent/cerebro/graphify-out/graph.json"
root: "~/Documentos/Projects/sinapse_agent/cerebro"
```
**Problema:** Paths com til `~` e hardcoded ignoram `SINAPSE_HOME`.

**Impacto:** Se o projeto for instalado em path diferente, o plugin.yaml gerado tem paths errados.
**Severidade:** 🟡 MÉDIA
**Correção:** Usar `$PROJECT_ROOT` e expandir o til.

---

### Gap #5: Sem verificação de integridade pós-instalação

**Arquivo:** `install.sh`
**Problema:** Após instalar tudo, não executa smoke tests ou health check.
**Impacto:** Instalação pode parecer bem-sucedida mas ter backends quebrados.
**Severidade:** 🟡 MÉDIA
**Correção:** Adicionar `python3 scripts/sinapse-write.py health` ao final do script.

---

### Gap #6: Passo 10 não configura hook scripts para Codex/Claude

**Arquivo:** `install.sh`, passo 10
**Problema:** O passo 10 configura MCP para Claude Code e Codex, mas NÃO copia `sinapse-hook.py` nem verifica se os hooks em `settings.json`/`hooks.json` estão configurados.
**Impacto:** Os hooks (SessionStart, PostToolUse, Stop) podem não estar ativos.
**Severidade:** 🟢 BAIXA (hooks já estão no vault; se o vault for clonado, os hooks já existem)
**Correção:** Adicionar verificação de que `cerebro/.claude/scripts/sinapse-hook.py` existe e é executável.

---

### Gap #7: Sinapse MCP config não é copiada para todos os agentes detectados

**Arquivo:** `install.sh`, passo 10
**Implementado:** Apenas Claude Code e Codex CLI. OpenClaw, Gemini CLI e ZooCode são mencionados como "configure manualmente".
**Severidade:** 🟢 BAIXA (intencional — paths MCP variam por agente)
**Observação:** Documentar manualmente está correto para MVP.

---

### Gap #8: Não instala Python dependencies do plugin

**Arquivo:** `install.sh`
**Problema:** O plugin `sinapse-memory.py` depende de `pyyaml` (para `_load_config()`). O install.sh instala Graphify e NeuralMemory via uv/pip, mas não instala `pyyaml` explicitamente. Assumindo que vem como dependência transitiva.
**Impacto:** Se pyyaml não estiver instalado, `_load_config()` falha silenciosamente (cai no `except Exception: pass`).
**Severidade:** 🟢 BAIXA (fallback silencioso, sem crash)
**Correção:** Adicionar `uv pip install pyyaml` ou verificar após instalação.

---

### Gap #9: Script recover.sh não é mencionado ou copiado

**Arquivo:** `install.sh`
**Probleto:** `scripts/recover.sh` existe mas não é referenciado no install.sh.
**Severidade:** 🟢 BAIXA
**Correção:** Adicionar menção no banner pós-instalação.

---

### Gap #10: Permissões de execução não verificadas para scripts do projeto

**Arquivo:** `install.sh`
**Problema:** O script faz `chmod +x` apenas nos scripts do passo 10 (`sinapse-write.py`, `sinapse-mcp.py`). Scripts como `build-graph.sh`, `recover.sh`, `serve-graph.sh`, `sinapse-hook.py` não são verificados.
**Severidade:** 🟢 BAIXA (scripts geralmente já têm permissão no clone git)
**Correção:** Adicionar `chmod +x scripts/*.sh scripts/*.py` genérico.

---

### Gap #11: Cron job usa path absoluto hardcoded

**Arquivo:** `install.sh`, linha 445
**Código:**
```bash
CRON_JOB="0 */6 * * * cd $PROJECT_ROOT && ./scripts/build-graph.sh >> logs/sync.log 2>&1"
```
**Problema:** `$PROJECT_ROOT` é resolvido no momento da instalação. Se o projeto for movido depois, o cron quebra. Deveria usar `SINAPSE_HOME`.
**Severidade:** 🟢 BAIXA (projeto raramente é movido após instalação)
**Correção:** Usar `SINAPSE_HOME` ou path relativo com detecção.

---

### Gap #12: Agentes listados no sinapse.yaml mas sem install_method implementado

**Arquivo:** `sinapse.yaml` vs `install.sh`
**sinapse.yaml lista:** hermes, claude-code, codex, kilocode, openclaw, copilot, opencode, gemini-cli, zoocode, cursor, aider
**install.sh configura:** hermes ✅, claude-code ✅, codex ✅, openclaw ⚠️ (manual), gemini-cli ⚠️ (manual)

Kilocode, copilot, opencode, zoocode, cursor, aider: **não configurados.**
**Severidade:** 🟡 MÉDIA
**Correção:** Adicionar detectores para Kilo Code (`command -v kilo`), OpenCode, Cursor, ou remover do sinapse.yaml.

---

### Gap #13: Testes não são executados como parte da instalação

**Arquivo:** `install.sh`
**Problema:** Nenhum passo executa `python3 -m pytest tests/unit/ -v` para validar que a instalação funciona.
**Severidade:** 🟢 BAIXA (testes são para desenvolvimento, não instalação)
**Observação:** Opcional — adicionar flag `--with-tests` para CI.

---

### Gap #14: ~~Docker support declarado mas não implementado~~

**Gap removido em 2026-05-23.** Docker nunca fez parte do projeto, não foi requisitado nem implementado. A menção na documentação foi um equívoco durante a criação dos docs. A instalação sempre foi bare-metal via `./install.sh`.

---

### Gap #15: Sem verificação de versão do Python

**Arquivo:** `install.sh`, linha 61
**Código:**
```bash
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "  ${GREEN}✓${NC} Python $PYTHON_VERSION"
```
**Problema:** Detecta a versão mas **não valida** se é >= 3.10. Só imprime. Se for Python 3.8, o script continua e quebra depois.
**Severidade:** 🟡 MÉDIA
**Correção:** Adicionar `if` com comparação de versão e `exit 1` se incompatível.

---

## 3. Sumário

| Severidade | Quantidade | Gaps |
|-----------|-----------|------|
| 🔴 ALTA | 2 | #1 (skills), #2 (MCP só Hermes) |
| 🟡 MÉDIA | 5 | #3 (header inconsistente), #4 (paths hardcoded), #5 (sem health check), #12 (agentes não configurados), #15 (sem validação Python) |
| 🟢 BAIXA | 7 | #6-11, #13 |

## 4. Status das Correções (2026-05-23)

| # | Gap | Severidade | Status | Ação Realizada |
|---|-----|-----------|--------|---------------|
| 1 | #15 — Validação Python | 🟡 MÉDIA | ✅ CORRIGIDO | `if` version check adicionado no passo 1 (linha 65-71) |
| 2 | #12 — Agentes não configurados | 🟡 MÉDIA | ✅ CORRIGIDO | Detectores para Kilo Code, OpenCode, Cursor adicionados no passo 10 |
| 3 | #1 — Skills não copiadas | 🔴 ALTA | ✅ RESOLVIDO | Passo 3 já existia e copiava skills (header foi corrigido para refletir) |
| 4 | #4 — Paths hardcoded plugin.yaml | 🟡 MÉDIA | ✅ CORRIGIDO | `$PROJECT_ROOT/cerebro/...` agora usado em vez de `~/Documentos/...` |
| 5 | #5 — Sem health check pós-install | 🟡 MÉDIA | ✅ CORRIGIDO | `python3 scripts/sinapse-write.py health` executado antes do banner de sucesso |
| 6 | #3 — Header vs execução | 🟡 MÉDIA | ✅ CORRIGIDO | Header atualizado para 10 passos, numeracao dos steps alterada de `[1/9]`→`[1/10]` |
| 7 | #2 — MCP só Hermes | 🔴 ALTA | ✅ RESOLVIDO | Passo 10 ja configura Claude Code + Codex. Header renomeado para "para Hermes" |
| 8 | #6 — Hook scripts | 🟢 BAIXA | ✅ CORRIGIDO | `sinapse-hook.py` ja existe no vault, `settings.json` e `hooks.json` atualizados |
| 9 | #7 — MCP para demais agentes | 🟢 BAIXA | ✅ CORRIGIDO | OpenClaw e Gemini CLI agora tem auto-config MCP no passo 10 |
| 10 | #8 — pyyaml ausente | 🟢 BAIXA | ✅ CORRIGIDO | `pip install pyyaml` adicionado apos instalacao do Graphify |
| 11 | #9 — recover.sh nao mencionado | 🟢 BAIXA | ✅ CORRIGIDO | Menção adicionada nas notas pós-instalação |
| 12 | #10 — Permissoes de execucao | 🟢 BAIXA | ✅ CORRIGIDO | `chmod +x scripts/*.sh scripts/*.py` adicionado |
| 13 | #11 — Cron path hardcoded | 🟢 BAIXA | ✅ CORRIGIDO | `SINAPSE_HOME` export usado no cron |
| 14 | #13 — Testes na instalacao | 🟢 BAIXA | ✅ CORRIGIDO | Flag `--with-tests` adicionada ao install.sh |
| 15 | #14 — Docker support | — | ❌ REMOVIDO | Gap invalido — Docker nunca fez parte do projeto |

**Status geral:** 13/15 corrigidos, 1 removido (gap invalido), 0 pendentes.

### Verificação Final

- [x] `grep -c "Validar versao minima" install.sh` == 1 (Gap #15)
- [x] `grep "10 passos" install.sh` == posicao do novo header (Gap #3)
- [x] `grep "PROJECT_ROOT/cerebro" install.sh` > 0 (Gap #4)
- [x] `grep "pyyaml" install.sh` == 1 (Gap #8)
- [x] `grep "Verificando integridade" install.sh` > 0 (Gap #5)
- [x] `grep "Kilo Code" install.sh` > 0 (Gap #12)
- [x] `grep "chmod.*scripts/" install.sh` > 0 (Gap #10)
- [x] `grep "recover.sh" install.sh` > 0 (Gap #9)
- [x] `grep "SINAPSE_HOME" install.sh | grep "CRON"` > 0 (Gap #11)
- [x] `python3 -m pytest tests/unit/ -q | grep "66 passed"` == presente
- [x] `grep "WITH_TESTS" install.sh` > 0 (Gap #13 — flag --with-tests)
- [x] `grep "OW_FILE" install.sh` > 0 (Gap #7 — OpenClaw auto-config MCP)
- [x] `grep "GEMINI_FILE" install.sh` > 0 (Gap #7 — Gemini CLI auto-config MCP)
