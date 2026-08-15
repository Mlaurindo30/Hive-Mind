# Security artifact state — 2026-07-28

Status: no estado atual do host, os scrubs nativos e o auditor nativo de
backups/segredos não apontam segredo vivo remanescente nos artefatos
operacionais auditados por eles.

## Objetivo

Revalidar o gate `G14` no estado atual do host, sem assumir o relatório antigo
da auditoria como ainda vigente, distinguindo:

- artefatos operacionais que hoje ainda exigiriam scrub;
- backups/artefatos históricos que hoje ainda exibiriam segredo vivo;
- ocorrências documentais/placeholder que não equivalem a vazamento ativo.

## Evidência atual

Comandos executados em 28 de julho de 2026:

- `python -m hive_mind.cli backup scrub-capture-outbox --json`
- `python -m hive_mind.cli backup scrub-runtime-artifacts --json`
- `python -m hive_mind.cli backup scrub-env-backups --json`
- `python scripts/maintenance/backup.py --json`
- busca literal em `logs/` e `backups/` por padrões de segredo

Resultado relevante:

- `scrub-capture-outbox`:
  - `scanned_rows = 6123`
  - `changed_rows = 0`
  - `changed_payload_rows = 0`
  - `changed_error_rows = 0`
- `scrub-runtime-artifacts`:
  - `scanned = 7`
  - `changed = 0`
- `scrub-env-backups`:
  - `scanned = 1`
  - `changed = 0`
  - o único `.env` de backup já está redigido com sentinelas
- `scripts/maintenance/backup.py --json`:
  - `secret_hits = []`
  - `stale_candidates = []`

## Leitura operacional atual

### 1. Capture outbox do runtime local

O banco local auditado pelo scrub do runtime:

- `D:\Hive-Mind\logs\capture-outbox.db`

não exigiria rewrite hoje. O dry-run encontrou `0` linhas a serem alteradas.

### 2. Runtime artifacts alvo do scrub nativo

Os artefatos padrão de runtime/log auditados por:

- `scrub-runtime-artifacts`

também não exigiriam rewrite hoje. O dry-run encontrou `0` arquivos a serem
alterados.

### 3. Backups de `.env`

O único `.env` de backup encontrado em:

- `D:\Hive-Mind\backups\install-20260712-200339\.env`

já está redigido com sentinelas como:

- `[REDACTED:env-backup-secret]`

Por isso o scrub reconhece chaves sensíveis, mas `changed = 0`.

### 4. Auditor nativo de backup/segredo

O auditor nativo:

- `scripts/maintenance/backup.py --json`

não encontrou segredo vivo nos alvos que ele considera parte do problema de
backup/retention:

- `secret_hits = []`

### 5. Ocorrências literais fora do escopo do auditor

A busca textual simples ainda encontra ocorrências como:

- placeholders documentais (`GOOGLE_API_KEY=<your_key>`)
- campos vazios (`GOOGLE_API_KEY=`)
- sentinelas de redaction (`[REDACTED:env-backup-secret]`)
- texto de review contendo a palavra `secret`

Essas ocorrências não foram classificadas pelo auditor nativo como vazamento
ativo, e não provocaram mudança em nenhum scrub.

## Conclusão de disposição

O estado controlado correto em 28 de julho de 2026 é:

- os artefatos operacionais cobertos pelos scrubs nativos estão limpos no host;
- os backups auditados pelo scanner nativo não exibem segredo vivo;
- os hits literais restantes observados nesta passada são documentais ou já
  redigidos, não prova automática de exposição ativa.

## O que isso autoriza — e o que não autoriza

Isto sustenta:

- afirmar que a superfície operacional hoje coberta pelos scrubs nativos está
  saneada;
- afirmar que a auditoria histórica antiga do `G14` não pode ser tratada como
  prova atual sem rechecagem;
- reduzir o risco atual percebido de segredo vivo em backups/artefatos do host.

Isto não sustenta:

- declarar o `G14` encerrado de forma absoluta sem uma política formal sobre
  placeholders/documentação histórica fora do escopo do auditor;
- afirmar que nenhum artefato histórico do disco inteiro contém qualquer string
  semelhante a segredo;
- usar apenas busca textual ingênua como prova de vazamento ativo.
