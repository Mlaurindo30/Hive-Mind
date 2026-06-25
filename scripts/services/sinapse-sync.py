#!/usr/bin/env python3
"""CLI de sincronizacao CRDT entre instancias Hive-Mind (P8 CR-SQLite).

Usa o vendor integrations/crsqlite/client.py para exportar e aplicar
changesets crsql_changes entre duas instancias (workstation + laptop +
servidor). Cada instancia tem seu proprio site_id; LWW por coluna
converge apos merge bidirecional.

Uso:
    # Exportar mudancas locais desde versao N (stdout JSON)
    python3 sinapse-sync.py --export --since 0
    python3 sinapse-sync.py --export --since 42 --output changes.json

    # Importar JSON local
    python3 sinapse-sync.py --import changes.json

    # Push: exporta local e POSTa para peer remoto
    python3 sinapse-sync.py --push https://peer.example.com:37702

    # Pull: GET do peer remoto e importa local
    python3 sinapse-sync.py --pull https://peer.example.com:37702

    # Sync bidirecional (push + pull)
    python3 sinapse-sync.py --sync https://peer.example.com:37702

Variaveis de ambiente:
    HIVE_CRDT_SYNC=true          # obrigatorio (hook em core/database.py)
    SINAPSE_HOME=/path/to/hive   # default = diretorio do script
    HIVE_MIND_API_KEY=...        # para --push/--pull autenticacao Bearer

Pre-requisito:
    - install.sh rodou (integrations/crsqlite/<bin> presente)
    - DB migrado: python3 scripts/setup/setup_crdt.py
    - HIVE_CRDT_SYNC=true no .env
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Adiciona raiz do projeto ao sys.path para imports de core/integrations.
# Estrategia: o script vive em scripts/services/, entao o projeto raiz e
# dois niveis acima do __file__. SINAPSE_HOME pode apontar para outro
# local (instalacao real), mas o source/vendor do projeto esta onde
# __file__ indica - isso e o que precisamos para os imports.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))


def _export(since_version: int = 0) -> dict[str, Any]:
    """Exporta mudancas LOCAIS (site_id = proprio) em formato JSON serializavel."""
    import sqlite3
    import sqlite_vec
    from integrations.crsqlite.client import (
        load_crsqlite_extension,
        get_changes_since,
        current_db_version,
        finalize,
    )

    from core.database import DB_PATH
    # timeout=30 (segundos) = busy_timeout de 30s, alinhado com get_connection()
    # — evita "database is locked" sob escrita concorrente (dream cycle/captura).
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    load_crsqlite_extension(conn)
    try:
        # Serializa blobs/bytes como base64 para JSON
        changes_raw = get_changes_since(conn, since_version)
        changes_json = []
        for row in changes_raw:
            changes_json.append([
                _to_json_safe(v) for v in row
            ])
        return {
            "version": current_db_version(conn),
            "site_id_hex": _to_json_safe(conn.execute(
                "SELECT crsql_site_id()"
            ).fetchone()[0]),
            "changes": changes_json,
            "exported_at_unix": _now_unix(),
        }
    finally:
        try:
            finalize(conn)
        except Exception:
            pass
        conn.close()


def _import_changes(payload: dict[str, Any]) -> dict[str, int]:
    """Importa JSON de changes para o DB local aplicando via crsql_changes
    (caminho CRDT canonico do CR-SQLite).

    Delega para integrations.crsqlite.client.apply_changes, que insere em
    crsql_changes e deixa o CR-SQLite resolver o merge LWW por coluna. Isso
    preserva:
      - o pk binario packed do CR-SQLite (decodificar o pk como utf-8 corrompe
        a chave primaria);
      - todas as colunas de cada linha (nao so a de maior col_version);
      - propagacao de UPDATEs em linhas existentes (INSERT OR IGNORE faria
        no-op e perderia a mudanca).

    Performance: ~0.5s para 65k changes, inclusive em DB ja populado
    (medido 2026-06-25). A lentidao de 190s observada antes vinha do truque
    de arquivo temporario do Bloco C, nao desta operacao.
    """
    import sqlite3
    import sqlite_vec
    from integrations.crsqlite.client import (
        load_crsqlite_extension,
        apply_changes,
        finalize,
    )

    from core.database import DB_PATH
    raw = payload.get("changes", [])
    if not raw:
        return {"applied": 0, "received": 0}

    # Desserializa as tuplas crsql_changes (bytes voltam de hex via _from_json_safe).
    changes = [tuple(_from_json_safe(v) for v in row) for row in raw]

    # timeout=30 (segundos) = busy_timeout de 30s, alinhado com get_connection().
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    load_crsqlite_extension(conn)
    try:
        applied = apply_changes(conn, changes)
    finally:
        try:
            finalize(conn)
        except Exception:
            pass
        conn.close()

    return {"applied": applied, "received": len(changes)}


def _push(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Envia payload para {url}/api/v1/sync/import."""
    import urllib.request
    import urllib.error

    target = _join_url(url, "/api/v1/sync/import")
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        target, data=body, method="POST",
        headers=_request_headers(),
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pull(url: str, since_version: int = 0) -> dict[str, Any]:
    """GET {url}/api/v1/sync/export?since=N -> JSON."""
    import urllib.request
    import urllib.error

    target = f"{_join_url(url, '/api/v1/sync/export')}?since={since_version}"
    req = urllib.request.Request(target, headers=_request_headers())
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _sync(url: str, since_version: int = 0) -> dict[str, Any]:
    """Sync bidirecional: pull(remote) + apply + export(local) + push(remote)."""
    print(f"[sync] Pulling from {url} (since v{since_version})...")
    remote = _pull(url, since_version)
    remote_changes = remote.get("changes", [])
    print(f"[sync] Remote sent {len(remote_changes)} changes (v{remote.get('version')})")

    print("[sync] Applying remote changes locally...")
    applied = _import_changes(remote)
    print(f"[sync] Applied {applied['applied']}/{applied['received']}")

    print("[sync] Pushing local changes to remote...")
    local = _export(since_version)
    pushed = _push(url, local)
    print(f"[sync] Remote applied {pushed.get('applied')}/{pushed.get('received')}")

    return {
        "pulled": len(remote_changes),
        "applied_local": applied["applied"],
        "pushed_local": len(local.get("changes", [])),
        "remote_received": pushed.get("applied"),
    }


def _join_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    path = path if path.startswith("/") else "/" + path
    return base + path


def _request_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("HIVE_MIND_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _to_json_safe(value: Any) -> Any:
    """Converte bytes (do CRR) para string hex para JSON."""
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    return value


def _from_json_safe(value: Any) -> Any:
    """Inverso de _to_json_safe: restaura bytes a partir de hex."""
    if isinstance(value, dict) and "__bytes__" in value:
        return bytes.fromhex(value["__bytes__"])
    return value


def _now_unix() -> int:
    import time
    return int(time.time())


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--export", action="store_true",
                    help="Exporta mudancas LOCAIS como JSON")
    ap.add_argument("--import", dest="import_file", metavar="FILE",
                    help="Importa JSON de mudancas para DB local")
    ap.add_argument("--since", type=int, default=0,
                    help="Versao minima (default: 0 = todas)")
    ap.add_argument("--output", "-o", metavar="FILE",
                    help="Arquivo de saida (default: stdout)")
    ap.add_argument("--push", metavar="URL",
                    help="Exporta local + POSTa para <URL>/api/v1/sync/import")
    ap.add_argument("--pull", metavar="URL",
                    help="GET <URL>/api/v1/sync/export?since=N + importa local")
    ap.add_argument("--sync", metavar="URL",
                    help="Sync bidirecional (pull + push) com <URL>")
    args = ap.parse_args()

    # Gate: toda ação real depende de schema CRR migrado. Sem HIVE_CRDT_SYNC=true
    # o DB nao tem crsql_changes e a falha seria um OperationalError cru lá no
    # fundo de get_changes_since. Falha cedo com mensagem acionável.
    _wants_action = any((args.sync, args.push, args.pull, args.export, args.import_file))
    if _wants_action and os.environ.get("HIVE_CRDT_SYNC", "").lower() != "true":
        print(
            "[erro] HIVE_CRDT_SYNC != true. Este DB pode não estar migrado para CRR.\n"
            "       Defina HIVE_CRDT_SYNC=true (e rode scripts/setup/setup_crdt.py "
            "se ainda não migrou) antes de sincronizar.",
            file=sys.stderr,
        )
        return 1

    # Despacho
    if args.sync:
        result = _sync(args.sync, args.since)
    elif args.push:
        payload = _export(args.since)
        result = _push(args.push, payload)
        result["pushed_changes"] = len(payload.get("changes", []))
        result["local_version"] = payload.get("version")
    elif args.pull:
        payload = _pull(args.pull, args.since)
        result = _import_changes(payload)
        result["remote_version"] = payload.get("version")
    elif args.export:
        result = _export(args.since)
    elif args.import_file:
        with open(args.import_file) as f:
            payload = json.load(f)
        result = _import_changes(payload)
    else:
        ap.print_help()
        return 0

    # Saida
    output = json.dumps(result, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(output + "\n")
        print(f"[ok] escrito em {args.output}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
