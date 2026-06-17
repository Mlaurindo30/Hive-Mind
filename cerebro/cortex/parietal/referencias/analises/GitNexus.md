---
tags: [analise, gitnexus, knowledge-graph, codebase]
domain: ferramentas
status: rejeitada
created: 2026-05-24
---

# Análise Fria: GitNexus

**Avaliador:** Thoth (orquestrador THOTH AI)
**Para:** Ecossistema Thoth + panteão de subagentes
**Data:** 2026-05-24
**Status:** rejeitada (já temos stack superior e mais integrada)

## Veredito

Não adotar. O GitNexus é um knowledge graph de codebase client-side com Graph RAG Agent embutido. O Sinapse Agent já cobre 90%+ das funcionalidades com Graphify (knowledge graph estrutural, Leiden clustering) + claude-mem smart tools (tree-sitter AST parsing). Adicionar GitNexus seria redundância com pior integração.

## O que é / O que faz

GitNexus é um motor de inteligência de código zero-servidor. Roda no browser (Web UI) ou via CLI + MCP server. Indexa repositórios GitHub ou ZIP, gera knowledge graph interativo com Graph RAG Agent. 40k stars no GitHub.

**Stack:** TypeScript, LadybugDB (native/WASM), Tree-sitter, React (Web UI)
**Instalação:** `npm install -g gitnexus`
**MCP Server:** `gitnexus serve` expõe tools para Cursor, Claude Code, Codex, etc.
**Escala:** Modo browser limitado a ~5k arquivos; CLI mode sem limite

**Smart Tools pré-computadas:** impacto de mudanças, call chains, clusters, dependências upstream/downstream — tudo pré-calculado no index time.

## Vantagem prática para o projeto THOTH AI

1. **Análise de impacto pré-computada** — blast radius de PRs, call chains, clusters. Mas o Graphify já faz clustering (Leiden) e o claude-mem smart_search rastreia símbolos via tree-sitter.
2. **Graph RAG Agent embutido** — perguntas em linguagem natural sobre a codebase. Mas o Sinapse Agent faz isso com Qdrant + Chroma + FTS5, integrado ao vault.
3. **MCP server nativo** — conecta em qualquer agente MCP-compatível. Mas o Sinapse já tem MCP server (sinapse-mcp.py) com 5 tools.
4. **Zero-servidor** — browser-side, sem infra. Mas o Sinapse já é self-hosted e não depende de browser.

## Risco principal

Fragmentação da memória. Dois knowledge graphs (Graphify + GitNexus) operando em paralelo, sem sincronização, gerando respostas contraditórias entre agentes.

### Riscos específicos

- **Redundância de indexação**: Graphify indexa vault + codebases; GitNexus indexaria de novo, custo duplicado de CPU/tempo
- **Dependência nova**: LadybugDB como storage proprietário, sem caminho de migração claro
- **Modo browser capado**: ~5k arquivos no Web UI, inviável para codebases médias/grandes
- **Manutenção extra**: +1 ferramenta no stack para atualizar, debugar, documentar
- **Concorrência de MCP**: Dois MCP servers expondo tools similares, agente pode chamar o errado

## O que NÃO fazer / NÃO incluir

- NÃO usar como substituto do Graphify — o Graphify é mais integrado ao vault e cobre Obsidian + codebase
- NÃO expor dois MCP servers de knowledge graph simultaneamente ao mesmo agente
- NÃO indexar o vault no GitNexus — o Graphify já faz isso com Leiden clustering otimizado
- NÃO depender do modo browser para codebases de produção (>5k arquivos)

## Plano de adoção recomendado

*Não aplicável — rejeitado. Se houvesse adoção:*

### Fase 1 — Teste em codebase isolado
Indexar um repo cliente pequeno (<5k arquivos), comparar Graphify vs GitNexus na mesma codebase.

### Fase 2 — Integração MCP condicional
Conectar GitNexus MCP apenas em agentes que não têm acesso ao Sinapse (ex: Copilot).

### Rollback
`npm uninstall -g gitnexus && rm -rf ~/.gitnexus`. Nenhum dado do vault é afetado.

## Decisão sugerida

```
## 2026-05-24 — GitNexus rejeitado para THOTH AI
Status: rejeitada
Contexto:
- GitNexus é um knowledge graph de codebase client-side (40k stars)
- Já temos Graphify + claude-mem smart tools + Qdrant + Sinapse MCP
Decisão:
- NÃO adotar GitNexus no stack THOTH AI
Motivo:
- Redundância de 90%+ com stack existente
- Graphify já cobre knowledge graph estrutural com Leiden clustering
- claude-mem smart_search/smart_outline já fazem tree-sitter AST parsing
- Adicionar GitNexus fragmentaria a memória entre dois sistemas incompatíveis
Risco:
- Baixo (não adotar não tem impacto negativo)
Rollback:
- N/A — nada foi instalado
Responsável pela aprovação:
- Michel
```

## Veredito final

GitNexus é uma ferramenta bem executada (40k stars, MCP nativo, Graph RAG Agent) mas é redundante para o ecossistema THOTH AI. O Sinapse Agent já entrega knowledge graph estrutural (Graphify + Leiden clustering), parsing AST (claude-mem tree-sitter), busca semântica (Qdrant + Chroma), e MCP server — tudo integrado ao vault Obsidian. Adicionar GitNexus criaria dois sistemas de memória paralelos e incompatíveis, fragmentando o contexto dos agentes. Não adotar.

## Fontes

- [GitNexus GitHub](https://github.com/abhigyanpatwari/GitNexus)
- [Sinapse Agent — AGENTS.md](cerebro/AGENTS.md)
