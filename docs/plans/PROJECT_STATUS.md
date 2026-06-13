# Documento de Acompanhamento de Projeto: Hive-Mind

**Gerente de Projeto / Engenheiro Responsável:** Gemini CLI
**Data da última atualização:** 13 de Junho de 2026
**Status Global:** Fases HM-11 e HM-12 entregues (191 testes passando)

---

## 1. Histórico de Fases Concluídas

### Fase 1 e 2: Fundação e Unified Memory Core (UMC)
- **Status:** CONCLUÍDO
- **Entregas:**
    - Criação do banco de dados SQLite unificado com suporte a `sqlite-vec` e `FTS5`.
    - Refatoração do **Graphify** para indexação direta no SQLite.
    - Motor de busca híbrido (Texto + Vetor + Grafo).

### Fase 3: Unificação Temporal
- **Status:** CONCLUÍDO
- **Entregas:**
    - Migração total dos logs do `claude-mem` para o banco UMC.
    - Integração de logs do RTK (camada de execução).

### Fase 4 e 5: Interface e Dashboard
- **Status:** CONCLUÍDO
- **Entregas:**
    - Dashboard de visualização no Obsidian via plugin SQLite.
    - Implementação de Auto-Link Semântico (Soft-Links).

### Fase 6: Real-time Watcher
- **Status:** CONCLUÍDO
- **Entregas:**
    - Sincronização instantânea do Obsidian para o SQLite (Watcher via `watchdog`).
    - Eliminação do gap de 6 horas para reindexação.

### Fase 7: O Ciclo de Sonho (Hive-Dreamer)
- **Status:** CONCLUÍDO
- **Entregas:**
    - Motor `dream_cycle.py` para extração de fatos e preferências.
    - Suporte agnóstico a provedores (Google, OpenAI, Anthropic, DeepSeek, Ollama).
    - Fluxo de OAuth inquebrável para Google e Codex.
    - Script `setup-brain.py` para configuração de soberania do usuário sobre modelos.

### Fase 8: Enxame Multi-Máquina (P2P Sync)
- **Status:** CONCLUÍDO
- **Entregas:**
    - Migração de todas as Primary Keys para **UUID v4** (prevenção de colisões).
    - Implementação de **Hashes de Integridade** baseados em conteúdo (SHA-256).
    - Integração com **Syncthing** para transporte descentralizado.
    - Script `audit_memory.py` para sincronia entre arquivos físicos e SQLite.

### Fase 9: Fusão Semântica e Consenso (Semantic Merge)
- **Status:** CONCLUÍDO
- **Entregas:**
    - Tabela de `ambiguities` para rastreio de divergências P2P.
    - Motor `semantic_diff.py` (Híbrido Vetorial + LLM) para classificação de conflitos.
    - **Síntese Dialética Autônoma:** Resolução de conflitos via LLM sem intervenção manual.

---

## 2. Detalhamento da Fase Atual (Fase 10)

### Fase 10: Deep Portal (Memória Visual e Multimodal)
**Objetivo:** Transformar o Hive-Mind em um sistema multimodal capaz de processar imagens e documentos.

**Ações Realizadas:**
- [x] Criada infraestrutura de captura de tela (`visual_capture.py`) e Tool MCP.
- [x] Tabela `visual_memories` implementada no SQLite.
- [x] Estágio de processamento visual integrado ao `dream_cycle.py`.
- [x] Gerador de portal visual (`generate_portal.py`) para Obsidian Canvas.
- [x] **Auditoria de Modelos:** Removida qualquer dependência hardcoded de modelos de visão; o sistema agora obedece estritamente a `HIVE_DREAMER_PROVIDER/MODEL`.

**Pendências Críticas (Finalização da Fase 10):**
1.  **Ingestão de Documentos (PDF/DOCX):** Implementar extração local de texto para alimentar o pipeline de observações. (implementado; bug de metadata corrigido na auditoria de 10/06)
2.  **Extensão do Schema Multimodal:** Adicionar tabela `document_memories` (ou unificar em `multimodal_entities`).
3.  **Atualização do `install.sh`:** Incluir dependências `pypdf`, `python-docx` e `PyMuPDF`. (resolvido — requirements.txt completo + etapa no install.sh, 10/06)

---

## 3. Estrutura de Fases Subsequentes

### ✅ Fase HM-11: Raciocínio de Longo Prazo (Deep Reflection)
- **Status:** ENTREGUE
- **Entregas:**
    - `scripts/planner.py` — `decompose_goal()` decompõe objetivos em passos atômicos via LLM; `save_goal()` persiste plano na tabela `goals`; schemas Pydantic `GoalPlan`/`GoalStep`.
    - `core/hnsw_index.py` — índice vetorial incremental HNSW (hnswlib): `load_or_create()`, `add_neuron()`, `search()`, `rebuild_from_db()`, `incremental_update()`; persistido em `hnsw_neurons.idx`.
    - `core/database.py` — `get_causal_neighbors()` BFS multi-hop sobre `causal_edges`; migração idempotente da tabela `causal_edges` com índices em causa e efeito; colunas `goal_id`/`why` em `observations`; coluna `indexed_at` em `neurons`.
    - `core/schemas/dream_models.py` — `DistillerOutput` agora carrega `goal_id` e `why` opcionais, ligando cada extração ao objetivo ativo.
    - MCP tool `sinapse_plan_goal` (`scripts/sinapse-mcp.py`) — expõe `decompose_goal` + `save_goal` como tool MCP com campos `goal` (obrigatório) e `context` (opcional).

### ✅ Fase HM-12: Enxame Federado (Federated Swarm)
- **Status:** ENTREGUE
- **Entregas:**
    - `core/signing.py` — assinatura Ed25519: `generate_keypair()`, `load_private_key()`, `load_public_key()`, `sign_neuron()`, `verify_neuron()`, `fingerprint()`; chaves PEM em `config/keys/` (privkey com chmod 0600).
    - `core/redactor.py` — redação automática de PII: `redact_for_export()` e `redact_neuron()`; 8 categorias de regras (tokens de API, e-mails, IPs, paths, chaves SSH, CPF/CNPJ, telefones).
    - `scripts/sinapse-api.py` — novo endpoint `POST /api/v1/neurons/export` (Bearer + rate-limit 10/min): filtros por `type`/`created_after`, redação automática habilitada por padrão, assinatura opcional; retorna `neurons`, `count`, `exported_at`, `schema_version`.
    - `core/database.py` — coluna `visibility TEXT DEFAULT 'private'` em `neurons`; migração idempotente via `ensure_migrations()`.
    - `core/umc_schema.sql` — coluna `visibility` em `neurons` e tabela `causal_edges` integradas ao schema base.

---

## 4. Pendências e Próximas Ações Imediatas

**Convenção:** Usar prefixo HM-/TH-/RF- em todos os novos arquivos de planejamento de fases.

1.  **AÇÃO:** Implementar `scripts/document_ingest.py` (Suporte PDF/DOCX).
2.  **AÇÃO:** Atualizar `dream_cycle.py` para processar a fila de documentos.
3.  **DOCUMENTAÇÃO:** ~~Atualizar documentação com as camadas de Sincronização P2P e Multimodalidade.~~ (resolvido 10/06 — `README.md`, `docs/ARCHITECTURE.md`, `docs/README.md` e `AGENTS.md` reescritos com diagramas Mermaid da arquitetura atual; `docs/01-architecture.md` marcado como histórico)
4.  **INSTALADOR:** Adicionar novas dependências ao `install.sh`.
5.  **AUDITORIA:** Plano de ação P0/P1 do relatório docs/plans/2026-06-10-auditoria-tecnica-completa.md em execução (10/06).
