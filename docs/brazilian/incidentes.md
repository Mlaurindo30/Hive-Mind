# Incidentes — Severidade, Runbook e Escalação

> **Hive-Mind v3.10.1** — Modelo de severidade (SEV-1 a SEV-4), runbook por sintoma, escalação e fronteiras.
> Fontes: regras de alerta em  (T08.2), gates fail-closed em `scripts/health/knowledge_health.py` (`evaluate_fail_closed`), contrato de promoção em [`arquitetura.md`](arquitetura.md) §23/§27 (ADR-008, ADR-016), disciplina epistêmica em `AGENTS.md` §3 e frontmatter de incidente em `templates/vault/` (`ticket`, `severity`, `role`).

---

## 1. Modelo de severidade

O Hive-Mind classifica incidentes em **quatro níveis**. A tabela reconcilia os dois vocabulários existentes no projeto: o modelo de alerta operacional (crítico/alto/médio, de `FASE-08` T08.2) e o frontmatter de incidente do vault (`severity: high|medium|low`).

| Nível | Nome | Mapa de alerta | Definição | Exemplos concretos no projeto |
|---|---|---|---|---|
| **SEV-1** | Crítico | `crítico` / `high` | Cérebro **indisponível** ou **perda/risco imediato de perda** de memória. Acorda o dono a qualquer hora. | REST API não inicia (fail-closed); backup mais recente > 36 h; `dream_cycle_latest.json` `status≠ok` ou > 36 h; serviço `required` não running; task com `LastTaskResult ≠ 0`; job `status ≠ ok`. |
| **SEV-2** | Alto | `alto` / `high` | Degradação que **quebra um gate de conhecimento** ou **viola um SLO**, sem indisponibilidade total. | `knowledge_health.status = degraded` (órfãos, `observations_linked_pct < 80%`, `discoveries_pending > 500`); `milvus_sync_lag` crescente em produção. |
| **SEV-3** | Médio | `médio` / `medium` | Componente **parcialmente degradado** ou **risco latente** que ainda não quebrou gate. | Provider de captura sem evento novo por > N horas; fallback de LLM acionado com recorrência; `components_healthy=false` em um componente não-crítico. |
| **SEV-4** | Baixo | `baixo` / `low` | **Informativo** / dívida operacional sem impacto imediato. | Aviso de `LANGFUSE_HOST` em HTTP; `HIVE_ALLOW_DEFERRED_MIGRATIONS=1` ativo em diagnóstico legado; `HIVE_FORCE_LEGACY_LLM` usado pontualmente. |

### 1.1 Regras de alerta → severidade (referência canônica)

Extraída de `FASE-08-observabilidade.md` T08.2 (completada com os SLOs de K8):

| Condição | Severidade |
|---|---|
| Task com `LastTaskResult ≠ 0` | SEV-1 |
| Job com `status ≠ ok` no `-latest.json` | SEV-1 |
| Backup mais recente > 36 h | SEV-1 |
| `dream_cycle_latest.json` `status ≠ ok` ou > 36 h | SEV-1 |
| `services.managed.json` mais velho que 5 min | SEV-1 |
| Serviço `required` não running | SEV-1 |
| `knowledge_health.status = degraded` (falha de SLO fail-closed) | SEV-2 |
| `observations_linked_pct < 80%` (com `observations_total ≥ 100`) | SEV-2 |
| `discoveries_pending > 500` | SEV-2 |
| `orphan_vectors > 0` | SEV-2 |
| `milvus_sync_lag.total_lag > 0` em produção (`VECTOR_BACKEND=milvus`) | SEV-2 |
| Provider de captura sem evento novo por > N h | SEV-3 |
| `console-watch` com evento Hive-Mind | SEV-1 |

---

## 2. Runbook por sintoma

Tabela **sintoma → primeiro passo → segundo passo**. Para qualquer linha, o passo 0 é sempre `sinapse_health()` (ou `sinapse-write.py health`) para confirmar qual superfície está degradada antes de agir.

| # | Sintoma | Primeiro passo | Segundo passo |
|---|---|---|---|
| 1 | REST API `:37702` não sobe | Verificar `HIVE_MIND_API_KEY` definida no `.env` (fail-closed: sem chave a API não inicia) | Conferir porta (`HIVE_MIND_API_PORT`, default 37702) livre e log de startup do `scripts/services/sinapse-api.py` |
| 2 | `sinapse_query` retorna vazio / `null` | `sinapse_health()` → identificar backend com circuito aberto (≥3 falhas) | Reerguer o backend específico (claude-mem `:37700`, sqlite-vec worker `:37701`, FalkorDB `:6379`) e aguardar cooldown de 30 s |
| 3 | `claude_mem` falso no health | `curl http://127.0.0.1:37700/health` (espera `{"status":"ok"}`) | `systemctl --user restart sinapse-claude-mem.service`; `sqlite3 ~/.claude-mem/claude-mem.db 'PRAGMA quick_check;'` |
| 4 | `sqlite_vec` falso | `curl http://127.0.0.1:37701/health` | Reiniciar o worker sqlite-vec; verificar `sqlite_vec` carregável no venv |
| 5 | `graphify` falso / `graph_nodes=0` | Ver `cerebro/cortex/occipital/grafo/graph.json` legível | `./scripts/graph/build-graph.sh` (reindex estrutural, cache SHA-256) |
| 6 | `filesystem` falso | Verificar diretório `cerebro/` existe (`vault.exists`) | Corrigir caminho em `sinapse.yaml`/`SINAPSE_HOME` |
| 7 | `graphiti` falso | Verificar FalkorDB em `localhost:6379` | Subir container Graphiti/FalkorDB (`integrations/graphiti/docker-compose.yml`) |
| 8 | `knowledge_health.status = degraded` | `python scripts/health/knowledge_health.py --json` e ler `failures` | Resolver cada `failure` (órfãos → podar; `neurons_vectorized_pct=n/a` → reindex; SLO 1/2 → drenar promoção) |
| 9 | `orphan_vectors > 0` | `knowledge_health.py` sem `--no-prune` (grava `knowledge_tombstones`) | Verificar `orphan_vector_details` para identificar a coleção suja e corrigir a causa raiz |
| 10 | `observations_linked_pct < 80%` | Rodar `sinapse_promote_knowledge(dry_run=true)` para classificar pendências | Rodar Dream Cycle (`scripts/dream/dream_cycle.py --once --real`) e conferir `promotion_lag` |
| 11 | `discoveries_pending > 500` | `scripts/maintenance/drain-candidates.py` (dreno governance-aware, idempotente) | Revisar `HIVE_PROMOTION_BUDGET_*` (cap de custo por workspace; overflow permanece `archived=0`) |
| 12 | `milvus_sync_lag > 0` | `scripts/maintenance/vector-sync.py --collection <c> --json` | Verificar health do Milvus e `VECTOR_BACKEND`; re-sincronizar coleção divergente |
| 13 | Backup > 36 h | `scripts/health/backup_databases.py` manualmente | Verificar job do Task Scheduler/cron (`0 3 * * *`) e log `logs/backup.log` |
| 14 | Dream Cycle > 36 h / `status≠ok` | `tail logs/dream-cycle.log` | Verificar `HIVE_MAX_CYCLE_SECONDS` e configuração de modelo (`HIVE_DREAMER_PROVIDER/MODEL`) |
| 15 | Fallback de LLM recorrente (`fallback_used=true` / `legacy_fallback_used=true`) | `grep "model_gateway" stderr` para ver `error_class` | Corrigir provider primário; se `auth`/saldo → renovar chave; se `validation` → revisar schema/output do modelo |
| 16 | `HIVE_FORCE_LEGACY_LLM=true` em produção | Confirmar que é bypass de emergência intencional (emite warn em stderr) | Planejar retorno ao Model Gateway (`MODEL_GATEWAY_MODE=auto`) e reverter o flag |
| 17 | Suspeita de segredo/PII vazado | `core/redactor.py` não é reversível — ver `seguranca.md` §"Vazamento" | Registrar tombstone via `forget(reason="secret_leak")`; corrigir fonte; **nunca** commitar `.env` |
| 18 | Conflito P2P detectado | `scripts/health/audit_memory.py --fix` (reconcilia vault↔SQLite) | Revisar `cortex/insula/conflitos/` e resolver via Síntese Dialética (`dream_cycle.py` estágio 4) |

---

## 3. Escalação

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

**Registro de incidente** (frontmatter canônico do vault, `templates/vault/`): `ticket: TICKET-<n>`, `severity: high|medium|low`, `role: incident-lead`, além de `date`, `description` (~150 chars) e `tags`. Incidentes vivem no painel `tronco/paineis/Incidents.base`.

---

## 4. Fronteiras (invariantes que um incidente NUNCA deve violar)

1. **Quarentena nunca é descartada.** Observação com falha estrutural vai para `archived=2` (quarentena com motivo) — **nunca** é apagada. Falha transitória fica `archived=0` (retry). Nada é deletado por falha de promoção (ADR-008 / ADR-016). A "limpeza" de quarentena só ocorre via `forget()` com razão e tombstone auditável, nunca por delete físico silencioso.
2. **Hipótese refutada é corrigida no lugar, não apagada.** Se uma decisão/learning salva como hipótese for posteriormente refutada, o correto é **corrigir a nota** (reescrever com a verdade + evidência), não deixá-la no lugar envenenando a recuperação futura, nem apagá-la sem rastro. Uma hipótese refutada deixada no lugar **envenena** a recuperação (AGENTS.md §3).
3. **Fallback nunca é silencioso.** Toda troca de modelo emite telemetria (`fallback_used`, `record_gateway_failure`, `record_legacy_fallback_used`). Modelo não troca por falha de validação de saída (é qualidade, não disponibilidade) — ADR-009.
4. **Mudança de runtime só com evidência.** Antes de alterar configuração de modelo, schema ou rota em resposta a um incidente, registre a **evidência** (comando, teste, métrica) que justifica a mudança; sem evidência a ação é hipótese e fica marcada como tal (ver [`seguranca.md`](seguranca.md) §"Validação").
5. **Health check não é a correção.** `sinapse_health` é diagnóstico read-only (não poda, não reindexa). A correção é sempre o script/runbook da linha correspondente da tabela acima.
6. **Cross-workspace é bug de segurança, não de ranking.** Qualquer vazamento entre `workspace_id` durante um incidente é tratado como falha de segurança (ADR-015), não como degradação de ranking.

---

## Referências cruzadas

- [`observabilidade.md`](observabilidade.md) — métricas e superfícies que alimentam este runbook.
- [`seguranca.md`](seguranca.md) — vazamento de segredo, classificação de dados, validação por evidência.
- [`operacao.md`](operacao.md) — comandos de operação e `hive-mind doctor`.
- [`arquitetura.md`](arquitetura.md) — ADR-008/016 (quarentena), ADR-009 (fallback), ADR-015 (workspace).
- [`pipeline-dados.md`](pipeline-dados.md) — promoção (K3/K4) e gate K8.
- [`instalacao.md`](instalacao.md) — variáveis de ambiente (`HIVE_MIND_API_KEY`, `HIVE_PROMOTION_BUDGET_*`, `HIVE_MAX_CYCLE_SECONDS`).
- [`blueprint.md`](blueprint.md) — diagramas de fluxo.
