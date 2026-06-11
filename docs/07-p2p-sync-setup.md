# 07 — Sincronização P2P (Enxame Multi-Máquina)

> **Hive-Mind v2.0.0** — Syncthing como transporte, UUID v4 para evitar colisões, SHA-256 para integridade, e Síntese Dialética para resolução autônoma de conflitos.

---

## 1. Arquitetura do Enxame

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

O Syncthing é o "músculo" que transporta arquivos `.md` entre máquinas. O `hive_mind.db` **não** é sincronizado — cada máquina mantém seu índice local, reconstruído a partir dos arquivos Markdown recebidos.

---

## 2. Configuração do Syncthing

### 2.1 Instalação

```bash
# Ubuntu/Debian
sudo apt install syncthing

# macOS
brew install syncthing

# Windows — baixar em https://syncthing.net/downloads/
```

### 2.2 Configuração da Pasta

1. Acesse a UI do Syncthing: `http://localhost:8384`
2. Clique em **"Add Folder"**
3. Configure:
   - **Folder Path:** caminho absoluto para `cerebro/` (ex: `/home/user/Hive-Mind/cerebro`)
   - **Folder Type:** "Send & Receive"
   - **File Versioning:** "Simple File Versioning" — 5 versões mínimas
4. Compartilhe com outras máquinas usando o **Device ID** do Syncthing

### 2.3 Paths Recomendados

| Máquina | Path | Observação |
|---------|------|-----------|
| Linux | `/home/$USER/Documentos/Projects/Hive-Mind/cerebro` | Padrão |
| macOS | `/Users/$USER/Projects/Hive-Mind/cerebro` | |
| VPS | `/home/$USER/hive-mind/cerebro` | |

---

## 3. Prevenção de Colisões (UUID v4)

Todas as primary keys no UMC usam UUID v4 gerado localmente:

```python
import uuid
neuron_id = str(uuid.uuid4())  # ex: "550e8400-e29b-41d4-a716-446655440000"
```

**Por que UUID v4?** IDs sequenciais colidem entre máquinas distintas (máquina A e B ambas criam `id=1`). UUID v4 tem probabilidade de colisão de 1 em 10^36 — irrelevante na prática.

---

## 4. Integridade por Hash (SHA-256)

Cada arquivo indexado recebe um hash no momento da indexação:

```python
import hashlib
content_hash = hashlib.sha256(file_content.encode()).hexdigest()
# ex: "a3b4c5d6..."

# Armazenado em:
# neurons.hash TEXT  -- na tabela do UMC
# frontmatter YAML:  integrity_hash: "a3b4c5d6..."
```

O `audit_memory.py` compara o hash do arquivo físico com `neurons.hash`. Divergência indica que o arquivo foi modificado em outra máquina e o índice local está desatualizado.

---

## 5. Auditoria de Integridade (audit_memory.py)

### 5.1 O que o auditor verifica

```
  Para cada arquivo .md em cerebro/atlas/:
    1. sha256(arquivo.md) atual
    2. SELECT hash FROM neurons WHERE source_file = arquivo
    3. Comparação:
       - hash igual: OK, skip
       - hash diferente: divergência detectada
       - arquivo não indexado: INSERT neuron novo
```

### 5.2 Execução

```bash
# Verificar estado (read-only, sem modificações)
python3 scripts/audit_memory.py

# Corrigir — reindexar arquivos com hash divergente
python3 scripts/audit_memory.py --fix

# Verbose (mostra todos os arquivos verificados)
python3 scripts/audit_memory.py --fix --verbose
```

### 5.3 Output esperado

```
[audit] Verificando 142 arquivos em cerebro/atlas/...
[audit] OK:        138 (sem divergência)
[audit] Reindexado:  3 (hash divergente — arquivo modificado em outra máquina)
[audit] Novo:         1 (arquivo não estava no índice)
[audit] Conflito:     0 (sem ambiguidades detectadas)
[audit] Concluído em 4.2s
```

---

## 6. Resolução de Conflitos — Síntese Dialética (Phase 9)

Quando o auditor detecta que dois textos com o mesmo `source_file` têm conteúdos semânticos **irreconciliáveis** (não apenas hash diferente, mas conflito de fatos), o sistema registra uma **ambiguidade** e agenda resolução autônoma via LLM.

### 6.1 Tabela `ambiguities`

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

### 6.2 semantic_diff.py — Classificação de Conflitos

O `semantic_diff.py` usa uma abordagem híbrida para classificar o tipo de conflito:

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

### 6.3 Síntese Dialética — Resolução Autônoma

Para conflitos `contradictory`, o LLM aplica síntese dialética:

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

### 6.4 Fluxo Completo de Resolução

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

## 7. Metadados de Proveniência

Cada nota no Atlas tem proveniência rastreável no frontmatter:

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

Para rastrear um fato suspeito:
```bash
# Verificar proveniência de um neuron
python3 scripts/audit_memory.py --trace "nome-do-arquivo.md"
```

---

## 8. Cron Recomendado

```cron
# Auditoria e reindexação de arquivos recebidos via P2P (1x por hora)
0 * * * * cd $SINAPSE_HOME && python3 scripts/audit_memory.py --fix >> logs/audit.log 2>&1

# Backup do UMC antes da janela de auditoria (diário às 2:58am)
58 2 * * * cp $SINAPSE_HOME/hive_mind.db $SINAPSE_HOME/backups/hive_mind_$(date +\%F).db
```

---

## 9. Disaster Recovery

Se o `hive_mind.db` for corrompido ou perdido, pode ser reconstruído completamente a partir do vault:

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
