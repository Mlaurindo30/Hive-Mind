"""CR-SQLite vendor para Hive-Mind.

Wrapper Python sobre o binario nativo crsqlite (vlcn-io/cr-sqlite).
Habilita sincronizacao CRDT do hive_mind.db entre multiplas instancias
(workstation, laptop, servidor) sem servidor central.

Politica 0.2 do roadmap: vendor externo em integrations/<nome>/.
Clone: https://github.com/vlcn-io/cr-sqlite (release v0.16.3 - 2024-01-17).
"""
from integrations.crsqlite.client import (
    CRDT_TABLES,
    load_crsqlite_extension,
    enable_crdt,
    get_changes_since,
    apply_changes,
    current_db_version,
    finalize,
    vendor_path,
)

__all__ = [
    "CRDT_TABLES",
    "load_crsqlite_extension",
    "enable_crdt",
    "get_changes_since",
    "apply_changes",
    "current_db_version",
    "finalize",
    "vendor_path",
]

__version__ = "0.16.3"
