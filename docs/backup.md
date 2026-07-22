# Backup — auditoria e estado real

Entrega **D008-R1B**. Data: 2026-07-21.

> **CURRENT / TRANSITION / TARGET**
>
> | | Estado |
> |---|---|
> | **CURRENT** | O backup real é `scripts/health/backup_databases.py`, rastreado no git e agendado pelo systemd (`sinapse-backup`) e pelo manifesto (job `backup-databases`). No Windows, a tarefa `HiveMind-Backup` roda **outra coisa**: um auditor de artefatos. |
> | **TRANSITION** | O manifesto declara `backup-databases`; nenhum cutover ocorreu; o Task Scheduler segue dono no Windows. |
> | **TARGET** | `hive-mind backup run/status/verify` nativo, com `restore` separado e protegido. |

## O achado central

**O script chamado `backup.py` não faz backup.**

`D:\Hive-Mind\scripts\maintenance\backup.py` (3068 bytes, **untracked**,
SHA-256 `b891c100b17c7d7052b6d969ed130bb9f42128639ed6a7430a8a25e6913dbb05`)
é um wrapper de 99 linhas que chama
`scripts/health/backup_audit.py::run_audit()` — auditoria de artefatos e
retenção — e grava um JSON em `logs/backup/`.

A tarefa o invoca **sem `--apply`**:

```
Execute:   D:\Hive-Mind\.venv\Scripts\python.exe
Arguments: "D:\Hive-Mind\scripts\maintenance\backup.py"
```

Ou seja, em produção roda em **modo somente-relatório**: não copia dado,
não poda nada. Produz um JSON por dia.

## Definição real da tarefa

| Campo | Valor |
|---|---|
| Estado | Ready |
| Usuário / RunLevel | `miche` / Limited |
| Working directory | `D:\Hive-Mind` |
| Trigger | Daily, 02:00 (desde 2026-07-13) |
| Última execução | 2026-07-21 02:00:01 |
| **LastTaskResult** | **0 (sucesso)** |
| Próxima | 2026-07-22 02:00 |
| Execuções perdidas | 0 |

O job **não está morto** — roda e retorna sucesso todo dia. O que ele faz
é que não corresponde ao nome.

## As três peças, separadas

| Arquivo | Git | O que faz |
|---|---|---|
| `scripts/health/backup_databases.py` (175 L) | **rastreado** | **O backup real.** Usa `sqlite3.Connection.backup()` — cópia consistente com o banco em uso — e poda por `keep_last`. Destinos: `~/.claude-mem/backups`, `<root>/backups`, `~/.swarmclaw/backups`, `~/.hermes/backups` |
| `scripts/health/backup_audit.py` (312 L) | **rastreado** | Auditoria de artefatos, retenção e varredura de segredos |
| `scripts/maintenance/backup.py` (99 L) | **untracked** | Wrapper: chama `backup_audit` com defaults de retenção fixos e grava log |

O wrapper contribui **apenas** defaults de retenção
(`keep_umc=10`, `keep_component_lock=20`, `keep_session_logs=10`,
`keep_fk_repair=5`, `keep_legacy_per_family=1`, `legacy_max_age_days=30`)
e o artefato de log. A lógica está rastreada.

## Duplicação encontrada

Além do wrapper Python, existem **dois PowerShell dormentes** com a mesma
responsabilidade, escrevendo em diretórios de log diferentes:

| Script | Log | Registrado como tarefa? |
|---|---|---|
| `scripts/maintenance/backup.py` | `logs/backup/` | **sim** (`HiveMind-Backup`) |
| `scripts/maintenance/backup-audit-daily.ps1` | `logs/backup-audit/` | não |
| `scripts/maintenance/backup-prune-weekly.ps1` | `logs/backup-prune/` | não |

Nada consome `logs/backup/` — o valor do artefato é diagnóstico manual.

## Riscos avaliados

| Risco | Verificado |
|---|---|
| copiar SQLite em uso sem backup API | **não ocorre** no backup real: `backup_databases.py` usa `sqlite3.Connection.backup()` sobre origem `mode=ro` |
| apagar backup antigo antes de validar o novo | `backup_databases._prune` roda por alvo após o hot-backup; **validação por checksum não existe** |
| ausência de checksum / manifesto de conteúdo | **confirmado ausente** |
| ausência de teste de restauração | **confirmado ausente** |
| segredos no backup | `backup_audit` faz varredura de segredos; o wrapper roda report-only |
| paths hardcoded | destinos derivados de `HOME`/`ROOT`, não hardcoded |
| lock de execução única | **ausente** |
| duas execuções simultâneas | não protegido |

## Cobertura por componente

O backup atual cobre **apenas SQLite**. Declaração honesta:

| Componente | Cobertura |
|---|---|
| claude-mem SQLite | BACKED_UP |
| UMC / `hive_mind.db` | BACKED_UP |
| swarmclaw / hermes SQLite | BACKED_UP |
| Markdown do `cerebro/` | **NOT_SUPPORTED** (não incluído) |
| Milvus | REQUIRES_SERVICE_SNAPSHOT |
| FalkorDB | REQUIRES_SERVICE_SNAPSHOT |
| RAGFlow (mysql/es01/minio/redis) | REQUIRES_SERVICE_SNAPSHOT |
| LightRAG | EXTERNALLY_MANAGED |
| `.env` / segredos | **NOT_SUPPORTED** (deliberado) |

Copiar volume Docker em uso não é backup consistente e não é feito.

## Classificação

| Item | Classificação |
|---|---|
| `scripts/maintenance/backup.py` (wrapper untracked) | **SUPERSEDED** — sua única contribuição são defaults de retenção sobre lógica já rastreada |
| Capacidade "auditoria diária de artefatos de backup" | **OPTIONAL_BY_PROFILE** — diagnóstica, sem consumidor automático |
| `backup-databases` (backup real) | **REQUIRED** — já no manifesto, já rastreado |

**Correção à D008-R1V:** remover o job `backup` do manifesto foi o
resultado certo pelo motivo errado. Eu disse "job morto, nunca
registrado". O correto: o job roda e tem sucesso, mas **não é backup** —
é auditoria de artefatos, e o backup real (`backup-databases`) já estava
no manifesto. O manifesto não perdeu capacidade de backup.

## Trabalho nativo pendente

O motor de backup **já existe e está correto no essencial** (SQLite
backup API). O trabalho nativo não é reescrevê-lo, e sim:

1. expor `hive-mind backup run|status|verify` sobre `backup_databases`;
2. adicionar o que falta: manifesto de conteúdo, SHA-256, lock de
   execução única, validação antes da retenção;
3. `hive-mind backup restore` separado e protegido;
4. decidir se a auditoria diária de artefatos permanece como job.

Nada disso foi implementado nesta entrega — ela é auditoria.

## Evidência preservada

`D:\Hive-Mind\backups\backup-job-audit-20260721-205811\`:
`backup.py`, `backup.py.sha256`, `HiveMind-Backup.xml`,
`task-info.txt`, `runtime-paths.txt`. Original intocado.
