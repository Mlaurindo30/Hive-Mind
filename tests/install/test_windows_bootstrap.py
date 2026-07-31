"""Pytest contracts for the native Windows bootstrap owners."""
from __future__ import annotations
import sqlite3
from pathlib import Path
from hive_mind.install.fullstack_readiness import test_fullstack_readiness as fullstack_readiness
from hive_mind.install.snapshot import create_install_snapshot
from hive_mind.install.windows_prereqs import get_prerequisites, invoke_prerequisite_bootstrap
ROOT=Path(__file__).resolve().parents[2]
def test_local_full_rejects_unavailable_required_services():
 result=fullstack_readiness(root=ROOT,profile='local-full',probe=lambda _name:False)
 assert not result.ready and 'docker-desktop' in result.missing
def test_prerequisite_dry_run_exposes_requirements():
 result=invoke_prerequisite_bootstrap(root=ROOT,profile='local-full',dry_run=True); names={item.name:item for item in get_prerequisites('local-full')}
 assert not result.restart_required and result.missing is not None and names['WSL 2'].required and names['Visual Studio Build Tools'].required
def test_python_snapshot_preserves_vault_database_and_env(tmp_path):
 (tmp_path/'cerebro/cortex').mkdir(parents=True); (tmp_path/'.env').write_text('TEST_KEY=value\n',encoding='utf-8'); (tmp_path/'cerebro/cortex/note.md').write_text('preserve me',encoding='utf-8'); db=tmp_path/'hive_mind.db'; conn=sqlite3.connect(db); conn.execute('create table fixture (id integer primary key)'); conn.commit(); conn.close()
 snapshot=create_install_snapshot(root=tmp_path,output_root=tmp_path/'backups')
 assert snapshot.manifest_path.is_file() and snapshot.database_backup_path.is_file() and (snapshot.snapshot_path/'.env').is_file() and (snapshot.snapshot_path/'cerebro/cortex/note.md').is_file()
