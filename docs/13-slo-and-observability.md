# SLO e Observabilidade K8

> Status: contrato K8 (v3.7.0+)
> Fonte canônica: `scripts/health/knowledge_health.py::evaluate_fail_closed`
> Teste de aceitação: `tests/real/test_knowledge_health.py::test_knowledge_health_cli_fail_closed_acceptance`

Este documento define os **Service Level Objectives (SLOs)** que o cérebro
do Hive-Mind deve sustentar em produção, como são medidos, e onde os
dashboards vivem. É o **gêmeo observável** do K8 — sem SLO público, o
fail-closed gate fica sem régua.

## 1. Princípios

- **SLO é contrato**, não aspiração. Se um gate está em `evaluate_fail_closed`,
  ele é parte do SLO. Mover um gate exige ADR.
- **Mensurável via `knowledge_health.py --json`**. Toda métrica do SLO
  aparece no payload JSON e pode ser scraped por Prometheus/Loki/etc.
- **Failure modes explícitos**. Cada SLO tem um único dono de código
  e um único teste que verifica o gate. Sem dono = sem SLO.
- **Tolerância zero em vazamento**. `orphan_vectors > 0` é SLO violado,
  não importa os outros números.

## 2. SLOs canônicos

| ID  | Métrica                        | Threshold            | Ação quando violado              | Dono                     |
| --- | ------------------------------ | -------------------- | -------------------------------- | ------------------------- |
| S1  | `orphan_vectors`               | `== 0`               | fail-closed imediato             | `core/indexing.py`        |
| S2  | `neurons_vectorized_pct`       | conhecido ≠ `None`   | fail-closed quando há neurons   | `core/indexing.py`        |
| S3  | `document_vectors_vectorized_pct` | conhecido ≠ `None` quando há documents | fail-closed | `core/retrieval/document_pipeline.py` |
| S4  | `observations_linked_pct`      | `≥ 80%` quando `observations_total ≥ 100` | fail-closed | `core/knowledge/promotion.py` |
| S5  | `discoveries_pending`          | `≤ 500`              | fail-closed (backlog excessivo)  | `core/knowledge/promotion.py` |
| S6  | `summary_vectors_total`        | conhecido            | aviso (não fail-closed)          | `core/indexing.py`        |
| S7  | `observations_total`           | conhecido            | aviso (não fail-closed)          | `core/knowledge/promotion.py` |

### S1 — `orphan_vectors == 0`

Vetor em `search_vec` sem neurônio correspondente em `neurons`. Causa
mais comum: `prune_orphan_vectors` não foi rodado após um delete manual
ou uma migração. Auto-reparo: `scripts/health/knowledge_health.py --prune`.

### S4 — `observations_linked_pct ≥ 80%`

Razão entre observações com `neuron_id` não vazio e total de observações
**não-quarentenadas** (`archived != 2`). Quarentenadas são excluídas do
denominador de propósito — elas não deveriam contar contra o gate de
linking. Causa comum: promotion pipeline parou (ver S5).

### S5 — `discoveries_pending ≤ 500`

Backlog de observações que passaram por `sinapse_query` e ainda não foram
processadas pelo `promote_pending_observations` (K3). 500 é o limite
operacional atual — acima disso o `dream_cycle` provavelmente travou.

## 3. Latência e taxa de erros (futuro)

Os SLOs acima são **cobertura** (o cérebro sabe o que sabe?). Para
completar a observabilidade de produção falta:

| ID    | Métrica                         | Threshold (alvo)         | Status |
| ----- | ------------------------------- | ------------------------ | ------ |
| L1    | p50 `sinapse_query`             | ≤ 800ms (cold start)     | rascunho — sem histogramas hoje |
| L2    | p99 `sinapse_query`             | ≤ 2.5s                   | rascunho |
| E1    | Error rate `sinapse_*` tools    | ≤ 1% (24h)               | não instrumentado |
| D1    | `dream_cycle` duração p95       | ≤ 6min (batch de 200)    | parcial — `dream_cycle_log` tem `duration_s` |

L1/L2/E1 exigem tracing OpenTelemetry no `sinapse-mcp.py` e `sinapse-api.py`.
Não fazem parte do fail-closed até existir instrumentação. Estão aqui
para o K9 (test harness) cobrar.

## 4. Dashboards

| URL / path                                         | Conteúdo                                |
| -------------------------------------------------- | --------------------------------------- |
| `cerebro/cortex/insula/saude/` (Obsidian)          | Notas diárias/semanais do `health_dashboard.py` |
| `docs/reports/k9/knowledge-health-*.json` (CI)     | Snapshots `--json` por release          |
| `sinapse-api:37702/health` (HTTP)                  | Liveness + última métrica do knowledge_health |
| `prometheus` (a integrar)                          | L1/L2/E1 quando Telemetry existir       |

## 5. Como adicionar um novo SLO

1. Adicionar a métrica em `compute_knowledge_health` (cerebro/cortex/...)
2. Adicionar o gate em `evaluate_fail_closed` com `failures.append(...)`
3. Adicionar entrada na tabela §2
4. Adicionar teste em `tests/unit/test_knowledge_health.py` que prove
   que `--fail-closed` retorna código 1 quando o gate é violado
5. Adicionar entrada em `docs/12-knowledge-implementation-plan.md`
   §K8 caso a métrica ainda não esteja trackeada

## 6. Mudanças incompatíveis

- v3.7.0: `evaluate_fail_closed` adicionado (S1, S2, S3)
- v3.7.7: gate S5 adicionado (backlog)
- v3.7.8: gate S4 adicionado (`observations_linked_pct`); `observations_total`
  exposto no payload; `discoveries_pending` gate S5 refinado (era warning, agora fail-closed)

## 7. Onde olhar quando algo cai

```bash
# 1. Quais gates falham?
python3 scripts/health/knowledge_health.py --fail-closed --json --no-report

# 2. Métricas cruas
python3 scripts/health/knowledge_health.py --json --no-report | jq '.metrics'

# 3. Se S1 (orphan_vectors) falhou, prune e rode de novo
python3 scripts/health/knowledge_health.py --prune --fail-closed --json

# 4. Se S5 (discoveries_pending) falhou, force o dream_cycle
python3 scripts/dream/dream_cycle.py --once

# 5. Se S4 (observations_linked_pct) baixo, reprocessar quarentena
python3 scripts/health/reprocess_quarantine.py --dry-run
python3 scripts/health/reprocess_quarantine.py
```
