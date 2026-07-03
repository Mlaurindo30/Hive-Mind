# 07 — P2P Synchronization (Multi-Machine Swarm)

> **Hive-Mind v2.0.0** — Syncthing as transport, UUID v4 to prevent collisions, SHA-256 for integrity, and Dialectical Synthesis for autonomous conflict resolution.

---

## 1. Swarm Architecture

```
  Máquina A (PC)           Máquina B (Laptop)         VPS
  cerebro/                 cerebro/                   cerebro/
     │                         │                         │
     └──────── Syncthing ───────┴──────── Syncthing ─────┘
                (TLS, P2P, sem servidor central)

  Cada máquina tem:
    • hive_mind.db próprio (SQLite local)
    • Watcher rodando em background
    • audit_memory.py via cron (1x/hora)
```

Syncthing is the "muscle" that transports `.md` files between machines. `hive_mind.db` is **not** synchronized — each machine keeps its own local index, rebuilt from the received Markdown files.

---

## 2. Syncthing Configuration

### 2.1 Installation

```bash
# Ubuntu/Debian
sudo apt install syncthing

# macOS
brew install syncthing

# Windows — baixar em https://syncthing.net/downloads/
```

### 2.2 Folder Configuration

1. Open the Syncthing UI: `http://localhost:8384`
2. Click **"Add Folder"**
3. Configure:
   - **Folder Path:** absolute path to `cerebro/` (e.g., `/home/user/Hive-Mind/cerebro`)
   - **Folder Type:** "Send & Receive"
   - **File Versioning:** "Simple File Versioning" — at least 5 versions
4. Share with other machines using the Syncthing **Device ID**

### 2.3 Recommended Paths

| Machine | Path | Notes |
|---------|------|-----------|
| Linux | `/home/$USER/Documentos/Projects/Hive-Mind/cerebro` | Default |
| macOS | `/Users/$USER/Projects/Hive-Mind/cerebro` | |
| VPS | `/home/$USER/hive-mind/cerebro` | |

---

## 3. Collision Prevention (UUID v4)

All primary keys in UMC use locally generated UUID v4:

```python
import uuid
neuron_id = str(uuid.uuid4())  # ex: "550e8400-e29b-41d4-a716-446655440000"
```

**Why UUID v4?** Sequential IDs collide across different machines (machine A and B both create `id=1`). UUID v4 has a collision probability of 1 in 10^36 — irrelevant in practice.

---

## 4. Integrity by Hash (SHA-256)

Each indexed file receives a hash at indexing time:

```python
import hashlib
content_hash = hashlib.sha256(file_content.encode()).hexdigest()
# ex: "a3b4c5d6..."

# Armazenado em:
# neurons.hash TEXT  -- na tabela do UMC
# frontmatter YAML:  integrity_hash: "a3b4c5d6..."
```

`audit_memory.py` compares the hash of the physical file with `neurons.hash`. A mismatch indicates the file was modified on another machine and the local index is outdated.

---

## 5. Integrity Audit (`audit_memory.py`)

### 5.1 What the auditor checks

```
  Para cada arquivo .md em cerebro/atlas/:
    1. sha256(arquivo.md) atual
    2. SELECT hash FROM neurons WHERE source_file = arquivo
    3. Comparação:
       - hash igual: OK, skip
       - hash diferente: divergência detectada
       - arquivo não indexado: INSERT neuron novo
```

### 5.2 Execution

```bash
# Verificar estado (read-only, sem modificações)
python3 scripts/health/audit_memory.py

# Corrigir — reindexar arquivos com hash divergente
python3 scripts/health/audit_memory.py --fix

# Verbose (mostra todos os arquivos verificados)
python3 scripts/health/audit_memory.py --fix --verbose
```

### 5.3 Expected output

```
[audit] Verificando 142 arquivos em cerebro/atlas/...
[audit] OK:        138 (sem divergência)
[audit] Reindexado:  3 (hash divergente — arquivo modificado em outra máquina)
[audit] Novo:         1 (arquivo não estava no índice)
[audit] Conflito:     0 (sem ambiguidades detectadas)
[audit] Concluído em 4.2s
```

---

## 6. Conflict Resolution — Dialectical Synthesis (Phase 9)

When the auditor detects that two texts with the same `source_file` have **irreconcilable** semantic content (not just a different hash, but a factual conflict), the system records an **ambiguity** and schedules autonomous resolution via LLM.

### 6.1 `ambiguities` Table

```sql
CREATE TABLE ambiguities (
    id            TEXT PRIMARY KEY,
    neuron_id_a   TEXT NOT NULL,  -- versão local
    neuron_id_b   TEXT NOT NULL,  -- versão recebida via P2P
    source_file   TEXT NOT NULL,
    status        TEXT DEFAULT 'pending',  -- pending | resolved | escalated
    resolution    TEXT,           -- "merge" | "choose_a" | "choose_b" | "branch"
    resolved_at   DATETIME,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 6.2 `semantic_diff.py` — Conflict Classification

`semantic_diff.py` uses a hybrid approach to classify the conflict type:

```
  Versão A (local) + Versão B (recebida via P2P)
         │
         ▼
  Etapa 1: Similaridade Vetorial
    cosine(embed(A), embed(B))
    ├── > 0.92: conteúdo quase idêntico → reindex simples, sem conflito
    ├── 0.70-0.92: complementares → merge candidato
    └── < 0.70: divergentes → LLM para análise semântica

  Etapa 2: LLM Semantic Analysis (se similaridade < 0.92)
    Prompt: "Versão A diz X. Versão B diz Y. São conflitantes?"
    Output: ConflictClassification {
      type: "complementary" | "contradictory" | "different_context"
      resolution: "merge" | "choose_a" | "choose_b" | "branch"
      confidence: float
      rationale: str
    }
```

### 6.3 Dialectical Synthesis — Autonomous Resolution

For `contradictory` conflicts, the LLM applies dialectical synthesis:

```
  Conflito:
    Versão A: "O servidor usa PostgreSQL"
    Versão B: "O servidor usa SQLite"
  
  Síntese Dialética:
    Prompt → LLM:
      "Tese: {A}
       Antítese: {B}
       Sintetize: qual afirmação é mais provável correta dado o contexto
       {contexto do Atlas}?
       Responda com JSON: {winner, rationale, merged_content}"
    
    Possíveis resultados:
      ┌──────────────┬────────────────────────────────────────┐
      │ merge        │ Cria nova nota combinando ambas        │
      │              │ "O servidor usava PostgreSQL mas       │
      │              │  migrou para SQLite (ver nota X)"      │
      ├──────────────┼────────────────────────────────────────┤
      │ choose_a     │ Mantém versão A, arquiva B             │
      │              │ (A tem timestamp mais recente ou       │
      │              │  maior trust_level)                    │
      ├──────────────┼────────────────────────────────────────┤
      │ choose_b     │ Mantém versão B, arquiva A             │
      ├──────────────┼────────────────────────────────────────┤
      │ branch       │ Cria ambas as notas com sufixo         │
      │              │ "-version-a" e "-version-b"            │
      │              │ (conflito genuíno sem resolução clara) │
      └──────────────┴────────────────────────────────────────┘
```

### 6.4 Complete Resolution Flow

```
  Syncthing sincroniza arquivo modificado
         │
         ▼ (~2s)
  Watcher detecta → reindexação
         │
         ▼
  hash(novo) ≠ hash(antigo)?
         │
       Sim ─▶ audit_memory.py (próxima execução do cron)
                    │
                    ▼
               semantic_diff.py
                    │
               cosine similarity
                    │
          < 0.70 (divergência) ─▶ LLM analysis
                    │
               INSERT ambiguities (status='pending')
                    │
                    ▼ (Dream Cycle ou execução manual)
               Síntese Dialética
                    │
               UPDATE ambiguities SET status='resolved'
                    │
               Aplica resolução (merge/choose/branch)
                    │
               Atomic write do resultado final
```

---

## 7. Provenance Metadata

Each note in Atlas has traceable provenance in frontmatter:

```yaml
---
title: Decisão de migrar para Hetzner
agent: claude-fable-5
trust_level: 2           # 1=baixo, 2=médio, 3=alto
machine_id: laptop-home  # de qual máquina veio
integrity_hash: a3b4c5d6e7f8...
created: 2026-06-10
source_observation_ids:
  - "550e8400-e29b-41d4-a716-446655440000"
  - "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
---
```

To track a suspicious fact:
```bash
# Verificar proveniência de um neuron
python3 scripts/health/audit_memory.py --trace "nome-do-arquivo.md"
```

---

## 8. Recommended Cron

```cron
# Auditoria e reindexação de arquivos recebidos via P2P (1x por hora)
0 * * * * cd $SINAPSE_HOME && python3 scripts/health/audit_memory.py --fix >> logs/audit.log 2>&1

# Backup do UMC antes da janela de auditoria (diário às 2:58am)
58 2 * * * cp $SINAPSE_HOME/hive_mind.db $SINAPSE_HOME/backups/hive_mind_$(date +\%F).db
```

---

## 9. Disaster Recovery

If `hive_mind.db` is corrupted or lost, it can be fully rebuilt from the vault:

```bash
# Reconstrução completa do índice a partir dos .md
./scripts/recover.sh

# O que o recover.sh faz:
# 1. Para o Watcher
# 2. Faz backup do db corrompido (se existir)
# 3. Cria novo hive_mind.db do zero (schema do zero)
# 4. Indexa todos os arquivos em cerebro/ via Graphify
# 5. Reinicia o Watcher
# Tempo estimado: 2-10 minutos dependendo do tamanho do vault
```