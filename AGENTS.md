# Sinapse Agent — AGENTS.md (v3.0)
>
> Guia para agentes de IA que trabalham neste projeto.
> Formato cross-agent: Thoth (Hermes), Claude Code, Codex, OpenCode, Cursor, Copilot, etc.
>
> Última revisão: 2026-05-22

---

## 0. Idioma

- **Conversas:** Português (BR).
- **Código e saída técnica:** Inglês.
- **Documentação:** Português (BR).

---

## 1. O que é o Sinapse Agent

Camada de memória universal para agentes de IA. Três componentes:

| Camada | Ferramenta | O que faz | Source |
|--------|-----------|----------|--------|
| Estrutural | **Graphify** | Knowledge graph do vault (Leiden clustering) | `graphify/` (safishamsi/graphify) |
| Temporal | **claude-mem** | Tracking de eventos e observações (FTS5 + Chroma) | `claude-mem/` (thedotmack/claude-mem) |
| Execução | **RTK** | Otimização de comandos shell | `rtk/` (rtk-ai/rtk) |

Vault: `cerebro/` (Obsidian, template obsidian-mind). Fonte única de verdade.

---

## 2. Como trabalhar neste projeto

### Ao iniciar

1. Leia `cerebro/AGENTS.md`
2. Leia `cerebro/brain/Current State.md`
3. Verifique se o graph.json está atualizado: `cerebro/graphify-out/graph.json`

### Ao modificar código

- **Graphify**: Python. `pip install -e graphify/[all]` para instalar do source.
- **claude-mem**: TypeScript/Node. `cd claude-mem && npm install && npm run build`.
- **RTK**: Rust. `cd rtk && cargo build --release`.

### Ao modificar o vault

- Toda nota em `cerebro/` usa frontmatter YAML + WikiLinks.
- Após editar o vault, reindexe: `./scripts/build-graph.sh` (ou aguarde o cron a cada 6h).

### Ao commitar

- Não commite `cerebro/graphify-out/cache/` (cache regenerável).
- Não commite `claude-mem/data/` (dados locais).
- Não commite `rtk/target/` (build Rust).

---

## 3. Arquitetura de fluxo

```
ESCRITA                        INDEXAÇÃO                    LEITURA (v2.0)
───────                        ─────────                    ───────────────
Agente decide                  Cron (6h)                    Usuário pergunta
     │                             │                            │
     ▼                             ▼                            ▼
sinapse-memory                build-graph.sh              sinapse-memory v2
(post_tool_use)                   │                       (pre_prompt_build)
     │                             ▼                            │
     ├──► work/active/         graphify update             ├──► 1. claude-mem
     ├──► brain/Patterns.md    cerebro/                    │    (Chroma semantic)
     └──► brain/Current            │                       │
          State.md                 ▼                       └──► 2. graph.json
                              graph.json                       (Graphify structural)
                              (491 nodes,                       │
                              606 edges,                        ▼
                              55 communities)              Contexto injetado
                                                          no prompt
```

---

## 4. Comandos úteis

```bash
# Indexar vault (sem LLM)
./scripts/build-graph.sh

# Iniciar MCP server Graphify (modo stdio)
./scripts/serve-graph.sh

# Iniciar claude-mem worker
./scripts/start-claude-mem.sh

# Compilar RTK
cd rtk && cargo build --release

# Instalar tudo
./install.sh
```

---

## 5. Guardrails

- **Nunca** modifique `cerebro/` manualmente sem atualizar o graph.json depois.
- **Nunca** use `graphify cerebro/` sem `--backend` se não tiver API key ou Ollama. Use `graphify update cerebro/` para AST-only.
- **Nunca** duplique dados entre vault e ferramentas externas. O vault é a fonte única.
- **Nunca** commite dados sensíveis (API keys, .env, tokens).
