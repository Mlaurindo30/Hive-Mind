# Sinapse Agent — Documentação Técnica

> **Versão:** 1.1.0 | **Data:** 2026-05-23
> **Stack:** Python 3.14 + TypeScript/Node + Rust | **Tests:** 103 passing
> **Vault:** Obsidian (cerebro/) | **Agentes:** Hermes, Claude Code, Codex CLI, Kilo Code, OpenClaw

---

## Índice de Documentação

| # | Documento | Conteúdo | Público-alvo |
|---|-----------|----------|-------------|
| 1 | [Arquitetura e Abordagem Técnica](01-architecture.md) | Visão geral do sistema, 4 camadas de memória, fluxos de leitura/escrita, decisões de design | Arquitetos, Engenheiros |
| 2 | [Modelos de IA](02-ai-models.md) | LLMs utilizados (Gemini, Ollama, embeddings), rationale de seleção, fallback chain | ML Engineers, CTOs |
| 3 | [Pipeline de Dados](03-data-pipeline.md) | Coleta → pré-processamento → embeddings → Leiden clustering → indexação → query | Data Engineers |
| 4 | [Infraestrutura e Escopo](04-infrastructure.md) | Requisitos de hardware, portas, serviços, limites, variáveis de ambiente, segurança | DevOps, SRE |
| 5 | [Blueprints e Fluxogramas](05-blueprints.md) | Diagramas Mermaid: arquitetura de camadas, fluxo de leitura, fluxo de escrita, deploy | Todos |
| 6 | [Análise de Gaps — install.sh](06-gap-analysis.md) | O que o install.sh faz vs. o que deveria fazer, discrepâncias, recomendações | Desenvolvedores |

## Documentação Complementar

| Arquivo | Conteúdo |
|---------|----------|
| `../ARCHITECTURE.md` | Blueprint completo com 14 seções (referência canônica) |
| `../AGENTS.md` | Guia para agentes de IA que trabalham no projeto |
| `../sinapse.yaml` | Configuração central do projeto |
| `../tests/README.md` | Estrutura e convenções da suite de testes |
| `../README.md` | README público do repositório |

## Stack Tecnológica

```
Camada 1 — Estrutural:    Graphify (Python) → Leiden clustering → graph.json (1266+ nodes)
Camada 2 — Temporal:      claude-mem (TypeScript/Bun) → FTS5 + Chroma → worker HTTP :37700
Camada 3 — Execução:      RTK (Rust) → pre_tool_call hook → otimização de comandos shell
Camada 4 — Associativa:   NeuralMemory (Python) → spreading activation → nmem recall CLI
Plugin — Integração:      sinapse-memory.py (Python) → hooks Hermes + MCP server + CLI standalone
Vault — Fonte única:      cerebro/ (Obsidian) → frontmatter YAML + WikiLinks
```

## Métricas do Projeto

| Métrica | Valor |
|---------|-------|
| Linhas de código (plugin) | 984 |
| Linhas de código (install.sh) | 625 |
| Testes unitários | 66 |
| Testes de integração | 15 |
| Testes E2E | 22 |
| Testes totais | 103 |
| Scripts de automação | 9 |
| Config files MCP | 3 |
| Hooks (Claude Code + Codex) | 6 |
| Variáveis de ambiente documentadas | 7 |

## Como usar esta documentação

1. **Novo no projeto:** Comece por `01-architecture.md` para entender o sistema
2. **Configurando deploy:** Leia `04-infrastructure.md`
3. **Debugando integração:** Consulte `05-blueprints.md` para diagramas de fluxo
4. **Instalando:** Execute `./install.sh` e verifique `06-gap-analysis.md` para limitações conhecidas
