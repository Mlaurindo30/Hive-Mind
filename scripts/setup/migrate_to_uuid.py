#!/usr/bin/env python3
import sqlite3
import uuid
import shutil
import os
import sys
import json
from pathlib import Path

# Tentativa de carregar sqlite-vec
try:
    import sqlite_vec
except ImportError:
    sqlite_vec = None

# Add root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "hive_mind.db"
BACKUP_PATH = PROJECT_ROOT / "hive_mind.db.bak"

def migrate():
    print(f"Starting FULL migration to UUIDs for {DB_PATH}...")

    # 1. Backup database
    if DB_PATH.exists():
        print(f"Creating backup at {BACKUP_PATH}...")
        shutil.copy2(DB_PATH, BACKUP_PATH)
    else:
        print("Database file not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    if sqlite_vec:
        sqlite_vec.load(conn)
        print("sqlite-vec extension loaded.")
    else:
        print("WARNING: sqlite-vec not found. Virtual tables (vec0) will NOT be migrated correctly.")

    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute("BEGIN TRANSACTION;")

        # --- 1. MIGRATE NEURONS (Mapping Slugs/IDs to UUIDs) ---
        print("Migrating 'neurons' table...")
        cursor.execute("SELECT id FROM neurons;")
        neuron_ids = [row['id'] for row in cursor.fetchall()]
        
        neuron_map = {}
        for old_id in neuron_ids:
            try:
                # Se já for um UUID v4, mantém
                uuid.UUID(old_id, version=4)
                neuron_map[old_id] = old_id
            except ValueError:
                neuron_map[old_id] = str(uuid.uuid4())

        cursor.execute("ALTER TABLE neurons RENAME TO neurons_old;")
        cursor.execute("""
            CREATE TABLE neurons (
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
        """)
        
        cursor.execute("SELECT * FROM neurons_old;")
        for row in cursor.fetchall():
            new_id = neuron_map[row['id']]
            cursor.execute("""
                INSERT INTO neurons (id, label, type, source_file, content, hash, metadata, community, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (new_id, row['label'], row['type'], row['source_file'], row['content'], 
                  row['hash'], row['metadata'], row['community'], row['created_at'], row['updated_at']))

        # --- 2. MIGRATE SYNAPSES ---
        print("Migrating 'synapses' table...")
        cursor.execute("ALTER TABLE synapses RENAME TO synapses_old;")
        cursor.execute("""
            CREATE TABLE synapses (
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
        """)
        
        cursor.execute("SELECT * FROM synapses_old;")
        for row in cursor.fetchall():
            new_id = row['id'] if isinstance(row['id'], str) and len(row['id']) == 36 else str(uuid.uuid4())
            new_source = neuron_map.get(row['source_id'], row['source_id'])
            new_target = neuron_map.get(row['target_id'], row['target_id'])
            cursor.execute("""
                INSERT INTO synapses (id, source_id, target_id, relation, weight, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (new_id, new_source, new_target, row['relation'], row['weight'], row['metadata'], row['created_at']))

        # --- 3. MIGRATE OBSERVATIONS ---
        print("Migrating 'observations' table...")
        cursor.execute("ALTER TABLE observations RENAME TO observations_old;")
        cursor.execute("""
            CREATE TABLE observations (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                project TEXT,
                type TEXT,
                title TEXT,
                content TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                neuron_id TEXT,
                metadata JSON,
                FOREIGN KEY(neuron_id) REFERENCES neurons(id) ON DELETE SET NULL
            );
        """)
        
        cursor.execute("SELECT * FROM observations_old;")
        for row in cursor.fetchall():
            new_id = row['id'] if isinstance(row['id'], str) and len(row['id']) == 36 else str(uuid.uuid4())
            new_neuron_id = neuron_map.get(row['neuron_id'], row['neuron_id']) if row['neuron_id'] else None
            cursor.execute("""
                INSERT INTO observations (id, session_id, project, type, title, content, created_at, neuron_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (new_id, row['session_id'], row['project'], row['type'], row['title'], 
                  row['content'], row['created_at'], new_neuron_id, row['metadata']))

        # --- 4. MIGRATE VAULT ---
        print("Migrating 'vault' table...")
        cursor.execute("ALTER TABLE vault RENAME TO vault_old;")
        cursor.execute("""
            CREATE TABLE vault (
                id TEXT PRIMARY KEY,
                encrypted_secret BLOB NOT NULL,
                metadata JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cursor.execute("SELECT * FROM vault_old;")
        for row in cursor.fetchall():
            new_id = row['id'] if isinstance(row['id'], str) and len(row['id']) == 36 else str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO vault (id, encrypted_secret, metadata, created_at)
                VALUES (?, ?, ?, ?)
            """, (new_id, row['encrypted_secret'], row['metadata'], row['created_at']))

        # --- 5. REBUILD VIRTUAL TABLES (FTS & VEC) ---
        print("Rebuilding virtual tables...")
        # FTS5 doesn't need schema change if neuron_id was already TEXT
        cursor.execute("DELETE FROM search_fts;")
        cursor.execute("INSERT INTO search_fts(neuron_id, label, content) SELECT id, label, content FROM neurons;")
        
        if sqlite_vec:
            try:
                cursor.execute("ALTER TABLE search_vec RENAME TO search_vec_old;")
                cursor.execute("CREATE VIRTUAL TABLE search_vec USING vec0(neuron_id TEXT PRIMARY KEY, embedding FLOAT[384]);")
                cursor.execute("SELECT * FROM search_vec_old;")
                for row in cursor.fetchall():
                    new_id = neuron_map.get(row['neuron_id'], row['neuron_id'])
                    cursor.execute("INSERT INTO search_vec(neuron_id, embedding) VALUES (?, ?)", (new_id, row['embedding']))
                cursor.execute("DROP TABLE search_vec_old;")
            except Exception as ve:
                print(f"Warning during search_vec migration: {ve}")

        # --- 6. CLEANUP ---
        cursor.execute("DROP TABLE neurons_old;")
        cursor.execute("DROP TABLE synapses_old;")
        cursor.execute("DROP TABLE observations_old;")
        cursor.execute("DROP TABLE vault_old;")

        conn.commit()
        print("Migration COMPLETED successfully.")

    except Exception as e:
        conn.rollback()
        print(f"CRITICAL ERROR during migration: {e}")
        raise
    finally:
        cursor.execute("PRAGMA foreign_keys = ON;")
        conn.close()

if __name__ == "__main__":
    migrate()
