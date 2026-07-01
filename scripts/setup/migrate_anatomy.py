#!/usr/bin/env python3
"""
migrate_anatomy.py — Fase 0: reorganiza cerebro/ para o MODELO ANATÔMICO.

SEM perda de memória: backup completo + dry-run por DEFAULT + rollback gerado.

Move neurônios (atlas → cortex/temporal/{projeto}/{topico}/neuronio-*), renomeia
fact→neuronio, atualiza hive_mind.db (neurons.source_file), e reorganiza as demais
regiões do cérebro. Os facts existentes não têm `project` no frontmatter, então
recebem o default (Hive-Mind) — todos são sobre construir este sistema.

Uso:
  python scripts/migrate_anatomy.py            # DRY-RUN (só mostra o plano)
  python scripts/migrate_anatomy.py --apply    # executa (com backup + rollback)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core import paths as P  # noqa: E402

VAULT = P.VAULT_ROOT
DB = P.SINAPSE_HOME / "hive_mind.db"
DEFAULT_PROJECT = "Hive-Mind"

# Esqueleto anatômico a garantir (mkdir)
SKELETON = [
    P.TEMPORAL, P.HIPOCAMPO, P.ARQUIVO, P.TEMPORAL_GLOBAL,
    P.FRONTAL, P.DECISIONS_ROOT, P.PROJECTS_ROOT, P.WORK_ROOT, P.WORK_ACTIVE,
    P.PARIETAL, P.INBOX_ROOT, P.REFERENCES_ROOT,
    P.OCCIPITAL, P.CAPTURAS_VISUAIS, P.GRAFO_ROOT,
    P.INSULA, P.SAUDE_ROOT, P.CONFLICTS_ROOT,
    P.DIENCEFALO, P.SECTORS_ROOT, P.ROTEAMENTO_ROOT,
    P.CEREBELO, P.DAILY_ROOT, P.SESSIONS_ROOT, P.WEEKLY_ROOT, P.PADROES_ROOT,
    P.TRONCO, P.META_ROOT, P.MODELOS_ROOT, P.PAINEIS_ROOT,
]

# Movimentos de pasta inteira (origem relativa a cerebro → destino absoluto)
# NOTA: graphify-out NÃO é movido — é build regenerável; o grafo passa a ser
# escrito em occipital/grafo pela config do graphify (sem mover artefatos antigos).
FOLDER_MOVES = {
    "conflicts": P.CONFLICTS_ROOT,        # insula/conflitos
    "inbox": P.INBOX_ROOT,                # parietal/inbox
    "reference": P.REFERENCES_ROOT,       # parietal/referencias
    "templates": P.MODELOS_ROOT,          # tronco/modelos
    "bases": P.PAINEIS_ROOT,              # tronco/paineis
    "work": P.WORK_ROOT,                  # frontal/trabalho
    "org": P.FRONTAL / "org",             # frontal (pessoas/times)
    "thinking": P.FRONTAL / "rascunhos",  # frontal (pensamento)
    "atoms": P.TEMPORAL / DEFAULT_PROJECT / "atoms",   # merge no store de neurônios
    "hive mind": P.META_ROOT / "hive-mind",            # tronco/meta
}


def plan_neuron_moves() -> list[tuple[Path, Path]]:
    """atlas/{topic}/**/*.md → cortex/temporal/{projeto}/{topico}/neuronio-*.md.
    atlas/visual/* → occipital/capturas-visuais/."""
    moves: list[tuple[Path, Path]] = []
    atlas = VAULT / "atlas"
    if not atlas.exists():
        return moves
    for item in sorted(atlas.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(atlas)          # {topic}/.../{file}
        topic = rel.parts[0]
        if topic == "visual":                  # capturas visuais → occipital
            dest = P.CAPTURAS_VISUAIS / Path(*rel.parts[1:])
        else:
            name = item.name
            new_name = name.replace("fact-", "neuronio-", 1) if name.startswith("fact-") else name
            sub = Path(*rel.parts[1:-1]) if len(rel.parts) > 2 else Path()
            dest = P.TEMPORAL / DEFAULT_PROJECT / topic / sub / new_name
        moves.append((item, dest))
    return moves


def plan_brain_moves() -> list[tuple[Path, Path]]:
    """brain/Patterns.md → cerebelo/padroes/; resto de brain/ → frontal/brain/."""
    moves = []
    brain = VAULT / "brain"
    if not brain.exists():
        return moves
    for item in sorted(brain.rglob("*")):
        if not item.is_file():
            continue
        if item.name.lower().startswith("patterns"):
            dest = P.PADROES_ROOT / item.name
        else:
            dest = P.FRONTAL / "brain" / item.relative_to(brain)
        moves.append((item, dest))
    return moves


def plan_folder_moves() -> list[tuple[Path, Path]]:
    moves = []
    for src_name, dest_root in FOLDER_MOVES.items():
        src = VAULT / src_name
        if not src.exists():
            continue
        for item in sorted(src.rglob("*")):
            if item.is_file():
                moves.append((item, dest_root / item.relative_to(src)))
    return moves


def all_moves() -> list[tuple[Path, Path]]:
    return plan_neuron_moves() + plan_brain_moves() + plan_folder_moves()


def db_remap(moves: list[tuple[Path, Path]]) -> list[tuple[str, str]]:
    """Mapa (old_rel, new_rel) relativo a cerebro/ para atualizar neurons.source_file."""
    out = []
    for src, dest in moves:
        try:
            old_rel = str(src.relative_to(VAULT))
            new_rel = str(dest.relative_to(VAULT))
            out.append((old_rel, new_rel))
        except ValueError:
            pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="executa (default: dry-run)")
    args = ap.parse_args()

    moves = all_moves()
    print(f"=== Plano de migração anatômica ({len(moves)} arquivos) ===\n")
    by_dest = {}
    for src, dest in moves:
        key = str(dest.parent.relative_to(VAULT))
        by_dest[key] = by_dest.get(key, 0) + 1
    for k, n in sorted(by_dest.items()):
        print(f"  {n:4d} → cerebro/{k}/")
    print(f"\n  SQLite neurons.source_file a atualizar: {len(db_remap(moves))} mapeamentos")
    print(f"  Esqueleto a criar: {len(SKELETON)} pastas")

    if not args.apply:
        print("\n[DRY-RUN] nada foi movido. Rode com --apply para executar (com backup).")
        # mostra 10 exemplos
        print("\nExemplos:")
        for src, dest in moves[:10]:
            print(f"  {src.relative_to(VAULT)}  →  {dest.relative_to(VAULT)}")
        return 0

    # ===== APPLY =====
    ts = time.strftime("%Y%m%dT%H%M%S")
    backup_dir = P.SINAPSE_HOME / "backups" / f"anatomy-migration-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[1/5] Backup → {backup_dir}")
    shutil.copytree(VAULT, backup_dir / "cerebro", dirs_exist_ok=True)
    if DB.exists():
        shutil.copy2(DB, backup_dir / "hive_mind.db")

    print("[2/5] Criando esqueleto anatômico…")
    for d in SKELETON:
        d.mkdir(parents=True, exist_ok=True)

    print(f"[3/5] Movendo {len(moves)} arquivos…")
    rollback = []
    for src, dest in moves:
        if not src.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        rollback.append((str(dest), str(src)))

    print("[4/5] Atualizando hive_mind.db (source_file)…")
    remap = dict(db_remap(moves))
    n_db = 0
    if DB.exists():
        con = sqlite3.connect(DB)
        con.execute("PRAGMA busy_timeout=10000")
        for old_rel, new_rel in remap.items():
            cur = con.execute(
                "UPDATE neurons SET source_file=? WHERE source_file=?", (new_rel, old_rel))
            n_db += cur.rowcount
        con.commit()
        con.close()
    print(f"      {n_db} linhas de neuron atualizadas")

    print("[5/5] Gravando rollback…")
    (backup_dir / "rollback.json").write_text(json.dumps({
        "file_moves": rollback,
        "db_remap": {v: k for k, v in remap.items()},
        "backup": str(backup_dir),
    }, indent=2))

    print(f"\n✓ Migração concluída. Backup + rollback em {backup_dir}")
    print("  Verifique e rode `graphify update cerebro/` para reindexar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
