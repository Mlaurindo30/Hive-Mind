# Modelos de IA

> **Hive-Mind v3.10.1** — Papéis de LLM, modelos em uso, Model Gateway, structured output para modelos de raciocínio, fallback chain e embeddings.
> Revisão 2026-08-15. Consolida [`02-ai-models.md`](02-ai-models.md) e [`modelos-ia.md`](modelos-ia.md).

---

## 1. Visão geral

O Hive-Mind **não treina modelos proprietários**. Usa modelos de terceiros em contextos distintos, todos configuráveis por papel via `HIVE_{ROLE}_*`:

1. **Graphify** — indexação estrutural do vault (extração de entidades e relações).
2. **Hive-Dreamer** — consolidação semântica offline (Dream Cycle, K3 Knowledge Intake + K4 Promotion Layer).
3. **Cadência** — escritores de cadência (K5: `session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer`, `yearly_synthesizer`), cada um com seu modelo ou herança do Dreamer.

Em todos os casos, a escolha de modelo é **configurável pelo usuário** via variáveis de ambiente e pelo `setup-brain.sh`/`setup-brain.py`. Nenhum modelo é hardcoded.

### Modelos em uso (v3.10.1)

| Modelo | Papel | Tipo | Onde roda |
|--------|-------|------|-----------|
| `granite4.1:8b` | Distiller / Router (Dream Cycle), extração instruct local | instruct local | Ollama |
| `qwen3.5:397b` | Validator (Dream Cycle) e reasoning | reasoning | cloud |
| `gpt-oss-120b` | reasoning (síntese/validação) | reasoning | cloud (`gpt-oss-120b-maas` via antigravity) |
| `snowflake-arctic-embed2:latest` | embeddings (1024d) | embedding | Ollama local |

> A divisão de papéis v3.10.1: **Distiller/Router** roteiam via config de papel (`granite4.1:8b` instruct local); **Validator** mantém reasoning (`qwen3.5:397b`). O registro de modelos marca `reasoning=True` por papel (`dreamer`/`validator`/`synthesis`).

---

## 2. Papéis canônicos de LLM

Constante `HIVE_LLM_ROLES` em `core/auth.py`. Papéis são case-insensitive (`-` vira `_`); nomes vazios ou não-string levantam `ValueError`. Resolução centralizada em `get_role_config()` (`core/auth.py`).

| Papel | Usado por | Perfil de chamada | reasoning=True |
|-------|-----------|-------------------|----------------|
| `dreamer` | Knowledge Intake + Distiller, Validator, Router (legado) | Raciocínio — qualidade importa | ✅ |
| `graphify` | Extração entidade/relação na indexação | Volume — custo importa | — |
| `vision` | Descrição de screenshot (Fase 10) | Requer modelo multimodal | — |
| `synthesis` | Síntese Dialética P2P | Raciocínio crítico — decide verdade | ✅ |
| `planner` | Decomposição de meta (`sinapse_plan_goal`, `scripts/planner.py`) | Raciocínio estrutural; herda de `HIVE_DREAMER_*` | — |
| `claude_mem` | Ponte `claude_mem_bridge.py` (K4) — classifica `knowledge_type` | Barato e rápido; herda do Dreamer se indefinido | — |
| `session_summarizer` (K5) | `session_consolidator.py` — resumo de sessão | Pequeno/rápido; comprime logs locais | — |
| `daily_writer` (K5) | `daily_writer.py` — síntese diária | Pequeno ou médio; agrega sessões do dia | — |
| `weekly_synthesizer` (K5) | `weekly_synthesizer.py` — síntese semanal | Médio/forte; cruza dias, detecta padrões | — |
| `monthly_synthesizer` (K5) | `monthly_synthesizer.py` — síntese mensal | Forte; produz metas, drift, riscos | — |
| `yearly_synthesizer` (K5) | `yearly_synthesizer.py` — síntese anual | Forte/batch offline; memória histórica, princípios | — |
| `alias_miner` | Mineração de aliases (slugs) | Barato | — |
| `topic_router` | Roteamento de fatos ao lobo temporal | Barato | — |
| `sector_classifier` | Setor cross-projeto (Diencéfalo) | Barato | — |
| `drift_detector` | Detecção de drift (>90d → arquivo frio) | Barato | — |
| `decision_promoter` | Promoção de decisão ao Córtex Frontal | Raciocínio curto | — |
| `project_synthesizer` | Síntese de projeto | Médio/forte | — |
| `pattern_distiller` | Destilação de padrões para `cerebelo/padroes/` | Raciocínio médio | — |
| `conflict_detector` | Detecção de conflito na Ínsula | Barato | — |
| `graphiti` | Extração causal Graphiti/FalkorDB | Barato | — |
| `lightrag` | Extração LightRAG (entidades + relações) | local `qwen2.5:3b` | — |
| `reranker` (opcional, §31.1) | Rerank lexical local via `HIVE_RETRIEVAL_RERANKER=1`; cross-encoder local forte via `HIVE_RERANKER_PROVIDER/MODEL` + extra `reranker` | Pequeno local; off por padrão no `local-min` | — |

**Regra de cadência (K5):** sessão e diário podem usar modelos pequenos (compressão local); semanal usa modelos médios/fortes; mensal e anual **não devem** ser rebaixadas automaticamente sem aviso. **Fail-closed:** um papel sem modelo próprio e sem herança do `dreamer` registra uma falha auditável e não fabrica síntese.

### Configuração por papel

```bash
# Em .env — caso mínimo: só o Dreamer (todos os papéis herdam dele)
HIVE_DREAMER_PROVIDER=google
HIVE_DREAMER_MODEL=gemini-2.0-flash

# Caso diferenciado: extração barata no Graphify + fallback local no Dreamer
HIVE_GRAPHIFY_PROVIDER=ollama
HIVE_GRAPHIFY_MODEL=qwen2.5-coder:3b
HIVE_DREAMER_FALLBACK_PROVIDER=ollama
HIVE_DREAMER_FALLBACK_MODEL=qwen2.5-coder:7b
```

O `setup-brain.py`/`setup-brain.sh` oferece UI interativa que pergunta **qual papel configurar**, mostra o valor atual (ou "herda do Dreamer"), oferece fluxo de fallback opcional, lista modelos por provider (API em tempo real), testa conectividade antes de salvar, detecta saldo disponível (DeepSeek, OpenRouter) e **recomenda explicitamente o modelo por cadência** ao configurar `session_summarizer`, `daily_writer`, `weekly_synthesizer`, `monthly_synthesizer` ou `yearly_synthesizer`.

---

## 3. Hive-Dreamer — providers suportados

O Dream Cycle usa LLMs para: Distiller (extração de fatos), Validator (verificação de qualidade), Router (classificação Atlas) e Síntese Dialética (resolução de conflito P2P).

### 3.1 Tabela de providers

| Provider | Autenticação | Endpoint | Exemplo de modelo |
|----------|--------------|----------|-------------------|
| `google` | OAuth Device Flow | AI Studio / Vertex | `gemini-2.0-flash` |
| `antigravity` | token nativo `agy` em `~/.gemini/antigravity-cli/antigravity-oauth-token` | CLI `agy` | `gemini-3.5-flash`, `gemini-3.1-pro`, `claude-sonnet-4-6`, `gpt-oss-120b-maas` |
| `gemini-cli` | OAuth do Gemini CLI / extensão VS Code | Code Assist `cloudcode-pa` | `gemini-2.5-flash`, `gemini-3.1-flash-lite` |
| `openai` | Bearer token | api.openai.com | `gpt-4o`, `gpt-4.1-mini` |
| `anthropic` | Bearer token | api.anthropic.com | `claude-fable-5`, `claude-haiku-4-5` |
| `deepseek` | Bearer token | api.deepseek.com | `deepseek-v3`, `deepseek-r1` |
| `huggingface` | Bearer token | api-inference.huggingface.co | `meta-llama/Llama-3-8b-instruct` |
| `qwen` | Bearer token | dashscope.aliyuncs.com | `qwen-turbo`, `qwen-plus` |
| `nvidia` | Bearer token | integrate.api.nvidia.com | `meta/llama-3.3-70b-instruct` |
| `openrouter` | Bearer token | openrouter.ai/api/v1 | `google/gemini-flash-1.5` |
| `lmstudio` | Sem auth (local) | localhost:1234/v1 | modelo carregado no LM Studio |
| `ollama` | Sem auth (local) | localhost:11434/v1 | `qwen2.5-coder:3b`, `llama3.2` |

`antigravity` e `gemini-cli` não usam o provider legado `google`. O caminho operacional preferido para Antigravity é o token nativo `agy`; o OAuth do Gemini CLI permanece suportado apenas para o provider `gemini-cli`/Code Assist.

---

## 4. Structured Output (Pydantic)

Todas as chamadas de LLM no Dream Cycle usam JSON Schema derivado de modelos Pydantic:

```
Chamada LLM:
  entrada:  texto da observação + system prompt com JSON schema
  saída:    JSON → model_validate_json(response) → objeto tipado

  Se a validação falhar:
    → Distiller tenta de novo (máx. 2x)
    → Se persistir: archived=2 (quarentena)
```

Isso garante que qualquer provider (Ollama local ou Anthropic cloud) produza a mesma estrutura processável.

### Tratamento de modelos de raciocínio para structured output (v3.10.1)

Modelos de raciocínio (`qwen3.5:397b`, `gpt-oss-120b`) **ignoram** `json_schema` estrito e vazam chain-of-thought para o conteúdo. A correção aplicada:

```text
reasoning_effort=none
+ json_object
+ retry em structured_output_not_json / schema_invalid
```

Ou seja: para saída estruturada, o modelo de raciocínio é executado com `reasoning_effort=none` (sem cadeia de pensamento embutida na resposta), força `json_object` como formato de resposta, e re-tenta na validação quando a saída não é JSON ou viola o schema. Isso isola o raciocínio da estrutura e evita contaminação do campo de conteúdo.

---

## 5. Model Gateway (camada canônica de execução de LLM)

O Model Gateway é a **única** camada que executa chamadas de LLM. Lê a configuração legada de papéis (`HIVE_{ROLE}_PROVIDER`/`MODEL`/`FALLBACK*` em `.env`) via `core.auth.PROVIDERS_CONFIG`, compõe com overrides opcionais de `config/model-gateway.yaml`, seleciona um `ModelProfile` por papel + capability exigida e despacha para um adapter de provider.

```
Call site do Hive-Mind (Promotion Layer, Dream Cycle, ...)
  → core/llm_client.call_llm_with_fallback  (wrapper, R4)
      → core/model_gateway.ModelGateway.from_combined_config()
      → core/model_registry.ModelRegistry.from_combined_config()
          lê:
            core/auth.PROVIDERS_CONFIG (base_url, env_var, auth_type)
            HIVE_{ROLE}_PROVIDER/MODEL/FALLBACK* (primary, fallback, fallback2)
            config/model-gateway.yaml (capabilities, cost_mode, role overrides)
      → integrations/model_gateway/<adapter>
          (openai_compatible / litellm / native / lmstudio /
           llamacpp / vllm / sglang)
```

`core/llm_client.call_llm_with_fallback` agora é um wrapper fino que delega aqui — não é mais um caminho de execução paralelo.

### 5.1 Vocabulário

- **Provider** (legado, em `PROVIDERS_CONFIG`) — nome lógico de backend configurado em `.env`.
- **Adapter** (runtime, em `integrations/model_gateway/`) — o código que fala com a API HTTP do provider: `native`, `openai_compatible`, `litellm`, `lmstudio`, `llamacpp`, `vllm`, `sglang`.
- **Model profile** (`ModelProfile` em `core/model_registry.py`) — um por tripla `(role, level)`, com `level ∈ {primary, fallback, fallback2}`.
- **Role** — propósito lógico declarado pelo call site (`dreamer`, `graphify`, `vision`, `synthesis`, `claude_mem`, ...).
- **Adapter hint** — família de adapter runtime para a qual um provider legado mapeia (ex.: `ollama → openai_compatible`, `gemini-cli → native`). `unsupported_explicit` quando não há hint.

### 5.2 Modos de operação (R5)

`MODEL_GATEWAY_MODE` é o switch canônico. `MODEL_GATEWAY_ENABLED` permanece como shim deprecado. `HIVE_FORCE_LEGACY_LLM` é o bypass de emergência.

| `MODEL_GATEWAY_MODE` | Comportamento | Fallback legado? |
|---|---|---|
| `auto` *(padrão)* | Gateway via `ModelRegistry.from_combined_config()`. Se o registry falhar ao validar ou a chamada falhar, o wrapper loga aviso estruturado (`gateway_attempted=true, gateway_failed=true, legacy_fallback_used=true`) e delega a `_legacy_call_llm_with_fallback`. | **Sim**, com aviso explícito + telemetria. Nunca silencioso. |
| `on` | Gateway obrigatório. Se falhar de ponta a ponta, o wrapper levanta `RuntimeError` estruturado e NUNCA faz fallback. | **Não.** Sete `HIVE_FORCE_LEGACY_LLM=true` para bypass. |
| `off` *(deprecado)* | Gateway desligado, `_legacy_call_llm_with_fallback` roda direto. Emite aviso de deprecação. | Sempre. |
| `HIVE_FORCE_LEGACY_LLM=true` | Bypass de emergência — vence qualquer `MODEL_GATEWAY_MODE`. Emite aviso no stderr. | Sempre. |

```bash
# config/model-gateway.env.example — copiado para .env pelo install.sh
MODEL_GATEWAY_MODE=auto
# HIVE_FORCE_LEGACY_LLM=false   # bypass de emergência; NÃO setar por padrão
# MODEL_GATEWAY_ENABLED=false   # DEPRECADO; use MODEL_GATEWAY_MODE

LMSTUDIO_BASE_URL=http://localhost:1234/v1
LLAMACPP_BASE_URL=http://localhost:8080/v1
VLLM_BASE_URL=http://localhost:8000/v1
SGLANG_BASE_URL=http://localhost:30000/v1
LITELLM_BASE_URL=http://localhost:4000/v1
LITELLM_API_KEY=
```

### 5.3 Mapeamento provider → adapter (R2)

`core/model_registry.PROVIDER_ADAPTER_HINT` é a fonte única de verdade:

| Provider legado | Adapter runtime |
|---|---|
| `openai`, `openrouter`, `deepseek`, `nvidia`, `qwen`, `omniroute`, `ollama`, `ollama-cloud`, `anthropic` | `openai_compatible` |
| `google`, `gemini`, `huggingface` | `litellm` |
| `gemini-cli`, `antigravity` | `native` (ponte legada) |
| `lmstudio` | `lmstudio` |
| `llamacpp`, `vllm`, `sglang` | dedicado (já entregues) |

Todo provider em `PROVIDERS_CONFIG` é mapeado a um adapter ou reportado como `unsupported_explicit` em `ModelRegistry.validate()`.

### 5.4 Fontes de configuração

O registry combina três fontes, nesta ordem de prioridade:

1. **`HIVE_{ROLE}_PROVIDER/MODEL` em `.env`** — primary, fallback, fallback2 por papel. Papéis herdados caem para `HIVE_DREAMER_*` como antes.
2. **`PROVIDERS_CONFIG` em `core/auth.py`** — base URL, env var, tipo de auth por provider legado.
3. **`config/model-gateway.yaml`** — camada de override OPCIONAL: `providers.<name>` (adapter_hint, cost_mode, capabilities) e `roles.<name>` (require, prefer, priority, cost_mode, context_window, max_output_tokens). `roles.<name>.provider`/`model` são ignorados a menos que `role_override: true`.

### 5.5 Limit conhecidas

- **LiteLLM modo SDK direto fora de escopo** — só o modo proxy HTTP.
- **Streaming não implementado** — `chat()` sempre retorna resposta completa.
- **JSON Schema → Pydantic é best-effort e flat** — internals de objetos/arrays aninhados são aceitos como `dict`/`list` opacos.
- **Vision delegada ao caminho legado (R8)** — quando `image_path` é passado, o wrapper emite `legacy_vision_bridge_used=true`.
- **SSRF hardening básico** — bloqueia esquemas não-http(s) e endereços de metadados AWS/GCP; sem proteção de DNS-rebinding.
- **Tool-calling declarado mas não exercitado de ponta a ponta.**

---

## 6. Fallback chain

Cada papel resolve para uma cadeia `(primary, fallback, fallback2)` nessa ordem estrita, espelhando o `core/llm_client.py` legado.

### 6.1 Classificação de erros e política de fallback

`core/llm_client.py` (`classify_llm_error()` + `call_llm_with_fallback()`):

| Classe de erro | Exemplos | Ação |
|----------------|----------|------|
| **Transitório** | timeout, erro de conexão, HTTP 429, 5xx | retry com backoff `min(2^n, 8s)` → fallback (se definido) → quarentena `archived=2` |
| **Auth/saldo** | HTTP 401/402/403, "insufficient balance/quota" | **fallback direto, sem retry** → senão quarentena + aviso |
| **Validação Pydantic** | saída do LLM falhou validação de schema | retry no **mesmo modelo** → quarentena. **NUNCA dispara fallback** (problema de qualidade, não disponibilidade) |
| **Desconhecido** | qualquer outra exceção | tratado como transitório |

### 6.2 Regras R6 do gateway

- **Explícito e logado** — toda tentativa é registrada via `record_call` (legado) ou `record_gateway_attempt`/`record_gateway_failure`/`record_legacy_fallback_used` (gateway).
- **Pula perfis desabilitados** automaticamente.
- **Detecta ciclos** no `fallback_chain` do YAML e para, em vez de loopar.
- **Nunca retorna sucesso fabricado** — se todos os modelos da cadeia falham, o gateway retorna `ok=False` com `error`/`error_chain` classificados; o caminho legado levanta `LLMChainFailure` preservando `primary_exc` e `fallback_exc`.
- **Erros de validação nunca disparam fallback** (R6 §1) — o caller re-tenta no mesmo modelo até `max_retries`, então levanta `LLMValidationError`.
- **Auth / 401 / 403 / 402 / saldo** bypassam retries e vão direto ao próximo par (R6 §3).
- **429 / 5xx / timeouts** re-tentam com backoff exponencial (teto 8s), então fallback (R6 §2/§4).

### 6.3 Escape hatches (rollback para o llm_client legado)

1. **Por processo** — `HIVE_FORCE_LEGACY_LLM=true` bypassa o gateway inteiro para toda chamada. Caminho de recuperação quando o gateway se comporta mal em produção. Emite aviso no stderr.
2. **Modo inteiro** — `MODEL_GATEWAY_MODE=off` (deprecado) desliga o gateway para o processo.

O `core/llm_client.py` legado é preservado verbatim como `_legacy_call_llm_with_fallback` para manter o contrato dos callers (`LLMValidationError`, `LLMChainFailure` com `chain`, `primary_exc`, `fallback_exc`).

---

## 7. Embeddings

### 7.1 Modelo de embedding

| Modelo | Dimensões | Uso | Onde |
|--------|-----------|-----|------|
| `snowflake-arctic-embed2:latest` | 1024 | busca KNN semântica no UMC | sqlite-vec HNSW (env `HNSW_DIM=1024`) |
| `snowflake-arctic-embed2:latest` | 1024 | busca semântica de observações | sqlite-vec HNSW |
| `snowflake-arctic-embed2:latest` | 1024 | embeddings de memória para LightRAG | `core/lightrag_index.py` (P4) |

O modelo é carregado via **Ollama local** (`OLLAMA_EMBED_MODEL=snowflake-arctic-embed2:latest`), exposto por `OllamaEmbedder` em `core/database.py:get_embedder()`. Não requer API key. Vetores persistidos na tabela virtual `search_vec` (vec0, 1024d) dentro de `hive_mind.db`. `core/hnsw_index.py` mantém índice HNSW incremental (via `hnswlib`) sobre os mesmos vetores 1024d.

**Por que snowflake-arctic-embed2 (1024d)?**

- Mantém a dimensão 1024d já usada por sqlite-vec, HNSW, LightRAG e Graphiti.
- Em testes locais (2026-06-27), teve 0 NaNs em gatilhos problemáticos.
- Teve melhor separação PT↔EN vs conteúdo não relacionado do que `bge-m3` e `qwen3-embedding:0.6b`.
- Ollama local remove dependência de API cloud para embeddings.

### 7.2 VectorBackend e identidade de coleção (K1/K10)

`VectorBackend` opera sobre **sete coleções canônicas** com identidade `(name, embedding_model, dim)`. Modelo/dimensão de embedding fazem parte do contrato — uma coleção carrega `snowflake-arctic-embed2:latest` a **1024d** salvo override por env.

```text
coleção carrega (embedding_model, dim) na identidade
upsert com modelo divergente: rejeitado ou vai para nova coleção (nunca misturado)
migração: re-embed online por workspace, dual-write (modelo antigo+novo) até cutover
métrica: vectors_model_mismatch = 0 dentro de uma coleção
```

**Plano típico de migração de embedding:**

1. Criar nova coleção com `(name, new_model, new_dim)`.
2. Dual-write: vetores novos vão para as coleções antiga e nova durante o cutover.
3. Backfill dos embeddings antigos em lote (offline) na nova coleção.
4. Cutover: `sinapse_query` e `RetrievalRouter` consultam a nova coleção.
5. Coleção antiga entra em `forget` (`superseded`) — tombstone, sem delete físico silencioso.

### 7.3 Variáveis de ambiente relevantes

| Variável | Função | Padrão |
|---|---|---|
| `HNSW_DIM` | dimensão HNSW (sqlite-vec) | `1024` |
| `OLLAMA_EMBED_MODEL` | modelo Ollama para embeddings | `snowflake-arctic-embed2:latest` |
| `HIVE_RETRIEVAL_RERANKER` | habilita rerank lexical determinístico no `RetrievalRouter` via adaptador LlamaIndex (§31.1) | off |
| `HIVE_RERANKER_PROVIDER`/`HIVE_RERANKER_MODEL` | habilita cross-encoder local forte com extra `reranker` (`uv sync --extra reranker`) | off |
| `HIVE_PROMOTION_BUDGET_*` | teto de custo de promoção por workspace (§30.5) | sem teto |

---

## 8. Graphify — modelos de indexação

| Modelo | Provider | Backend flag | Qualidade |
|--------|----------|-------------|-----------|
| `gemini-2.5-flash` | Google AI | `--backend gemini` | Alta (cloud) |
| `qwen2.5-coder:3b` | Ollama local | `--backend ollama` | Média (local, grátis) |
| `tree-sitter + regex` | Determinístico | `--backend ast` | Estrutural (sem LLM) |

`scripts/build-graph.sh` lê `HIVE_GRAPHIFY_PROVIDER/MODEL` do `.env` (herdando de `HIVE_DREAMER_*` se ausente) e mapeia o provider para o backend Graphify. Sem config definida, usa fallback determinístico tree-sitter + regex (AST-only, sempre funciona).

---

## 9. LightRAG — extração de entidades + grafo (P4)

LightRAG é o **segundo extrator** ao lado do Graphify: enquanto o Graphify extrai entidades de **código** (AST + LLM), o LightRAG extrai entidades e relações de **memórias consolidadas** pelo Dream Cycle (texto livre, decisões, aprendizados).

```
  Dream Cycle (Estágio 3 — Síntese)
       │ synthesis.final_content
       ▼
  core/lightrag_index.py:index_memory()
       │
       ├──> working_dir LightRAG: claude-mem/data/lightrag/
       │    ├── graph.npz (NetworkX)         — entidades + arestas
       │    ├── vdb_chunks.json              — embeddings de chunk (snowflake-arctic-embed2)
       │    ├── vdb_entities.json            — embeddings de entidade
       │    └── vdb_relationships.json       — embeddings de relação
       ▼
  sinapse_rag_query(question, mode="hybrid")
       ▼
  MCP: retorna entidades + relações + chunks relevantes
```

| Modelo | Provider | Justificativa |
|--------|----------|---------------|
| `qwen2.5:3b` | Ollama local | ~1.9 GB · multilíngue PT/EN · extrai entidades/relações melhor que `granite3-dense:2b` em testes reais |

- Sem fallback remoto: se o modelo local Ollama falhar, `index_memory` retorna `False` e o Dream Cycle continua.
- `.env` (`HIVE_LIGHTRAG_MODEL`) faz override do padrão; `qwen2.5:7b` pode ser usado em máquinas com mais VRAM.

**Modos de consulta (`sinapse_rag_query`):** `naive` (busca vetorial simples), `local` (entidades mencionadas + vizinhos), `global` (traversal de arestas), `hybrid` (padrão — melhor para perguntas multi-hop).

---

## 10. NeuralMemory — sem LLM

NeuralMemory usa **spreading activation** — algoritmo puramente matemático, sem chamada de LLM (TF-IDF + cosseno → ativação propagada por 24 tipos de aresta, atenuação 0.7 por hop).

---

## 11. Modelos NÃO usados (e por quê)

| Modelo | Por que não |
|--------|-------------|
| GPT-4 / Claude Opus | Overkill para extração; custo proibitivo para indexação diária |
| BERT multilíngue | Mais pesado que Qwen 2.5 Coder 3B para o mesmo NER |
| Fine-tunes proprietários | Complexidade de manutenção incompatível com soberania de modelo |
| OpenAI Embeddings (text-embedding-3) | Dependência de API; snowflake-arctic-embed2 local via Ollama é suficiente |
| ChromaDB + all-MiniLM-L6-v2 | Substituído por sqlite-vec + snowflake-arctic-embed2 (1024d) no UMC |
| all-MiniLM-L6-v2 (384d) | Substituído por embedding local 1024d no Ollama |

---

## 12. Matriz de capacidade por cenário

| Cenário | Graphify (código) | LightRAG (texto) | Embeddings | Dream Cycle | Recall |
|---------|-------------------|------------------|-----------|-------------|--------|
| Cloud (API keys) | provider configurado | Qwen 2.5 3B (local) | snowflake-arctic-embed2 (local) | provider configurado | Spreading Activation |
| Local (Ollama) | Qwen 2.5 Coder 3B | Qwen 2.5 3B (local) | snowflake-arctic-embed2 (local) | Ollama configurado | Spreading Activation |
| Offline (sem Ollama) | tree-sitter + regex | Indisponível (best-effort) | Indisponível | Indisponível | Spreading Activation |
| Mínimo (sem Python) | Indisponível | Indisponível | Indisponível | Indisponível | Indisponível |

O sistema degrada graciosamente: mesmo no cenário mínimo, o vault Obsidian permanece legível e as buscas FTS5 seguem funcionando. LightRAG é o primeiro a falhar em ambientes mínimos — `index_memory` é best-effort (try/except) e a síntese dialética nunca é abortada por falha de grafo.

---

## 13. Governança de segredos e telemetria (R10)

- `record_call` aceita apenas campos de metadados — sua assinatura não tem parâmetro `prompt`/`content`/`response`.
- Hooks novos seguem a mesma disciplina: sem payload, segredos redigidos via `core.redactor.redact_for_export` antes de qualquer escrita.
- API keys são resolvidas de `ModelProfile.api_key_env` no momento da chamada (`profile.api_key()`) — nunca armazenadas no objeto de perfil, nunca logadas.
- `record_gateway_attempt`/`record_gateway_failure`/`record_legacy_fallback_used`/`record_setup_brain_role_configured` mantêm o mesmo rigor.

---

## 14. Referências cruzadas

- [`pipeline-dados.md`](pipeline-dados.md) — fluxo completo de dados que consome estes modelos (K3/K4/K5/K6/K7).
- [`arquitetura.md`](arquitetura.md) — §24 (VectorBackend), §26 (RetrievalRouter), §27 (K3/K4), §29 (cadência), §30 (workspace/federação), §31 (rerank/forget).
- [`runtime.md`](runtime.md) — serviços e jobs que executam o Dream Cycle e o `sinapse-consolidate`.
- [`instalacao.md`](instalacao.md) — `setup-brain`, registro de agentes, `install.sh` e o bloco env do gateway.
- [`operacao.md`](operacao.md) — operação de fallback, quarentena e escape hatches (`HIVE_FORCE_LEGACY_LLM`).
- [`observabilidade.md`](observabilidade.md) — `ModelGateway.health()`, benchmark CLI (`model_benchmark.py`), telemetria de gateway.
- Fontes de origem: [`02-ai-models.md`](02-ai-models.md), [`modelos-ia.md`](modelos-ia.md), [`03-data-pipeline.md`](03-data-pipeline.md).
