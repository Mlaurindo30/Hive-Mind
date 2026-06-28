---
type: pattern
slug: leitura-previa-antes-de-editar
confidence: 1.0
---
# Padrão: Leitura prévia obrigatória antes de editar arquivos

<!-- auto:gerado por pattern_distiller.py -->
## Contexto
Ambientes de desenvolvimento e agentes autônomos que utilizam ferramentas de edição de arquivos com restrição de leitura prévia (Read-Before-Write).

## Passos
1. Identificar o arquivo que precisa de modificações.
2. Executar uma ferramenta de leitura (como view_file ou Read) no caminho do arquivo alvo.
3. Verificar a estrutura do conteúdo lido.
4. Chamar a ferramenta de edição (como replace_file_content ou Edit) passando as alterações desejadas.

## Quando usar
Sempre que tentar editar ou escrever em um arquivo e receber o erro informando que o arquivo não foi lido antes da escrita.
