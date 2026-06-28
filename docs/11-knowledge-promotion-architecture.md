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

| Parte | O que recebe | Unidade atomica | Escrita primaria | Indices |
|---|---|---|---|---|
| Cortex temporal | fatos, preferencias, aprendizados, lore | `neuronio-*.md` | Dream Cycle / Promotion Layer | memory vector, FTS, Graphiti |
| Cortex frontal | decisoes, planos, trabalho ativo, objetivos | decision/task/goal | MCP/CLI/Dream Cycle | FTS, goals, memory vector |
| Cortex parietal | documentos, referencias, inbox, inputs sensoriais | document/chunk/input | DocumentPipeline | doc vector, FTS, parent context |
| Cortex occipital | screenshots, visao, grafo estrutural | visual memory / graph node | capture + Graphify | visual index, graph |
| Cerebelo | sessoes, rotinas, padroes aprendidos | session summary / learning atomico | claude-mem + Dream Cycle | memory vector, FTS |
| Diencefalo | conhecimento cross-projeto/setorial | sector relation | sector classifier | graph, metadata filter |
| Tronco | modelos, configs, infra, agentes | operational fact/config | setup/runtime/audit | FTS, operational graph |

Regra: arquivo grande pode existir para leitura humana, mas a unidade de busca
deve ser atomica. `Patterns.md` nao pode ser o unico neuronio de aprendizado;
cada aprendizado precisa virar `type=learning` individual.

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
| `memory_vectors` | facts, decisions, learnings, preferences | sqlite-vec `search_vec` | Milvus |
| `observation_vectors` | claude-mem observations/discoveries | sqlite-vec `vec_observations` | Milvus |
| `document_vectors` | document chunks/vault docs | sqlite-vec ou local files | Milvus |
| `code_vectors` | code symbols/files | sqlite-vec/Graphify | Milvus |
| `visual_vectors` | screenshots/visual descriptions | LanceDB/sqlite-vec | Milvus |
| `graph_vectors` | entity/relation summaries | LightRAG local | Milvus + graph |

`sqlite-vec` continua obrigatorio para local-first/offline. Milvus e backend
de producao, nao substitui a fonte de verdade.

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

---

## 11. RetrievalRouter Born-Large

Inspirado em LlamaIndex, implementado como contrato proprio.

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
4. `goal/task` quando ha proximo passo acionavel, dono ou criterio de aceite.
5. `rationale` quando explica por que uma mudanca foi feita e onde ela aplica.

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

Implementado hoje:

1. `session_consolidator.py` escreve resumo de sessao com `session_summarizer`.
2. `daily_writer.py` escreve diario com `daily_writer`.
3. `weekly_synthesizer.py` escreve semanal com `weekly_synthesizer`.

Contrato born-large reservado agora:

1. `monthly_synthesizer` e `yearly_synthesizer` sao papeis canonicos de LLM.
2. `MONTHLY_ROOT`, `YEARLY_ROOT`, `monthly_path()` e `yearly_path()` sao caminhos
   canonicos em `core/paths.py`.
3. Os scripts `monthly_synthesizer.py` e `yearly_synthesizer.py` devem seguir o
   mesmo contrato de schema, fonte, idempotencia e promocao descrito aqui.

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
