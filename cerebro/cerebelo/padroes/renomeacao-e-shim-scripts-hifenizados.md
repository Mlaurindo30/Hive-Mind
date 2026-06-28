---
type: pattern
slug: renomeacao-e-shim-scripts-hifenizados
confidence: 0.95
---
# Padrão: Renomeação e Shim para importação de scripts Python com hífens

<!-- auto:gerado por pattern_distiller.py -->
## Contexto
Refatoração de arquivos Python que possuem hífens em seus nomes de arquivo (e consequentemente não podem ser importados normalmente) e que precisam ser mantidos como entrypoint/executáveis hifenizados para compatibilidade externa.

## Passos
1. Renomear o arquivo original substituindo hífens por underscores usando o comando git mv.
2. Criar um arquivo shim com o nome hifenizado original no mesmo local.
3. No shim, ajustar o sys.path e importar a função principal (main) do novo módulo com underscores.
4. Substituir nos consumidores as importações complexas via importlib por importações nativas usando o nome com underscores.

## Quando usar
Sempre que houver arquivos python com hífens no nome sendo executados externamente e que precisem ser importados ou mockados/testados em outros módulos.
