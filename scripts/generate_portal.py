import os
import json
import math
import sys
import sqlite3
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from core.database import get_connection

def get_spiral_coords(index, scale=500):
    """Calculates x, y coordinates in a spiral."""
    angle = 0.5 * index
    radius = math.sqrt(index) * scale
    x = radius * math.cos(angle)
    y = radius * math.sin(angle)
    return int(x), int(y)

def generate_portal():
    """Generates an Obsidian .canvas file from the Hive-Mind database."""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return

    # 1. Fetch data
    try:
        neurons = conn.execute("SELECT * FROM neurons ORDER BY created_at DESC LIMIT 100").fetchall()
        if not neurons:
            print("No neurons found in database.")
            return

        neuron_ids = [n['id'] for n in neurons]
        placeholders = ','.join(['?'] * len(neuron_ids))
        
        synapses = conn.execute(f"SELECT * FROM synapses WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})", neuron_ids + neuron_ids).fetchall()
        visual_memories = conn.execute(f"SELECT * FROM visual_memories WHERE neuron_id IN ({placeholders})", neuron_ids).fetchall()
        documents = conn.execute("SELECT * FROM document_memories ORDER BY created_at DESC LIMIT 50").fetchall()
    except Exception as e:
        print(f"Error querying data: {e}")
        return
    finally:
        conn.close()

    nodes = []
    edges = []

    # 2. Map Documents (Source Layer)
    for k, doc in enumerate(documents):
        dx, dy = get_spiral_coords(k, scale=1200) # Outer circle for documents
        nodes.append({
            "id": doc['id'],
            "type": "file",
            "file": f"attachments/{doc['file_path']}",
            "x": dx,
            "y": dy - 2000,
            "width": 300,
            "height": 400,
            "color": "3" # Yellow for documents
        })

    # 3. Map neurons
    for i, n in enumerate(neurons):
        x, y = get_spiral_coords(i)
        content = n['content'] or ""
        if len(content) > 500:
            content = content[:497] + "..."
            
        # Clean up text for JSON/Canvas
        label = n['label'].replace('"', '\"').replace('\n', ' ')
        display_content = content.replace('"', '\"').replace('\n', '\\n')
        
        nodes.append({
            "id": n['id'],
            "type": "text",
            "x": x,
            "y": y,
            "width": 400,
            "height": 300,
            "text": f"## {label}\\n\\n{display_content}",
            "color": "1" # Blue
        })
        
        # Add visual memories adjacent to neuron
        neuron_vms = [v for v in visual_memories if v['neuron_id'] == n['id']]
        for j, vm in enumerate(neuron_vms):
            nodes.append({
                "id": vm['id'],
                "type": "file",
                "file": vm['image_path'],
                "x": x + 450,
                "y": y + (j * 500),
                "width": 600,
                "height": 450,
                "color": "2" # Green
            })
            
    # 4. Map edges
    for s in synapses:
        edges.append({
            "id": s['id'],
            "fromNode": s['source_id'],
            "toNode": s['target_id'],
            "label": s['relation']
        })
        
    # 5. Save
    portal_data = {"nodes": nodes, "edges": edges}
    output_path = Path("cerebro/portal.canvas")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(output_path, "w") as f:
            json.dump(portal_data, f, indent=2)
        print(f"Portal successfully generated at: {output_path}")
    except Exception as e:
        print(f"Error saving portal: {e}")

if __name__ == "__main__":
    generate_portal()
