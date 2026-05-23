# Atoms — Zettelkasten Notes

> Cada arquivo neste diretório é uma **nota atômica**: uma ideia, um conceito, uma decisão.
> Uma nota = um node no knowledge graph (Graphify).

## Regras

1. **Atomicidade**: Uma nota cobre UM único conceito. Se tem 2 ideias distintas, split em 2 notas.
2. **Densidade de links**: Toda nota atômica deve linkar para pelo menos 2 outras notas (preferencialmente 3+).
3. **Nome descritivo**: O título da nota DEVE ser uma frase completa que expressa o conteúdo. Ex: "Graphify usa Leiden clustering para detecção de comunidades" (não "Graphify clustering").
4. **Frontmatter obrigatório**: tags, aliases, created, updated, confidence.
5. **Bidirectional linking**: Se A linka B, B deve linkar A (via backlinks ou link explícito).

## Template

```yaml
---
tags: [atom, domain, subdomain]
aliases: [termos alternativos para busca]
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: certain | probable | speculative
---
# Título como frase completa descritiva

Conteúdo atômico — 3-10 parágrafos no máximo. Se precisa de mais, split.

## Related
- [[nota-relacionada-1]] — como se conecta
- [[nota-relacionada-2]] — como se conecta
```

## Exemplos de bons átomos

- "Claude Code usa hooks para injeção de contexto no ciclo de vida da sessão"
- "O algoritmo Leiden supera Louvain em qualidade de comunidades para grafos grandes"
- "QMD usa embeddinggemma-300M localmente sem depender de API externa"
- "sqlite-vec substitui ChromaDB com SIMD acceleration e zero processos externos"

## Exemplos de notas que DEVEM SER SPLIT

- ❌ "Graphify e claude-mem e RTK" → 3 átomos separados
- ❌ "Histórico completo do projeto Sinapse Agent" → linha do tempo, não átomo
- ❌ "Todas as decisões de arquitetura de 2026" → cada decisão é um átomo
