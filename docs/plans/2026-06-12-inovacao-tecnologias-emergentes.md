# Plano Unificado — Fases 11 e 12 do Hive-Mind

> **Tipo:** Plano de Implementação — Conclusão de Dívidas P2 + Infraestrutura Emergente + Novas Fases
> **Data:** 2026-06-12
> **Origem:** Auditoria técnica 2026-06-10 (itens P2 pendentes) + Auditoria QA 2026-06-12 (tecnologias emergentes)
> **Escopo:** `core/`, `scripts/`, `tests/`, `docs/`, `install.sh` — visão completa do que falta para o projeto atingir Fase 12
> **Pré-requisito:** Itens P0/P1 da auditoria 2026-06-10 já resolvidos; 161 testes verdes; Dream Cycle operacional

---

**TL;DR:** O Hive-Mind está pronto para avançar às Fases 11-12, mas há dívida técnica P2 aberta da auditoria anterior (plugin monolítico, RRF incompleto, governança ausente) que vai travar as fases novas se não for liquidada antes. Este documento unifica tudo num único plano sequenciado: primeiro zera a dívida P2 (Sprint A), depois instala as tecnologias de infraestrutura que habilitam as fases novas (Sprint B), e então implementa as Fases 11 ("Deep Reflection") e 12 ("Federated Swarm") (Sprints C e D).

---

## 1. Mapa de Dependências

```
Sprint A — Dívida P2 (1-2 semanas)
    ├── A1: Quebrar sinapse-memory.py em pacote
    ├── A2: Testes do núcleo novo (document_ingest, audit_memory, core/database)
    ├── A3: RRF real + FS-backend → FTS5
    └── A4: Governança de fases (namespace HM-/THOTH-)
         ↓
Sprint B — Infraestrutura Emergente (2-3 semanas)
    ├── B1: Pydantic model_validator nos schemas do Dream Cycle   ← habilita A2 + Fase 11
    ├── B2: Syncthing REST API (syncthing_watcher.py)            ← habilita Fase 12
    ├── B3: DuckDB camada analítica                              ← habilita Fase 11
    ├── B4: HNSW incremental (hnswlib)                          ← habilita Fase 11 (grafo de causalidade)
    └── B5: sqlite-lembed ONNX                                   ← avaliar em 90 dias
         ↓
Sprint C — Fase 11: Raciocínio de Longo Prazo (1 mês)
    ├── C1: Agente Planner (decomposição de objetivos via Atlas)
    ├── C2: Memória de Intenção (coluna "why" no UMC)
    └── C3: Grafo de Causalidade no UMC
         ↓
Sprint D — Fase 12: Federated Swarm (1-2 meses)
    ├── D1: Protocolo de compartilhamento seletivo de neurônios
    ├── D2: Assinaturas de integridade via chaves públicas (Web of Trust)
    └── D3: Camada de privacidade (redação automática de dados sensíveis)
```

---

## 2. Sprint A — Liquidação da Dívida P2

### A1 — Quebrar `sinapse-memory.py` em pacote instalável

**Origem:** P2-14 da auditoria 2026-06-10. Arquivo com 1536 linhas acumula 5 backends, circuit breaker, fusão de contexto, hooks, escrita no vault e health check — viola o padrão "Files under 500 lines" do próprio `CLAUDE.md`. É carregado por 3 entry points distintos via `importlib` manual, tornando refatorações de Fase 11 e 12 arriscadas.

**Estrutura proposta:**

```
core/
  memory/
    __init__.py          ← re-exporta o que os entry points precisam
    backends/
      __init__.py
      filesystem.py      ← _backend_filesystem, _FS_CACHE
      fts5.py            ← _backend_fts5
      vector.py          ← _backend_vec, get_embedder
      rtk.py             ← _backend_rtk
      http.py            ← _backend_http
    circuit_breaker.py   ← CircuitBreaker, BACKENDS_STATE
    context_fusion.py    ← query_hybrid, fuse_contexts
    writers.py           ← _save_decision, _save_learning, _umc_save_observation
    hooks.py             ← session_start/end, _update_current_state
    health.py            ← health_check
    config.py            ← SINAPSE_HOME, DEFAULT_*, constantes
```

**Regra de migração:** cada entry point (`sinapse-mcp.py`, `sinapse-memory.py` legado como shim, `sinapse-write.py`) importa de `core.memory` — não muda a interface pública. O shim `sinapse-memory.py` vira um arquivo de 20 linhas re-exportando `from core.memory import *` para compatibilidade com plugins externos.

| Item | Valor |
|---|---|
| Esforço | 2–3 dias |
| Risco | Médio — mover código sem alterar comportamento; mitigado por testes pré-existentes |
| Pré-requisito para | Fase 11 (Planner precisa importar backends sem carregar o monolito inteiro) |

**Critério de Aceite:**
- `sinapse-memory.py` com ≤ 50 linhas (shim puro)
- Todos os testes existentes passam sem modificação
- `import core.memory` funciona em ambiente limpo (`pip install -e .`)

---

### A2 — Cobertura de testes do núcleo novo

**Origem:** P2-15 da auditoria (parcialmente resolvido — `test_synthesis.py` com 5 testes offline foi criado na sessão QA). Faltam:

| Módulo | Cobertura atual | Meta |
|---|---|---|
| `scripts/dream_cycle.py` | 5 testes offline (synthesis) | + testes do Distiller, Validator, Router |
| `scripts/document_ingest.py` | Apenas regressão AST (P0-2) | + teste de ingestão de PDF e DOCX reais com fixtures mínimas |
| `scripts/audit_memory.py` | Zero | Teste de detecção de `.sync-conflict-*` em tmpdir |
| `core/database.py` | Zero | Teste de migração idempotente (`ensure_migrations`) |

**Fixtures a criar em `tests/fixtures/`:**
- `minimal.pdf` — PDF de 1 página gerado por `fpdf2` no próprio conftest (sem arquivo binário commitado)
- `minimal.docx` — DOCX de 1 parágrafo via `python-docx`
- `sync_conflict.md` — arquivo nomeado `.sync-conflict-20260612-120000.md` para `audit_memory`

**Nota:** cobrir `B1` (Pydantic validators) com `test_distiller_rejects_empty_facts()` e `test_router_quarantine_needs_reason()` como parte deste sprint.

| Item | Valor |
|---|---|
| Esforço | 1–2 dias |
| Risco | Baixo — testes novos, zero quebra |
| Meta de cobertura | ≥ 80% nas linhas críticas dos 4 módulos acima |

---

### A3 — RRF real + delegação do FS-backend para FTS5

**Origem:** P2-17 da auditoria (parcialmente resolvido — hidratação em `SELECT IN` já feita). Faltam duas partes:

**Parte 1 — RRF (Reciprocal Rank Fusion) de verdade:**

Hoje `query_hybrid` concatena resultados de FTS5 e vec0 e tira os primeiros N. O comentário no código promete RRF, mas não implementa. Resultado: se FTS5 dá 10 hits e vec0 dá 10 hits diferentes, os 10 de FTS5 sempre vencem.

```python
# core/memory/context_fusion.py — RRF real
def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],  # cada lista é uma sequência de neuron IDs rankeados
    k: int = 60,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, neuron_id in enumerate(ranked, start=1):
            scores[neuron_id] = scores.get(neuron_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

O `k=60` é o padrão da literatura (Cormack et al. 2009). Resultado: neurônios que aparecem no topo de AMBOS os rankings ganham bônus multiplicativo — exatamente o comportamento esperado de busca híbrida.

**Parte 2 — FS-backend → FTS5:**

O `_backend_filesystem` lê todos os `.md` do vault a cada query fora do TTL de 30s. Com vault crescendo acima de 2.000 arquivos, isso vira o gargalo de latência (leitura de disco × número de arquivos). O FTS5 do UMC já indexa o conteúdo dos neurônios — basta redirecionar:

```python
# Antes: _backend_filesystem lê disco a cada query
results = _backend_filesystem(query, limit)

# Depois: delegar ao FTS5 que já existe no UMC
results = _backend_fts5(query, limit)
# _backend_filesystem vira fallback somente quando hive_mind.db não existe
```

| Item | Valor |
|---|---|
| Esforço | 4–6h |
| Ganho esperado | Latência de busca híbrida cai de 800ms → ~150ms em vault com 2k+ arquivos |
| Risco | Baixo — FTS5 já testado; mudança é trocar o backend chamado |

---

### A4 — Governança de fases (namespace HM-/THOTH-)

**Origem:** P2-18 da auditoria. Dois sistemas de numeração coexistem: fases 1-12 do Hive-Mind e "PHASE-33/34" do Thoth. Causa ambiguidade nos arquivos do vault e nos próprios agentes.

**Convenção a adotar:**

| Projeto | Prefixo | Exemplo |
|---|---|---|
| Hive-Mind | `HM-` | `HM-11`, `HM-12` |
| Thoth | `TH-` | `TH-33`, `TH-34` |
| Ruflo | `RF-` | `RF-01` |

**Regra de conclusão de fase** (a ser documentada em `docs/01-architecture.md`):

> Nenhum agente ou humano marca uma fase como `✅ Concluída` sem: (a) commit com todos os arquivos da entrega, (b) pelo menos um teste cobrindo o caminho principal, (c) CI verde no momento do merge.

**Arquivos a atualizar:** `docs/01-architecture.md` (adicionar seção "Governança de Fases"), `cerebro/work/active/` (renomear arquivos de fase com namespace correto).

| Item | Valor |
|---|---|
| Esforço | 2–4h |
| Risco | Baixo — só convenção e documentação |

---

## 3. Sprint B — Infraestrutura Emergente

### B1 — Pydantic `model_validator` nos schemas do Dream Cycle

**Por que habilita Fase 11:** a Memória de Intenção (C2) vai adicionar campos novos (`why`, `goal_id`, `causal_chain`) a `DistillerOutput` e `RouterOutput`. Sem validators, um campo obrigatório ausente na resposta da LLM causa quarentena silenciosa sem diagnóstico.

**Arquivo:** `core/schemas/dream_models.py`

```python
from pydantic import BaseModel, model_validator, field_validator
from typing import List, Literal, Optional

class ExtractedFact(BaseModel):
    content: str
    confidence: float
    category: str

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence deve ser 0.0–1.0, recebido: {v}")
        return v

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content não pode ser vazio")
        return v.strip()

class DistillerOutput(BaseModel):
    facts: List[ExtractedFact]
    summary: str

    @model_validator(mode="after")
    def facts_not_empty(self) -> "DistillerOutput":
        if not self.facts:
            raise ValueError("DistillerOutput.facts não pode ser lista vazia")
        return self

class ValidatorOutput(BaseModel):
    validated_facts: list
    overall_quality: float

    @model_validator(mode="after")
    def quality_matches_facts(self) -> "ValidatorOutput":
        if not self.validated_facts and self.overall_quality > 0:
            raise ValueError("overall_quality > 0 com zero fatos validados é inconsistente")
        return self

class RouterOutput(BaseModel):
    routed_facts: list
    destination: Literal["atlas", "quarantine", "pending"]

    @model_validator(mode="after")
    def quarantine_needs_reason(self) -> "RouterOutput":
        if self.destination == "quarantine" and not any(
            getattr(f, "reason", None) for f in self.routed_facts
        ):
            raise ValueError("destination='quarantine' exige pelo menos um fato com 'reason'")
        return self
```

**Impacto em `dream_cycle.py`:** trocar `except Exception → quarentena` genérico por captura explícita de `pydantic.ValidationError` com `e.errors()` no log.

| Esforço | Risco | Dependência nova |
|---|---|---|
| 2–4h | Baixo | Nenhuma (Pydantic 2.13.4 já instalado) |

---

### B2 — Syncthing REST API (`syncthing_watcher.py`)

**Por que habilita Fase 12:** o Federated Swarm precisa que conflitos P2P sejam detectados e resolvidos em segundos, não horas. O watcher fecha esse gap.

**Arquivo novo:** `scripts/syncthing_watcher.py`

```python
#!/usr/bin/env python3
import os, time, subprocess, requests
from pathlib import Path

SYNCTHING_URL = os.environ.get("SYNCTHING_URL", "http://127.0.0.1:8384")
SYNCTHING_API_KEY = os.environ.get("SYNCTHING_API_KEY", "")
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(Path(__file__).parent.parent))

def _headers():
    return {"X-API-Key": SYNCTHING_API_KEY} if SYNCTHING_API_KEY else {}

def poll_conflicts(interval: float = 30.0):
    last_event_id = 0
    while True:
        try:
            r = requests.get(
                f"{SYNCTHING_URL}/rest/events",
                params={"since": last_event_id, "limit": 100, "timeout": 25},
                headers=_headers(),
                timeout=30,
            )
            if r.status_code == 200:
                for event in r.json():
                    last_event_id = max(last_event_id, event.get("id", 0))
                    if event.get("type") == "ItemFinished":
                        item = event.get("data", {}).get("item", "")
                        if ".sync-conflict-" in item and item.endswith(".md"):
                            subprocess.run(
                                ["python3", f"{SINAPSE_HOME}/scripts/audit_memory.py", "--fix"],
                                check=False,
                            )
        except requests.exceptions.ConnectionError:
            pass
        except Exception as e:
            print(f"[syncthing_watcher] Erro: {e}")
        time.sleep(interval)

if __name__ == "__main__":
    if not SYNCTHING_API_KEY:
        raise SystemExit("SYNCTHING_API_KEY não configurada — defina em .env")
    poll_conflicts()
```

**Adicionar ao `.env.example`:**
```bash
SYNCTHING_URL=http://127.0.0.1:8384
SYNCTHING_API_KEY=     # GUI → Actions → Settings → API Key
```

| Esforço | Risco | Degradação sem Syncthing |
|---|---|---|
| 4–6h | Baixo | Cron a cada 6h (comportamento atual) |

---

### B3 — DuckDB camada analítica (`hive_analytics.py`)

**Por que habilita Fase 11:** o Agente Planner precisa responder perguntas como "quais objetivos ficaram pendentes nos últimos 30 dias?" — queries que fariam full scan no SQLite WAL enquanto o Dream Cycle está escrevendo.

**Arquivo novo:** `scripts/hive_analytics.py`

```python
#!/usr/bin/env python3
import duckdb
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "hive_mind.db"

QUERIES = {
    "growth": """
        SELECT strftime('%Y-%m-%d', created_at) as dia, COUNT(*) as obs
        FROM hive.observations GROUP BY 1 ORDER BY 1 DESC LIMIT 30
    """,
    "top_topics": """
        SELECT type, COUNT(*) as c FROM hive.neurons
        GROUP BY type ORDER BY c DESC LIMIT 10
    """,
    "quarantine_rate": """
        SELECT
            ROUND(100.0 * SUM(archived = 2) / COUNT(*), 1) as pct_quarentena,
            SUM(archived = 0) as pendentes,
            SUM(archived = 1) as processadas,
            SUM(archived = 2) as quarentena
        FROM hive.observations
    """,
    "intent_by_goal": """
        SELECT goal_id, COUNT(*) as obs, AVG(confidence) as avg_conf
        FROM hive.observations
        WHERE goal_id IS NOT NULL
        GROUP BY goal_id ORDER BY obs DESC
    """,
}

def run(query_name: str):
    conn = duckdb.connect(":memory:")
    conn.execute(f"ATTACH '{DB_PATH}' AS hive (TYPE sqlite, READ_ONLY)")
    result = conn.execute(QUERIES[query_name]).fetchdf()
    print(result.to_string(index=False))
    conn.close()

if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else "quarantine_rate")
```

**Limitação:** DuckDB não lê tabelas virtuais (`search_vec vec0`, `search_fts fts5`) — só tabelas reais.

| Esforço | Risco | Dependência nova |
|---|---|---|
| 4–8h | Baixo | `pip install duckdb` (~15MB) |

---

### B4 — HNSW incremental (`core/hnsw_index.py`)

**Por que habilita Fase 11:** o Grafo de Causalidade (C3) vai adicionar milhares de arestas entre neurônios — a busca ANN precisa ser instantânea para o Planner raciocinar em tempo real, não esperar 8min de rebuild do vec0.

**Arquivo:** `core/hnsw_index.py` (novo)

```python
import hnswlib
import numpy as np
from pathlib import Path

INDEX_PATH = Path(__file__).parent.parent / "graphify-out" / "hnsw.index"
DIM = 384

def load_or_create(max_elements: int = 50_000) -> hnswlib.Index:
    idx = hnswlib.Index(space="cosine", dim=DIM)
    if INDEX_PATH.exists():
        idx.load_index(str(INDEX_PATH), max_elements=max_elements)
    else:
        idx.init_index(max_elements=max_elements, ef_construction=200, M=16)
    idx.set_ef(50)
    return idx

def upsert_neuron(idx: hnswlib.Index, neuron_rowid: int, embedding: list[float]) -> None:
    vec = np.array([embedding], dtype=np.float32)
    try:
        idx.mark_deleted(neuron_rowid)
    except Exception:
        pass
    idx.add_items(vec, [neuron_rowid])

def search(idx: hnswlib.Index, query_vec: list[float], k: int = 10):
    labels, distances = idx.knn_query(np.array([query_vec], dtype=np.float32), k=k)
    return list(zip(labels[0].tolist(), distances[0].tolist()))

def save(idx: hnswlib.Index) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    idx.save_index(str(INDEX_PATH))
```

**Schema:** adicionar coluna `indexed_at TIMESTAMP` em `neurons` para rebuild incremental (`WHERE updated_at > indexed_at OR indexed_at IS NULL`).

| Esforço | Risco | Dependência nova |
|---|---|---|
| 1–2 dias | Médio | `pip install hnswlib numpy` |

---

### B5 — sqlite-lembed ONNX (avaliação diferida)

Substitui `fastembed` externo por embeddings ONNX executados dentro do SQLite. Ganho esperado: ~40% de redução de latência de embedding. Mantido como planejado para 90 dias — extensão ainda em `v0.x` (requer Rust para build). **Não bloqueia Fases 11-12.** Revisar quando atingir `v1.0`.

---

## 4. Sprint C — Fase 11: Raciocínio de Longo Prazo (Deep Reflection)

> **Objetivo:** Transformar o Hive-Mind de um sistema de "o que foi feito" para "o que foi feito e por quê" — permitindo raciocínio causal e planejamento de longo prazo.

### C1 — Agente Planner

O Planner usa o Atlas (vault) para decompor objetivos complexos em tarefas atômicas, delegando cada uma ao pipeline existente (Dream Cycle + Síntese).

**Interface mínima:**

```python
# scripts/planner.py
def decompose_goal(goal: str, context_limit: int = 20) -> list[dict]:
    """
    1. Busca neurônios relevantes via query_hybrid(goal)
    2. Envia para LLM com role=dreamer: "Decomponha este objetivo em tarefas atômicas"
    3. Persiste cada tarefa como observation com goal_id=uuid e archived=0
    4. Retorna lista de {"task": str, "goal_id": str, "obs_id": str}
    """
```

**Novo campo no schema:** `goal_id TEXT` em `observations` (nullable — migração idempotente via `ensure_migrations`). Permite rastrear progresso por objetivo com a query DuckDB `intent_by_goal` do B3.

**Integração com MCP:** novo tool `sinapse_plan_goal(goal: str)` em `sinapse-mcp.py`.

| Esforço | Risco | Pré-requisitos |
|---|---|---|
| 3–5 dias | Baixo (usa stack existente) | A1 (pacote), B1 (validators), B3 (DuckDB) |

---

### C2 — Memória de Intenção

Hoje o UMC salva *o que* foi feito. A Memória de Intenção adiciona *por que* — o contexto de decisão que o agente tinha quando gerou uma observação.

**Schema:** adicionar coluna `why TEXT` em `observations` (nullable) e `intent_source TEXT` (ex: `"user"`, `"planner"`, `"dream_cycle"`).

**Pipeline:** quando `add_observation()` for chamado com `goal_id` presente, o Dream Cycle inclui o campo `why` no prompt do Distiller: *"Para cada fato extraído, inclua o campo `why` explicando qual intenção do usuário este fato serve."*

**Exemplo de output:**

```json
{
  "content": "DuckDB é 3x mais rápido que SQLite em queries analíticas",
  "category": "discovery",
  "confidence": 0.92,
  "why": "Pesquisando alternativas para evitar travamento do WAL durante análise de memória",
  "goal_id": "hm-goal-20260612-analytics"
}
```

| Esforço | Risco |
|---|---|
| 1–2 dias | Baixo — campos nullable, nenhum código existente quebra |

---

### C3 — Grafo de Causalidade no UMC

Hoje `neurons` e `synapses` representam relações semânticas (similaridade, co-ocorrência). O Grafo de Causalidade adiciona arestas direcionadas do tipo `caused_by`, `enables`, `contradicts` com peso e timestamp.

**Schema novo:**

```sql
CREATE TABLE IF NOT EXISTS causal_edges (
    id TEXT PRIMARY KEY,
    source_neuron_id TEXT NOT NULL REFERENCES neurons(id),
    target_neuron_id TEXT NOT NULL REFERENCES neurons(id),
    relation TEXT NOT NULL CHECK(relation IN ('caused_by','enables','contradicts','refines')),
    confidence REAL DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'dream_cycle'
);
CREATE INDEX IF NOT EXISTS idx_causal_source ON causal_edges(source_neuron_id);
CREATE INDEX IF NOT EXISTS idx_causal_target ON causal_edges(target_neuron_id);
```

**Integração com HNSW (B4):** ao buscar contexto para o Planner, incluir neurônios alcançáveis por causalidade (max 2 hops) além dos K vizinhos semânticos — isso dá ao Planner contexto sobre *consequências* de decisões passadas, não só sobre tópicos similares.

**Exportação para graphify:** o `build-graph.sh` já exporta `synapses` como arestas do `graph.json`; adicionar `causal_edges` com cor/estilo diferente no Obsidian Canvas.

| Esforço | Risco | Pré-requisitos |
|---|---|---|
| 2–3 dias | Médio (novo tipo de dado, query de grafo) | B4 (HNSW), A1 (pacote memory) |

---

## 5. Sprint D — Fase 12: Federated Swarm (Marketplace de Memórias)

> **Objetivo:** Permitir compartilhamento seletivo e seguro de neurônios entre diferentes usuários e enxames, mantendo privacidade e integridade.

### D1 — Protocolo de Compartilhamento Seletivo

Cada neurônio recebe um atributo `visibility` (`private` | `shared` | `public`). Neurônios `shared` podem ser exportados para outros nós do enxame via endpoint autenticado.

**Schema:** coluna `visibility TEXT DEFAULT 'private'` em `neurons`.

**Endpoint:** `POST /api/v1/neurons/export` — retorna lista de neurônios `shared`/`public` em formato canônico (JSON-LD + hash de integridade). Autenticado com `HIVE_MIND_API_KEY`.

**Filtros de exportação:** por `type`, `category`, `created_after`, `min_confidence` — para evitar exportar neurônios de baixa qualidade.

| Esforço | Risco | Pré-requisito |
|---|---|---|
| 3–5 dias | Médio | A1, B2 (Syncthing watcher para detecção de conflitos pós-importação) |

---

### D2 — Assinaturas de Integridade (Web of Trust)

Cada neurônio exportado é assinado com a chave privada do emissor (Ed25519). O importador verifica a assinatura antes de persistir no UMC — impede que um nó malicioso injete memórias falsas.

**Bibliotecas:** `cryptography` (já no `requirements.txt` — usada pelo vault de segredos).

**Fluxo:**

```
Exportador:
  1. Serializa neurônio como JSON canônico (chaves ordenadas, sem timestamps)
  2. Assina com Ed25519 privkey: signature = key.sign(json_bytes)
  3. Adiciona {signature: base64, pubkey_fingerprint: sha256(pubkey)} ao payload

Importador:
  1. Resolve pubkey via fingerprint (Web of Trust local ou DNS TXT)
  2. Verifica assinatura — rejeita se inválida
  3. Persiste com created_by = pubkey_fingerprint
```

**Armazenamento de chaves:** `config/keys/` (no `.gitignore`). Chave pública pode ser publicada em `/.well-known/hive-mind-pubkey.txt` no servidor do usuário.

| Esforço | Risco |
|---|---|
| 3–4 dias | Alto — criptografia é área sensível; testar com vetores conhecidos |

---

### D3 — Camada de Privacidade (Redação Automática)

Antes de exportar neurônios `shared`, aplicar redação automática de dados sensíveis: nomes próprios, emails, tokens, IPs, paths absolutos do sistema.

**Integração com o vault de segredos existente:** o `sinapse-api.py` já tem regexes de segredos (`sk-proj-`, `GOCSPX-`, etc.). Reusar e expandir como `redact_for_export(text: str) -> str`.

**Estratégia:** redação irreversível (substitui por `[REDACTED:email]`, `[REDACTED:token]`, etc.) — o neurônio exportado nunca contém o dado original. O neurônio local permanece intacto.

| Esforço | Risco |
|---|---|
| 1–2 dias | Baixo — regex + substituição, sem criptografia |

---

## 6. Cronograma e Priorização

### Sequência completa

| Sprint | Item | Esforço | Risco | Bloqueia |
|---|---|---|---|---|
| A | A1 Quebrar sinapse-memory.py | 2–3d | Médio | Fase 11 |
| A | A2 Testes núcleo novo | 1–2d | Baixo | CI verde |
| A | A3 RRF real + FTS5 | 4–6h | Baixo | Fase 11 |
| A | A4 Governança HM-/THOTH- | 2–4h | Baixo | — |
| B | B1 Pydantic validators | 2–4h | Baixo | A2, C |
| B | B2 Syncthing watcher | 4–6h | Baixo | D1 |
| B | B3 DuckDB analítico | 4–8h | Baixo | C1 |
| B | B4 HNSW incremental | 1–2d | Médio | C3 |
| B | B5 sqlite-lembed | — | Alto | Avaliar 90d |
| C | C1 Agente Planner | 3–5d | Baixo | D |
| C | C2 Memória de Intenção | 1–2d | Baixo | D |
| C | C3 Grafo de Causalidade | 2–3d | Médio | D |
| D | D1 Compartilhamento seletivo | 3–5d | Médio | — |
| D | D2 Assinaturas Ed25519 | 3–4d | Alto | — |
| D | D3 Redação automática | 1–2d | Baixo | D1 |

### Marcos

| Marco | Critério | Estimativa |
|---|---|---|
| **HM-11 Pronto** | C1+C2+C3 implementados, CI verde, `goal_id` em produção | Semana 5–6 |
| **HM-12 Alpha** | D1+D3 funcionando entre 2 instâncias locais | Semana 8–10 |
| **HM-12 Estável** | D2 (assinaturas) + testes de segurança | Semana 11–12 |

---

## 7. Critérios Globais de Aceite

1. **CI sempre verde** — nenhum sprint começa com testes quebrando
2. **Commit atômico por item** — A1, A2, ... D3 em commits separados com tag `HM-11` ou `HM-12`
3. **Fallback explícito** — B2/B3/B4 degradam graciosamente se dependência ausente (log claro, sem `except: pass`)
4. **Governança** (A4) — nenhuma fase marcada `✅` sem commit + teste + CI verde
5. **Zero segredos** — D2 usa apenas `config/keys/` (gitignored); nenhuma chave privada em código ou `.env` commitado
6. **Benchmark** — B3/B4 documentam ganho mensurável (latência antes/depois)

---

## 8. Status de Implementação

| Item | Status | Commit | Observação |
|---|---|---|---|
| **Sprint A** | | | |
| A1 Quebrar sinapse-memory.py | ⏳ Pendente | — | Maior item do sprint; fazer primeiro |
| A2 Testes núcleo novo | 🟡 Parcial | `80e12b4` | synthesis offline ✅; document_ingest/audit_memory/database ⏳ |
| A3 RRF real + FTS5 | ⏳ Pendente | — | `SELECT IN` já feito; RRF e FS→FTS5 pendentes |
| A4 Governança HM-/THOTH- | ⏳ Pendente | — | Convenção a documentar em `docs/01-architecture.md` |
| **Sprint B** | | | |
| B1 Pydantic model_validator | ⏳ Pendente | — | Pydantic 2.13.4 instalado — zero dependência nova |
| B2 Syncthing watcher | ⏳ Pendente | — | `audit_memory.py` já tem base |
| B3 DuckDB analítico | ⏳ Pendente | — | `hive_analytics.py` pode ser criado independentemente |
| B4 HNSW incremental | ⏳ Pendente | — | Coluna `indexed_at` + `core/hnsw_index.py` |
| B5 sqlite-lembed ONNX | ⏳ Diferido | — | Avaliar quando extensão atingir v1.0 |
| **Sprint C — Fase HM-11** | | | |
| C1 Agente Planner | ⏳ Pendente | — | `scripts/planner.py` + tool MCP |
| C2 Memória de Intenção | ⏳ Pendente | — | Coluna `why` + `goal_id` em `observations` |
| C3 Grafo de Causalidade | ⏳ Pendente | — | Tabela `causal_edges` + integração HNSW |
| **Sprint D — Fase HM-12** | | | |
| D1 Compartilhamento seletivo | ⏳ Pendente | — | Coluna `visibility` + endpoint `/neurons/export` |
| D2 Assinaturas Ed25519 | ⏳ Pendente | — | Web of Trust + `config/keys/` |
| D3 Redação automática | ⏳ Pendente | — | Reusar regexes do vault de segredos |
