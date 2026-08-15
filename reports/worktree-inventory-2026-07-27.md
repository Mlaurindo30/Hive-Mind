# Worktree inventory — 2026-07-27

Status: fechado para as worktrees/cópias principais já registradas

## Snapshot objetivo

| Path | Exists | Branch | HEAD | Dirty lines | Classification | Operational reading |
|---|---:|---|---|---:|---|---|
| `D:\Hive-Mind` | yes | `codex/universal-provider-capture` | `52a8441b3b661c15a9385a98d042f2e3c70d0277` | `47` | `CANONICAL_RUNTIME` | raiz operacional ativa |
| `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install` | yes | `codex/control-plane-redesign` | `315befe40856f476734440a5bf3819bc47e993b4` | `0` | `DEVELOPMENT_WORKTREE` | worktree histórica limpa; não é a raiz ativa |
| `D:\Hive-Mind-Consolidation\20260722-201726\repo` | yes | `codex/runtime-consolidation` | `c4366aea6c962e28d3370d30350f3b5e79697e9f` | `23` | `BACKUP_SNAPSHOT` | snapshot de consolidação anterior; sem evidência operacional ativa |
| `D:\Hive-Mind-Dev\runtime-consolidation-final` | yes | `codex/runtime-consolidation-final` | `52a8441b3b661c15a9385a98d042f2e3c70d0277` | `0` | `BACKUP_SNAPSHOT` | cópia limpa fora da raiz ativa; sem evidência operacional ativa |
| `D:\Hive-Mind\.tmp\capture-3way-test` | yes | detached | `c2df042c62cd584c85297ad4c8552e969363028e` | `21` | `STALE_WORKTREE` | worktree temporária sob `.tmp`; proibida para runtime |
| `C:\Users\miche\.codex\visualizations\2026\07\13\019f5c0b-88c3-7262-81d3-1e7f24aa69d5\hive-mind-windows-zero-install` | yes | `codex/windows-zero-install` | `aa9435ed1da1bca3fd1de234c3270a37cf471d9e` | `0` | `UNTRACKED_COPY` | cópia externa limpa; sem evidência operacional ativa |
| `C:\Users\miche\.gemini\antigravity\worktrees\Hive-Mind\hive-mind-windows-install` | no | — | — | — | `STALE_WORKTREE` | `git worktree list` ainda registra entrada prunable, mas o path não existe no disco |

## Leitura operacional

- Não há `UNKNOWN` entre essas worktrees/cópias principais já registradas.
- Há múltiplas cópias/worktrees ainda presentes no host, mas a evidência
  operacional atual continua convergindo para `D:\Hive-Mind`.
- O fato de `D:\Hive-Mind-Consolidation\20260722-201726\repo` ainda ter `23`
  linhas dirty impede tratá-lo como simples lixo descartável sem revisão
  administrativa posterior.
- O mesmo vale para `D:\Hive-Mind\.tmp\capture-3way-test`, que continua
  existindo e suja, embora proibida para runtime.

## Conclusão

Para a auditoria do anexo, a lacuna “talvez ainda exista `UNKNOWN` relevante”
fica reduzida: nas worktrees/cópias principais já registradas, o estado atual
é classificável e não mostra uma segunda raiz operacional concorrente ao
runtime ativo `D:\Hive-Mind`.
