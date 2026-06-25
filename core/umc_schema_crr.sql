-- Unified Memory Core (UMC) Schema - CRR-compatible variant.
--
-- Derivado de core/umc_schema.sql com as correcoes necessarias para
-- CR-SQLite v0.16.3 (vlcn-io/cr-sqlite). Mudancas em relacao ao schema
-- original:
--   1. PK TEXT PRIMARY KEY         -> TEXT PRIMARY KEY NOT NULL DEFAULT ''
--   2. Colunas NOT NULL sem DEFAULT -> NOT NULL DEFAULT '' (forward-compat)
--   3. document_memories.file_hash perdeu UNIQUE (CRR proibe alem da PK)
--   4. FOREIGN KEY constraints removidas (inline + constraints separadas)
--      das 5 tabelas com FK: synapses, observations, ambiguities,
--      visual_memories, causal_edges. CR-SQLite rejeita FKs checked porque
--      replicacao pode violar a ordem de INSERT. Integridade referencial
--      passa a ser responsabilidade do codigo de aplicacao. Ver
--      scripts/setup/setup_crdt.py para logica de validacao pre-INSERT.
--   5. search_vec (vec0) e search_fts (fts5) mantidos como virtuais;
--      CR-SQLite nao suporta virtual tables como CRR - cada maquina
--      reconstroi via Dream Cycle.
--
-- Este schema e o destino do script scripts/setup/setup_crdt.py, que:
--   (a) faz backup hive_mind.db.pre-crr
--   (b) cria DB novo com este schema
--   (c) copia dados preservando PKs (e removendo orfaos de FK se houver)
--   (d) executa crsql_as_crr em cada tabela CRR-elegivel
--
-- Regra de nomenclatura: ver docs/01-architecture.md §1.1 e
-- docs/10-implementation-roadmap.md §0.7 - sufixo _crr descreve a
-- propriedade (CRR-compat), nao uma versao.

-- Unified Memory Core (UMC) Schema

-- Structural Layer (Neurons)
CREATE TABLE IF NOT EXISTS neurons (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    source_file TEXT,
    content TEXT,
    hash TEXT,
    metadata JSON,
    community INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    visibility TEXT DEFAULT 'private',
    indexed_at TIMESTAMP
);

-- Structural Layer (Synapses)
CREATE TABLE IF NOT EXISTS synapses (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '',
    source_id TEXT NOT NULL DEFAULT '',
    target_id TEXT NOT NULL DEFAULT '',
    relation TEXT,
    weight FLOAT DEFAULT 1.0,
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Temporal Layer (Observations)
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '',
    session_id TEXT,
    project TEXT,
    type TEXT, -- decision, learning, event
    title TEXT,
    content TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    neuron_id TEXT, -- Link optional to a neuron
    archived INTEGER DEFAULT 0,  -- 0=pendente, 1=consolidado, 2=quarentena
    metadata JSON,
    uuid TEXT,           -- Phase 8: P2P/Syncthing sync identifier
    source_machine TEXT, -- Phase 8: originating machine hostname
    goal_id TEXT,        -- HM-11: objective that motivated the observation
    why TEXT,            -- HM-11: explicit intent/reason
    intent_source TEXT  -- user, planner, dream_cycle, agent


);

CREATE INDEX IF NOT EXISTS idx_observations_archived ON observations(archived);

-- Vault for Encrypted Secrets
CREATE TABLE IF NOT EXISTS vault (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '', -- UUID or Placeholder ID
    encrypted_secret BLOB NOT NULL DEFAULT '',
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Phase 9: Semantic Merge (Ambiguities)
CREATE TABLE IF NOT EXISTS ambiguities (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '',
    neuron_id TEXT NOT NULL DEFAULT '',
    source_a_hash TEXT NOT NULL DEFAULT '',
    source_b_hash TEXT NOT NULL DEFAULT '',
    content_a TEXT NOT NULL DEFAULT '',
    content_b TEXT NOT NULL DEFAULT '',
    metadata_a JSON,
    metadata_b JSON,
    status TEXT DEFAULT 'pending', -- pending, synthesized, branched
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ambiguities_neuron_status ON ambiguities(neuron_id, status);

-- Full-Text Search (FTS5) for content
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    neuron_id UNINDEXED,
    label,
    content,
    tokenize='unicode61'
);

-- Vector Search (sqlite-vec)
-- Note: vec0 tables are created dynamically or defined here if supported by the loader
CREATE VIRTUAL TABLE IF NOT EXISTS search_vec USING vec0(
    neuron_id TEXT PRIMARY KEY,
    embedding FLOAT[1024] -- bge-m3:latest (Ollama) size
);

-- Triggers for FTS sync
CREATE TRIGGER IF NOT EXISTS neurons_after_insert AFTER INSERT ON neurons BEGIN
    INSERT INTO search_fts(neuron_id, label, content) VALUES (new.id, new.label, new.content);
END;

CREATE TRIGGER IF NOT EXISTS neurons_after_delete AFTER DELETE ON neurons BEGIN
    DELETE FROM search_fts WHERE neuron_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS neurons_after_update AFTER UPDATE ON neurons BEGIN
    DELETE FROM search_fts WHERE neuron_id = old.id;
    INSERT INTO search_fts(neuron_id, label, content) VALUES (new.id, new.label, new.content);
END;

-- Multimodal Layer (Visual Memories)
CREATE TABLE IF NOT EXISTS visual_memories (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    description TEXT,
    ocr_text TEXT,
    neuron_id TEXT, -- Link to a conceptual neuron
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_memories (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    file_hash TEXT,
    summary TEXT,
    topics TEXT,
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Phase HM-11: Causal Graph
CREATE TABLE IF NOT EXISTS causal_edges (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '',
    cause_neuron_id TEXT NOT NULL DEFAULT '',
    effect_neuron_id TEXT NOT NULL DEFAULT '',
    label TEXT,
    confidence REAL DEFAULT 1.0 CHECK(confidence BETWEEN 0.0 AND 1.0),
    source TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_causal_cause ON causal_edges(cause_neuron_id);
CREATE INDEX IF NOT EXISTS idx_causal_effect ON causal_edges(effect_neuron_id);

-- Phase HM-11: Intent Memory plans
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    steps_json TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- PRAGMAS for performance
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
