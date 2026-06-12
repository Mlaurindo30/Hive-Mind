-- Unified Memory Core (UMC) Schema

-- Structural Layer (Neurons)
CREATE TABLE IF NOT EXISTS neurons (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    type TEXT NOT NULL,
    source_file TEXT,
    content TEXT,
    hash TEXT,
    metadata JSON,
    community INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Structural Layer (Synapses)
CREATE TABLE IF NOT EXISTS synapses (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT,
    weight FLOAT DEFAULT 1.0,
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(source_id) REFERENCES neurons(id) ON DELETE CASCADE,
    FOREIGN KEY(target_id) REFERENCES neurons(id) ON DELETE CASCADE
);

-- Temporal Layer (Observations)
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
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
    FOREIGN KEY(neuron_id) REFERENCES neurons(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_archived ON observations(archived);

-- Vault for Encrypted Secrets
CREATE TABLE IF NOT EXISTS vault (
    id TEXT PRIMARY KEY, -- UUID or Placeholder ID
    encrypted_secret BLOB NOT NULL,
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Phase 9: Semantic Merge (Ambiguities)
CREATE TABLE IF NOT EXISTS ambiguities (
    id TEXT PRIMARY KEY,
    neuron_id TEXT NOT NULL,
    source_a_hash TEXT NOT NULL,
    source_b_hash TEXT NOT NULL,
    content_a TEXT NOT NULL,
    content_b TEXT NOT NULL,
    metadata_a JSON,
    metadata_b JSON,
    status TEXT DEFAULT 'pending', -- pending, synthesized, branched
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(neuron_id) REFERENCES neurons(id) ON DELETE CASCADE
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
    embedding FLOAT[384] -- all-MiniLM-L6-v2 size
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
    id TEXT PRIMARY KEY,
    image_path TEXT NOT NULL,
    description TEXT,
    ocr_text TEXT,
    neuron_id TEXT, -- Link to a conceptual neuron
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(neuron_id) REFERENCES neurons(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS document_memories (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_hash TEXT UNIQUE,
    summary TEXT,
    topics TEXT,
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- PRAGMAS for performance
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
