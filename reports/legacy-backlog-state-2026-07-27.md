# Legacy/backlog controlled state — 2026-07-27

Status: legado ativo reduzido ao mínimo preservado

## Objetivo

Fechar com evidência atual o que ainda existe de legado antigo no UMC e no
backlog histórico, sem tocar no runtime já funcional e sem migrar por chute.

## Estado atual lido do host

Fonte principal:

- `D:\Hive-Mind\.venv\Scripts\python.exe -m hive_mind.cli validate delivery --json`

Resultado relevante:

- `capture_outbox.total = 0`
- `capture_outbox.delivered = 0`
- `capture_outbox.dead_letter = 0`
- `observations = 2612`
- `canonical = 2075`
- `legacy = 537`
- `legacy.default_workspace = 537`
- `legacy.unclassified_legacy = 0`
- `legacy.default_active_by_project.ins = 139`
- `recovery.legacy_source_sessions = 0`
- `recovery.bridged_recoverable = 0`
- `recovery.session_rows_found = 0`
- `recovery.canonical_alias_matches = 0`

## Leitura operacional

### 1. Backlog histórico perigoso

Não há backlog vivo no outbox histórico:

- nenhuma linha pendente;
- nenhuma dead-letter ativa;
- nenhuma fila antiga aguardando drenagem.

Isso elimina o risco operacional de “captura antiga ainda encalhada”.

### 2. Legado `unclassified/legacy`

Não restam linhas ativas em `workspace_id = unclassified/legacy`.

Logo, o legado genérico sem classificação já foi reduzido a zero no estado
ativo atual.

### 3. Legado `default`

O que resta de legado no UMC está concentrado em `workspace_id = default`:

- `537` linhas no total;
- bucket ativo identificado: `project = ins` com `139` linhas.

Esse bloco não aparece como candidato recuperável seguro hoje.

### 4. Recoverability real

O validador atual não encontrou base para reconciliação automática:

- `legacy_source_sessions = 0`
- `bridged_recoverable = 0`
- `session_rows_found = 0`
- `canonical_alias_matches = 0`

Interpretação:

- não há sinal atual suficiente para migrar esse restante por regra segura;
- qualquer migração agora seria inferência, não evidência.

## Conclusão de disposição

O estado controlado correto em 2026-07-27 é:

- backlog histórico: encerrado (`0`);
- `unclassified/legacy`: encerrado (`0`);
- restante `default/ins`: preservar como histórico até existir regra canônica
  explícita e comprovada de reconciliação.

## O que isso autoriza — e o que não autoriza

Isto sustenta:

- declarar que o legado operacional perigoso foi neutralizado;
- separar claramente “backlog vivo” de “histórico preservado”.

Isto não sustenta:

- migrar `default/ins` automaticamente;
- apagar o histórico remanescente;
- alegar que todo o legado foi convertido para identidade canônica.
