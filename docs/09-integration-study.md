# Estudo de Integração e Melhorias — Hive-Mind
**Data:** 2026-06-21 | **Fonte:** pesquisa online com WebSearch/WebFetch em 26 fontes

---

## Sumário Executivo

- **Graphiti (Zep)** é a integração de maior impacto arquitetural: grafo de conhecimento temporal com janelas de validade de fatos, 27.7k stars, backend FalkorDB (open-source local), MCP server pronto — complementa diretamente o grafo neurônios/sinapses atual com semântica temporal que o Hive-Mind ainda não tem.
- **Screenpipe** (19.4k stars, YC S26) substitui o Deep Portal com captura orientada a eventos (não contínua), SQLite+FTS5, MCP nativo em localhost:3030 e transcrição Whisper local — sobreposição arquitetural quase total, tornando integração via API mais viável que reimplementação.
- **sqlite-lembed + sqlite-vec** formam um duo nativo: gerar e armazenar embeddings 100% dentro do SQLite sem processo externo, usando modelos GGUF locais — upgrade direto sobre a abordagem sqlite-vec atual sem mudar o stack.
- **CR-SQLite** (vlcn-io) adiciona sincronização multi-writer CRDT ao `hive_mind.db` sem mudar o schema — habilita instâncias Hive-Mind em múltiplas máquinas convergirem automaticamente, hoje impossível sem cópia manual.
- **Langfuse (self-hosted) + OpenTelemetry** é a rota de observabilidade de menor fricção: o Hive-Mind já captura sessões; expor spans OTLP para Langfuse self-hosted adiciona replay de sessões, custo por agente e detecção de anomalias sem vendor lock-in.

---

## 1. Sistemas de Memória para Agentes

### Mem0
- **GitHub/URL**: [github.com/mem0ai/mem0](https://github.com/mem0ai/mem0) · [docs.mem0.ai](https://docs.mem0.ai)
- **O que faz**: Camada de memória universal para agentes — salva/busca/atualiza memórias semânticas via embeddings, com API Python/TypeScript e server cloud ou self-hosted. Plugin para Claude Code, Cursor e Codex (lançado mar-abr/2026) expõe 9 ferramentas MCP com lifecycle hooks.
- **Diferencial vs Hive-Mind**: Mem0 tem gestão de usuário/agente multi-session com deduplicação automática e "single-pass hierarchical extraction" (abr/2026) para token-efficiency. Não tem grafo neuronal, FTS5 nem Dream Cycle. É mais simples e mais operacionalizável out-of-box.
- **Potencial de integração**: Alta
- **Como integrar**: Substituir ou augmentar o MCP server do Hive-Mind com o `mem0-mcp` oficial ([github.com/mem0ai/mem0-mcp](https://github.com/mem0ai/mem0-mcp)), apontando o backend para o `hive_mind.db` local via adapter customizado. Alternativamente, usar o **OpenMemory MCP** como camada de memória compartilhada entre todos os agentes que hoje o Hive-Mind captura manualmente.

### OpenMemory (by Mem0)
- **GitHub/URL**: [mem0.ai/openmemory](https://mem0.ai/openmemory) · [github.com/mcpconcierge/mem0-OpenMemory-MCP-server](https://github.com/mcpconcierge/mem0-OpenMemory-MCP-server)
- **O que faz**: Servidor MCP local-first que cria uma camada de memória compartilhada e persistente para todos os clientes MCP (Claude Desktop, Cursor, Windsurf, VS Code). Tudo armazenado localmente, sem cloud. Lançado mai/2025.
- **Diferencial vs Hive-Mind**: Drop-in para o caso de uso "memória compartilhada entre agentes" sem precisar instrumentar cada agente individualmente. Não tem Dream Cycle nem grafo neuronal.
- **Potencial de integração**: Alta
- **Como integrar**: Configurar o OpenMemory MCP como endpoint de memória para Claude Code, Codex e demais agentes. Ao invés de interceptar sessões via arquivo/inotify, os agentes escrevem diretamente no OpenMemory, e o Hive-Mind consome via API REST local.

### Letta (ex-MemGPT)
- **GitHub/URL**: [letta.com](https://www.letta.com) · [github.com/letta-ai/letta](https://github.com/letta-ai/letta)
- **O que faz**: Runtime de agentes com memória em 3 camadas: Core Memory (RAM — contexto ativo), Recall Memory (histórico buscável), Archival Memory (cold storage consultável via tool calls). O próprio LLM controla quando ler/escrever em cada camada. Lançou Context Repositories (git-based memory, fev/2026) e Letta Code — terminal agent rankeado #1 open-source em Terminal-Bench (42.5%).
- **Diferencial vs Hive-Mind**: Arquitetura self-managed onde o LLM é seu próprio controlador de memória. Git-versioning de contexto. Mais voltado a agentes autônomos de longa duração, não a indexação de sessões externas.
- **Potencial de integração**: Média
- **Como integrar**: Usar o Letta REST API para injetar memórias do Dream Cycle como Archival Memory em agentes Letta que o Hive-Mind orquestre.

### Zep
- **GitHub/URL**: [getzep.com](https://www.getzep.com) · [github.com/getzep/zep](https://github.com/getzep/zep)
- **O que faz**: Servidor de memória com grafo de conhecimento temporal (baseado no Graphiti). Armazena fatos com timestamps, extrai entidades e relacionamentos de conversas assincronamente, e resolve conflitos temporais automaticamente. Score 71.2% em LongMemEval (ICLR 2025).
- **Diferencial vs Hive-Mind**: Temporal knowledge graph de produção com sumarização automática de conversas e extração de entidades. O Hive-Mind tem grafo neurônios/sinapses, mas sem semântica temporal explícita de fatos.
- **Potencial de integração**: Alta
- **Como integrar**: O componente open-source do Zep é o Graphiti (seção 4). Integrar o Graphiti diretamente é mais flexível que depender do servidor Zep completo.

### Cognee
- **GitHub/URL**: [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee) — 18.5k stars, Apache-2.0
- **O que faz**: Plataforma de memória open-source que combina embeddings vetoriais, raciocínio em grafo e ontologia cognitiva. API Python de 4 operações: `remember()`, `recall()`, `forget()`, `improve()`. Roda localmente. Ingere qualquer formato de dado e constrói knowledge graph self-hosted.
- **Diferencial vs Hive-Mind**: Ontologia gerada automaticamente por LLM (não manual), roteamento automático de estratégia de busca em `recall()`, suporte multimodal nativo. O Hive-Mind tem FTS5 + sqlite-vec, mas sem routing semântico automático de queries.
- **Potencial de integração**: Média
- **Como integrar**: Usar cognee como camada de `recall` sobre o corpus do Hive-Mind para perguntas complexas multi-hop que o FTS5 atual não suporta bem. `pip install cognee`.

### MemoryOS (BAI-LAB)
- **GitHub/URL**: [github.com/BAI-LAB/MemoryOS](https://github.com/BAI-LAB/MemoryOS) — EMNLP 2025 Oral
- **O que faz**: Sistema operacional de memória para agentes com 4 módulos: Storage hierárquico, Updating, Retrieval e Generation. Foco em personalização de agentes de longa duração.
- **Diferencial vs Hive-Mind**: Abordagem acadêmica com benchmark rigoroso. Hierarquia de storage mais sofisticada.
- **Potencial de integração**: Baixa (projeto acadêmico, menos maduro operacionalmente)
- **Como integrar**: Referência arquitetural para o Dream Cycle — os módulos Storage/Updating/Retrieval/Generation do MemoryOS mapeiam diretamente para Distiller/Validator/Router/Síntese do Hive-Mind.

### MemOS (MemTensor)
- **GitHub/URL**: [github.com/MemTensor/MemOS](https://github.com/MemTensor/MemOS)
- **O que faz**: "Self-evolving memory OS" com persistent memory, hybrid-retrieval e cross-task skill reuse. Reporta 35.24% de economia de tokens. v2.0 (dez/2025) inclui memory feedback, multi-modal memory e tool memory para agent planning.
- **Diferencial vs Hive-Mind**: Skill reuse cross-task — memórias procedurais (como fazer algo) além de memórias factuais. O Hive-Mind foca em conhecimento factual/semântico.
- **Potencial de integração**: Média
- **Como integrar**: Integrar o módulo de tool memory do MemOS como camada de memória procedural no Dream Cycle — classificar memórias como factuais vs. procedurais e rotear para armazenamentos diferentes.

### A-MEM (AGI Research)
- **GitHub/URL**: [github.com/agiresearch/A-mem](https://github.com/agiresearch/A-mem) — 1.1k stars, NeurIPS 2025
- **O que faz**: Sistema de memória agnótico inspirado no método Zettelkasten. Cada memória gera notas estruturadas com keywords, tags e descrições contextuais. Quando uma memória é adicionada, o sistema analisa memórias históricas e estabelece links de forma autônoma. Usa ChromaDB para recuperação.
- **Diferencial vs Hive-Mind**: Evolução dinâmica de links entre memórias (o grafo de sinapses do Hive-Mind é mais estático). O A-MEM cria e evolui conexões autonomamente sem pipeline explícito de consolidação.
- **Potencial de integração**: Alta
- **Como integrar**: Substituir a etapa de "Síntese Dialética" do Dream Cycle pela lógica de link-evolution do A-MEM — ao inserir novas memórias, A-MEM cria e evolui automaticamente os links no grafo neuronal do Hive-Mind.

---

## 2. Ecossistema MCP

### Servidor Oficial de Memory (Anthropic/MCP)
- **GitHub/URL**: [github.com/modelcontextprotocol/servers/tree/main/src/memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory)
- **O que faz**: Knowledge graph persistente oficial via MCP. Armazena entidades, relações e observações em arquivo JSONL (configurável via `MEMORY_FILE_PATH`). Ferramenta de referência, não de produção.
- **Potencial de integração**: Alta
- **Como integrar**: Garantir que o schema de entidades/relações do Hive-Mind seja compatível com o servidor oficial permite que agentes Claude Desktop usem o Hive-Mind como backend sem reconfiguração.

### SQLite Memory MCP (mcp-memory-sqlite)
- **GitHub/URL**: [github.com/Daichi-Kudo/mcp-memory-sqlite](https://github.com/Daichi-Kudo/mcp-memory-sqlite) e [github.com/RMANOV/sqlite-memory-mcp](https://github.com/RMANOV/sqlite-memory-mcp)
- **O que faz**: Drop-in replacement para o servidor oficial de memória MCP, com backend SQLite WAL, FTS5, rastreamento de sessões e sincronização cross-machine. Arquitetura quase idêntica ao componente SeenStore do Hive-Mind.
- **Potencial de integração**: Alta
- **Como integrar**: Usar o schema do `sqlite-memory-mcp` como referência para tornar o MCP server do Hive-Mind um drop-in replacement compatível com qualquer cliente MCP.

### MegaMem (Obsidian + MCP + SQLite)
- **GitHub/URL**: [github.com/C-Bjorn/MegaMem](https://github.com/C-Bjorn/MegaMem)
- **O que faz**: Transforma vault Obsidian em knowledge graph com suporte MCP (spec 2025-03-26, Streamable HTTP). Estado de sincronização rastreado em SQLite (`sync.db`).
- **Diferencial vs Hive-Mind**: Integração Obsidian nativa bidirecional com MCP Streamable HTTP (o Hive-Mind usa stdio). Suporta o novo padrão MCP 2025-03-26 que permite múltiplos clientes simultâneos.
- **Potencial de integração**: Alta
- **Como integrar**: Migrar o MCP server do Hive-Mind de stdio para Streamable HTTP (MCP spec 2025-03-26) usando o MegaMem como referência. Permite múltiplos agentes conectados simultaneamente.

### Langfuse MCP
- **GitHub/URL**: [github.com/avivsinai/langfuse-mcp](https://github.com/avivsinai/langfuse-mcp)
- **O que faz**: MCP server que expõe traces do Langfuse para agentes — permite que coding agents consultem dados de produção em tempo real para debugging.
- **Potencial de integração**: Média
- **Como integrar**: Após integrar Langfuse (seção 5), usar este MCP para que o próprio Hive-Mind consulte seus traces de captura e otimize rotas de processamento autonomamente.

---

## 3. Bancos Vetoriais Local-First

### sqlite-lembed + sqlite-vec (duo nativo)
- **GitHub/URL**: [github.com/asg017/sqlite-lembed](https://github.com/asg017/sqlite-lembed) + [github.com/asg017/sqlite-vec](https://github.com/asg017/sqlite-vec)
- **O que faz**: `sqlite-lembed` gera embeddings de texto a partir de modelos GGUF locais via llama.cpp dentro do SQLite. Juntos formam um pipeline completo de geração+busca sem processo externo.
- **Diferencial vs Hive-Mind**: O Hive-Mind já usa `sqlite-vec` para busca, mas os embeddings são gerados externamente. `sqlite-lembed` fecha o loop — gerar embeddings via SQL puro: `SELECT lembed(text) FROM memories`. Nenhum servidor de embeddings necessário.
- **Potencial de integração**: Alta (melhoria direta e imediata)
- **Como integrar**:
  ```python
  # Em core/indexing.py — substituir chamada externa por:
  conn.execute("SELECT lembed_init('nomic-embed-text-v1.5.Q4_K_M.gguf')")
  conn.execute("INSERT INTO vec_memories SELECT lembed(content) FROM memories WHERE id=?", [id])
  ```
  Modelos GGUF compatíveis: `nomic-embed-text-v1.5` (384d, ~270MB), `all-MiniLM-L6-v2` (384d, ~90MB).

### LanceDB (embedded columnar + vector)
- **GitHub/URL**: [github.com/lancedb/lancedb](https://github.com/lancedb/lancedb) — Apache-2.0
- **O que faz**: Banco de dados embarcado (sem servidor) para busca vetorial multimodal sobre o formato colunar Lance. Suporte nativo a DuckDB para SQL retrieval (jan/2026), object storage nativo, 1.5M IOPS em benchmarks.
- **Diferencial vs Hive-Mind**: LanceDB suporta dados multimodais (imagens, vídeos, embeddings de screenshots) nativamente — útil para armazenar embeddings visuais do Deep Portal.
- **Potencial de integração**: Média
- **Como integrar**: Usar LanceDB como armazenamento secundário para memórias multimodais (screenshots, transcrições via Whisper) enquanto mantém `hive_mind.db` SQLite para dados textuais. `pip install lancedb`.

### DuckDB + extensão vetorial (vss)
- **GitHub/URL**: [duckdb.org](https://duckdb.org)
- **O que faz**: DuckDB suporta vetores via extensão `vss` (HNSW). Útil para análise OLAP de memórias consolidadas. Pode ler diretamente do `hive_mind.db` via extensão SQLite.
- **Potencial de integração**: Média
- **Como integrar**: Usar DuckDB como motor de análise no Dream Cycle sem migrar dados: `ATTACH 'hive_mind.db' AS hive (TYPE sqlite); SELECT ...`.

---

## 4. Knowledge Graph e RAG

### Graphiti (Zep Open Source)
- **GitHub/URL**: [github.com/getzep/graphiti](https://github.com/getzep/graphiti) — 27.7k stars, Python 99.4%
- **O que faz**: Motor de grafo de contexto temporal em tempo real. Entidades e relacionamentos têm janelas de validade (`valid_from`, `valid_until`). Quando um fato muda, o antigo é invalidado (não deletado) — histórico completo preservado. Backends: Neo4j, FalkorDB (open-source), Kuzu. MCP server: [github.com/klaviyo/graphiti_mcp](https://github.com/klaviyo/graphiti_mcp).
- **Diferencial vs Hive-Mind**: O grafo neurônios/sinapses do Hive-Mind é estático (sinapses não têm timestamping de validade). Graphiti adiciona semântica temporal — "o que era verdade ontem vs hoje".
- **Potencial de integração**: Alta (maior impacto arquitetural)
- **Como integrar**:
  ```python
  from graphiti_core import Graphiti
  from graphiti_core.nodes import EpisodeType

  # No Dream Cycle, após consolidação:
  graphiti = Graphiti("bolt://localhost:7687", user, password)  # FalkorDB local
  await graphiti.add_episode(
      name=f"session_{session_id}",
      episode_body=consolidated_text,
      source=EpisodeType.text,
      reference_time=datetime.now()
  )
  results = await graphiti.search(query, num_results=10)
  ```
  Usar **FalkorDB** como backend (open source, in-memory graph DB) para manter filosofia local-first.

### LightRAG ✅ Concluído P4 (2026-06-24)
- **GitHub/URL**: [github.com/HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) — EMNLP 2025
- **O que faz**: Framework RAG com knowledge graph leve. Indexação 100x mais barata que GraphRAG (Microsoft). Extrai entidades e relações, constrói grafo plano, e usa dual-mode retrieval (grafo + vetor). Custo: ~$0.50 por 500 páginas, ~3min de indexação. 4 estratégias de chunking (mai/2026).
- **Diferencial vs Hive-Mind**: O Dream Cycle usa LLM para destilação mas sem estrutura de grafo explícita para o resultado. LightRAG gera automaticamente entidades/relações do corpus consolidado com eficiência 100x vs GraphRAG.
- **Status**: ✅ **Integrado e operacional** (commit `56f1e98` P4 inicial, `dee365b` fix de modelo para `granite3-dense:2b`, hoje também alimentado pelo Dream Cycle Estágio 3.5).
- **Como foi integrado**:
  - `core/lightrag_index.py` — wrapper do `lightrag-hku>=1.5.4` com Ollama snowflake-arctic-embed2 (1024d embeddings) + `granite3-dense:2b` (LLM, fixo, 1.5GB).
  - `scripts/dream/dream_cycle.py:372-381` — após síntese dialética, chama `index_memory()` best-effort (try/except, nunca aborta síntese).
  - `scripts/services/sinapse-mcp.py:340` — expõe `sinapse_rag_query(question, mode)` com modos `naive|local|global|hybrid`.
  - Storage: `claude-mem/data/lightrag/` (graph.npz + 3 vdb JSON).

### Microsoft GraphRAG
- **GitHub/URL**: [github.com/microsoft/graphrag](https://github.com/microsoft/graphrag)
- **O que faz**: Extração de entidades/relações via LLM, community detection (Leiden algorithm), sumários hierárquicos. Dynamic Community Selection (jan/2025) reduziu tokens em 79%. Melhor para corpora acima de 1k documentos.
- **Potencial de integração**: Baixa (custo de indexação inviável para uso diário)
- **Como integrar**: Reservar para análises mensais/trimestrais de grandes corpora consolidados — "batch mode" do Dream Cycle para síntese de longo prazo.

### HippoRAG 2 (OSU NLP Group)
- **GitHub/URL**: [github.com/OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG) — NeurIPS 2024 + v2
- **O que faz**: Framework RAG inspirado na teoria de indexação hipocampal. Usa Personalized PageRank sobre knowledge graphs para recuperação associativa multi-hop. v2 melhora factual, sense-making e memória associativa.
- **Diferencial vs Hive-Mind**: O mecanismo de spreading activation mimetiza recall humano associativo — mais adequado para "o que se relaciona com X que vi na sessão de Y semanas atrás" do que busca vetorial direta.
- **Potencial de integração**: Média
- **Como integrar**: Usar HippoRAG 2 como retriever alternativo no MCP server para queries de raciocínio multi-hop, complementando o sqlite-vec atual para queries factuais diretas.

---

## 5. Observabilidade de Agentes

### Langfuse (self-hosted)
- **GitHub/URL**: [github.com/langfuse/langfuse](https://github.com/langfuse/langfuse) — YC W23, Apache-2.0
- **O que faz**: Plataforma open-source de observabilidade LLM com tracing via OpenTelemetry (OTLP endpoint `/api/public/otel`). Self-hostable sem limites de uso. Suporte nativo ao Claude Agent SDK. Captura: tool calls, custo por agente, latência, tokens, multi-turn sessions.
- **Diferencial vs Hive-Mind**: O Hive-Mind captura sessões via inotify/parsing de logs. Langfuse captura via instrumentação OpenTelemetry — mais preciso, com timestamps de spans individuais, custo por chamada e replay de sessões. Self-hosted preserva privacidade.
- **Potencial de integração**: Alta
- **Como integrar**:
  ```python
  # Em capture_core.py, adicionar instrumentação OTEL:
  from opentelemetry import trace
  from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

  exporter = OTLPSpanExporter(
      endpoint="http://localhost:3000/api/public/otel",
      headers={"Authorization": f"Basic {langfuse_key}"}
  )
  # Cada sessão capturada vira um span rastreável
  ```
  Deploy: `docker-compose up -d` com `langfuse/langfuse`.

### AgentOps
- **GitHub/URL**: [agentops.ai](https://www.agentops.ai) · [github.com/AgentOps-AI/agentops](https://github.com/AgentOps-AI/agentops)
- **O que faz**: Plataforma de observabilidade especializada em agentes autônomos. Suporta 400+ LLMs, session replay, time-travel debugging, rastreamento de tool calls e interações multi-agente.
- **Diferencial vs Hive-Mind**: Mais forte para debugging de agentes multi-framework — o Hive-Mind captura sessões de 10+ agentes mas tem debugging limitado. AgentOps adicionaria replay e análise post-mortem.
- **Potencial de integração**: Média (cloud-first, sem self-hosting gratuito)
- **Como integrar**: Instrumentar os parsers do Hive-Mind com o SDK AgentOps: `import agentops; agentops.init(api_key)`. Cada sessão capturada vira uma AgentOps session rastreável.

### Arize Phoenix
- **GitHub/URL**: [github.com/Arize-ai/phoenix](https://github.com/Arize-ai/phoenix) — Apache-2.0
- **O que faz**: Plataforma de observabilidade e avaliação open-source baseada em OpenTelemetry. Suporta 10 tipos de span: CHAIN, LLM, TOOL, RETRIEVER, EMBEDDING, AGENT, RERANKER, GUARDRAIL, EVALUATOR. Tem embeddings analysis e drift detection.
- **Diferencial vs Hive-Mind**: Phoenix detecta quando as sessões capturadas estão gerando memórias semanticamente desviadas (semantic drift) — problema identificado na literatura (SSGM framework, 2026).
- **Potencial de integração**: Média
- **Como integrar**: Usar Phoenix como backend de avaliação do Dream Cycle — após síntese dialética, enviar embeddings das memórias consolidadas para Phoenix detectar drift vs corpus histórico.

### W&B Weave
- **GitHub/URL**: [github.com/wandb/weave](https://github.com/wandb/weave) · [docs.wandb.ai/weave/guides/integrations/mcp](https://docs.wandb.ai/weave/guides/integrations/mcp)
- **O que faz**: Observabilidade para agentes de produção com auto-logging de traces MCP, suporte a A2A protocol (em breve). Uma linha de código para capturar traces MCP completos.
- **Potencial de integração**: Média
- **Como integrar**: No MCP server do Hive-Mind: `import weave; weave.init("hive-mind")` para auto-logging de todos os spans MCP. Útil principalmente para debug do MCP server em si.

---

## 6. Consolidação/Destilação de Memória

### A-MEM — Agentic Memory Evolution
- **GitHub/URL**: [github.com/agiresearch/A-mem](https://github.com/agiresearch/A-mem) — NeurIPS 2025, 1.1k stars
- **O que faz**: Sistema Zettelkasten para LLMs — cada nova memória analisa o corpus histórico e cria links dinâmicos com memórias relacionadas. Memórias evoluem autonomamente: novos dados atualizam tags, keywords e conexões existentes.
- **Diferencial vs Hive-Mind**: O Dream Cycle do Hive-Mind é um pipeline explícito (Distiller → Validator → Router). A-MEM não tem pipeline — as conexões emergem organicamente de cada inserção. Mais resiliente a falhas de pipeline.
- **Potencial de integração**: Alta
- **Como integrar**: Usar A-MEM para a etapa de "link evolution" pós-consolidação: após o Validator aprovar memórias, A-MEM cria/atualiza links no grafo de sinapses do Hive-Mind automaticamente.

### RAPTOR (Recursive Abstractive Processing)
- **GitHub/URL**: [github.com/parthsarthi03/raptor](https://github.com/parthsarthi03/raptor) — Stanford 2024
- **O que faz**: Constrói árvore hierárquica de sumários via clustering recursivo e sumarização LLM. Recuperação em múltiplos níveis de abstração (chunk → parágrafo → documento → corpus).
- **Diferencial vs Hive-Mind**: O Dream Cycle atual faz uma única passagem de destilação. RAPTOR faz destilação recursiva em múltiplos níveis — memórias de ontem são sumariadas em memórias semanais, que são sumariadas em mensais.
- **Potencial de integração**: Média
- **Como integrar**: Implementar RAPTOR como scheduler no Dream Cycle: destilação diária cria nível 1, destilação semanal sobre os diários cria nível 2, etc. Cada nível armazenado como tipo de neurônio diferente no grafo.

### MemCoT (Memory-Driven Chain-of-Thought)
- **GitHub/URL**: [arxiv.org/pdf/2604.08216](https://arxiv.org/pdf/2604.08216) — abr/2026
- **O que faz**: Test-time scaling via memória — usa memórias de interações anteriores para guiar raciocínio CoT em novas queries. Reduz tokens de raciocínio reutilizando padrões de solução passados.
- **Potencial de integração**: Baixa (ainda paper sem implementação madura)

---

## 7. Sincronização P2P e CRDT

### CR-SQLite (vlcn-io)
- **GitHub/URL**: [github.com/vlcn-io/cr-sqlite](https://github.com/vlcn-io/cr-sqlite) — 3.7k stars, Rust+Python, v0.16.3
- **O que faz**: Extensão loadable para SQLite que adiciona suporte CRDT via `SELECT crsql_as_crr('tabela')`. CRDTs implementados: Last-Write-Wins (LWW), Fractional Index, Observe-Remove Sets. Carrega como `.so`/`.dylib` sem modificar o schema existente. Inserts 2.5x mais lentos; leituras idênticas em velocidade.
- **Diferencial vs Hive-Mind**: O `hive_mind.db` hoje não suporta múltiplos escritores concorrentes (WAL resolve leituras concorrentes, não writes multi-master). CR-SQLite habilitaria múltiplas instâncias Hive-Mind (workstation + laptop + servidor) convergindo automaticamente sem conflitos.
- **Potencial de integração**: Alta
- **Como integrar**:
  ```python
  import sqlite3
  conn = sqlite3.connect("hive_mind.db")
  conn.enable_load_extension(True)
  conn.load_extension("crsqlite")
  # Converter tabelas principais para CRR:
  conn.execute("SELECT crsql_as_crr('neurons')")
  conn.execute("SELECT crsql_as_crr('synapses')")
  conn.execute("SELECT crsql_as_crr('memories')")
  # Sincronizar com outra instância:
  changes = conn.execute("SELECT * FROM crsql_changes()").fetchall()
  # Enviar changes via qualquer protocolo (HTTP, rsync, etc.)
  ```
  O `capture-state.db` deve ser mantido separado — CR-SQLite é para o `hive_mind.db` principal.

### Automerge
- **GitHub/URL**: [github.com/automerge/automerge](https://github.com/automerge/automerge) · [automerge.org](https://automerge.org)
- **O que faz**: Biblioteca CRDT para estruturas de dados colaborativas (JSON, texto). Adequado para sincronizar o vault Obsidian (`cerebro/`) entre máquinas com resolução automática de conflitos.
- **Potencial de integração**: Média
- **Como integrar**: Usar Automerge para sincronizar o diretório `cerebro/` entre instâncias. Cada arquivo `.md` vira um documento Automerge. `npm install @automerge/automerge`.

### Yjs
- **GitHub/URL**: [github.com/yjs/yjs](https://github.com/yjs/yjs) — 17k stars
- **O que faz**: Framework CRDT com tipos de dados compostos (YText, YMap, YArray). Foco em edição colaborativa em tempo real.
- **Potencial de integração**: Baixa (caso de uso mais nicho que CR-SQLite para o Hive-Mind)

---

## 8. Captura Visual

### Screenpipe
- **GitHub/URL**: [github.com/screenpipe/screenpipe](https://github.com/screenpipe/screenpipe) — 19.4k stars, YC S26, Rust 59.5% + TypeScript 37.3%
- **O que faz**: Captura de tela e áudio contínua e local com armazenamento SQLite+FTS5. Captura **orientada a eventos** (app switches, cliques, pausas de digitação, scroll) — não contínua. Screenshots como JPEGs (~300 MB/8h vs ~2 GB contínuo). Transcrição via Whisper local ou Deepgram. REST API em `localhost:3030` + MCP server nativo.
- **Diferencial vs Hive-Mind**: Screenpipe é o que o Hive-Mind quer ser para captura visual — mais maduro, com event-driven capture, compressão inteligente, Whisper local, e MCP pronto. O Deep Portal atual é uma implementação mais simples (mss + LLM Vision) sem as otimizações de evento.
- **Potencial de integração**: Alta
- **Como integrar**:
  - Opção A: Deprecar Deep Portal e consumir Screenpipe via REST API: `GET localhost:3030/search?q=...&content_type=ocr&limit=20`
  - Opção B: Usar o schema SQLite do Screenpipe (`frames`, `audio_chunks`, `ocr_text`) diretamente via `ATTACH DATABASE`
  - Ganho imediato: compressão 6x de screenshots, transcrição Whisper local, event-driven sem polling

### OmniParser v2 (Microsoft)
- **GitHub/URL**: [github.com/microsoft/OmniParser](https://github.com/microsoft/OmniParser)
- **O que faz**: Parser de UI screenshots para elementos estruturados. v2 alcança 39.5% no benchmark ScreenSpot Pro. Controla VM Windows 11 com suporte a OpenAI, DeepSeek R1, Qwen 2.5VL e Anthropic Computer Use. Logging local de trajetórias + orquestração multi-agente (mar/2025).
- **Diferencial vs Hive-Mind**: OmniParser estrutura screenshots em elementos UI clicáveis/textuais, enquanto o Deep Portal extrai texto via LLM Vision de forma menos estruturada. Produz output mais rico (bounding boxes, tipos de elemento).
- **Potencial de integração**: Média
- **Como integrar**: Usar OmniParser como pré-processador das screenshots capturadas antes de enviar ao LLM Vision — extrai elementos estruturados (custo menor que LLM Vision pura), e o LLM interpreta apenas os elementos relevantes. Reduz custo de tokens no pipeline visual.

---

## Matriz de Prioridade de Integrações

| Projeto | Área | Impacto | Esforço | Prioridade |
|---------|------|---------|---------|------------|
| **sqlite-lembed** | Vetorial | Alto | Baixo | **P0** |
| **Graphiti (FalkorDB)** | Knowledge Graph | Alto | Médio | **P1** |
| **CR-SQLite** | Sincronização | Alto | Médio | **P1** |
| **Screenpipe (API)** | Captura Visual | Alto | Baixo | **P1** |
| **OpenMemory MCP** | MCP Ecosystem | Alto | Baixo | **P1** |
| **Langfuse (self-hosted)** | Observabilidade | Alto | Médio | **P2** |
| ~~**LightRAG**~~ ✅ | Knowledge Graph | Alto | Médio | **Concluído P4** (2026-06-24) |
| **A-MEM (link evolution)** | Consolidação | Médio | Médio | **P2** |
| **MegaMem (Streamable HTTP)** | MCP Ecosystem | Médio | Médio | **P2** |
| **RAPTOR (multi-level)** | Consolidação | Médio | Alto | **P3** |
| **Cognee (recall router)** | Memória | Médio | Médio | **P3** |
| **HippoRAG 2** | RAG/Retrieval | Médio | Alto | **P3** |
| **LanceDB (multimodal)** | Vetorial | Médio | Alto | **P3** |
| **DuckDB (analytics)** | Análise | Médio | Baixo | **P3** |
| **Automerge (Obsidian)** | Sincronização | Baixo | Alto | **P4** |
| **OmniParser v2** | Captura Visual | Médio | Alto | **P4** |
| **AgentOps** | Observabilidade | Médio | Médio | **P4** |
| **Letta (archival)** | Memória | Baixo | Alto | **P4** |
| **MemoryOS (BAI-LAB)** | Memória | Baixo | Alto | **P5** |
| **Microsoft GraphRAG** | Knowledge Graph | Baixo | Alto | **P5** |

---

## Próximos Passos Recomendados (Top 5 por ROI)

### 1. sqlite-lembed — Embeddings 100% Local (ROI: máximo, esforço: horas)
Instalar `sqlite-lembed` + modelo GGUF local (ex: `nomic-embed-text-v1.5.Q4_K_M.gguf`) e substituir a geração de embeddings externa em `core/indexing.py` por chamadas SQL diretas. Elimina o único processo externo no pipeline de indexação, reduz latência e simplifica o deploy. Compatível com `sqlite-vec` existente.

### 2. Screenpipe via REST API — Substituir Deep Portal (ROI: alto, esforço: dias)
Deprecar o Deep Portal (`mss + LLM Vision`) e consumir `GET localhost:3030/search` do Screenpipe. Screenpipe já roda localmente, já tem SQLite+FTS5, já tem MCP server, e o schema pode ser lido via `ATTACH DATABASE`. Ganho: compressão 6x de screenshots, transcrição Whisper local, event-driven capture sem polling contínuo.

### 3. Graphiti (FalkorDB backend) — Semântica Temporal no Grafo (ROI: alto, esforço: semanas)
Integrar Graphiti como camada temporal sobre o grafo neurônios/sinapses atual. FalkorDB é open source e local-first. No Dream Cycle, após validação, cada memória consolidada vira um `Episode` no Graphiti. Adiciona ao Hive-Mind a capacidade de responder "o que era verdade sobre X em tal data" — impossível hoje com o grafo estático.

### 4. CR-SQLite — Sync Multi-Dispositivo (ROI: alto, esforço: dias para prototipagem)
Converter as tabelas `neurons`, `synapses` e `memories` do `hive_mind.db` para conflict-free replicated relations via `SELECT crsql_as_crr(...)`. Habilita múltiplas instâncias do Hive-Mind (workstation, laptop, servidor) sincronizando via qualquer protocolo de transporte (rsync, HTTP, WebSocket) sem conflitos.

### 5. Langfuse Self-Hosted — Observabilidade do Dream Cycle (ROI: médio-alto, esforço: dias)
Deploy do Langfuse via Docker e instrumentação OpenTelemetry em `capture_core.py` e no pipeline do Dream Cycle. Sem custo de cloud, sem limites de uso. Ganha: replay de sessões, custo por agente rastreado, detecção de anomalias, e MCP server do Langfuse para que o próprio Hive-Mind consulte seus próprios traces.

---

## Fontes

- [Mem0 GitHub](https://github.com/mem0ai/mem0) · [Mem0 MCP](https://github.com/mem0ai/mem0-mcp) · [OpenMemory MCP](https://mem0.ai/openmemory)
- [Letta](https://www.letta.com/) · [Mem0 vs Letta 2026](https://vectorize.io/articles/mem0-vs-letta)
- [AI Agent Memory Frameworks 2026](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/)
- [Zep vs Cognee 2026](https://explore.n1n.ai/blog/ai-agent-memory-comparison-2026-mem0-zep-letta-cognee-2026-04-23)
- [Cognee GitHub](https://github.com/topoteretes/cognee) · [MemoryOS BAI-LAB](https://github.com/BAI-LAB/MemoryOS)
- [MemOS MemTensor](https://github.com/MemTensor/MemOS) · [A-MEM GitHub](https://github.com/agiresearch/A-mem)
- [Knowledge Graph Memory MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/memory)
- [MegaMem Obsidian MCP](https://github.com/C-Bjorn/MegaMem) · [mcp-memory-sqlite](https://github.com/Daichi-Kudo/mcp-memory-sqlite)
- [sqlite-lembed GitHub](https://github.com/asg017/sqlite-lembed) · [sqlite-vec GitHub](https://github.com/asg017/sqlite-vec)
- [LanceDB GitHub](https://github.com/lancedb/lancedb)
- [Graphiti GitHub](https://github.com/getzep/graphiti) · [Graphiti MCP Server](https://github.com/klaviyo/graphiti_mcp)
- [LightRAG GitHub EMNLP 2025](https://github.com/HKUDS/LightRAG)
- [Graph RAG em produção 2026](https://www.paperclipped.de/en/blog/graph-rag-production/)
- [HippoRAG GitHub](https://github.com/OSU-NLP-Group/HippoRAG)
- [Langfuse GitHub](https://github.com/langfuse/langfuse) · [Langfuse MCP Server](https://github.com/avivsinai/langfuse-mcp)
- [AgentOps observabilidade 2026](https://latitude.so/blog/best-ai-agent-observability-tools-2026-comparison)
- [Arize Phoenix GitHub](https://github.com/Arize-ai/phoenix) · [W&B Weave MCP](https://docs.wandb.ai/weave/guides/integrations/mcp)
- [A-MEM OpenReview NeurIPS 2025](https://openreview.net/forum?id=FiM0M8gcct)
- [RAPTOR recursivo](https://github.com/parthsarthi03/raptor)
- [CR-SQLite GitHub](https://github.com/vlcn-io/cr-sqlite) · [Automerge](https://github.com/automerge/automerge) · [Yjs](https://github.com/yjs/yjs)
- [Screenpipe GitHub](https://github.com/screenpipe/screenpipe)
- [OmniParser v2 Microsoft](https://github.com/microsoft/OmniParser)
- [ScreenAgent IJCAI-24](https://github.com/niuzaisheng/ScreenAgent)
