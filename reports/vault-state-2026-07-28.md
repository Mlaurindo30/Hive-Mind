# Vault markdown state — 2026-07-28

Status: no estado atual do host, os validadores nativos do `cerebro/` não
encontram mais os sintomas operacionais que definiam o `G11` na auditoria
antiga.

## Objetivo

Revalidar o gate `G11` no estado atual do host, sem assumir as métricas antigas
como ainda válidas, distinguindo:

- mojibake real ainda presente;
- frontmatter inválido ainda presente;
- notas temporais sem `project_id`;
- broken links e notas órfãs no escopo operacional do vault.

## Evidência atual

Comandos executados em 28 de julho de 2026:

- `repair_legacy_encoding(vault_root=cerebro, apply=False)`
- `repair_invalid_frontmatter(vault_root=cerebro, apply=False)`
- `repair_missing_project_id(vault_root=cerebro, apply=False)`
- `audit_vault_markdown(cerebro)`

Resultado relevante:

- `encoding.scanned = 248`
- `encoding.candidates = 0`
- `encoding.repaired = 0`
- `encoding.failed = 0`
- `frontmatter.scanned = 191`
- `frontmatter.candidates = 0`
- `frontmatter.repaired = 0`
- `frontmatter.failed = 0`
- `project_id.scanned = 115`
- `project_id.candidates = 0`
- `project_id.repaired = 0`
- `project_id.failed = 0`
- `vault_audit.metrics.total_md = 248`
- `vault_audit.metrics.empty_md = 1`
- `vault_audit.metrics.invalid_frontmatter = 0`
- `vault_audit.metrics.missing_project_id = 0`
- `vault_audit.metrics.mojibake_files = 0`
- `vault_audit.metrics.broken_wikilinks = 0`
- `vault_audit.metrics.orphan_notes = 0`

## Leitura operacional atual

### 1. Encoding / mojibake

O reparador de encoding não encontrou candidatos reais de normalização:

- `candidates = 0`
- `failed = 0`

No estado atual, não há sinal operacional de mojibake restante no conjunto de
Markdown auditado pelo validador nativo.

### 2. Frontmatter YAML

O reparador de frontmatter inválido também não encontrou candidatos:

- `candidates = 0`
- `failed = 0`

No estado atual, não há bloco de frontmatter inválido detectado no escopo
auditado.

### 3. `project_id` nas notas temporais

O reparador de `project_id` ausente não encontrou candidatos:

- `candidates = 0`
- `failed = 0`

O auditor do vault confirma:

- `missing_project_id = 0`

### 4. Links e órfãos

O auditor de Markdown do vault retorna:

- `broken_wikilinks = 0`
- `orphan_notes = 0`

No estado atual, o escopo operacional do vault não apresenta links quebrados
nem notas órfãs segundo as regras do próprio auditor nativo.

## Conclusão de disposição

O estado controlado correto em 28 de julho de 2026 é:

- os sintomas operacionais que motivaram o `G11` não reaparecem no estado atual
  do `cerebro/` auditado;
- a auditoria antiga do `G11` não pode mais ser tratada como prova atual sem
  considerar esta rechecagem do host real.

## O que isso autoriza — e o que não autoriza

Isto sustenta:

- afirmar que o `cerebro/` atual está limpo nos validadores nativos usados para
  mojibake, frontmatter, `project_id`, broken links e órfãos;
- substituir a leitura “G11 ainda falho por sintomas ativos” por “a falha
  histórica precisa de evidência atual para continuar valendo”.

Isto não sustenta:

- declarar a missão global inteira concluída;
- afirmar que toda evidência histórica anterior estava errada;
- extrapolar este resultado para além do escopo coberto pelos validadores
  nativos executados nesta passada.
