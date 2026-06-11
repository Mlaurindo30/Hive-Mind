import os
import sys
import sqlite3
import hashlib
from pathlib import Path

# Setup paths
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = str(_HERE.parent)
sys.path.append(SINAPSE_HOME)

from core.database import get_connection

def test_synthesis():
    conn = get_connection()
    
    # 1. Setup Test Data
    neuron_id = "test-neuron-123"
    topic = "test_topic"
    atlas_dir = Path(SINAPSE_HOME) / "cerebro" / "atlas" / topic
    atlas_dir.mkdir(parents=True, exist_ok=True)
    atlas_file = atlas_dir / "test-fact.md"
    
    # Create Markdown file
    with open(atlas_file, "w") as f:
        f.write("# Test Fact\n\nOriginal Content")
    
    # Insert Neuron
    conn.execute("DELETE FROM neurons WHERE id = ?", (neuron_id,))
    conn.execute("""
        INSERT INTO neurons (id, label, type, source_file, content, hash)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (neuron_id, "Test Fact", "fact", f"{topic}/test-fact.md", "Original Content", "hash1"))
    
    # Insert Ambiguity
    amb_id = "amb-123"
    conn.execute("DELETE FROM ambiguities WHERE id = ?", (amb_id,))
    conn.execute("""
        INSERT INTO ambiguities (id, neuron_id, source_a_hash, source_b_hash, content_a, content_b, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (amb_id, neuron_id, "hash1", "hash2", "Original Content", "Updated Content with more info", "pending"))
    
    conn.commit()
    conn.close()
    
    print(f"Test data setup complete. Running synthesis cycle...")
    
    # 2. Run Synthesis Cycle
    from scripts.dream_cycle import run_synthesis_cycle
    run_synthesis_cycle()
    
    # 3. Verify Results
    conn = get_connection()
    neuron = conn.execute("SELECT * FROM neurons WHERE id = ?", (neuron_id,)).fetchone()
    amb = conn.execute("SELECT * FROM ambiguities WHERE id = ?", (amb_id,)).fetchone()
    
    print("\n=== Verification ===")
    print(f"Neuron Content: {neuron['content']}")
    print(f"Ambiguity Status: {amb['status']}")
    
    # Check Markdown
    with open(atlas_file, "r") as f:
        md_content = f.read()
    print(f"Markdown Content preview: {md_content[:100]}...")
    
    if amb['status'] == 'synthesized' and "Updated" in neuron['content']:
        print("\nSUCCESS: Synthesis stage worked end-to-end!")
    else:
        print("\nFAILURE: Synthesis stage did not work as expected.")
        sys.exit(1)
    
    conn.close()

if __name__ == "__main__":
    test_synthesis()
