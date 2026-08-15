# Legacy/backlog controlled state — 2026-07-28

Status: legado operacional perigoso segue encerrado; resíduo restante continua preservado por falta de regra canônica segura.

## Objetivo

Revalidar no estado atual do host o legado antigo do UMC e do backlog histórico
sem tocar no runtime que já voltou a funcionar, distinguindo backlog vivo de
histórico preservado.

## Evidência atual

Comandos executados em 28 de julho de 2026:

- `python -m hive_mind.cli validate delivery --json`
- `python -m hive_mind.cli projects migrate-legacy --source-workspace default --json`
- `python -m hive_mind.cli backup archive-historical-outbox --json`

Resultado relevante:

- `capture_outbox.total = 0`
- `capture_outbox.delivered = 0`
- `capture_outbox.dead_letter = 0`
- `historical_outbox.scanned = 0`
- `historical_outbox.eligible = 0`
- `historical_outbox.archived = 0`
- `umc.observations = 3459`
- `umc.canonical = 2922`
- `umc.legacy = 537`
- `legacy.default_workspace = 537`
- `legacy.unclassified_legacy = 0`
- `legacy.default_active_by_project.ins = 139`
- `recovery.legacy_source_sessions = 1`
- `recovery.session_rows_found = 1`
- `recovery.canonical_alias_matches = 0`
- `recovery.unmapped_session_projects.ins = 1`
- `projects migrate-legacy --source-workspace default`: `scanned = 139`, `candidates = 0`, `updated = 0`, `unmapped_rows_by_label.ins = 139`
- `backup archive-historical-outbox`: `scanned = 0`, `eligible = 0`, `archived = 0`

## Leitura operacional atual

### 1. Backlog histórico perigoso

O backlog vivo do outbox histórico continua encerrado:

- nenhuma linha pendente;
- nenhuma dead-letter ativa;
- nenhuma fila antiga aguardando drenagem.

Isso mantém fechado o risco operacional de captura antiga ainda encalhada.

### 2. Bucket `unclassified/legacy`

Não restam linhas ativas em `workspace_id = unclassified/legacy`.

Portanto, o legado genérico sem classificação permanece zerado no estado ativo.

### 3. Resíduo `default/ins`

O resíduo legado restante continua concentrado em `workspace_id = default`:

- `537` linhas no total;
- `139` linhas ativas em `project = ins`;
- todas as `139` linhas ativas apontam para a mesma sessão preservada:
  `openrouter-019f6b7a-98a8-7e22-85b8-661bbcee3d91-1784228743493`;
- a sessão correspondente ainda existe em `C:\Users\miche\.claude-mem\claude-mem.db`
  com `content_session_id = 019f6b7a-98a8-7e22-85b8-661bbcee3d91` e
  `project = ins`;
- as observações mais recentes desse bloco são de 16 de julho de 2026.

### 4. Recoverability real em 28 de julho de 2026

Agora existe um único sinal de sessão preservada, mas ele continua não
recuperável por regra canônica:

- `legacy_source_sessions = 1`
- `session_rows_found = 1`
- `canonical_alias_matches = 0`
- `unmapped_session_projects = ins: 1`
- o dry-run de `projects migrate-legacy --source-workspace default` encontrou
  `0` candidatos seguros e `139` linhas não mapeadas por label `ins`

Interpretação:

- o bloco `default/ins` não é backlog vivo do runtime;
- ele é um histórico preservado de uma única sessão antiga;
- ainda não existe alias/regra canônica no registro atual que autorize
  reconciliação automática segura;
- migrar agora continuaria sendo inferência, não evidência.

## Conclusão de disposição

O estado controlado correto em 28 de julho de 2026 é:

- backlog histórico: encerrado (`0`);
- `unclassified/legacy`: encerrado (`0`);
- resíduo `default/ins`: preservar como histórico até existir regra canônica
  explícita, comprovada e registrada no alias registry.

## O que isso autoriza — e o que não autoriza

Isto sustenta:

- afirmar que o legado operacional perigoso permanece neutralizado;
- separar backlog vivo de histórico preservado com evidência atual;
- prosseguir com outras correções sem tocar nesse bloco histórico.

Isto não sustenta:

- migrar `default/ins` automaticamente;
- apagar esse histórico remanescente;
- alegar que todo o legado foi convertido para identidade canônica.
