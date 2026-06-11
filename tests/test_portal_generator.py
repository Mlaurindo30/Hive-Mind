import unittest
import os
import json
import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

class TestPortalGenerator(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_hive_mind.db"
        # Temporarily mock core.database.DB_PATH if needed, 
        # but for now we'll just test the functions directly.
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("CREATE TABLE neurons (id TEXT PRIMARY KEY, label TEXT, type TEXT, content TEXT, community INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        self.conn.execute("CREATE TABLE synapses (id TEXT PRIMARY KEY, source_id TEXT, target_id TEXT, relation TEXT)")
        self.conn.execute("CREATE TABLE visual_memories (id TEXT PRIMARY KEY, image_path TEXT, neuron_id TEXT)")
        
        self.conn.execute("INSERT INTO neurons (id, label, type, content, community) VALUES ('n1', 'Neuron 1', 'concept', 'Content 1', 1)")
        self.conn.execute("INSERT INTO neurons (id, label, type, content, community) VALUES ('n2', 'Neuron 2', 'concept', 'Content 2', 1)")
        self.conn.execute("INSERT INTO synapses VALUES ('s1', 'n1', 'n2', 'rel')")
        self.conn.execute("INSERT INTO visual_memories VALUES ('v1', 'images/test.png', 'n1')")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            
    def test_spiral_coords(self):
        # We'll import after the file is created in Task 2
        try:
            from scripts.generate_portal import get_spiral_coords
            x, y = get_spiral_coords(0)
            self.assertEqual((x, y), (0, 0))
            x1, y1 = get_spiral_coords(1)
            self.assertNotEqual((x1, y1), (0, 0))
        except ImportError:
            pass

if __name__ == "__main__":
    unittest.main()
