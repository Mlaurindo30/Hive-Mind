#!/usr/bin/env python3
"""Reprocessa observações em quarentena (archived=2) por idade.

Proposito:
    O promotion pipeline (K3/K4) move observacoes com erro estrutural
    para `archived=2` e grava a razao em `metadata.quarantine`. Sem um
    mecanismo automatico de reprocessamento, essas observacoes ficam
    "mumificadas" - nunca sao revisitadas mesmo quando a causa do erro
    ja foi corrigida em uma migracao posterior.

Politica (F4.2 - K8 harden):
    1. DEFAULT: observacoes com 7+ dias em quarentena entram em retry
       automatico. O loop tenta promover de novo; se a migracao corrigiu
       a causa, a obs volta para `archived=0` e segue o pipeline normal.
    2. CRITICAL: observacoes com 30+ dias que falharam 3+ retries sao
       marcadas como `archived=3` (quarentena terminal) e listadas em
       dry-run para inspecao manual. NUNCA deletadas - o conteudo pode
       ser recuperado via audit_memory.py.
    3. `--dry-run` mostra o que mudaria sem alterar nada.
    4. `--max-age-days` customiza o limite de retry automatico.
    5. `--reset-reason "..."` reprocessa todas as observacoes com
       `retry_policy` especifico (ex: "schema_fix_2026_07").

Uso:
    python3 scripts/health/reprocess_quarantine.py
    python3 scripts/health/reprocess_quarantine.py --dry-run
    python3 scripts/health/reprocess_quarantine.py --max-age-days 14
    python3 scripts/health/reprocess_quarantine.py --reset-reason schema_fix_2026_07

Saida:
    JSON em stdout com chaves: scanned, retried, recovered, terminal,
    skipped_recent, by_reason. Exit code 0 sempre (a ferramenta nao
    falha em dados ruins, apenas reporta).
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.database import get_connection, with_sqlite_retry  # noqa: E402
from core.knowledge.promotion import (  # noqa: E402
    promote_held_candidates,
    promote_pending_observations,
    quarantine_observation,
)

# Limite de tentativas antes de marcar como terminal (archived=3)
MAX_RETRY_ATTEMPTS = 3
# Idade em dias acima da qual vai para terminal se esgotar retries
TERMINAL_AGE_DAYS = 30
# Idade minima para entrar em retry automatico (evita flapping)
DEFAULT_RETRY_AGE_DAYS = 7


def _parse_quarantine_at(metadata_json: str) -> datetime | None:
    try:
        meta = json.loads(metadata_json or "{}")
    except (ValueError, TypeError):
        return None
    q = meta.get("quarantine") or {}
    at = q.get("at")
    if not at:
        return None
    try:
        return datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        return None


def _retry_count(metadata_json: str) -> int:
    try:
        meta = json.loads(metadata_json or "{}")
    except (ValueError, TypeError):
        return 0
    q = meta.get("quarantine") or {}
    return int(q.get("retries", 0))


def _reset_archived(conn, obs_id: str) -> None:
    """Move observation de volta para archived=0 (pending) e zera o motivo
    de quarentena anterior para que o proximo failure reescreva do zero."""
    conn.execute(
        "UPDATE observations SET archived = 0, "
        "metadata = json_remove(metadata, '$.quarantine') "
        "WHERE id = ?",
        (obs_id,),
    )


def _mark_terminal(conn, obs_id: str, reason: str) -> None:
    """Marca observation como quarentena terminal (archived=3). Conteudo
    preservado - audit_memory.py pode listar/reparar manualmente."""
    payload = json.dumps({
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    # json() envolve o segundo argumento como JSON value real (objeto),
    # em vez de gravar a string literal. Sem isso, json_set grava a
    # string escapada e o consumidor leria string em vez de dict.
    conn.execute(
        "UPDATE observations SET archived = 3, "
        "metadata = json_set(metadata, '$.quarantine_terminal', json(?)) "
        "WHERE id = ?",
        (payload, obs_id),
    )


def _bump_retry_count(conn, obs_id: str) -> None:
    conn.execute(
        "UPDATE observations SET metadata = json_set("
        "  IFNULL(metadata, '{}'), "
        "  '$.quarantine.retries', "
        "  COALESCE(json_extract(metadata, '$.quarantine.retries'), 0) + 1"
        ") WHERE id = ?",
        (obs_id,),
    )


def _quarantined_rows(conn, *, reset_reason: str | None = None):
    """Lista observacoes em quarentena (archived=2)."""
    sql = "SELECT id, metadata, created_at FROM observations WHERE archived = 2"
    params: tuple = ()
    if reset_reason:
        sql += " AND json_extract(metadata, '$.quarantine.retry_policy') = ?"
        params = (reset_reason,)
    return conn.execute(sql, params).fetchall()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reprocessa observacoes em quarentena (archived=2) por idade."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que mudaria sem aplicar nenhuma alteracao.",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_RETRY_AGE_DAYS,
        help=f"Idade minima (em dias) para entrar em retry automatico. "
        f"Default: {DEFAULT_RETRY_AGE_DAYS}.",
    )
    parser.add_argument(
        "--reset-reason",
        type=str,
        default=None,
        help="Se passado, reprocessa todas as observacoes com esse "
        "retry_policy (ex: schema_fix_2026_07), ignorando idade.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=5000,
        help="Limite de linhas a processar por execucao (default 5000).",
    )
    parser.add_argument(
        "--include-high-risk",
        action="store_true",
        help="Promove tambem candidatos held com risk=high (aprovacao "
        "explicita da fila de revisao de governanca). Sem esta flag, "
        "high-risk nunca e promovido automaticamente.",
    )
    parser.add_argument(
        "--held-min-age-days",
        type=int,
        default=7,
        help="Idade minima (dias) para drenar candidatos held "
        "hypothesis+low (default 7).",
    )
    args = parser.parse_args()

    conn = get_connection()
    rows = _quarantined_rows(conn, reset_reason=args.reset_reason)
    now = datetime.now(timezone.utc)

    report: dict = {
        "scanned": 0,
        "skipped_recent": 0,
        "retried": 0,
        "recovered": 0,
        "terminal": 0,
        "errors": 0,
        "by_reason": {},
        "dry_run": args.dry_run,
        "max_age_days": args.max_age_days,
    }

    for row in rows[: args.max_rows]:
        report["scanned"] += 1
        obs_id = str(row["id"])
        metadata = row["metadata"] or ""
        q_at = _parse_quarantine_at(metadata)
        retries = _retry_count(metadata)

        # Razao do erro (para agrupar no relatorio)
        try:
            q_meta = json.loads(metadata).get("quarantine", {})
            reason_key = (q_meta.get("reason") or "unknown")[:80]
        except Exception:
            reason_key = "unknown"
        report["by_reason"][reason_key] = report["by_reason"].get(reason_key, 0) + 1

        # 1) Filtro de idade (a menos que --reset-reason tenha sido dado)
        if args.reset_reason is None and q_at is not None:
            age_days = (now - q_at).days
            if age_days < args.max_age_days:
                report["skipped_recent"] += 1
                continue

        # 2) Se retries esgotados E idade >= terminal, marcar terminal
        if (
            retries >= MAX_RETRY_ATTEMPTS
            and q_at is not None
            and (now - q_at).days >= TERMINAL_AGE_DAYS
        ):
            if not args.dry_run:
                _mark_terminal(
                    conn,
                    obs_id,
                    f"retry {retries}x exhausted over {(now - q_at).days}d: {reason_key}",
                )
            report["terminal"] += 1
            continue

        # 3) Tentar reprocessar
        report["retried"] += 1
        if args.dry_run:
            continue

        try:
            _reset_archived(conn, obs_id)
            # promote_pending_observations processa TODAS as pendentes;
            # para reprocessar UMA, a opcao mais simples e' rodar o
            # promotion completo e contar o resultado. Para batch
            # grandes, isso fica caro - mas 5000 linhas processadas
            # individualmente seria pior.
            # F4.2 alternativa: o _reset_archived ja' moveu a obs para
            # pending, entao um unico promote_pending_observations no
            # final do loop cobre todas.
        except sqlite3.Error as exc:
            report["errors"] += 1
            quarantine_observation(
                conn,
                obs_id,
                f"reprocess failed: {type(exc).__name__}: {exc}",
                retry_policy="reprocess_error",
            )

    # Promove as que foram resetadas em batch
    if not args.dry_run and report["retried"] > 0:
        try:
            sub_report = with_sqlite_retry(
                lambda: promote_pending_observations(conn),
                op_label="reprocess_quarantine",
            )
            # Tudo que nao foi quarantined de novo, foi recuperado.
            quarantined_again = sub_report.get("quarantined", 0)
            report["recovered"] = max(0, report["retried"] - quarantined_again)
            conn.commit()
        except Exception as exc:
            report["errors"] += 1
            report["promote_error"] = f"{type(exc).__name__}: {exc}"

    # Drena a fila de revisao de governanca (candidatos status='held').
    # hypothesis+low promove apos a janela de idade; risk=high exige
    # --include-high-risk (nunca automatico).
    try:
        report["held"] = with_sqlite_retry(
            lambda: promote_held_candidates(
                conn,
                min_age_days=args.held_min_age_days,
                include_high_risk=args.include_high_risk,
                apply=not args.dry_run,
            ),
            op_label="drain_held_candidates",
        )
    except Exception as exc:
        report["errors"] += 1
        report["held_error"] = f"{type(exc).__name__}: {exc}"

    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
