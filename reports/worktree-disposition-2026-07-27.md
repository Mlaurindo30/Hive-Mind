# Worktree disposition — 2026-07-27

Status: decisão administrativa proposta, sem mutação

## Objetivo

Transformar o inventário atual de worktrees/cópias em uma leitura operacional
 simples: o que pode permanecer como histórico preservado e o que deve entrar
 numa limpeza administrativa posterior, sem tocar no runtime ativo
 `D:\Hive-Mind`.

## Disposição proposta

| Path | Classification | Disposição | Motivo |
|---|---|---|---|
| `D:\Hive-Mind` | `CANONICAL_RUNTIME` | PRESERVAR COMO ATIVO | raiz operacional canônica atual |
| `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install` | `DEVELOPMENT_WORKTREE` | PRESERVAR COMO HISTÓRICO DE DESENVOLVIMENTO | worktree limpa, citada pelo anexo, sem commits mais novos que a raiz ativa |
| `D:\Hive-Mind-Consolidation\20260722-201726\repo` | `BACKUP_SNAPSHOT` | REVISÃO ADMINISTRATIVA POSTERIOR | snapshot fora da raiz ativa, mas ainda com `23` dirty lines |
| `D:\Hive-Mind-Dev\runtime-consolidation-final` | `BACKUP_SNAPSHOT` | PRESERVAR COMO SNAPSHOT | cópia limpa, fora do caminho operacional |
| `D:\Hive-Mind\.tmp\capture-3way-test` | `STALE_WORKTREE` | REVISÃO ADMINISTRATIVA POSTERIOR | worktree temporária sob `.tmp`, proibida para runtime e com `21` dirty lines |
| `C:\Users\miche\.codex\visualizations\2026\07\13\019f5c0b-88c3-7262-81d3-1e7f24aa69d5\hive-mind-windows-zero-install` | `UNTRACKED_COPY` | PRESERVAR COMO CÓPIA EXTERNA | cópia limpa fora da raiz operacional, sem evidência de uso no runtime |
| `C:\Users\miche\.gemini\antigravity\worktrees\Hive-Mind\hive-mind-windows-install` | `STALE_WORKTREE` | REMOVER REGISTRO/RESÍDUO QUANDO CONVENIENTE | entrada prunable; path não existe mais no disco |

## Regra operacional derivada

No estado atual do host:

- nenhuma dessas cópias, exceto `D:\Hive-Mind`, deve ser tratada como raiz
  operacional;
- nenhuma delas precisa ser promovida para substituir a baseline ativa;
- as únicas que merecem revisão manual antes de qualquer remoção são as que
  continuam sujas:
  - `D:\Hive-Mind-Consolidation\20260722-201726\repo`
  - `D:\Hive-Mind\.tmp\capture-3way-test`

## Conclusão

Para a missão atual, a decisão segura é:

- manter `D:\Hive-Mind` como única raiz operacional;
- manter a worktree de desenvolvimento citada no anexo apenas como histórico;
- empurrar a limpeza das cópias/snapshots não operacionais para uma etapa
  administrativa posterior, sem misturar isso com o runtime já consolidado.
