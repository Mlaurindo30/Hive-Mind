# hive-mind

**Universal, persistent, local-first memory layer for swarms of AI agents.**

Este pacote é a porta de entrada npm do [Hive-Mind](https://github.com/Mlaurindo30/Hive-Mind):
um CLI leve (Node ≥18, zero dependências) que instala e gerencia o runtime completo
(Python 3.12 via uv, vault Obsidian, grafo de conhecimento, MCP `sinapse-memory`,
REST API, Dream Cycle).

## Instalação

```bash
# Assistente interativo
npx hive-sinapse-mind@latest init wizard

# Não-interativo
npx hive-sinapse-mind@latest init

# Ou global
npm install -g hive-sinapse-mind
hive-mind init
```

One-liner sem Node (Linux/WSL/macOS):

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/Mlaurindo30/Hive-Mind@main/install.sh | bash
```

## Suporte por plataforma

| Plataforma | Status | Serviços |
|---|---|---|
| Linux | ✅ estável (validado por teste de máquina virgem) | systemd `--user` |
| WSL2 | ✅ estável | systemd `--user` |
| macOS | 🧪 experimental | launchd (LaunchAgents) |
| Windows nativo | 🚧 beta — instale via WSL2; supervisor Node gerencia serviços | supervisor Node |

## Comandos

```bash
hive-mind init [--profile=local-min|local-full] [--with-tests]
hive-mind init wizard
hive-mind doctor
hive-mind services start|stop|status|restart
hive-mind mcp register --agent claude   # ou codex, gemini, cursor, ...
hive-mind update
```

- **Diretório de instalação:** `~/Hive-Mind` (ou `$HIVE_MIND_HOME`).
- **Pré-requisitos** (o CLI verifica e orienta): git, curl, [uv](https://docs.astral.sh/uv/),
  Node 18+, [Bun](https://bun.sh). Opcionais: Ollama (busca semântica local),
  Docker (perfil `local-full`: Milvus/RAGFlow/FalkorDB).
- Sem Ollama/Docker o sistema instala e roda em modo degradado documentado
  (busca semântica cai para texto; wrappers ficam adiados).

## Depois de instalar

Registre o MCP no seu agente e reinicie-o:

```bash
hive-mind mcp register --agent claude
```

Confirme com: *"use the sinapse_health tool"*.

## Documentação

Repositório e docs completas: https://github.com/Mlaurindo30/Hive-Mind

## Licença

Apache-2.0
