# Arquitetura de Conhecimento e Promoção

> Status: arquitetura alvo born-large. O Hive-Mind deve nascer preparado para
> escala, sem depender de refatoração estrutural posterior para suportar
> Milvus, pipelines documentais avançados ou roteadores compostos.

---

## 1. Decisão

O Hive-Mind não é apenas um RAG local. Ele é um cérebro persistente com:

- captura temporal rica;
- memória consolidada;
- documentos e código;
- visão;
- grafo estrutural;
- causalidade temporal;
- busca híbrida e vetorial.

Portanto, a arquitetura de conhecimento deve separar **captura**, **promoção**,
**armazenamento**, **indexação** e **recuperação** desde o início.

Ferramentas externas entram como padrões/backends oficiais:

| Ferramenta | Papel no Hive-Mind | Status arquitetural |
|---|---|---|
| RAGFlow | Referência/adapter para ingestão documental, parsing, chunking, citações | primeira classe no `DocumentPipeline` |
| Milvus | Backend vetorial de produção para coleções grandes | primeira classe no `VectorBackend` |
| LlamaIndex | Referência/adapter para retrievers compostos e workflows | primeira classe no `RetrievalRouter` |
| sqlite-vec | Backend local/dev/offline e cache operacional | obrigatório para local-first |
| claude-mem | Hipocampo temporal: prompts, observations, discoveries, summaries | obrigatório |
| Graphify | Grafo estrutural de vault/código | obrigatório |
| Graphiti | Causalidade e validade temporal | obrigatório |
| LightRAG/GraphRAG | Relações multi-hop e perguntas globais | obrigatório/expandível |

### 1.1 Vendor: clone vs wrapper

- **Clone** (`integrations/<nome>/` via `components.lock.json`): só o que o
  `install.sh` builda/patcha do source — `graphify`, `neural-memory`, `rtk`,
  `omniparser`, binário `crsqlite`.
- **Wrapper** (`client.py` + `docker-compose.yml` com imagem pinada por digest):
  serviço rodado via container/SDK — `graphiti`, **Milvus** (`pymilvus`),
  **RAGFlow** (`ragflow-sdk`, headless).
- **Pip**: **LlamaIndex** (`llama-index` em `pyproject.toml`).

Milvus e RAGFlow **não são clonados**. RAGFlow roda headless: resultado flui
para `document_vectors`+UMC; o store dele é cache de ingestão, não fonte de
verdade (§16). Fork da UI do RAGFlow = trilha futura separada
(`docs/12` §3.4): só então migra para clone+patch.

`components.lock.json` também é um **contrato negativo**: se Milvus, RAGFlow ou
LlamaIndex aparecerem ali nesta frente, a implementação está errada. Eles entram
respectivamente por wrapper/compose+SDK e pip.

---

## 2. Fluxo Completo

```text
Agente / Humano / Sistema
        |
        v
[1] Capture Layer
    hooks, MCP, CLI, browser, documentos, codigo, screenshots, runtime
        |
        v
[2] Temporal Hippocampus
    claude-mem:
      user_prompts
      observations
      discoveries
      session_summaries
      facts / narrative / concepts
        |
        v
[3] Knowledge Intake
    normaliza, classifica, deduplica, preserva evidencia
        |
        v
[4] Promotion Layer
    raw -> summary -> fact / learning / decision / preference / task / rationale
        |
        v
[5] Anatomical Memory
    cerebro/ + UMC:
      cortex temporal
      cortex frontal
      cortex parietal
      cortex occipital
      cerebelo
      diencefalo
      tronco
        |
        v
[6] Index Layer
    FTS, sqlite-vec, Milvus, vec_observations, Graphify, Graphiti, LightRAG
        |
        v
[7] Retrieval Router
    escolhe temporal, memoria, documento, codigo, grafo, chunk ou hibrido
        |
        v
[8] Answer + Citation
    resposta com fonte, evidencia, caminho e data
        |
        v
[9] Feedback
    nova observacao, decisao, aprendizado ou tarefa
```

---

## 3. Preenchimento Por Parte Do Cerebro

| Parte | O que recebe | Unidade atomica | Ferramentas que escrevem (real) | Indices |
|---|---|---|---|---|
| Cortex temporal | fatos, preferencias, aprendizados | `neuronio-*.md` | `dream_cycle` (Distiller→Validator→Router) ← `claude_mem_bridge`; `drift_detector`(→arquivo); `topic_consolidator`; `alias_miner` | memory vector, FTS, Graphiti, LightRAG |
| Cortex frontal | decisoes, planos, trabalho, objetivos | decision/task/goal | `decision_promoter`, `work_tracker`, `decision_staleness`, MCP `save_decision`/`plan_goal` | FTS, goals, memory vector |
| Cortex parietal | documentos, referencias, inbox | document/chunk/input | `capture/*`, `document_ingest` (→DocumentPipeline) | doc vector, FTS, parent |
| Cortex occipital | screenshots, visao, grafo estrutural | visual memory / graph node | `visual_capture`, Graphify, dream estagio visual | visual index, graph |
| Cortex insula | saude, autoconsciencia, conflitos | operational_fact / conflito | `health_dashboard`, `alert_dispatcher`, `review_writer`(→saude); `conflict_detector`, `topic_consolidator`(→conflitos); `ambiguities`(sintese) | FTS, ambiguities |
| Cerebelo | sessoes, diario, semanal, padroes | session/summary / learning atomico | `session_consolidator`, `daily_writer`, `weekly_synthesizer`, `pattern_distiller` | summary vector, FTS |
| Diencefalo | conhecimento cross-projeto/setorial | sector relation / MOC | `sector_classifier`, `generate_mocs` | graph, metadata filter |
| Tronco | modelos, configs, infra, agentes | operational fact/config/template | `setup-brain`, templates `modelos/`, `meta/` (mais estatico que promovido) | FTS |

Regra: arquivo grande pode existir para leitura humana, mas a unidade de busca
deve ser atomica. `Patterns.md` nao pode ser o unico neuronio de aprendizado;
cada aprendizado precisa virar `type=learning` individual.

### 3.1 Quem preenche cada area — estado atual (codigo real)

A tabela acima e o contrato; esta e a verdade em codigo hoje (arquivos reais que
escrevem em cada area). Toda nova ferramenta de promocao deve se encaixar aqui,
nao reinventar.

> Estado operacional K3 (2026-06-28; revalidado em 2026-06-29): `core/knowledge/intake.py` e
> `core/knowledge/promotion.py` materializam a camada `[3] Knowledge Intake` e
> `[4] Promotion Layer`. Os promotores especializados abaixo mantem sua escrita
> historica, mas tambem expõem saida `candidate-only` idempotente com
> `workspace_id` para orquestracao central. Superficies: CLI
> `sinapse-write.py promotion`, MCP `sinapse_promote_knowledge`, e Dream Cycle
> com intake candidate-only antes da sintese legada. Aceite real: pipeline
> SQLite, Dream Cycle `--once --real`, query via CLI e suite completa
> `./tests/run_all.sh` verdes em 2026-06-29.

| Area | Ferramentas que escrevem (arquivo real) | Indice |
|---|---|---|
| Cortex temporal (neuronios) | `claude_mem_bridge.py` (claude-mem→observations, preserva `project`) → `dream_cycle.py` (Distiller→Validator→Router→`neuronio-*.md` + UPSERT) · `drift_detector.py` (→`arquivo/` frio >90d) · `topic_consolidator.py` · `alias_miner.py` · `generate_mocs.py` | UMC vec/fts + Graphiti `push_neuron` + LightRAG `index_memory` |
| Cortex frontal (decisao/trabalho) | `decision_promoter.py` (→`decisoes/`) · `work_tracker.py` (→`trabalho/ativo/`) · `decision_staleness.py` · `sinapse_mcp` `save_decision`/`plan_goal` (goals) · Current State (`session_end`) | UMC fts/vec, `goals` |
| Cortex parietal (sensorial) | `capture/` (screenpipe+parsers→`inbox/`) · `document_ingest.py` (→`document_memories`+`inbox/documents/`) | document index, fts |
| Cortex occipital (visao/grafo) | `visual_capture.py`/`sinapse_capture_screen` (→`visual_memories`,`capturas-visuais/`) · Graphify (→`graph.json`) · `dream_cycle` estagio visual | grafo Leiden, visual |
| Cortex insula (autoconsciencia) | `health_dashboard.py` · `alert_dispatcher.py` · `review_writer.py` (→`saude/`) · `conflict_detector.py` · `topic_consolidator.py` (→`conflitos/`) · `ambiguities` (sintese dialetica estagio 3) | UMC, `ambiguities` |
| Cerebelo (cadencia) | `session_consolidator` · `daily_writer.py` · `weekly_synthesizer.py` · `monthly_synthesizer.py` · `yearly_synthesizer.py` · `pattern_distiller.py` (→`padroes/`) | summary, fts |
| Diencefalo (relay) | `sector_classifier.py` (→`setores/` MOCs) · `generate_mocs.py` · `roteamento/` | grafo |
| Tronco (infra) | `modelos/` (templates) · `paineis/` (.base) · `meta/` — mais estatico que promovido | — |

---

## 4. Tipos Canonicos De Conhecimento

| Tipo | Origem comum | Promove para | Observacao |
|---|---|---|---|
| `event_raw` | hook/claude-mem/runtime | temporal apenas ou investigation | nunca apagar |
| `user_prompt` | claude-mem | evidencia/intencao | preserva pergunta original |
| `session_summary` | claude-mem | cerebelo/sessao | contem investigado, feito, pendente |
| `discovery` | claude-mem | fact/learning/rationale/task | nao e bruto descartavel |
| `fact` | Dream Cycle/discovery | cortex temporal | fato atomico validado |
| `preference` | conversa/decisao | cortex temporal/_global | preferencia do usuario/projeto |
| `decision` | MCP/summary/discovery | cortex frontal + temporal | decisao com razao |
| `learning` | discovery/Patterns | cerebelo + temporal | aprendizado atomico |
| `rationale` | codigo/decisao | temporal/frontal | por que algo existe |
| `operational_fact` | health/runtime/audit | tronco/insula | estado real verificavel |
| `document_chunk` | docs/PDF/vault | parietal | chunk pequeno + parent |
| `code_symbol` | Graphify/code scan | occipital/structural | funcao/classe/modulo |
| `visual_observation` | screenshot | occipital/parietal | imagem + descricao |
| `next_step` | session summary/discovery | goal/task | vira trabalho rastreavel |

---

## 5. Fluxo Ideal De Promocao

```text
claude-mem observation/discovery/session_summary
        |
        v
Knowledge Intake
  - normaliza campos
  - preserva source ids
  - extrai evidence/files/timestamps
  - classifica tipo
        |
        v
Promotion Layer
  investigated  -> rationale / investigation note
  completed     -> operational_fact / session_summary
  learned       -> learning atomico
  decisions     -> decision
  preferences   -> preference
  next_steps    -> goal / task
  facts         -> fact
        |
        v
Persistencia
  - cria/atualiza Markdown anatomico
  - UPSERT neurons
  - observation.neuron_id = neuron.id
  - archived = 1
        |
        v
Indexacao
  - FTS
  - vector backend local/producao
  - Graphiti edges
  - LightRAG/GraphRAG quando relacional
```

Falha:

```text
erro transitorio -> archived=0, retry futuro
erro estrutural  -> archived=2, quarentena com motivo
```

Dados nunca sao deletados por falha de promocao.

---

## 6. Claude-Mem Nao E Apenas Dado Bruto

O claude-mem gera artefatos ricos que precisam ser preservados:

| Artefato | Uso |
|---|---|
| `user_prompts` | intencao original, auditoria, reproducao |
| `observations` | eventos, discoveries, bugfixes, changes |
| `session_summaries` | investigado, concluido, pendente |
| `facts` | candidatos a `fact` |
| `narrative` | contexto de raciocinio |
| `concepts` | tags/roteamento |
| `files_read/files_modified` | evidencia e links com codigo/documento |
| `prompt_number` | ordem temporal |
| `generated_by_model` | procedencia |

Regra: discovery/session summary nao fica esquecido como `archived=0`.
Ele precisa passar pelo Promotion Layer e produzir unidades atomicas quando
contiver aprendizado, decisao, fato, preferencia ou proximo passo.

Implementacao K4 (2026-06-29):

- Bridge canonico: `core/knowledge/claude_mem_bridge.py`.
- Entry point legado: `scripts/services/claude_mem_bridge.py` apenas delega ao
  core.
- Mecanismo: leitura SQL direta read-only de `~/.claude-mem/claude-mem.db`.
  Este e o caminho de promocao/backfill porque aceita ids e janela temporal sem
  depender de busca textual. O workflow `search -> timeline -> get_observations`
  segue sendo o caminho interativo para recuperar contexto bruto antes de
  escolher ids.
- Schema real atual: `session_summaries` existe; `discoveries` pode nao existir.
  Quando ausente, discoveries vêm de `observations.type='discovery'` com campos
  `facts`, `narrative`, `concepts` e `files_*`.
- `source_id` estavel: `claude-mem:<table>:<id>`, preservado em metadata e
  evidencia para rastrear a origem.
- CLI/MCP: `sinapse-write.py promotion --import-claude-mem` e
  `sinapse_promote_knowledge(import_claude_mem=true)` importam e promovem no
  mesmo fluxo.
- Aceite 2026-06-29: bridge real 2 passed, promocao operacional contra
  `~/.claude-mem/claude-mem.db` importou registros reais por `source_id`, CLI
  com `python3` do sistema saiu 0 via reexecucao na `.venv`, e
  `./tests/run_all.sh` fechou verde. A validacao de visao real usa o papel
  `vision` configurado no `setup-brain`/`.env` (`HIVE_VISION_*`), sem hardcode
  de Ollama Cloud.

---

## 7. Chunking E Parent Context

Vector search deve operar sobre chunks pequenos, mas a resposta deve recuperar
o contexto pai.

```text
documento / sessao / arquivo / discovery
        |
        v
chunks atomicos
  - 300 a 800 tokens para texto comum
  - por secao para Markdown
  - por simbolo para codigo
  - por observation/discovery para claude-mem
        |
        v
embedding do chunk
        |
        v
resultado vetorial
        |
        v
recupera parent:
  - documento completo
  - sessao
  - arquivo
  - observation original
  - neuronio anatomico
```

Cada chunk deve ter metadata minima:

```yaml
chunk_id:
parent_id:
parent_type:
project:
brain_lobe:
knowledge_type:
source_uri:
created_at:
valid_at:
agent_id:
model:
hash:
offset_start:
offset_end:
```

---

## 8. Estrategia De Vector Search

O Hive-Mind deve suportar colecoes separadas. Nao colocar tudo no mesmo ranking.

| Colecao | Conteudo | Backend local | Backend producao |
|---|---|---|---|
| `memory_vectors` | facts, decisions, learnings, preferences | UMC `hive_mind.db/search_vec` | Milvus |
| `observation_vectors` | claude-mem observations/discoveries | `~/.claude-mem/claude-mem.db/vec_observations` (`sqlite-vec-worker`, read-only pelo VectorBackend local) | Milvus |
| `document_vectors` | document chunks/vault docs | UMC `vec_documents` + `vector_metadata` | Milvus |
| `code_vectors` | code symbols/files | UMC `vec_code` + `vector_metadata` | Milvus |
| `visual_vectors` | screenshots/visual descriptions | UMC `vec_visual` + `vector_metadata` | Milvus |
| `graph_vectors` | entity/relation summaries | UMC `vec_graph` + `vector_metadata` | Milvus + graph |
| `summary_vectors` | resumos de cadencia (sessao→anual) | UMC `vec_summary` + `vector_metadata` | Milvus |

`sqlite-vec` continua obrigatorio para local-first/offline. Milvus e backend
de producao, nao substitui a fonte de verdade.

Cada item vetorial precisa carregar metadados canônicos: `parent_id`,
`parent_type`, `brain_lobe`, `knowledge_type`, `project`, `source_uri`, `hash`,
`valid_at` e `workspace_id`. No UMC, coleções auxiliares guardam esses campos em
`vector_metadata`; no Milvus, eles viram campos obrigatórios do schema. O modelo
e a dimensão do embedding continuam controlados pelo contrato global:
`snowflake-arctic-embed2:latest`, 1024d, salvo override explícito por env.

---

## 9. Contrato VectorBackend

Todo backend vetorial precisa implementar o mesmo contrato:

```text
upsert(collection, id, vector, metadata)
delete(collection, id)
query(collection, vector, top_k, filters)
hybrid_query(collection, text, vector, filters)
count(collection, filters)
health()
```

Backends oficiais:

| Backend | Papel |
|---|---|
| `sqlite_vec` | local/dev/offline/cache |
| `milvus` | producao/escala/multi-colecao |

Requisito: a aplicacao nunca deve chamar Milvus diretamente fora do contrato.
Isso evita trocar a anatomia do cerebro por detalhe de infraestrutura.

---

## 10. DocumentPipeline Born-Large

Inspirado em RAGFlow, mas preservando a anatomia do Hive-Mind.

```text
document input
        |
        v
parse layout-aware
        |
        v
normalize
        |
        v
chunk by structure
        |
        v
metadata + citations
        |
        v
embedding
        |
        v
document_vectors + parent document
        |
        v
optional promotion to facts/learnings
```

RAGFlow pode entrar como adapter/servico de ingestao, mas nao como fonte de
verdade. A fonte de verdade continua sendo `cerebro/` e UMC.

Contrato K6 implementado:

- `DocumentPipeline.ingest(path, project)` grava um parent em
  `document_memories` e chunks atomicos em `document_chunks`.
- `document_chunks` preserva offsets absolutos (`offset_start`, `offset_end`),
  `heading`, `source_uri`, `hash`, `workspace_id` e ponte de parent
  (`parent_id`, `parent_type=document`).
- Cada chunk entra em `document_vectors` pelo `VectorBackend`, com
  `brain_lobe=parietal` e `knowledge_type=document_chunk`.
- `DocumentPipeline.query(text)` retorna citacoes auditaveis:
  `source_uri`, offsets, conteudo do chunk e parent com `file_hash` e metadata.
- `scripts/knowledge/document_ingest.py` usa o pipeline quando o banco real
  tem `sqlite-vec`; o caminho legado existe apenas para compatibilidade com
  schemas minimos/testes antigos.
- RAGFlow e usado como adapter/headless opcional (`integrations/ragflow/`),
  nunca como fonte canonica. Qualquer output externo precisa ser normalizado
  para `document_memories` + `document_chunks` + `document_vectors`.

### 10.1 Contrato De Documento, Chunk E Vetor

K6 separa tres niveis para evitar "texto solto" sem prova:

| Nivel | Tabela/colecao | Conteudo | Por que existe |
|---|---|---|---|
| Documento-pai | `document_memories` | `document_id`, `source_uri`, `file_hash`, `project`, `workspace_id`, metadata | Prova de origem e unidade de reingestao |
| Chunk | `document_chunks` | `parent_id`, `parent_type=document`, `chunk_index`, `heading`, offsets, `hash`, metadata | Unidade atomica recuperavel |
| Vetor | `document_vectors` | embedding do chunk + metadata canonica | Busca semantica local/Milvus sem perder parent context |

Metadados obrigatorios em `document_vectors`:

- `parent_id`
- `parent_type=document`
- `brain_lobe=parietal`
- `knowledge_type=document_chunk`
- `project`
- `source_uri`
- `hash`
- `valid_at`
- `workspace_id`

Sem esses campos, o vetor e considerado incompleto para o desenho K6, porque
nao da para provar a origem, filtrar por workspace/projeto nem sincronizar para
Milvus com idempotencia.

### 10.2 Ingestao Local-First

Fluxo normativo:

```text
path real
  |
  +-- calcular file_hash e document_id estavel
  +-- parser por tipo (.md/.txt/.pdf/.docx)
  +-- gerar chunks estruturais com offsets
  +-- substituir parent/chunks/vetores antigos do mesmo document_id
  +-- gravar parent em document_memories
  +-- gravar chunks em document_chunks
  +-- indexar cada chunk em document_vectors
```

Markdown deve preservar headings. Texto sem estrutura deve quebrar por
paragrafo e depois por janela fixa. PDF com texto usa parser real; PDF sem texto
gera chunk fallback auditavel para nao perder a existencia do documento. DOCX
depende de `python-docx` e deve falhar de forma clara quando a dependencia nao
estiver instalada.

### 10.3 Consulta Com Parent Context

Consulta documental valida segue este formato:

```text
query
  -> document_vectors
  -> document_chunks
  -> document_memories
  -> citations[{source_uri, offset_start, offset_end, score, parent}]
```

O retorno nao pode ser apenas "melhor trecho". Ele precisa carregar o trecho,
score, `source_uri`, offsets e parent completo o suficiente para auditoria. O
`RetrievalRouter` K7 usa esta rota quando classifica a pergunta como
documental; K6 nao decide intent global.

### 10.4 Papel Do RAGFlow

RAGFlow e permitido como parser/headless para documentos complexos, mas com
fronteiras:

- nao e fonte de verdade;
- nao substitui `document_memories`, `document_chunks` ou `document_vectors`;
- cache/store proprio nao entra no contrato de recuperacao;
- indisponibilidade do RAGFlow nao pode quebrar o caminho local-first;
- qualquer saida aproveitada precisa ser normalizada para UMC antes de ser
  recuperavel pelo cerebro.

### 10.5 Relacao Com Promocao De Conhecimento

K6 torna documentos recuperaveis. Ele nao decide sozinho que um trecho virou
fato, decisao ou aprendizado duravel. A promocao continua no fluxo K3/K4:

```text
document_chunks/document_vectors
  -> evidencia citavel
  -> KnowledgePromotionPipeline
  -> fact/learning/decision/preference
  -> cortex temporal/frontal/cerebelo
```

Essa separacao evita poluir memoria duravel com todo chunk de documento e
preserva a diferenca entre evidencia recuperavel e conhecimento promovido.

---

## 11. RetrievalRouter Born-Large

Inspirado em LlamaIndex, implementado como contrato proprio.

**Status K7 (v3.5.0, 2026-06-30):** entregue em
`core/retrieval/router.py`. O router classifica intent, executa rotas
especializadas, preserva fallback para `sinapse_query`/Context Fusion e retorna
`retrieval_path`, `citations`, `confidence` e `missing_context` em todas as
consultas. `core/search.py` expoe `route_retrieval()` como adaptador interno
para callers que precisam do contrato K7 sem passar por MCP/API. LlamaIndex
entra apenas como adapter opcional de rerank; nao decide rota nem vira fonte de
verdade.

```text
query
  |
  +-- recente / "o que aconteceu"       -> claude-mem temporal
  +-- decisao / preferencia             -> memory_vectors + FTS
  +-- aprendizado                       -> learning atoms + Patterns parent
  +-- documento                         -> document_vectors + parent context
  +-- codigo                            -> code_vectors + Graphify
  +-- causalidade / quando era verdade  -> Graphiti
  +-- pergunta global / multi-hop       -> LightRAG/GraphRAG
  +-- saude / autoconsciencia           -> insula (saude/conflitos)
  +-- config / operacional / modelo     -> tronco (operational_fact)
  +-- setor / cross-projeto             -> diencefalo + Graphiti
  +-- ambigua                           -> hybrid + reranker
```

O roteador deve retornar:

```json
{
  "answer_context": [],
  "citations": [],
  "retrieval_path": [],
  "confidence": 0.0,
  "missing_context": []
}
```

---

## 12. Contrato De Escrita

Toda tool ou pipeline que escreve memoria deve declarar:

| Pergunta | Obrigatorio |
|---|---|
| Cria observation? | sim/nao |
| Cria arquivo anatomico? | caminho |
| Cria neuron? | tipo |
| Cria vector? | colecao |
| Cria edge? | Graphiti/Graphify/LightRAG |
| Cria task/goal? | sim/nao |
| Qual evidencia? | source ids/files |
| Como reprocessa? | idempotency key/hash |

Exemplo:

```yaml
writer: sinapse_save_learning
observation: true
file: cerebro/cerebelo/padroes/Patterns.md
neuron: learning
vector_collection: memory_vectors
edges:
  - related_to
promotion_required: false
idempotency: title+content_hash
```

---

## 13. Metricas De Saude

O sistema deve expor metricas por camada:

**Status K8 (v3.6.0, 2026-06-30):** entregue em
`scripts/health/knowledge_health.py`. Este modulo adiciona metricas de
cobertura de conhecimento; ele nao substitui `health_dashboard.py`,
`alert_dispatcher.py` nem `review_writer.py`, que continuam sendo o health da
Insula. `sinapse_health` inclui um bloco `knowledge_health` read-only em modo
quick, e a REST API expoe `GET /api/v1/knowledge/health` para o gate completo.

| Metrica | Sinal |
|---|---|
| `neurons_total` | tamanho da memoria consolidada |
| `neurons_vectorized_pct` | cobertura vetorial |
| `observations_pending` | backlog temporal |
| `observations_linked_pct` | promocao efetiva |
| `discoveries_pending` | risco de perder aprendizado |
| `learnings_atomized` | aprendizado granular |
| `document_chunks_total` | ingestao documental |
| `code_symbols_total` | cobertura estrutural |
| `milvus_sync_lag` | divergencia local/producao |
| `orphan_vectors` | indice sujo |
| `query_route_distribution` | quais camadas respondem |
| `*_vectorized_pct` | cobertura por colecao canonica |

K8 mede as sete colecoes canonicas: `memory_vectors`,
`observation_vectors`, `document_vectors`, `code_vectors`, `visual_vectors`,
`graph_vectors` e `summary_vectors`. O gate nao pode olhar apenas
`neurons_vectorized_pct`: document/code/visual/graph/summary tambem precisam
aparecer explicitamente.

`query_route_distribution` vem de `query_route_log`, preenchida pelo
`RetrievalRouter` em modo best-effort. A query gravada e sempre hash; o texto
bruto da pergunta nao entra na telemetria.

Gate minimo de producao:

```text
neurons_vectorized_pct >= 99%
observations_linked_pct crescente por ciclo
discoveries_pending dentro do SLA
0 orphan vectors
todos os chunks com parent_id
citations presentes nas respostas documentais
```

---

## 14. Cadencia Hierarquica De Escrita

A memoria do Hive-Mind nao deve depender de um unico resumo gigante. Ela deve
subir em camadas: sessao -> diario -> semanal -> mensal -> anual. Cada camada
tem um objetivo diferente, um modelo possivel e uma regra de promocao propria.

| Cadencia | Writer / papel | Entrada | Saida anatomica | Modelo | Promove |
|---|---|---|---|---|---|
| Sessao | `scripts/dream/session_consolidator.py` / `session_summarizer` | log bruto da sessao, tool calls e notas incrementais | `cerebro/cerebelo/sessoes/YYYY/MM/YYYY-MM-DD-HHMM-{slug}.md` | pequeno/rapido e suficiente na maioria dos casos | decisoes, perguntas abertas e evidencias candidatas |
| Diario | `scripts/dream/daily_writer.py` / `daily_writer` | sessoes do dia e resumos de sessao | `cerebro/cerebelo/diario/YYYY/MM/YYYY-MM-DD.md` | pequeno ou medio | aprendizados candidatos, progresso do dia, proximos passos |
| Semanal | `scripts/dream/weekly_synthesizer.py` / `weekly_synthesizer` | diarios, sessoes relevantes, fatos, decisoes, status de projetos e metricas | `cerebro/cerebelo/semanal/YYYY-Wxx.md` | medio/forte recomendado | padroes, decisoes estrategicas, status de projeto e prioridades |
| Mensal | `scripts/dream/monthly_synthesizer.py` / `monthly_synthesizer` | semanais, projetos ativos, decisoes, discoveries, metricas de saude e backlog | `cerebro/cerebelo/mensal/YYYY-MM.md` | forte recomendado | sintese executiva, drift estrategico, metas, riscos persistentes |
| Anual | `scripts/dream/yearly_synthesizer.py` / `yearly_synthesizer` | mensais, marcos, padroes duradouros e retrospectiva de projetos | `cerebro/cerebelo/anual/YYYY.md` | mais forte disponivel ou batch offline | memoria historica, principios, estrategias e lessons learned duraveis |

`session_summarizer`, `daily_writer`, `weekly_synthesizer`,
`monthly_synthesizer` e `yearly_synthesizer` sao papeis configuraveis no
`setup-brain`. Eles herdam do `dreamer` se nao houver modelo proprio, mas o
desenho correto e permitir custo/qualidade por cadencia:

1. Sessao e diario podem usar modelo pequeno porque a tarefa e compressao local
   com pouco contexto e baixo risco. O objetivo e reduzir ruido, nao tomar
   decisoes globais.
2. Semanal deve usar modelo medio ou forte, pois cruza varios dias, projetos,
   decisoes e metricas. Aqui comeca a deteccao real de padroes.
3. Mensal e anual devem usar modelo forte ou batch offline, porque produzem
   memoria estrategica e podem alterar prioridade, arquitetura e backlog.

### 14.1 O Que Vai E O Que Nao Vai

Cada cadencia deve escrever resumo, mas nem todo resumo vira neuronio ou vetor
de longo prazo.

| Fonte | Vai para memoria de longo prazo | Nao vai |
|---|---|---|
| Log bruto de sessao | apenas evidencias referenciaveis e eventos importantes | tool call repetitivo, erro temporario sem aprendizagem, ruido de terminal |
| Resumo de sessao | decisoes, perguntas abertas, tarefas e descobertas com fonte | bullets narrativos sem consequencia |
| Diario | aprendizados do dia, progresso por projeto, bloqueios recorrentes | lista completa de arquivos lidos ou comandos executados |
| Semanal | padroes, mudancas de direcao, status consolidado, prioridades | microdetalhes ja cobertos por sessoes/diarios |
| Mensal | sintese executiva, riscos estruturais, metas, drift de estrategia | progresso operacional sem impacto duravel |
| Anual | principios, retrospectiva de arquitetura, grandes decisoes, lessons learned | repeticao de semanais/mensais sem abstracao nova |

Regra de ouro: quanto mais alta a cadencia, menos ela deve copiar texto e mais
ela deve consolidar causalidade, decisao, padrao e consequencia.

### 14.2 Contrato De Promocao Por Cadencia

O pipeline de promocao deve tratar cada resumo como fonte com `source_id`,
`period_start`, `period_end`, `cadence` e `parent_summary_id`.

```yaml
summary:
  cadence: session | daily | weekly | monthly | yearly
  source_id: path-or-observation-id
  period_start: ISO-8601
  period_end: ISO-8601
  parent_summary_id: optional
  llm_role: session_summarizer | daily_writer | weekly_synthesizer | monthly_synthesizer | yearly_synthesizer
  llm_model: resolved-provider/model
  promotes:
    observations: true
    neurons: candidate-only
    vectors: summary_vectors
    tasks: candidate-only
```

Promocao automatica permitida:

1. `decision` quando o texto declara escolha, alternativa rejeitada e motivo.
2. `learning` quando ha padrao reutilizavel com contexto e consequencia.
3. `project_status` quando ha estado verificavel de projeto, data e fonte.
4. `operational_fact` quando `completed` ou um sumario operacional declara
   estado verificavel produzido pela sessao.
5. `goal/task` quando ha proximo passo acionavel, dono ou criterio de aceite.
6. `rationale` quando explica por que uma mudanca foi feita e onde ela aplica.

Promocao automatica proibida:

1. Transformar todo bullet em `fact`.
2. Criar neuronio sem fonte rastreavel.
3. Vetorizar duplicatas sem `parent_id` e hash de conteudo.
4. Promover opiniao temporaria como decisao arquitetural.
5. Sobrescrever decisoes anteriores sem criar conflito ou `invalid_at`.

### 14.3 Relacao Com `setup-brain`

O `setup-brain` deve permitir configurar cada papel de cadencia separadamente,
mas a instalacao basica pode herdar tudo do `dreamer`.

| Papel | Default aceitavel | Quando sobrescrever |
|---|---|---|
| `session_summarizer` | modelo pequeno local/cloud barato | se os logs forem longos, multilíngues ou cheios de codigo |
| `daily_writer` | modelo pequeno ou medio | se o dia tiver muitos projetos e decisoes |
| `weekly_synthesizer` | modelo medio/forte | sempre que houver promocao para padroes/status |
| `monthly_synthesizer` | modelo forte | quando gerar metas, riscos, drift e sintese executiva |
| `yearly_synthesizer` | modelo forte/batch | quando consolidar memoria historica e principios |

Para maquina zerada, a regra e fail-closed: se um papel nao tiver modelo
proprio nem heranca do `dreamer`, o writer deve registrar falha auditavel e nao
inventar sintese. Para custo baixo, sessao e diario podem usar modelo pequeno;
mensal/anual nao devem ser rebaixados automaticamente sem aviso.

### 14.4 Estado De Implementacao

Implementado hoje (K5, 2026-06-29):

1. `session_consolidator.py` escreve resumo de sessao com
   `session_summarizer` e indexa o arquivo em `summary_vectors`.
2. `daily_writer.py` escreve diario com `daily_writer` e indexa o arquivo em
   `summary_vectors`.
3. `weekly_synthesizer.py` escreve semanal com `weekly_synthesizer`, aceita
   `--real` para o gate de aceite e indexa o arquivo em `summary_vectors`.
4. `monthly_synthesizer.py` escreve `cerebro/cerebelo/mensal/YYYY-MM.md` com
   `MonthlySummaryModel`, `source_id`, `parent_summary_id`, periodo, papel e
   modelo resolvido.
5. `yearly_synthesizer.py` escreve `cerebro/cerebelo/anual/YYYY.md` com
   `YearlySummaryModel`, `source_id`, `parent_summary_id`, periodo, papel e
   modelo resolvido.
6. `core/vector_sync.py` tem `index_summary_file_to_sqlite()` para indexacao
   imediata e o backfill de `summary_vectors` cobre tambem `anual/`.

Regra operacional: mensal/anual geram resumos estrategicos, mas a promocao
automatica continua restrita a decisoes, aprendizados, riscos, metas e
principios duraveis com fonte rastreavel.

---

## 15. Implementacao Inicial Obrigatoria

Para nascer grande, o projeto deve implementar agora:

1. `VectorBackend` com `sqlite_vec` e contrato para `milvus`.
2. `KnowledgePromotionPipeline` explicito.
3. `DocumentPipeline` com chunk/parent/citation metadata.
4. `RetrievalRouter` com rotas por intencao.
5. Atomizacao de `learning` a partir de `Patterns.md` e discoveries.
6. Promocao de `session_summaries` e discoveries do claude-mem.
7. Metricas de cobertura por camada.
8. Documentacao de colecoes vetoriais e tipos canonicos.

O plano operacional detalhado vive em
[`12-knowledge-implementation-plan.md`](12-knowledge-implementation-plan.md):
fases K0-K10, tasks, integracoes clonadas em `integrations/`, modelos locais
pequenos por papel, env vars e testes reais sem mocks como criterio de aceite.

Nao e aceitavel deixar esses conceitos para uma migracao estrutural posterior.
Mesmo que a primeira implementacao use sqlite-vec local, a arquitetura e os
contratos precisam nascer compatíveis com Milvus e ingestion/retrieval em escala.

---

## 16. Regra Final

O Hive-Mind deve ser:

```text
local-first por operacao
born-large por arquitetura
plugavel por contrato
anatomico por fonte de verdade
auditable por evidencia
```

Nenhum backend externo pode substituir o cerebro. Backends externos aceleram,
escalam ou especializam indices. A verdade continua no vault anatomico e no UMC.

---

## 17. Contratos Pendentes (lacunas verificadas)

Capacidades **ja existentes** (nao reimplementar): merge/dedup na promocao
(Dream Cycle Router `append|create_new|merge` + tabela `ambiguities` +
`register_ambiguity` + dedup de learning por titulo + dedup cross-backend em
`context_fusion`); redacao de PII/segredo (`core/redactor.py`, no export federado).

As lacunas abaixo nao tem implementacao hoje e nascem como contrato.

### 17.1 Reranker (reordenacao por relevancia)

Hoje `context_fusion._fuse_contexts` dedupa e **trunca** por ordem de backend —
nao reordena pelo que responde a query. Contrato:

```text
rerank(query, candidates[]) -> candidates[] reordenados
  entra: top-N bruto da fusao (ex.: 30)
  modelo: cross-encoder pequeno local (env HIVE_RERANKER_PROVIDER/MODEL); papel opcional
  sai: top-K (ex.: 5) ordenado por score de relevancia
  fail-open: sem modelo/erro -> ordem atual (dedup+truncate), sem quebrar
```

Plugar entre a fusao e o retorno do `RetrievalRouter` (§11). Off por padrao em
`local-min`.

### 17.2 Esquecimento intencional (forget / retention)

A regra "nunca deletar por falha" (§5) cobre falha, nao esquecimento deliberado.
Falta apagar segredo vazado, expirar efemero e podar orfao. Contrato:

```text
forget(target, reason) -> tombstone auditavel (nunca delete fisico silencioso)
  motivos: secret_leak | expired | superseded | user_request | orphan_vector
  CRDT-safe: delete em CR-SQLite e tombstone; vetor correspondente removido no backend
  audita: registra em insula (motivo, quem, quando); raw preservado so se nao for segredo
```

Casa com a metrica `orphan_vectors` (§13) — orfao podado, nao so medido. Segredo
em sync/Milvus-remoto deve reusar `core/redactor.py` antes de cruzar maquina.

K8 implementa a primeira fatia desse contrato para vetores orfaos:
`knowledge_health.py` chama `forget_vector()` com motivo `orphan_vector`, remove
o item da colecao sqlite-vec local, limpa `vector_metadata` quando aplicavel e
grava `knowledge_tombstones` com `target_type`, `target_id`, `collection`,
`reason`, `actor`, `workspace_id` e metadata auditavel. Extensoes futuras para
`secret_leak`, `expired`, `superseded` e `user_request` devem reaproveitar a
mesma tabela de tombstone.

### 17.3 Avaliacao de recuperacao (eval)

§13 mede **cobertura** (plumbing), nao **qualidade** da resposta. Contrato:

```text
golden set: tests/real/golden_retrieval.jsonl
  cada caso: {query, expected_source_ids[], expected_intent}
metricas: precision@k, recall@k, citation_correctness, intent_accuracy
gate: regressao acima de limiar reprova a frente (junto do harness real K9)
```

Pequeno e curado a mao; cresce a cada bug de recuperacao reproduzido como caso.

### 17.4 Harness real e skip de servicos

O aceite de fase da frente de conhecimento usa `tests/real/` e nao conta mock
como fechamento. O contrato do marker `requires_service` e:

```text
se o servico real exigido estiver online: roda e falha se o comportamento falhar
se o servico real estiver offline: skip explicito com motivo e servico nomeado
se o teste nao depende de servico externo: roda sempre
```

O skip precisa ser implementado por fixture/hook de servico, nao apenas por
comentario no `pytest.ini`. Cada novo backend real (Milvus, FalkorDB, claude-mem,
RAGFlow) deve registrar sua propria fixture ou service registry antes de virar
gate de fase.

Implementação atual: `tests/real/service_registry.py` + hook em
`tests/real/conftest.py`. Serviços conhecidos: `ollama`, `milvus`, `falkordb`,
`claude_mem`, `ragflow`. Serviço desconhecido é erro de teste; serviço offline é
skip explícito com nome e motivo.

---

## 18. Escala e Isolamento (born-large, open-source)

Hive-Mind e produto open-source que nasce com escala. Nao e SaaS B2B: o eixo de
escala e (a) **per-install** (um usuario acumula anos de corpus), (b)
**multi-usuario por instancia** (um time self-hosta), (c) **federacao** entre
instancias. O isolamento abaixo nasce no schema — nao se enxerta depois — e o
single-user local-first nao percebe (default workspace unico).

### 18.1 Workspace (fronteira de isolamento)

```text
coluna workspace_id em: neurons, observations, synapses, goals, document_memories,
                        visual_memories, ambiguities, causal_edges, vault
  default: 'default'  (single-user nao precisa setar; born-large sem custo local)
indice: (workspace_id, ...) nas queries quentes
filtro: TODA leitura/escrita do RetrievalRouter e da promocao carrega workspace_id
vault: cerebro/ pode ser subtree por workspace quando multi-usuario
```

Regra: nenhum neuronio/vetor/edge cruza `workspace_id` sem passar pela camada de
federacao (§18.3). Vazamento cross-workspace e bug de seguranca, nao de ranking.

Migrações que criam essa fronteira sao estruturais. Falha de migração deve ser
fail-closed por padrão: seguir com schema parcial é bug de instalação, não modo
operacional. O único bypass permitido é diagnóstico explícito de DB legado via
`HIVE_ALLOW_DEFERRED_MIGRATIONS=1`, com log visível e sem marcar a instalação
como saudável.

### 18.2 Particao das colecoes vetoriais

```text
sqlite-vec (local/dev): filtro por workspace_id no metadata (§7)
Milvus (producao):      partition-key = workspace_id (isolamento + poda por particao)
```

A identidade da colecao inclui `(name, embedding_model, dim)` — ver §18.4.

### 18.3 Federacao entre instancias (reusa HM-12)

Ja existe e nao se reimplementa: `visibility` (private|shared|public),
assinatura Ed25519 (`core/signing.py`), redacao de PII no export
(`core/redactor.py`). Contrato born-large:

```text
export inter-instancia: so visibility in (shared, public) + redact + sign
import: verifica assinatura; neuronio importado entra com workspace_id do destino
        e proveniencia (origin_instance, origin_signature) preservada
nunca: importar raw cross-instancia sem redact; sobrescrever local sem invalid_at
```

### 18.4 Migracao de embedding versionada

Trocar modelo de embedding em escala nao e script one-shot. Espaco vetorial e
versionado:

```text
colecao carrega (embedding_model, dim) na identidade
upsert de modelo divergente: rejeitado ou vai pra colecao nova (nunca mistura)
migracao: reembed online por workspace, dual-write (modelo antigo+novo) ate cutover
metrica: vectors_model_mismatch (§13) = 0 dentro de uma colecao
```

### 18.5 Custo/throughput da promocao por workspace

Cada observacao promovida = 1 LLM (classifica) + 1 embedding. Em escala isso e
fila com backpressure e teto de custo por workspace:

```text
promocao em batch (nao 1-a-1), fila com prioridade
teto por workspace (env HIVE_PROMOTION_BUDGET_*), excedente fica archived=0 (retry)
metrica: promotion_lag e promotion_cost por workspace
```
