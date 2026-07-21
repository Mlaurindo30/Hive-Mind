# Scheduler & Job Inventory

Inventário canônico de jobs, validado na entrega **D008-R1V**.

> **Estado (não confundir com alvo):**
>
> | | Quem é o dono hoje |
> |---|---|
> | **CURRENT** | systemd timers (POSIX) e Task Scheduler (Windows) são os **donos reais**. Eles executam os jobs. |
> | **TRANSITION** | `config/runtime.yaml` é o **manifesto candidato**. O `hive-mindd` apenas **calcula** next-run em shadow; **não dispara nada**. |
> | **TARGET** | `hive-mindd` como dono único, após cutover (D010). |
>
> **Nenhum cutover ocorreu. Nenhum dos jobs foi ativado pelo daemon.**

## Por que este inventário existe

A D008-R1 completou o manifesto tomando os timers systemd como referência.
Paridade textual **não prova** que um job ainda é necessário. A D008-R1V
validou cada job contra o código real — e encontrou um job morto.

## Tabela canônica

Classificação: `REQUIRED` · `OPTIONAL_BY_PROFILE` · `LEGACY_TO_REMOVE` ·
`DUPLICATE` · `SUPERSEDED`.

| Job | Cron | Script | Escreve em | Classificação |
|---|---|---|---|---|
| `claude-mem-bridge` | `45 2 * * *` | `services/claude_mem_bridge.py` | UMC (observations) | REQUIRED |
| `dream-cycle` | `0 3 * * *` | `dream/dream_cycle.py` | `cortex/temporal/` | REQUIRED |
| `capture-tailer` | interval 30s | `capture/capture-tailer.py` | Claude Mem via `capture_core.ingest` | REQUIRED |
| `daily-writer` | `55 23 * * *` | `dream/daily_writer.py` | `cerebelo/diario/` | REQUIRED |
| `weekly-synthesizer` | `0 4 * * 0` | `dream/weekly_synthesizer.py` | vault (síntese semanal) | OPTIONAL_BY_PROFILE |
| `capture-maintenance` | `0 4 * * 0` | `capture/capture_maintenance.py` | banco de captura | REQUIRED |
| `health-dashboard` | `50 23 * * *` | `health/health_dashboard.py` | `cortex/insula/saude/` | REQUIRED |
| `alert-dispatcher` | `52 23 * * *` | `health/alert_dispatcher.py` | alertas | OPTIONAL_BY_PROFILE |
| `backup-databases` | `0 2 * * *` | `health/backup_databases.py` | backups de SQLite | REQUIRED |
| `knowledge-health` | `0 2 * * *` | `health/audit_memory.py` | `cortex/temporal/` + métricas | REQUIRED |
| `decision-promoter` | `40 23 * * *` | `knowledge/decision_promoter.py` | `cortex/temporal/` | REQUIRED |
| `project-synthesizer` | `42 23 * * *` | `knowledge/project_synthesizer.py` | `cortex/frontal/projetos/` | OPTIONAL_BY_PROFILE |
| `work-tracker` | `44 23 * * *` | `knowledge/work_tracker.py` | `cortex/frontal/trabalho/` | OPTIONAL_BY_PROFILE |
| `pattern-distiller` | `0 5 * * 0` | `knowledge/pattern_distiller.py` | vault (padrões) | OPTIONAL_BY_PROFILE |
| `conflict-detector` | `30 5 * * 0` | `knowledge/conflict_detector.py` | `cortex/insula/conflitos/` | OPTIONAL_BY_PROFILE |
| `topic-consolidator` | `0 6 * * 0` | `knowledge/topic_consolidator.py` | `cortex/temporal/` | OPTIONAL_BY_PROFILE |
| `review-writer` | `7 8 * * *` | `knowledge/review_writer.py` | `cortex/insula/saude/revisao` | OPTIONAL_BY_PROFILE |
| `drift-detector` | `0 2 1 * *` | `knowledge/drift_detector.py` | `cortex/temporal/arquivo/` | OPTIONAL_BY_PROFILE |

**18 jobs.** Todos têm entry point (`__main__`), código executável e um
destino de escrita identificável (consumidor).

### Job removido do manifesto

| Job | Motivo | Classificação |
|---|---|---|
| `backup` (`maintenance/backup.py`) | O script **não existe no repositório** — está apenas como arquivo *untracked* na máquina do mantenedor. O próprio `register-windows-jobs.ps1` o pula (`Test-Path … continue`), então em instalação limpa nunca foi registrado. Coberto por `backup-databases`. | **LEGACY_TO_REMOVE / DUPLICATE** |

Travado por `test_dead_windows_tasks_are_deliberately_excluded`: se o
script virar código real, o teste falha e força uma decisão nova em vez
de deixar um buraco silencioso.

## Ordenação como dependência, não como relógio

O Linux codifica "a bridge alimenta o dream" como 02:45 vs 03:00. Isso
**não é contrato**: uma bridge lenta, um reboot no intervalo ou um
misfire quebram a ordem em silêncio.

O manifesto agora declara:

```yaml
  - name: dream-cycle
    depends_on:
      - claude-mem-bridge
    dependency_policy:
      require_success_since_last_run: true
```

O schema valida: dependência inexistente, auto-referência e ciclo são
rejeitados na carga do manifesto.

## Gates ainda NÃO comprovados

Estes exigem o scheduler **disparando** jobs (F7) e cutover (D010):

| Gate | Estado |
|---|---|
| execução real dos 18 jobs | NOT_STARTED |
| enforcement da dependência bridge→dream em runtime | NOT_STARTED |
| bridge falha / atrasa / reboot entre 02:45 e 03:00 | NOT_STARTED |
| misfire policy | NOT_STARTED |
| lock/lease (duas instâncias) | PARTIAL — lease existe no `SqliteSchedulerStore`, sem execução real |
| backup restaurável | NOT_STARTED |
| ausência de dupla execução pós-cutover | NOT_STARTED |

A suíte de testes prova **declaração e regressão**, não execução.
