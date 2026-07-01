# Hive-Mind — Documentação Técnica

> **Versão:** 3.0.0 | **Atualizado:** 2026-07-01
> **Stack:** Python 3.10+ (core/pipeline) · TypeScript/Bun (claude-mem) · Rust (RTK) · SQLite (`sqlite-vec` + FTS5) · Milvus (produção, opcional) · RAGFlow (adapter headless, opcional) · LlamaIndex (adapter, opcional)
> **Status:** Fase HM-12 (Federated Swarm) entregue · **Fase K (Conhecimento Born-Large)**: K0–K10 implementadas e revalidadas em local-full · **Testes:** 706 funções `test_` em 123 arquivos com testes (contagem 2026-07-01); gate K9 real separado em `tests/run_real_knowledge.sh` com 59/59 passed, 0 skipped

---

## Documento canônico

| Documento | Conteúdo |
|-----------|----------|
|  **[01-architecture.md](01-architecture.md)** | Referência canônica: princípios, anatomia, UMC, fluxos de leitura/escrita, Dream Cycle (com Knowledge Intake + Promotion Layer), P2P, multimodal, camada de acesso (MCP/Plugin/CLI/REST), auth multi-provedor, ADRs (§32), **Arquitetura de Conhecimento Born-Large** (§22–§31) |

## Documentação por área

| # | Documento | Conteúdo | Público-alvo |
|---|-----------|----------|--------------|
| 1 | [Arquitetura](01-architecture.md) | **Canônico** — princípios, UMC, fluxos, Dream Cycle, P2P, ADRs (§32), Born-Large (§22–§31) | Todos |
| 2 | [Modelos de IA](02-ai-models.md) | LLMs e embeddings utilizados, rationale, fallback chain, papéis de cadência (K5) | ML Engineers |
| 3 | [Pipeline de Dados](03-data-pipeline.md) | Capture → Intake → Promotion → Persistência → Index; DocumentPipeline (K6) e VectorBackend (K1) | Data Engineers |
| 4 | [Infraestrutura e Escopo](04-infrastructure.md) | Hardware, portas (incluindo Milvus e RAGFlow), serviços, limites, variáveis de ambiente, workspace_id | DevOps/SRE |
| 5 | [Blueprints e Fluxogramas](05-blueprints.md) | Diagramas ASCII de arquitetura, fluxo de 9 etapas, Dream Cycle, P2P, cadência, RetrievalRouter | Todos |
| 6 | [Análise de Gaps — install.sh](06-gap-analysis.md) | Auditoria técnica (C1-C5), gaps do instalador, métricas de testes | Desenvolvedores |
| 7 | [Setup de Sincronização P2P](07-p2p-sync-setup.md) | Syncthing, UUID v4, SHA-256, Síntese Dialética (Phase 9) | DevOps |
| 11 | [Arquitetura de Conhecimento e Promoção](11-knowledge-promotion-architecture.md) | **Normativo** — fluxo ideal de promoção, preenchimento por parte do cérebro, tipos canônicos, chunks, vector search, Milvus/RAGFlow/LlamaIndex born-large, DocumentPipeline, RetrievalRouter, métricas, contratos evolutivos (Reranker, Forget, Eval) | Arquitetos / Data Engineers |
| 12 | [Plano de Implementação da Arquitetura de Conhecimento](12-knowledge-implementation-plan.md) | Fases K0–K10, tasks, integrações em `integrations/`, modelos locais pequenos por papel, env vars, testes reais sem mocks como critério de aceite | Engenharia |

> Todos os documentos 01–07 foram reescritos para v3.0.0 em 2026-06-13. Em 2026-06-30, a frente de Conhecimento Born-Large (K0–K10) foi consolidada no canônico: o **`01-architecture.md` §22–§31** destila a referência normativa de [`11-knowledge-promotion-architecture.md`](11-knowledge-promotion-architecture.md), e **`[12-knowledge-implementation-plan.md](12-knowledge-implementation-plan.md)** é o plano operacional por fase. Em caso de conflito entre eles, **[01-architecture.md](01-architecture.md) prevalece**.

## Relatórios e planos

| Documento | Conteúdo |
|-----------|----------|
| [plans/2026-06-10-auditoria-tecnica-completa.md](plans/2026-06-10-auditoria-tecnica-completa.md) | Auditoria técnica completa (achados C1–C5, A1–A6, P1/P2) e plano de correção |
| [walkthrough.md](walkthrough.md) | Tour guiado pelo sistema |

## Documentação complementar (raiz)

| Arquivo | Conteúdo |
|---------|----------|
| [`../README.md`](../README.md) | Visão geral pública: arquitetura, instalação, operação, API |
| [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md) | Acompanhamento de fases (HM-01–HM-12, K0–K10) |
| [`../IMPLEMENTATION.md`](../IMPLEMENTATION.md) | Log de entregas por data |
| [`../sinapse.yaml`](../sinapse.yaml) | Configuração central comentada |
| [`../tests/README.md`](../tests/README.md) | Estrutura e convenções da suíte de testes |

## Stack em uma linha por camada

```
Cérebro (UMC):       hive_mind.db — SQLite + sqlite-vec (1024d snowflake-arctic-embed2) + FTS5 + grafo + multimodal
                     + workspace_id (default 'default') em todas as tabelas críticas
Estrutural:          Graphify (Python, clone em integrations/) → neurons/synapses/communities
Temporal:            claude-mem (TypeScript/Bun, wrapper) → observations · discoveries · session_summaries
Execução:            RTK (Rust, clone) → hooks/plugins/instruções por agente/CLI
Associativa:         NeuralMemory (Python, clone) → spreading activation
Captura:             Capture Layer → claude-mem temporal hippocampus → Knowledge Intake (K3)
Promoção:            Promotion Layer (K4) → Distiller→Validator→Router→Persistência→Indexação
                     → cadência sessão/diário/semanal/mensal/anual (K5)
Documentos:          DocumentPipeline (K6) → document_memories + document_chunks + document_vectors
RAGFlow:             adapter headless (ragflow-sdk) — nunca fonte de verdade
LlamaIndex:          adapter opcional de rerank no RetrievalRouter
Retrieval:           RetrievalRouter (K7) → classifica intent, escolhe rota especializada, devolve
                     retrieval_path + citations + confidence + missing_context
VectorBackend:       sqlite-vec (local/dev/offline) · Milvus (produção) · contrato único
Coleções canônicas:  memory/observation/document/code/visual/graph/summary vectors
Plano de execução:   docs/12 → fases K0-K10, modelos/env, vendors e testes reais
Saúde do conhecimento: knowledge_health.py (K8) → gate com 7 coleções canônicas + query_route_distribution
Tempo real:          Watcher (watchdog) → Obsidian→SQLite em ~2s
Acesso:              MCP (15 tools) · plugin Hermes · CLI · REST FastAPI :37702
Distribuição:        Syncthing (P2P) + UUID v4 + SHA-256 + Síntese Dialética + workspace + federação
Fonte de verdade:    cerebro/ (Obsidian) — frontmatter YAML + WikiLinks
Regra:               local-first por operação · born-large por arquitetura · plugável por contrato
                     · anatômico por fonte de verdade · auditável por evidência
```

## Como usar esta documentação

1. **Novo no projeto:** [`../README.md`](../README.md) → [01-architecture.md](01-architecture.md)
2. **Integrando um agente:** 01-architecture.md §9 e §13
3. **Deploy em VPS:** 01-architecture.md §9.4 + [04-infrastructure.md](04-infrastructure.md)
4. **Multi-máquina:** 01-architecture.md §7 + [07-p2p-sync-setup.md](07-p2p-sync-setup.md)
5. **Debugando:** 01-architecture.md §14–15 (testes e recovery)
6. **Entendendo o pipeline de conhecimento (K0–K10):** [01-architecture.md §22–§31](01-architecture.md#22-arquitetura-de-conhecimento-born-large) → [11-knowledge-promotion-architecture.md](11-knowledge-promotion-architecture.md) → [12-knowledge-implementation-plan.md](12-knowledge-implementation-plan.md)
7. **Operando o `VectorBackend` (sqlite-vec ↔ Milvus):** [01-architecture.md §24](01-architecture.md#24-vectorbackend-contrato-coleções-canônicas-e-escala) + [01-architecture.md §2.6](01-architecture.md#26-ferramentas-externas-como-órgãos-do-cérebro)
8. **Operando o `DocumentPipeline` / RAGFlow:** [01-architecture.md §25](01-architecture.md#25-documentpipeline-k6--ingestao-born-large) + [01-architecture.md §2.6](01-architecture.md#26-ferramentas-externas-como-órgãos-do-cérebro)
