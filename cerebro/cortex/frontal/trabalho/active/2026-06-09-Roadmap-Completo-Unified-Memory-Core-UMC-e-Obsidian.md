---
tags: [decision]
status: active
created: 2026-06-09
updated: 2026-06-09
source: hermes-session
---

# Roadmap Completo: Unified Memory Core (UMC) e Obsidian

## Roadmap: Unificação do Motor de Memória (UMC) e Evolução do Obsidian

### Visão Geral
Transformar o Sinapse Agent em um motor de memória de baixa latência e alta fidelidade, onde o Obsidian atua como o "Painel de Controle Humano" e o SQLite UMC atua como o "Sistema Nervoso da IA".

---

### Fase 1: Fundação do Unified Memory Core (UMC)
**Objetivo:** Consolidar todos os silos de dados em um único banco SQLite.

1.  **Esquema Unificado (Design):**
    - Adotar o esquema de `neurons` e `synapses` do NeuralMemory.
    - Adicionar tabelas de `observations` e `timeline` (ex-claude-mem).
    - Integrar o módulo **FTS5** para busca textual e **`sqlite-vec`** para busca semântica.
2.  **Migração do Graphify (Escrita):**
    - Refatorar o indexador do Graphify para escrever diretamente no banco UMC.
    - Implementar rastreamento de mudanças (SHA256/mtime) para indexação incremental.
3.  **Migração do claude-mem:**
    - Redirecionar o worker do claude-mem para salvar eventos na tabela `observations` do banco UMC.
    - Vincular observações a neurônios existentes (ex: vincular um log de chat à nota do projeto correspondente).

---

### Fase 2: Motor de Busca Híbrido e MCP
**Objetivo:** Prover uma interface de consulta ultra-rápida e padronizada.

1.  **Query Engine Unificado:**
    - Criar uma função `query_hybrid(text)` que realiza:
        - Busca por termos exatos (FTS5).
        - Busca semântica (sqlite-vec).
        - Ativação por espalhamento (NeuralMemory).
    - Aplicar **Reciprocal Rank Fusion (RRF)** para priorizar resultados.
2.  **Servidor MCP Sinapse (Evolução):**
    - Atualizar o servidor MCP para expor ferramentas que consultam o banco UMC diretamente.
    - Adicionar suporte a queries complexas (ex: "quem trabalhou no projeto X na semana passada?").

---

### Fase 3: Evolução do Obsidian (Interface)
**Objetivo:** Transformar o Obsidian no portal de visualização da IA.

1.  **Integração do Plugin SQLite:**
    - Configurar o plugin **SQLite DB Viewer** no vault para ler o banco UMC.
    - Criar blocos de código `sqlite-query` em notas de "Dashboard" para exibir métricas e histórico da IA.
2.  **Links Semânticos Sugeridos:**
    - Implementar um script que sugere links `[[relacionados]]` no frontmatter das notas com base na proximidade vetorial do banco UMC.
3.  **Resumos Automáticos (Mirror Writing):**
    - O banco UMC gera periodicamente arquivos `.md` de resumo (como o `Current State.md`) para consumo visual no Obsidian.

---

### Fase 4: Estabilização e Deploy
**Objetivo:** Facilitar o uso e garantir a performance.

1.  **Containerização/Packaging:**
    - Empacotar o UMC Core em um único pacote Python/Docker.
    - Simplificar o `install.sh` para configurar apenas um serviço de memória.
2.  **Benchmarking de Latência:**
    - Garantir que as consultas híbridas retornem em < 200ms para vaults de até 5.000 notas.

---

### Esquema SQL Proposto (UMC Core)

```sql
-- TABELAS ESTRUTURAIS (ex-Graphify)
CREATE TABLE neurons (
    id TEXT PRIMARY KEY,
    label TEXT,
    type TEXT,
    source_file TEXT,
    community INTEGER,
    metadata JSON,
    last_indexed DATETIME
);

CREATE TABLE synapses (
    id INTEGER PRIMARY KEY,
    source_id TEXT,
    target_id TEXT,
    relation TEXT,
    weight FLOAT,
    FOREIGN KEY(source_id) REFERENCES neurons(id),
    FOREIGN KEY(target_id) REFERENCES neurons(id)
);

-- TABELAS TEMPORAIS (ex-claude-mem)
CREATE TABLE observations (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    project TEXT,
    content TEXT,
    type TEXT,
    created_at DATETIME,
    neuron_id TEXT, -- Vinculo opcional com estrutural
    FOREIGN KEY(neuron_id) REFERENCES neurons(id)
);

-- MOTORES DE BUSCA
CREATE VIRTUAL TABLE search_fts USING fts5(
    content, 
    source='neurons', 
    content_rowid='id'
);

CREATE VIRTUAL TABLE search_vec USING vec0(
    neuron_id TEXT PRIMARY KEY,
    embedding FLOAT[768]
);
```
