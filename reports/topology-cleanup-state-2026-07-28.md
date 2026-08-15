# Topology cleanup state — 2026-07-28

Status: a topologia física híbrida original foi reduzida e a pendência residual
`D:\Hive-Mind\.tmp` foi arquivada/removida por cleanup controlado. No host
atual, a topologia viva ficou restrita à raiz canônica e à raiz de arquivo.

## Objetivo

Revalidar no estado atual do host o gate físico de topologia (`G15`) sem
executar remoção ainda, distinguindo:

- raiz operacional canônica;
- raízes históricas já preservadas;
- resíduo temporário removível após aprovação.

## Evidência atual

Comandos executados em 28 de julho de 2026:

- `python -m hive_mind.cli validate topology --json`
- `python -m hive_mind.cli backup archive-topology --json`
- `python -m hive_mind.cli backup cleanup-topology-stale --json`
- `git worktree list --porcelain`
- inventário direto de `D:\Hive-Mind\.tmp`
- `python -m hive_mind.cli backup cleanup-topology-stale --apply --json`
- revalidação final de `python -m hive_mind.cli validate topology --json`

Resultado relevante:

- `validate topology` antes do cleanup: `scanned = 3`
- `D:\Hive-Mind`: `CANONICAL_RUNTIME`, `KEEP`
- `D:\Hive-Mind-Archive`: `ARCHIVE_ROOT`, `KEEP`
- `D:\Hive-Mind\.tmp`: `STALE_WORKTREE`, `REMOVE_AFTER_APPROVAL`
- `archive-topology`: `eligible = 0`
- `cleanup-topology-stale`: `eligible = 1`
- `cleanup-topology-stale --apply`: `eligible = 1`, `archived = 1`, `removed = 1`, `preserved = 0`
- `validate topology` após o cleanup: `scanned = 2`
- worktrees Git registradas: apenas `D:\Hive-Mind`

Inventário atual de `D:\Hive-Mind\.tmp`:

- `g5-fresh-clone` — `3291375220` bytes
- `g5-wheel-smoke` — `530442690` bytes
- `g5-current-proof` — `165342977` bytes
- total aproximado: `3987160887` bytes

## Leitura operacional atual

### 1. Raiz operacional

O runtime canônico permanece concentrado em:

- `D:\Hive-Mind`

Não há outra worktree Git registrada além da raiz canônica.

### 2. Raiz histórica preservada

A raiz:

- `D:\Hive-Mind-Archive`

permanece classificada corretamente como área de preservação histórica, não como
raiz operacional concorrente.

### 3. Árvores legadas originalmente citadas no gate

No host atual, as árvores explicitamente citadas pela auditoria original como
fontes de ambiguidade não apareceram mais no inventário vivo:

- `D:\Hive-Mind-Dev`
- `D:\Hive-Mind-Consolidation`

Também não apareceu worktree externa registrada além da raiz canônica.

### 4. Resíduo físico pendente antes do cleanup

A única pendência física ainda classificada para limpeza controlada é:

- `D:\Hive-Mind\.tmp`

Ela não foi classificada como raiz operacional. O conteúdo atual é compatível
com resíduos temporários desta própria correção:

- clone fresco de prova do G5;
- smoke wheel local;
- prova corrente de instalação da wheel.

### 5. Estado após o cleanup controlado

O cleanup nativo arquivou e removeu `D:\Hive-Mind\.tmp`:

- batch de archive: `D:\Hive-Mind-Archive\topology-cleanup\20260727-225214`
- ação reportada: `ARCHIVE_AND_REMOVE_DIRECTORY`
- status reportado: `ARCHIVED_REMOVED`

Após a revalidação final, restaram apenas:

- `D:\Hive-Mind`
- `D:\Hive-Mind-Archive`

## Conclusão de disposição

O estado controlado correto em 28 de julho de 2026, após o cleanup, é:

- `D:\Hive-Mind`: `KEEP`
- `D:\Hive-Mind-Archive`: `KEEP`

## O que isso autoriza — e o que não autoriza

Isto sustenta:

- afirmar que a topologia híbrida anterior foi substancialmente reduzida;
- afirmar que não há, hoje, worktree Git concorrente registrada fora da raiz
  canônica;
- afirmar que a única pendência física objetiva do `G15`, `D:\Hive-Mind\.tmp`,
  foi arquivada e removida por fluxo nativo controlado.

Isto não sustenta:

- usar essa evidência isolada para afirmar o objetivo global inteiro como concluído;
- afirmar que toda ambiguidade física histórica do disco foi eliminada sem uma
  execução final do cleanup aprovado.
