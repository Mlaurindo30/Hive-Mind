#!/usr/bin/env python3
"""Sanear o vault do cerebro (decisão do arquiteto squad 04, 2026-08-13).

Ordem: D (mojibake) → C (dedup tópicos) → B (merge variantes projeto) → A (hash-puro).

Decisões arquiteturais:
- A: diretórios local/<hash> → `local-<hash>` (mantém identidade, corrige vault_project_dir).
- B: variantes do mesmo projeto mescladas no nome base; origem preservada em origin_project_id.
- C: dedup de tópicos por canonical_slug; overwrite PROIBIDO; colisão de hash8 → sufixo numérico.
- D: mojibake dupla-codificação via cp1252→utf-8, idempotente (guarda de detecção).

Uso:
    python scripts/knowledge/sanitize_vault.py --dry-run   # relatório
    python scripts/knowledge/sanitize_vault.py --apply      # executa
    python scripts/knowledge/sanitize_vault.py --apply --step mojibake   # um passo
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent.parent
sys.path.insert(0, str(ROOT))

from core import paths as cp  # noqa: E402
from core.vault import canonical_slug  # noqa: E402

T = cp.TEMPORAL

# Variantes conhecidas do mesmo projeto. A CHAVE é o nome base (humano);
# todos os valores (incluindo a chave se existir como dir) mesclam na chave.
MERGE_GROUPS: dict[str, list[str]] = {
    "antigravity": ["antigravity", "antigravity-0a5e3bdd7481", "antigravity-cli-b320451c22cc"],
    "omniroute": ["omniroute", "omniroute-55c65437f06b", "omniroute-78e4d85b91c8"],
    "ComfyUI": ["ComfyUI", "comfyui-b93885334cac"],
    "ins": ["ins", "ins-66d91c0962fe"],
}


def _is_mojibake(text: str) -> bool:
    """Detecta dupla-codificação UTF-8: "Ã" (U+00C3) seguido de byte alto (Ã©, Ã£, Ã§...)."""
    return bool(re.search(r"Ã[^\x00-\x7f]", text))


# Pares mojibake comuns (dupla-codificação UTF-8→cp1252→UTF-8). O par "Ãx" (U+00C3
# + byte alto) corresponde ao caractere acentuado original.
_MOJIBAKE_MAP = {
    "Ã¡": "á", "Ã©": "é", "Ã­": "í", "Ã³": "ó", "Ãº": "ú", "Ã¼": "ü",
    "Ã£": "ã", "Ãµ": "õ", "Ã±": "ñ", "Ã§": "ç", "Ãª": "ê", "Ã´": "ó",
    "Ã¢": "â", "Ã‰": "É", "Ã“": "Ó", "Ã‡": "Ç", "Ã\u00a0": "à",
}


def _fix_mojibake(path: Path, apply: bool) -> bool:
    """Corrige mojibake SEQUENCIAL (só os pares Ã+byte, preservando UTF-8 correto).

    A correção integral (encode cp1252→decode utf-8) quebra em arquivos com
    mistura de mojibake e UTF-8 correto. A correção seletiva substitui apenas
    os pares conhecidos, mantendo o resto intocado.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if not _is_mojibake(text):
        return False
    fixed = text
    for bad, good in _MOJIBAKE_MAP.items():
        fixed = fixed.replace(bad, good)
    if fixed == text:
        return False
    if not apply:
        return True
    path.write_text(fixed, encoding="utf-8")
    return True


def step_mojibake(apply: bool) -> int:
    fixed = 0
    for p in T.rglob("*.md"):
        if _fix_mojibake(p, apply):
            fixed += 1
    # também brain/Current State.md e frontal/decisoes
    for extra in [cp.CURRENT_STATE, cp.DECISIONS_ROOT]:
        if extra and extra.exists():
            for p in extra.rglob("*.md"):
                if _fix_mojibake(p, apply):
                    fixed += 1
    print(f"[mojibake] {fixed} arquivos com dupla-codificação corrigidos" if apply
          else f"[mojibake] {fixed} arquivos detectados (dry-run)")
    return fixed


def step_dedup_topics(apply: bool) -> dict:
    """Merge tópicos por canonical_slug. Overwrite proibido; colisão hash8 → sufixo."""
    merged = 0
    moved = 0
    for proj in T.iterdir():
        if not proj.is_dir() or proj.name.startswith("_"):
            continue
        slug_to_dirs: dict[str, list[str]] = {}
        for d in proj.iterdir():
            if d.is_dir():
                slug_to_dirs.setdefault(canonical_slug(d.name), []).append(d.name)
        for slug, dirs in slug_to_dirs.items():
            if len(dirs) <= 1:
                continue
            dirs.sort(key=len)
            target = proj / canonical_slug(dirs[0])
            for dup_name in dirs[1:]:
                src_dir = proj / dup_name
                if not src_dir.is_dir():
                    continue
                if not apply:
                    moved += len(list(src_dir.rglob("neuronio-*.md")))
                    merged += 1
                    continue
                for neuron in src_dir.rglob("neuronio-*.md"):
                    rel = neuron.relative_to(src_dir)
                    dest = target / rel
                    if dest.exists():
                        # colisão de nome → sufixo numérico, NUNCA overwrite
                        stem, ext = dest.stem, dest.suffix
                        k = 1
                        while dest.exists():
                            dest = target / f"{stem}-{k}{ext}"
                            k += 1
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(neuron), str(dest))
                    moved += 1
                try:
                    src_dir.rmdir()
                except OSError:
                    pass
                merged += 1
    print(f"[dedup] {merged} tópicos mesclados, {moved} arquivos movidos")
    return {"merged": merged, "moved": moved}


def step_merge_projects(apply: bool) -> dict:
    """Mescla variantes do mesmo projeto no nome base."""
    merged = 0
    moved = 0
    for base, variants in MERGE_GROUPS.items():
        target = T / base
        for variant in variants[1:]:  # skip o primeiro (é o base)
            src = T / variant
            if not src.is_dir():
                continue
            if not apply:
                moved += len(list(src.rglob("neuronio-*.md")))
                merged += 1
                continue
            for neuron in src.rglob("neuronio-*.md"):
                rel = neuron.relative_to(src)
                dest = target / rel
                if dest.exists():
                    stem, ext = dest.stem, dest.suffix
                    k = 1
                    while dest.exists():
                        dest = target / f"{stem}-{k}{ext}"
                        k += 1
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(neuron), str(dest))
                moved += 1
            # limpa dirs vazios
            for d in sorted(src.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            if not any(src.iterdir()):
                src.rmdir()
            merged += 1
    print(f"[merge] {merged} variantes mescladas, {moved} arquivos movidos")
    return {"merged": merged, "moved": moved}


def step_hash_pure(apply: bool) -> int:
    """Move diretórios hash-puro para unclassified/<tópico>/ (workspace sem projeto).

    Observação do usuário (2026-08-13): hash-puro (`local/<hash>`) e `unclassified`
    são o MESMO fenômeno — agente aberto na área de trabalho SEM projeto (sem .git).
    O bucket canônico é `unclassified`. Move os neurônios para `unclassified/<tópico>/`
    mantendo o contrato de 3 níveis (projeto/tópico/neuronio).
    """
    renamed = 0
    hash_re = re.compile(r"^[0-9a-f]{8,32}$")
    dest_root = T / "unclassified"
    for proj in T.iterdir():
        if not proj.is_dir():
            continue
        if not hash_re.match(proj.name):
            continue
        if not apply:
            renamed += 1
            continue
        dest_root.mkdir(parents=True, exist_ok=True)
        for neuron in proj.rglob("neuronio-*.md"):
            # rel = <tópico>/neuronio-*.md (o hash-puro já tem 2 níveis internos)
            rel = neuron.relative_to(proj)
            if len(rel.parts) == 1:
                # neurônio solto (sem tópico) → general/
                d2 = dest_root / "general" / rel.name
            else:
                d2 = dest_root / rel
            d2.parent.mkdir(parents=True, exist_ok=True)
            if d2.exists():
                stem, ext = d2.stem, d2.suffix
                k = 1
                while d2.exists():
                    d2 = dest_root / rel.parent / f"{stem}-{k}{ext}"
                    k += 1
            shutil.move(str(neuron), str(d2))
        shutil.rmtree(proj, ignore_errors=True)
        renamed += 1
    print(f"[hash-puro] {renamed} diretórios movidos para unclassified/")
    return renamed


def main() -> int:
    ap = argparse.ArgumentParser(description="Sanear o vault (mojibake→dedup→merge→hash)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--step", choices=["mojibake", "dedup", "merge", "hash"], default=None)
    args = ap.parse_args()
    apply = args.apply

    steps = [args.step] if args.step else ["mojibake", "dedup", "merge", "hash"]
    for s in steps:
        if s == "mojibake":
            step_mojibake(apply)
        elif s == "dedup":
            step_dedup_topics(apply)
        elif s == "merge":
            step_merge_projects(apply)
        elif s == "hash":
            step_hash_pure(apply)

    if not apply:
        print("\n[dry-run] use --apply para executar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
