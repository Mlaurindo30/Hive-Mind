# Hive-Mind — Documentação Técnica

> **Versão:** 3.0.0 | **Atualizado:** 2026-06-13
> **Stack:** Python 3.10+ (core/pipeline) · TypeScript/Bun (claude-mem) · Rust (RTK) · SQLite (`sqlite-vec` + FTS5)
> **Status:** Fase HM-12 (Federated Swarm) entregue | **Testes:** 191 passando

---

## Documento canônico

| Documento | Conteúdo |
|-----------|----------|
|  **[01-architecture.md](01-architecture.md)** | Referência canônica: princípios, UMC, fluxos de leitura/escrita, Dream Cycle, P2P, multimodal, camada de acesso (MCP/Plugin/CLI/REST), auth multi-provedor, extensão, testes, recovery |

## Documentação por área

| # | Documento | Conteúdo | Público-alvo |
|---|-----------|----------|-------------|
| 1 | [Arquitetura](01-architecture.md) | **Canônico** — princípios, UMC, fluxos, Dream Cycle, P2P, ADRs (§17) | Todos |
| 2 | [Modelos de IA](02-ai-models.md) | LLMs e embeddings utilizados, rationale, fallback chain | ML Engineers |
| 3 | [Pipeline de Dados](03-data-pipeline.md) | Coleta → pré-processamento → embeddings → clustering → indexação | Data Engineers |
| 4 | [Infraestrutura e Escopo](04-infrastructure.md) | Hardware, portas, serviços, limites, variáveis de ambiente | DevOps/SRE |
| 5 | [Blueprints e Fluxogramas](05-blueprints.md) | Diagramas ASCII de arquitetura, read/write path, Dream Cycle, P2P | Todos |
| 6 | [Análise de Gaps — install.sh](06-gap-analysis.md) | Auditoria técnica (C1-C5), gaps do instalador, métricas de testes | Desenvolvedores |
| 7 | [Setup de Sincronização P2P](07-p2p-sync-setup.md) | Syncthing, UUID v4, SHA-256, Síntese Dialética (Phase 9) | DevOps |

> Todos os documentos 01–07 foram reescritos para v3.0.0 em 2026-06-13. Em caso de conflito entre eles, **[01-architecture.md](01-architecture.md) prevalece**.

## Relatórios e planos

| Documento | Conteúdo |
|-----------|----------|
| [plans/2026-06-10-auditoria-tecnica-completa.md](plans/2026-06-10-auditoria-tecnica-completa.md) | Auditoria técnica completa (achados C1–C5, A1–A6, P1/P2) e plano de correção |
| [walkthrough.md](walkthrough.md) | Tour guiado pelo sistema |

## Documentação complementar (raiz)

| Arquivo | Conteúdo |
|---------|----------|
| [`../README.md`](../README.md) | Visão geral pública: arquitetura, instalação, operação, API |
| [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md) | Acompanhamento de fases (1–12) |
| [`../IMPLEMENTATION.md`](../IMPLEMENTATION.md) | Log de entregas por data |
| [`../sinapse.yaml`](../sinapse.yaml) | Configuração central comentada |
| [`../tests/README.md`](../tests/README.md) | Estrutura e convenções da suíte de testes |

## Stack em uma linha por camada

```
Cérebro (UMC):       hive_mind.db — SQLite + sqlite-vec (384d) + FTS5 + grafo + multimodal
Estrutural:          Graphify (Python) → neurons/synapses/communities
Temporal:            claude-mem (TypeScript/Bun) → observations, worker HTTP :37700
Execução:            RTK (Rust) → hooks/plugins/instruções por agente/CLI
Associativa:         NeuralMemory (Python) → spreading activation
Consolidação:        dream_cycle.py → Distiller→Validator→Router→Síntese (LLM multi-provedor)
Tempo real:          Watcher (watchdog) → Obsidian→SQLite em ~2s
Acesso:              MCP (15 tools) · plugin Hermes · CLI · REST FastAPI :37702
Distribuição:        Syncthing (P2P) + UUID v4 + SHA-256 + Síntese Dialética
Fonte de verdade:    cerebro/ (Obsidian) — frontmatter YAML + WikiLinks
```

## Como usar esta documentação

1. **Novo no projeto:** [`../README.md`](../README.md) → [01-architecture.md](01-architecture.md)
2. **Integrando um agente:** 01-architecture.md §9 e §13
3. **Deploy em VPS:** 01-architecture.md §9.4 + [04-infrastructure.md](04-infrastructure.md)
4. **Multi-máquina:** 01-architecture.md §7 + [07-p2p-sync-setup.md](07-p2p-sync-setup.md)
5. **Debugando:** 01-architecture.md §14–15 (testes e recovery)
