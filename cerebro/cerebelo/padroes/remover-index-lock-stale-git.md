---
type: pattern
slug: remover-index-lock-stale-git
confidence: 0.9
---
# Padrão: Remover index.lock stale antes de operações do Git

<!-- auto:gerado por pattern_distiller.py -->
## Contexto
Execução de comandos git em pipelines ou ambientes automatizados onde sessões anteriores interrompidas ou processos paralelos deixam travas no repositório.

## Passos
1. Verificar se existem processos git em execução com comandos de escrita (commit, add, merge, rebase).
2. Se não houver processos ativos, remover de forma segura a trava stale rodando 'rm -f .git/index.lock'.
3. Executar a operação git desejada (git add, git commit).

## Quando usar
Quando comandos do Git falharem com o erro informando que a trava index.lock já existe.
