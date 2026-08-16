# Incidents — Severity, Runbook and Escalation

> **Hive-Mind v3.10.1** — Severity model (SEV-1 to SEV-4), per-symptom runbook, escalation and boundaries.
> Sources: alert rules in  (T08.2), fail-closed gates in `scripts/health/knowledge_health.py` (`evaluate_fail_closed`), promotion contract in [`architecture.md`](architecture.md) §23/§27 (ADR-008, ADR-016), epistemic discipline in `AGENTS.md` §3 and incident frontmatter in `templates/vault/` (`ticket`, `severity`, `role`).

---

## 1. Severity model

Hive-Mind classifies incidents into **four levels**. The table reconciles the two vocabularies that exist in the project: the operational alert model (critical/high/medium, from `FASE-08` T08.2) and the vault's incident frontmatter (`severity: high|medium|low`).

| Level | Name | Alert map | Definition | Concrete examples in the project |
|---|---|---|---|---|
| **SEV-1** | Critical | `crítico` / `high` | Brain **unavailable** or **loss/immediate risk of loss** of memory. Wakes the owner at any hour. | REST API does not start (fail-closed); most recent backup > 36 h; `dream_cycle_latest.json` `status≠ok` or > 36 h; `required` service not running; task with `LastTaskResult ≠ 0`; job `status ≠ ok`. |
| **SEV-2** | High | `alto` / `high` | Degradation that **breaks a knowledge gate** or **violates an SLO**, without total unavailability. | `knowledge_health.status = degraded` (orphans, `observations_linked_pct < 80%`, `discoveries_pending > 500`); growing `milvus_sync_lag` in production. |
| **SEV-3** | Medium | `médio` / `medium` | Component **partially degraded** or **latent risk** that has not yet broken a gate. | Capture provider with no new event for > N hours; LLM fallback triggered repeatedly; `components_healthy=false` on a non-critical component. |
| **SEV-4** | Low | `baixo` / `low` | **Informational** / operational debt with no immediate impact. | Warning about `LANGFUSE_HOST` over HTTP; `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` active in legacy diagnosis; `HIVE_FORCE_LEGACY_LLM` used on a one-off basis. |

### 1.1 Alert rules → severity (canonical reference)

Extracted from `FASE-08-observabilidade.md` T08.2 (completed with the K8 SLOs):

| Condition | Severity |
|---|---|
| Task with `LastTaskResult ≠ 0` | SEV-1 |
| Job with `status ≠ ok` in `-latest.json` | SEV-1 |
| Most recent backup > 36 h | SEV-1 |
| `dream_cycle_latest.json` `status ≠ ok` or > 36 h | SEV-1 |
| `services.managed.json` older than 5 min | SEV-1 |
| `required` service not running | SEV-1 |
| `knowledge_health.status = degraded` (fail-closed SLO failure) | SEV-2 |
| `observations_linked_pct < 80%` (with `observations_total ≥ 100`) | SEV-2 |
| `discoveries_pending > 500` | SEV-2 |
| `orphan_vectors > 0` | SEV-2 |
| `milvus_sync_lag.total_lag > 0` in production (`VECTOR_BACKEND=milvus`) | SEV-2 |
| Capture provider with no new event for > N h | SEV-3 |
| `console-watch` with a Hive-Mind event | SEV-1 |

---

## 2. Runbook per symptom

Table **symptom → first step → second step**. For any row, step 0 is always `sinapse_health()` (or `sinapse-write.py health`) to confirm which surface is degraded before acting.

| # | Symptom | First step | Second step |
|---|---|---|---|
| 1 | REST API `:37702` does not start | Check `HIVE_MIND_API_KEY` set in `.env` (fail-closed: without a key the API does not start) | Check the port (`HIVE_MIND_API_PORT`, default 37702) is free and the startup log of `scripts/services/sinapse-api.py` |
| 2 | `sinapse_query` returns empty / `null` | `sinapse_health()` → identify backend with an open circuit (≥3 failures) | Bring the specific backend back up (claude-mem `:37700`, sqlite-vec worker `:37701`, FalkorDB `:6379`) and wait for the 30 s cooldown |
| 3 | `claude_mem` false in health | `curl http://127.0.0.1:37700/health` (expects `{"status":"ok"}`) | `systemctl --user restart sinapse-claude-mem.service`; `sqlite3 ~/.claude-mem/claude-mem.db 'PRAGMA quick_check;'` |
| 4 | `sqlite_vec` false | `curl http://127.0.0.1:37701/health` | Restart the sqlite-vec worker; check `sqlite_vec` is loadable in the venv |
| 5 | `graphify` false / `graph_nodes=0` | Check `cerebro/cortex/occipital/grafo/graph.json` is readable | `./scripts/graph/build-graph.sh` (structural reindex, SHA-256 cache) |
| 6 | `filesystem` false | Check the `cerebro/` directory exists (`vault.exists`) | Fix the path in `sinapse.yaml`/`SINAPSE_HOME` |
| 7 | `graphiti` false | Check FalkorDB on `localhost:6379` | Bring up the Graphiti/FalkorDB container (`integrations/graphiti/docker-compose.yml`) |
| 8 | `knowledge_health.status = degraded` | `python scripts/health/knowledge_health.py --json` and read `failures` | Resolve each `failure` (orphans → prune; `neurons_vectorized_pct=n/a` → reindex; SLO 1/2 → drain promotion) |
| 9 | `orphan_vectors > 0` | `knowledge_health.py` without `--no-prune` (writes `knowledge_tombstones`) | Check `orphan_vector_details` to identify the dirty collection and fix the root cause |
| 10 | `observations_linked_pct < 80%` | Run `sinapse_promote_knowledge(dry_run=true)` to classify pending items | Run the Dream Cycle (`scripts/dream/dream_cycle.py --once --real`) and check `promotion_lag` |
| 11 | `discoveries_pending > 500` | `scripts/maintenance/drain-candidates.py` (governance-aware drain, idempotent) | Review `HIVE_PROMOTION_BUDGET_*` (per-workspace cost cap; overflow stays `archived=0`) |
| 12 | `milvus_sync_lag > 0` | `scripts/maintenance/vector-sync.py --collection <c> --json` | Check Milvus health and `VECTOR_BACKEND`; re-sync the diverging collection |
| 13 | Backup > 36 h | `scripts/health/backup_databases.py` manually | Check the Task Scheduler/cron job (`0 3 * * *`) and the `logs/backup.log` log |
| 14 | Dream Cycle > 36 h / `status≠ok` | `tail logs/dream-cycle.log` | Check `HIVE_MAX_CYCLE_SECONDS` and model configuration (`HIVE_DREAMER_PROVIDER/MODEL`) |
| 15 | Recurring LLM fallback (`fallback_used=true` / `legacy_fallback_used=true`) | `grep "model_gateway" stderr` to see `error_class` | Fix the primary provider; if `auth`/balance → renew the key; if `validation` → review the model's schema/output |
| 16 | `HIVE_FORCE_LEGACY_LLM=true` in production | Confirm it is an intentional emergency bypass (emits a warn on stderr) | Plan the return to the Model Gateway (`MODEL_GATEWAY_MODE=auto`) and revert the flag |
| 17 | Suspected leaked secret/PII | `core/redactor.py` is not reversible — see `security.md` §"Leak" | Register a tombstone via `forget(reason="secret_leak")`; fix the source; **never** commit `.env` |
| 18 | P2P conflict detected | `scripts/health/audit_memory.py --fix` (reconciles vault↔SQLite) | Review `cortex/insula/conflitos/` and resolve via Dialectic Synthesis (`dream_cycle.py` stage 4) |

---

## 3. Escalation

```
SEV-4 (informativo)
  → registrar no snapshot de saúde (Ínsula). Nenhuma ação imediata.

SEV-3 (médio)
  → alert_dispatcher.py --apply escreve nota em parietal/inbox/.
  → dono do componente acompanha; tendência monitorada por 24–72 h.

SEV-2 (alto)
  → gate de conhecimento violado. Dono do pipeline (Knowledge/Promotion) age no mesmo dia.
  → documentar com evidência (comando rodado, métrica lida) e salvar decisão/learning.

SEV-1 (crítico)
  → intervenção imediata do dono de plantão (mesmo às 2 h).
  → pós-mortem obrigatório: causa raiz + evidência + correção no lugar.
```

**Incident record** (canonical vault frontmatter, `templates/vault/`): `ticket: TICKET-<n>`, `severity: high|medium|low`, `role: incident-lead`, plus `date`, `description` (~150 chars) and `tags`. Incidents live in the `tronco/paineis/Incidents.base` panel.

---

## 4. Boundaries (invariants an incident must NEVER violate)

1. **Quarantine is never discarded.** An observation with a structural failure goes to `archived=2` (quarantine with reason) — it is **never** deleted. A transient failure stays `archived=0` (retry). Nothing is deleted by a promotion failure (ADR-008 / ADR-016). Quarantine "cleanup" only happens via `forget()` with a reason and an auditable tombstone, never by silent physical delete.
2. **A refuted hypothesis is corrected in place, not deleted.** If a decision/learning saved as a hypothesis is later refuted, the correct move is to **correct the note** (rewrite with the truth + evidence), not to leave it in place poisoning future retrieval, nor to delete it without a trace. A refuted hypothesis left in place **poisons** retrieval (AGENTS.md §3).
3. **Fallback is never silent.** Every model switch emits telemetry (`fallback_used`, `record_gateway_failure`, `record_legacy_fallback_used`). A model does not switch on an output-validation failure (that is quality, not availability) — ADR-009.
4. **Runtime change only with evidence.** Before changing model configuration, schema, or routing in response to an incident, record the **evidence** (command, test, metric) that justifies the change; without evidence the action is a hypothesis and stays marked as such (see [`security.md`](security.md) §"Validation").
5. **The health check is not the fix.** `sinapse_health` is read-only diagnosis (does not prune, does not reindex). The fix is always the script/runbook of the corresponding row in the table above.
6. **Cross-workspace is a security bug, not a ranking one.** Any leakage between `workspace_id` during an incident is treated as a security failure (ADR-015), not as ranking degradation.

---

## Cross-references

- [`observability.md`](observability.md) — metrics and surfaces that feed this runbook.
- [`security.md`](security.md) — secret leakage, data classification, evidence-based validation.
- [`operations.md`](operations.md) — operation commands and `hive-mind doctor`.
- [`architecture.md`](architecture.md) — ADR-008/016 (quarantine), ADR-009 (fallback), ADR-015 (workspace).
- [`data-pipeline.md`](data-pipeline.md) — promotion (K3/K4) and the K8 gate.
- [`installation.md`](installation.md) — environment variables (`HIVE_MIND_API_KEY`, `HIVE_PROMOTION_BUDGET_*`, `HIVE_MAX_CYCLE_SECONDS`).
- [`blueprint.md`](blueprint.md) — flow diagrams.
