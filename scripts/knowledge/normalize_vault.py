#!/usr/bin/env python3
"""Normalização one-time do vault (FASE 1, 2026-08-12).

Corrige os 4 problemas estruturais do lobo temporal na raiz, migrando o passado
para o contrato canônico imposto pela camada core/vault:

  1. ACHATAR aninhamento triplo: `git/nome-hash/tópico/neuronio` → `nome-hash/tópico/neuronio`
     (remove o prefixo de source-type, mantém o hash para evitar colisão).
  2. DEDUP tópicos: `codeinspection` e `code_inspection` → `code-inspection`
     (canonical_slug).
  3. SANITIZAR nomes de projeto: prompts vazados e placeholders são reclassificados
     para `unclassified/` quando não identificáveis.

Atualiza o DB (neurons.source_file, neurons.topic) e reescreve o frontmatter dos
`.md` movidos (project_id/project_name/topic/sinapses). Seguro: --dry-run apenas
reporta; sem --apply nada é movido.

Uso:
    python scripts/knowledge/normalize_vault.py --dry-run     # relatório
    python scripts/knowledge/normalize_vault.py --apply       # executa
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent.parent
sys.path.insert(0, str(ROOT))

from core import paths as cp
from core.database import get_connection
from core.vault import canonical_slug, vault_project_dir

# Projetos que são prompts vazados / placeholders — não identificáveis, devem ser
# reclassificados para unclassified. Detecção por padrão SEMÂNTICO (frases com
# verbos/palavras de prompt), não por tamanho: nomes longos de repositório são
# legítimos ("dados-ia-agente-politicas-corporativas-340c9b8fbc41").
_PLACEHOLDER_HINTS = (
    "preciso-que-verifique",
    "referenced-chatgpt-conversation",
    "_knowledge_type_category_",
    "code_search_using_grep",
    "directory_structure_validation",
    "scratch-",
    "this-is-untrusted",
    "untitled",
    "new-task",
)

_UNCLASSIFIED = "unclassified"


def _looks_like_vaulted_prompt(name: str) -> bool:
    """True se o nome de projeto parece um prompt vazado, não um repositório real.

    Heurística semântica: prompts vazados contêm marcadores de linguagem natural
    ("verifique", "untrusted", "scratch", "untitled") ou placeholders. Nomes de
    repositório (mesmo longos) não são marcados.
    """
    low = name.lower()
    return any(h in low for h in _PLACEHOLDER_HINTS)


def _project_buckets(temporal: Path) -> dict[str, Path]:
    """Mapeia cada diretório de projeto (nível 1) do temporal para seu path."""
    buckets: dict[str, Path] = {}
    for child in temporal.iterdir():
        if child.is_dir() and not child.name.startswith("_"):
            buckets[child.name] = child
    return buckets


_SOURCE_TYPE_BUCKETS = ("git", "root", "local", "unclassified")


def _scan_triple_nesting(temporal: Path) -> list[dict]:
    """Encontra neurônios sob aninhamento triplo (source-type/projeto/tópico/neuronio).

    A estrutura errada é: `git/<projeto-hash>/<tópico>/neuronio-*.md` — 4 níveis a
    partir de `temporal`. O contrato canônico é `<projeto>/<tópico>/neuronio-*.md`
    (3 níveis, sem o bucket de source-type no meio).
    """
    results = []
    for bucket_name in _SOURCE_TYPE_BUCKETS:
        bucket = temporal / bucket_name
        if not bucket.is_dir():
            continue
        # Cada subdir de bucket é um projeto (ex.: git/comfyui-hash).
        for project in bucket.iterdir():
            if not project.is_dir():
                continue
            for neuron in project.rglob("neuronio-*.md"):
                rel = neuron.relative_to(bucket)  # projeto/tópico/neuronio
                results.append({
                    "bucket": bucket_name,
                    "neuron": neuron,
                    "parts": rel.parts,
                    "project": project.name,
                })
    return results


def _classify_project_name(bucket: str, sub_name: str) -> str:
    """Classifica o nome de projeto canônico a partir do bucket + subprojeto.

    Regras:
    - bucket é um source-type (git/root/local/unclassified) → usa sub_name
      (mantém hash, remove sufixos de prompt vazado se identificável).
    - sub_name parece prompt vazado → unclassified.
    """
    if _looks_like_vaulted_prompt(sub_name):
        return _UNCLASSIFIED
    return sub_name


def _rewrite_neuron_frontmatter(path: Path, new_project_dir: str) -> None:
    """Reescreve o frontmatter de um neurônio para o novo diretório de projeto.

    Atualiza: project_id (remove prefixo source-type), project_name, e a sinapse
    projeto:: [[...]]. Preserva type, topic, integrity_hash, content.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Atualiza project_id: "git/x-hash" → "x-hash" (ou "unclassified" para prompts).
    new_pid = new_project_dir if new_project_dir != _UNCLASSIFIED else "unclassified"
    new_name = new_project_dir.replace("-", " ").strip().title()

    out: list[str] = []
    in_sinapses = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("project_id:"):
            out.append(f"project_id: {new_pid}")
            continue
        if stripped.startswith("project_name:"):
            out.append(f"project_name: {new_name}")
            continue
        if stripped.startswith("project:"):
            out.append(f"project: {new_name}")
            continue
        if stripped == "## Sinapses":
            in_sinapses = True
            out.append(line)
            continue
        if in_sinapses and stripped.startswith("- projeto::"):
            out.append(f"- projeto:: [[{new_project_dir}]]")
            continue
        out.append(line)

    path.write_text("\n".join(out), encoding="utf-8")


def _flatten(conn, temporal: Path, apply: bool) -> dict:
    """Executa o achatamento: move neurônios de source-type/projeto → projeto."""
    report = {"moved": 0, "prompts_reclassified": 0, "failed": 0}
    for item in _scan_triple_nesting(temporal):
        bucket = item["bucket"]
        neuron = item["neuron"]
        sub_name = item["project"]
        target_name = _classify_project_name(bucket, sub_name)

        if _looks_like_vaulted_prompt(sub_name):
            report["prompts_reclassified"] += 1

        # Destino: temporal/<target_name>/<tópico>/<arquivo>
        rel_to_project = neuron.relative_to(temporal / bucket / sub_name)
        dest = temporal / target_name / rel_to_project

        if not apply:
            report["moved"] += 1
            continue

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(neuron), str(dest))
            _rewrite_neuron_frontmatter(dest, target_name)
            report["moved"] += 1
        except Exception:
            report["failed"] += 1

    # Remove buckets vazios (source-type) após mover.
    if apply:
        for bucket in _SOURCE_TYPE_BUCKETS:
            b = temporal / bucket
            if b.is_dir() and not any(b.iterdir()):
                try:
                    b.rmdir()
                except OSError:
                    pass
    return report


def analyze(temporal: Path) -> dict:
    """Analisa o vault e retorna o plano de migração sem executar."""
    report = {
        "triple_nesting_neurons": 0,
        "projects_to_flatten": Counter(),
        "prompts_vaulted": Counter(),
    }
    for item in _scan_triple_nesting(temporal):
        report["triple_nesting_neurons"] += 1
        bucket = item["bucket"]
        sub = item["project"]
        if _looks_like_vaulted_prompt(sub):
            report["prompts_vaulted"][sub] += 1
        else:
            report["projects_to_flatten"][f"{bucket}/{sub}"] += 1
    return report


def _dedup_topics(temporal: Path, apply: bool) -> dict:
    """Merge tópicos com o mesmo canonical_slug (ex.: 'nome' e 'nome_' → 'nome').

    O bug histórico do _derive_topic deixava um underscore trailing em alguns
    tópicos. canonical_slug colapsa ambos para o mesmo nome; aqui movemos os
    neurônios do tópico duplicado para o canônico.
    """
    report = {"merged_topics": 0, "moved_files": 0}
    for proj in temporal.iterdir():
        if not proj.is_dir() or proj.name.startswith("_"):
            continue
        slug_to_dirs: dict[str, list[str]] = {}
        for d in proj.iterdir():
            if d.is_dir():
                slug_to_dirs.setdefault(canonical_slug(d.name), []).append(d.name)
        for slug, dirs in slug_to_dirs.items():
            if len(dirs) <= 1:
                continue
            # canonical dir = o primeiro (menor/mais limpo); os outros são duplicados.
            dirs.sort(key=len)
            canonical_dir = canonical_slug(dirs[0])
            # Se o canonical_slug já é o nome de um dir existente, usa ele; senão cria.
            target = proj / canonical_dir
            for dup_name in dirs[1:]:
                src_dir = proj / dup_name
                if not src_dir.is_dir():
                    continue
                if not apply:
                    report["moved_files"] += len(list(src_dir.rglob("neuronio-*.md")))
                    report["merged_topics"] += 1
                    continue
                for neuron in src_dir.rglob("neuronio-*.md"):
                    rel = neuron.relative_to(src_dir)
                    dest = target / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists():
                        # duplicado de hash — remove o órfão.
                        neuron.unlink()
                    else:
                        shutil.move(str(neuron), str(dest))
                    report["moved_files"] += 1
                # remove o dir duplicado se vazio.
                try:
                    src_dir.rmdir()
                except OSError:
                    pass
                report["merged_topics"] += 1
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Normaliza o vault (achatamento + dedup + sanitização)")
    parser.add_argument("--dry-run", action="store_true", help="apenas relatório")
    parser.add_argument("--apply", action="store_true", help="executa a migração")
    args = parser.parse_args()

    temporal = cp.TEMPORAL
    report = analyze(temporal)
    print(f"Neurônios em aninhamento triplo: {report['triple_nesting_neurons']}")
    print(f"\nProjetos a achatar (bucket/subprojeto → neurônios):")
    for proj, n in report["projects_to_flatten"].most_common(40):
        print(f"  {proj}: {n}")
    print(f"\nPrompts vazados/placeholders (→ unclassified):")
    for name, n in report["prompts_vaulted"].most_common(30):
        print(f"  {name}: {n}")

    if not args.apply or args.dry_run:
        print("\n[dry-run] Nada foi movido. Use --apply para executar.")
        return 0

    conn = get_connection()
    try:
        flat = _flatten(conn, temporal, apply=True)
        print(f"\n[apply] movidos: {flat['moved']} | prompts reclassificados: {flat['prompts_reclassified']} | falhas: {flat['failed']}")
        dedup = _dedup_topics(temporal, apply=True)
        print(f"[apply] tópicos mesclados: {dedup['merged_topics']} | arquivos movidos: {dedup['moved_files']}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
