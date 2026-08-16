#!/usr/bin/env python3
"""
scripts/conflict_detector.py — Detecção de contradições (Memória Viva F4.4).

Acha pares de neurônios semanticamente próximos (fastembed) e usa o LLM (papel
'conflict_detector') para julgar se de fato se contradizem. Lista os conflitos em
cortex/insula/conflitos/{data}.md para revisão humana. READ-ONLY nos neurônios.

Boundedness: cap de pares candidatos por execução. Default = LOG-ONLY; --apply escreve.
Funções recebem embed_fn/llm_fn injetáveis (testável sem rede/modelo). load_env só na
execução (R3).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from core.paths import CONFLICTS_ROOT, TEMPORAL  # noqa: E402
from core.knowledge.intake import KnowledgeCandidate, build_candidate  # noqa: E402
from core.schemas.conflict_models import ConflictJudgement  # noqa: E402
from scripts.knowledge.drift_detector import scan_neuronios  # noqa: E402

SIM_THRESHOLD = float(os.environ.get("HIVE_CONFLICT_THRESHOLD", "0.82"))
MAX_PAIRS = int(os.environ.get("HIVE_MAX_CONFLICT_PAIRS", "50"))


def _text(n: dict) -> str:
    import re
    body = n.get("body", "")
    title = ""
    m = re.search(r"^# (.+)$", body, re.MULTILINE)
    if m:
        title = m.group(1)
    return f"{title}\n{body}"[:600]


def _default_embed(texts: list[str]):
    from fastembed import TextEmbedding
    import numpy as np
    model = TextEmbedding()
    embs = [e / (np.linalg.norm(e) + 1e-9) for e in model.embed(texts)]
    return embs


def _embed_single(text: str):
    """F3-otimização: embeda UMA nota (reusa o embedder do core, não o fastembed)."""
    from core.indexing import get_embedder
    embedder = get_embedder()
    vec = list(embedder.embed([text[:600]]))[0]
    import numpy as np
    return [float(x) for x in vec / (np.linalg.norm(vec) + 1e-9)]


def find_candidate_pairs(neurons: list[dict], *, threshold: float = SIM_THRESHOLD,
                         cap: int = MAX_PAIRS, embed_fn: Optional[Callable] = None) -> list[tuple]:
    """F3-otimização (2026-08-13): pares via índice vetorial do DB, SEM re-embedding.

    O gargalo anterior era duplo: (1) O(n²) comparação e (2) `_embed_single`
    chamando o Ollama para CADA um dos 90k neurônios. Ambos eliminados:

      - `embed_fn` injetado (testes): caminho O(n²) original, corpus pequeno.
      - produção: consulta o índice `search_vec` (vec0 KNN, já populado com os
        57k vetores 1024d) para os vizinhos mais próximos de cada neurônio,
        usando o PRÓPRIO vetor do neurônio como query (recuperado do search_vec,
        não re-embeddado). Complexidade ~O(n·k·log n), zero chamadas de embedding.
    """
    if len(neurons) < 2:
        return []

    # Caminho de teste (embed_fn injetado) — comportamento original, corpus pequeno.
    if embed_fn is not None:
        embs = embed_fn([_text(n) for n in neurons])
        pairs = []
        for i in range(len(neurons)):
            for j in range(i + 1, len(neurons)):
                sim = float(sum(a * b for a, b in zip(embs[i], embs[j])))
                if sim >= threshold:
                    pairs.append((i, j, sim))
        pairs.sort(key=lambda x: -x[2])
        return pairs[:cap]

    # Produção: KNN via vec0 no search_vec (sem re-embedding).
    from core.database import get_connection, serialize_f32
    conn = get_connection()
    try:
        # O search_vec indexa por neurons.id (k3-* / MOC), NÃO pelo path.stem
        # do arquivo. O scan_neuronios retorna `path`; o id canônico está em
        # `data.integrity_hash` ou derivado. Mapeamos via source_file → id:
        # construímos id→índice a partir do DB (neurons.id ↔ source_file stem).
        import re
        id_to_index: dict[str, int] = {}
        for i, n in enumerate(neurons):
            # candidatos de id: neurons do DB têm id; aqui usamos o hash do
            # frontmatter (integrity_hash) como chave estável compartilhada.
            h = (n.get("data") or {}).get("integrity_hash")
            if h:
                id_to_index[str(h)[:16]] = i
        # Mapeia search_vec.neuron_id → índice, via hash no id k3-*.
        # O id k3-fact-{hash16} contém o hash nos últimos 16 chars.
        id_to_index.clear()
        for i, n in enumerate(neurons):
            stem = n["path"].stem
            # hash_short são os últimos 8 chars do stem (neuronio-{slug}-{hash8})
            m = re.search(r"-([0-9a-f]{8})$", stem)
            if m:
                id_to_index[m.group(1)] = i

        seen: set[tuple[int, int]] = set()
        pairs: list[tuple] = []
        K = 8

        # Itera os VETORES diretamente (não os arquivos): cada row do search_vec
        # é um neurônio indexado; para cada um, busca vizinhos.
        all_vec_ids = [r["neuron_id"] for r in conn.execute("SELECT neuron_id FROM search_vec").fetchall()]
        # hash_short → neuron_id (id completo) para resolução
        hash_to_id: dict[str, str] = {}
        for nid in all_vec_ids:
            m = re.search(r"([0-9a-f]{8})$", nid)
            if m:
                hash_to_id.setdefault(m.group(1), nid)

        # Para cada neurônio do scan com hash resolvível, busca vizinhos.
        for i, n in enumerate(neurons):
            stem = n["path"].stem
            m = re.search(r"-([0-9a-f]{8})$", stem)
            if not m:
                continue
            h8 = m.group(1)
            nid = hash_to_id.get(h8)
            if nid is None:
                continue
            row = conn.execute(
                "SELECT vec_to_json(embedding) AS v FROM search_vec WHERE neuron_id = ?",
                (nid,),
            ).fetchone()
            if row is None:
                continue
            import json
            import numpy as np
            vec = json.loads(row["v"])
            norm = np.linalg.norm(vec) + 1e-9
            q = [float(x / norm) for x in vec]

            neighbors = conn.execute(
                "SELECT neuron_id, distance AS d FROM search_vec "
                "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                (serialize_f32(q), K),
            ).fetchall()
            for nb in neighbors:
                # resolve o vizinho de volta ao índice do scan pelo hash8
                m2 = re.search(r"([0-9a-f]{8})$", nb["neuron_id"])
                if not m2:
                    continue
                j = id_to_index.get(m2.group(1))
                if j is None or j == i:
                    continue
                key = (min(i, j), max(i, j))
                if key in seen:
                    continue
                seen.add(key)
                sim = 1.0 / (1.0 + float(nb["d"]))
                if sim >= threshold * 0.5:
                    pairs.append((i, j, sim))
        conn.close()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return []

    pairs.sort(key=lambda x: -x[2])
    return pairs[:cap]


def _default_judge(a: dict, b: dict) -> ConflictJudgement:
    from core.auth import load_env
    from core.llm_client import call_llm_with_fallback
    load_env()
    return call_llm_with_fallback(
        role="conflict_detector",
        prompt=f"NOTA A:\n{_text(a)}\n\nNOTA B:\n{_text(b)}\n\nElas se contradizem?",
        system_prompt="Você detecta CONTRADIÇÕES factuais entre duas notas. Responda "
                      "is_conflict=true só se houver contradição real (não só temas próximos).",
        response_model=ConflictJudgement,
    )


def judge_conflict(a: dict, b: dict, *, llm_fn: Optional[Callable] = None) -> Optional[dict]:
    j = (llm_fn or _default_judge)(a, b)
    if not j.is_conflict:
        return None
    return {"a": a["path"].stem, "b": b["path"].stem,
            "a_project": a["project"], "b_project": b["project"],
            "explanation": j.explanation}


def write_report(conflicts: list[dict], conflicts_root: Path = CONFLICTS_ROOT, *,
                 dry_run: bool = True, now: Optional[datetime] = None) -> Path:
    now = now or datetime.now()
    dest = conflicts_root / f"{now.strftime('%Y-%m-%d')}.md"
    if not dry_run:
        conflicts_root.mkdir(parents=True, exist_ok=True)
        if conflicts:
            rows = "\n".join(
                f"- [[{c['a']}]] _({c['a_project']})_ ⚔️ [[{c['b']}]] _({c['b_project']})_ — {c['explanation']}"
                for c in conflicts)
        else:
            rows = "_Nenhum conflito detectado. 👍_"
        dest.write_text(f"""---
type: conflict-report
date: {now.strftime('%Y-%m-%d')}
count: {len(conflicts)}
---
# Conflitos de Memória — {now.strftime('%Y-%m-%d')}

<!-- auto:gerado por conflict_detector.py -->
{rows}
""", encoding="utf-8")
    return dest


def conflicts_to_candidates(
    conflicts: list[dict],
    *,
    project: str = "default",
    workspace_id: str = "default",
) -> list[KnowledgeCandidate]:
    """Candidate-only conflict rationales for K3; no report writes."""
    candidates: list[KnowledgeCandidate] = []
    for conflict in conflicts:
        a = str(conflict.get("a") or "")
        b = str(conflict.get("b") or "")
        explanation = str(conflict.get("explanation") or "").strip()
        if not explanation:
            continue
        candidates.append(build_candidate(
            source_type="conflict_detector",
            source_id=f"{a}:{b}:{explanation}",
            knowledge_type="rationale",
            title=f"Conflito: {a} x {b}",
            content=explanation,
            project=str(conflict.get("a_project") or conflict.get("b_project") or project),
            workspace_id=workspace_id,
            evidence={"a": a, "b": b, "sim": conflict.get("sim")},
            metadata={"promoter": "conflict_detector"},
        ))
    return candidates


def _candidate_pairs_db(threshold: float, cap: int) -> list[tuple]:
    """F3-otimização (2026-08-13): pares candidatos via HNSW em batch.

    Usa `core.hnsw_index.all_pairs_below_threshold` — uma única passada sobre os
    vetores já indexados (zero re-embedding), retornando os k vizinhos de cada
    neurônio. Antes: O(n²) + 90k chamadas de embedding (~timeout). Agora: ~7s.

    `threshold` (similaridade) é convertido em max_distance (L2) com folga, e o
    resultado é ordenado por proximidade e limitado a `cap`.
    """
    from core import hnsw_index
    try:
        hnsw_index.load_or_create()
    except Exception:
        return []

    # O índice usa space="cosine" → distância = cosine distance (1 - cos), [0,2].
    # threshold=0.82 → max_distance = 1 - 0.82 = 0.18 (cosine distance).
    max_distance = float(1.0 - min(threshold, 0.99))

    try:
        raw = hnsw_index.all_pairs_below_threshold(k=8, max_distance=max_distance)
    except Exception:
        return []

    # Junta labels/projetos a partir do DB (uma query, não por par).
    from core.database import get_connection
    conn = get_connection()
    try:
        meta: dict[str, dict] = {}
        if raw:
            ids = {p["a"] for p in raw} | {p["b"] for p in raw}
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT id, label, workspace_id FROM neurons WHERE id IN ({placeholders})",
                list(ids),
            ).fetchall()
            meta = {r["id"]: r for r in rows}
    except Exception:
        meta = {}
    finally:
        conn.close()

    pairs: list[tuple] = []
    for p in raw:
        a, b = meta.get(p["a"]), meta.get(p["b"])
        if a is None or b is None:
            continue
        # cosine distance → similarity = 1 - distance
        sim = 1.0 - float(p["distance"])
        pairs.append((
            p["a"], p["b"], sim,
            a["label"] or a["id"], b["label"] or b["id"],
            a["workspace_id"], b["workspace_id"],
        ))
    pairs.sort(key=lambda x: -x[2])
    return pairs[:cap]


def run(*, temporal_root: Path = TEMPORAL, conflicts_root: Path = CONFLICTS_ROOT,
        apply: bool = False, threshold: float = SIM_THRESHOLD, cap: int = MAX_PAIRS,
        embed_fn=None, llm_fn=None) -> dict:
    # F3-otimização: se não há embed_fn injetado (testes), usa o caminho do DB
    # (KNN vec0). O caminho de teste (embed_fn) mantém o fluxo O(n²) original.
    if embed_fn is not None:
        neurons = scan_neuronios(temporal_root)
        pairs = find_candidate_pairs(neurons, threshold=threshold, cap=cap, embed_fn=embed_fn)
        pairs_with_meta = []
        for i, j, sim in pairs:
            pairs_with_meta.append((
                neurons[i]["path"].stem, neurons[j]["path"].stem, sim,
                neurons[i]["path"].stem, neurons[j]["path"].stem,
                neurons[i]["project"], neurons[j]["project"],
            ))
        pairs = pairs_with_meta
    else:
        pairs = _candidate_pairs_db(threshold, cap)

    conflicts = []
    judge_errors = 0
    for (id_a, id_b, sim, label_a, label_b, proj_a, proj_b) in pairs:
        # reconstrói dicts mínimos para o juiz
        a = {"path": Path(label_a), "project": proj_a, "body": label_a}
        b = {"path": Path(label_b), "project": proj_b, "body": label_b}
        try:
            c = judge_conflict(a, b, llm_fn=llm_fn)
        except Exception as e:
            judge_errors += 1
            print(f"  [Resiliência] julgamento falhou no par {id_a}/{id_b}: {e}")
            continue
        if c:
            c["sim"] = round(sim, 3)
            conflicts.append(c)
    dest = write_report(conflicts, conflicts_root, dry_run=not apply)
    stats = {"candidate_pairs": len(pairs),
             "conflicts": len(conflicts), "judge_errors": judge_errors,
             "applied": apply, "report": str(dest)}
    print(f"conflict_detector: {stats}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Detecta contradições entre neurônios (insula/conflitos).")
    ap.add_argument("--apply", action="store_true", help="escreve o relatório (default: log-only)")
    ap.add_argument("--threshold", type=float, default=SIM_THRESHOLD)
    ap.add_argument("--cap", type=int, default=MAX_PAIRS)
    args = ap.parse_args()
    run(apply=args.apply, threshold=args.threshold, cap=args.cap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
