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
import argparse
import fnmatch
from pathlib import Path
from datetime import datetime

# Configura paths
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent.parent))
sys.path.append(SINAPSE_HOME)

from core.database import get_connection, get_embedder, serialize_f32, register_ambiguity
from core.indexing import upsert_search_vec

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
    vector_ok = False
    if not embedder:
        print(f"  [!] Embedder indisponível para {neuron_id}")
    else:
        try:
            raw_vec = list(embedder.embed(content))[0]
            vec = raw_vec.tolist() if hasattr(raw_vec, "tolist") else list(raw_vec)
            upsert_search_vec(conn, neuron_id, serialize_f32(vec))
            vector_ok = True
        except Exception as e:
            print(f"  [!] Erro ao gerar embedding para {neuron_id}: {e}")

    conn.commit()
    return vector_ok

def _split_excludes(values: list[str] | None) -> list[str]:
    patterns: list[str] = []
    for value in values or []:
        patterns.extend(item.strip() for item in value.split(",") if item.strip())
    env_value = os.environ.get("SINAPSE_AUDIT_EXCLUDE", "")
    patterns.extend(item.strip() for item in env_value.split(",") if item.strip())
    return patterns


def _is_excluded(path: Path, patterns: list[str]) -> bool:
    if not patterns:
        return False
    rel = path.relative_to(SINAPSE_HOME).as_posix()
    temporal_rel = path.relative_to(Path(SINAPSE_HOME) / "cerebro" / "cortex" / "temporal").as_posix()
    return any(
        fnmatch.fnmatch(rel, pattern)
        or fnmatch.fnmatch(temporal_rel, pattern)
        or temporal_rel.startswith(pattern.rstrip("/") + "/")
        for pattern in patterns
    )


def _search_vector_exists(conn, neuron_id: str) -> bool:
    try:
        row = conn.execute("SELECT 1 FROM search_vec WHERE neuron_id = ? LIMIT 1", (neuron_id,)).fetchone()
    except sqlite3.OperationalError:
        return False
    return row is not None


def _delete_indexed_source(conn, file_path: Path) -> int:
    rel = os.path.relpath(file_path, SINAPSE_HOME)
    rows = conn.execute("SELECT id FROM neurons WHERE source_file = ?", (rel,)).fetchall()
    for row in rows:
        neuron_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
        try:
            conn.execute("DELETE FROM search_vec WHERE neuron_id = ?", (neuron_id,))
        except sqlite3.OperationalError:
            pass
    conn.execute("DELETE FROM neurons WHERE source_file = ?", (rel,))
    conn.commit()
    return len(rows)


def run_audit(fix=False, exclude: list[str] | None = None):
    print(f"=== Hive-Mind Swarm Auditor (Fix Mode: {'ON' if fix else 'OFF'}) ===")
    exclude_patterns = _split_excludes(exclude)
    if exclude_patterns:
        print(f"Exclusões ativas: {', '.join(exclude_patterns)}")
    
    # cortex/temporal — núcleo da memória (respeita SINAPSE_HOME do módulo p/ testes)
    atlas_root = Path(SINAPSE_HOME) / "cerebro" / "cortex" / "temporal"
    if not atlas_root.exists():
        print(f"ERRO: Córtex temporal não encontrado em {atlas_root}")
        return

    conn = get_connection()
    
    stats = {
        "total": 0, 
        "healthy": 0, 
        "mismatch_hash": 0, 
        "missing_db": 0, 
        "missing_vector": 0,
        "recovered": 0,
        "conflicts_found": 0,
        "conflicts_registered": 0,
        "excluded": 0,
        "ignored_non_neuron": 0,
        "removed_non_neuron": 0,
    }
    
    # 1. Main Audit Loop
    for md_file in atlas_root.rglob("*.md"):
        if ".sync-conflict-" in md_file.name:
            continue
        if _is_excluded(md_file, exclude_patterns):
            stats["excluded"] += 1
            continue

        frontmatter, content = parse_markdown(md_file)
        if frontmatter.get("type") in {"redirect", "moc"}:
            stats["ignored_non_neuron"] += 1
            if fix:
                stats["removed_non_neuron"] += _delete_indexed_source(conn, md_file)
            continue

        stats["total"] += 1
        neuron_id = md_file.stem
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
        elif not _search_vector_exists(conn, neuron_id):
            is_healthy = False
            reason = "MISSING_VECTOR"
            stats["missing_vector"] += 1
            
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
                
                if reindex_neuron(conn, md_file, neuron_id, label, content, n_type, file_hash):
                    stats["recovered"] += 1
                    print(f"      -> RECOVERED")
                else:
                    print(f"      -> FAILED")

    # 2. Conflict Ingestion Loop
    conflicts_dir = Path(SINAPSE_HOME) / "cerebro" / "cortex" / "insula" / "conflitos"
    if fix:
        conflicts_dir.mkdir(parents=True, exist_ok=True)
    
    import json
    for conflict_file in atlas_root.rglob("*.sync-conflict-*.md"):
        if _is_excluded(conflict_file, exclude_patterns):
            stats["excluded"] += 1
            continue
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
                print(f"      -> Movido para cortex/insula/conflitos/")
            except Exception as e:
                print(f"      [!] Erro ao mover arquivo de conflito: {e}")

    conn.close()
    
    print("\n--- Resultado da Auditoria ---")
    print(f"Total de arquivos:  {stats['total']}")
    print(f"Saudáveis:         {stats['healthy']}")
    print(f"Excluídos:         {stats['excluded']}")
    print(f"Não-neurônios ignorados: {stats['ignored_non_neuron']}")
    print(f"Ausentes no DB:    {stats['missing_db']}")
    print(f"Vetores ausentes:  {stats['missing_vector']}")
    print(f"Divergência Hash:  {stats['mismatch_hash']}")
    if fix:
        print(f"Recuperados:       {stats['recovered']}")
        print(f"Não-neurônios removidos do índice: {stats['removed_non_neuron']}")
    
    print(f"\nConflitos encontrados:  {stats['conflicts_found']}")
    print(f"Conflitos registrados: {stats['conflicts_registered']}")
    
    if not fix and (stats['missing_db'] > 0 or stats['mismatch_hash'] > 0 or stats["missing_vector"] > 0):
        print("\nDica: Use --fix para sincronizar o banco com o Vault.")

    return stats

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="Reindexa arquivos ausentes/divergentes.")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Padrão glob ou prefixo relativo a cerebro/cortex/temporal para ignorar. "
            "Pode repetir ou usar lista separada por vírgula. Também lê SINAPSE_AUDIT_EXCLUDE."
        ),
    )
    args = parser.parse_args()
    run_audit(fix=args.fix, exclude=args.exclude)
