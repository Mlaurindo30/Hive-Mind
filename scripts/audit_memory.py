#!/usr/bin/env python3
"""
Hive-Mind — Auditor de Integridade Swarm (Phase 8)
Verifica a consistência entre o Vault (Markdown) e o SQLite.
Recupera índices corrompidos ou ausentes após sincronização P2P.
"""

import os
import sys
import hashlib
import sqlite3
import yaml
import re
import shutil
from pathlib import Path
from datetime import datetime

# Configura paths
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent))
sys.path.append(SINAPSE_HOME)

from core.database import get_connection, get_embedder, serialize_f32, register_ambiguity

def get_content_hash(content: str) -> str:
    """Calcula o hash SHA256 do conteúdo (truncado para 16 chars)."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]

def parse_markdown(path: Path):
    """Extrai frontmatter e conteúdo de um arquivo Markdown."""
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    frontmatter = {}
    content = text
    
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1))
            content = match.group(2).strip()
        except Exception:
            pass
            
    return frontmatter, content

def reindex_neuron(conn, file_path: Path, neuron_id: str, label: str, content: str, n_type: str, n_hash: str):
    """Reindexa um neurônio no SQLite, FTS e Busca Vetorial."""
    cursor = conn.cursor()
    
    # 1. Update/Insert in neurons table
    cursor.execute("""
        INSERT INTO neurons (id, label, type, source_file, content, hash, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            label = excluded.label,
            type = excluded.type,
            content = excluded.content,
            hash = excluded.hash,
            updated_at = excluded.updated_at
    """, (neuron_id, label, n_type, os.path.relpath(file_path, SINAPSE_HOME), content, n_hash, datetime.now().isoformat()))
    
    # Triggers (neurons_after_update) should handle search_fts automatically
    
    # 2. Update Vector Search
    embedder = get_embedder()
    if embedder:
        try:
            vec = list(embedder.embed(content))[0].tolist()
            serialized = serialize_f32(vec)
            cursor.execute("""
                INSERT INTO search_vec (neuron_id, embedding)
                VALUES (?, ?)
                ON CONFLICT(neuron_id) DO UPDATE SET
                    embedding = excluded.embedding
            """, (neuron_id, serialized))
        except Exception as e:
            print(f"  [!] Erro ao gerar embedding para {neuron_id}: {e}")
            
    conn.commit()

def run_audit(fix=False):
    print(f"=== Hive-Mind Swarm Auditor (Fix Mode: {'ON' if fix else 'OFF'}) ===")
    
    atlas_root = Path(SINAPSE_HOME) / "cerebro" / "atlas"
    if not atlas_root.exists():
        print(f"ERRO: Vault Atlas não encontrado em {atlas_root}")
        return

    conn = get_connection()
    
    stats = {
        "total": 0, 
        "healthy": 0, 
        "mismatch_hash": 0, 
        "missing_db": 0, 
        "recovered": 0,
        "conflicts_found": 0,
        "conflicts_registered": 0
    }
    
    # 1. Main Audit Loop
    for md_file in atlas_root.rglob("*.md"):
        if ".sync-conflict-" in md_file.name:
            continue
            
        stats["total"] += 1
        neuron_id = md_file.stem
        
        # 1. Parse File
        frontmatter, content = parse_markdown(md_file)
        file_hash = get_content_hash(content)
        
        # 2. Check DB
        neuron = conn.execute("SELECT hash FROM neurons WHERE id = ?", (neuron_id,)).fetchone()
        
        is_healthy = True
        reason = ""
        
        if not neuron:
            is_healthy = False
            reason = "MISSING_IN_DB"
            stats["missing_db"] += 1
        elif neuron["hash"] != file_hash:
            is_healthy = False
            reason = "HASH_MISMATCH"
            stats["mismatch_hash"] += 1
            
        if is_healthy:
            stats["healthy"] += 1
        else:
            print(f"  [!] {reason}: {md_file.relative_to(SINAPSE_HOME)}")
            if fix:
                # Extrai dados básicos para reindexação
                label = frontmatter.get("label", neuron_id.replace("_", " ").title())
                if "# " in content: # Tenta pegar o H1 se o label sumiu
                    h1_match = re.search(r"^# (.*)", content, re.MULTILINE)
                    if h1_match: label = h1_match.group(1).strip()
                
                n_type = frontmatter.get("type", "fact")
                
                reindex_neuron(conn, md_file, neuron_id, label, content, n_type, file_hash)
                stats["recovered"] += 1
                print(f"      -> RECOVERED")

    # 2. Conflict Ingestion Loop
    conflicts_dir = Path(SINAPSE_HOME) / "cerebro" / "conflicts"
    if fix:
        conflicts_dir.mkdir(parents=True, exist_ok=True)
    
    import json
    for conflict_file in atlas_root.rglob("*.sync-conflict-*.md"):
        stats["conflicts_found"] += 1
        neuron_id = conflict_file.name.split(".sync-conflict-")[0]
        
        # Parse conflict file
        conf_fm, conf_content = parse_markdown(conflict_file)
        conf_hash = get_content_hash(conf_content)
        
        # Check canonical version in DB
        canon = conn.execute("SELECT content, hash, metadata FROM neurons WHERE id = ?", (neuron_id,)).fetchone()
        
        if canon:
            if canon["hash"] != conf_hash:
                version_a = {
                    "content": canon["content"],
                    "hash": canon["hash"],
                    "metadata": json.loads(canon["metadata"]) if canon["metadata"] else {}
                }
                version_b = {
                    "content": conf_content,
                    "hash": conf_hash,
                    "metadata": conf_fm
                }
                
                if fix:
                    try:
                        register_ambiguity(neuron_id, version_a, version_b)
                        stats["conflicts_registered"] += 1
                        print(f"  [C] Conflito registrado: {neuron_id} ({conflict_file.name})")
                    except Exception as e:
                        print(f"  [!] Erro ao registrar conflito para {neuron_id}: {e}")
                else:
                    print(f"  [C] Conflito detectado: {neuron_id} ({conflict_file.name})")
            else:
                print(f"  [C] Conflito idêntico ao DB: {neuron_id} (Ignorando)")
        else:
            print(f"  [C] Conflito para neurônio AUSENTE: {neuron_id} (Ignorando)")
            
        if fix:
            dest = conflicts_dir / conflict_file.name
            try:
                shutil.move(str(conflict_file), str(dest))
                print(f"      -> Movido para cerebro/conflicts/")
            except Exception as e:
                print(f"      [!] Erro ao mover arquivo de conflito: {e}")

    conn.close()
    
    print("\n--- Resultado da Auditoria ---")
    print(f"Total de arquivos:  {stats['total']}")
    print(f"Saudáveis:         {stats['healthy']}")
    print(f"Ausentes no DB:    {stats['missing_db']}")
    print(f"Divergência Hash:  {stats['mismatch_hash']}")
    if fix:
        print(f"Recuperados:       {stats['recovered']}")
    
    print(f"\nConflitos encontrados:  {stats['conflicts_found']}")
    print(f"Conflitos registrados: {stats['conflicts_registered']}")
    
    if not fix and (stats['missing_db'] > 0 or stats['mismatch_hash'] > 0):
        print("\nDica: Use --fix para sincronizar o banco com o Vault.")

if __name__ == "__main__":
    fix_mode = "--fix" in sys.argv
    run_audit(fix=fix_mode)
