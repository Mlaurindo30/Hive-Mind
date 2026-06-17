---
tags: [analise, omniroute, memoria, gateway, proxy]
domain: infraestrutura
status: rejeitada
created: 2026-05-23
---

# Análise Fria: OmniRoute (Memória)

**Avaliador:** Thoth (orquestrador THOTH AI)
**Data:** 2026-05-23
**Status:** rejeitada (não adotar — gateway, não memória. Propósito diferente.)

## Veredito

Não adotar como sistema de memória. O OmniRoute é um gateway de API (roteador multi-provider), não um sistema de memória. O módulo de memória dele é um addon secundário, acoplado ao gateway, com escopo por API key (modelo multi-tenant). O Sinapse Agent é um sistema de memória dedicado, self-hosted, com knowledge graph e vault pessoal. São produtos de categorias diferentes.

## O que é / O que faz

OmniRoute é um gateway AI universal (177 providers, 14 estratégias de roteamento, Node.js + Next.js). O módulo de memória (v3.5) é um subsistema interno com:

- **Extração automática**: regex-based, não-blocking, extrai fatos de respostas LLM
- **Injeção automática**: como system message (ou primeira user message em providers sem system role)
- **4 tipos de memória**: factual, episódica, procedural, semântica
- **Storage**: SQLite (primário) + FTS5 full-text + Qdrant opcional (vetores)
- **Upsert semantics**: evita crescimento ilimitado (merge por chave)
- **Escopo**: por API key (não por usuário), com session_id opcional

Arquitetura: `Client → /v1/chat/completions → resolveMemoryOwnerId → retrieveMemories → injectMemory → provider → extractFacts (non-blocking) → createMemory`

## Comparação: Memória OmniRoute vs Sinapse Agent

| Dimensão | OmniRoute (módulo memória) | Sinapse Agent (nosso) |
|---|---|---|
| **Categoria** | Gateway AI com addon de memória | Sistema de memória dedicado |
| **Propósito** | Roteamento multi-provider + memória como feature | Memória universal para agentes |
| **Extração** | Regex em respostas LLM (leve, limitado) | Hooks de plugin (post_tool_call, pre_gateway_dispatch) |
| **Tipos de memória** | 4 tipos (factual, episódica, procedural, semântica) | 4 camadas (estrutural, temporal, executiva, associativa) |
| **Knowledge Graph** | ❌ Não tem | ✅ Graphify + Leiden clustering (1266 nodes) |
| **Vault** | ❌ Não tem (SQLite raw) | ✅ Obsidian com frontmatter + WikiLinks |
| **Memória associativa** | ❌ Não tem | ✅ NeuralMemory com 24 relações |
| **Vetores** | ✅ Qdrant (opcional) | ✅ Chroma via claude-mem |
| **FTS5** | ✅ SQLite FTS5 | ✅ claude-mem FTS5 |
| **Escopo** | Por API key (multi-tenant) | Pessoal (agente único) |
| **Self-hosted** | Sim (local) | Sim (local) |
| **Stack** | Node.js + Next.js + SQLite | Python + TypeScript + Obsidian |
| **Interface** | API REST + MCP (29 tools) + Dashboard | Plugin Hermes + MCP server + CLI |
| **Extração automática** | ✅ Regex não-blocking | ✅ Hooks automáticos |
| **Upsert/merge** | ✅ Por chave | ❌ Appends (pode crescer) |

## Vantagem prática para o projeto THOTH AI

Nenhuma como sistema de memória. Como gateway, 1 vantagem marginal:

1. **Gateway multi-provider** — O OmniRoute como gateway poderia rotear entre providers pros subagentes. Mas isso é categoria diferente de memória. E já temos o Hermes com seu próprio roteamento de providers.

## Risco principal

Confusão de categorias. OmniRoute é gateway que tem um módulo de memória simples. Sinapse é sistema de memória que não é gateway. Tentar usar OmniRoute como memória é como usar um canivete suíço como machado — faz, mas não é pra isso que serve.

### Riscos específicos

- **Memória acoplada ao gateway**: se o gateway cair, a memória cai junto
- **Regex extraction é frágil**: depende de padrões no texto. Perde nuances que hooks capturam
- **Sem knowledge graph**: não faz clustering, não entende relações entre conceitos
- **Stack diferente**: Node.js + Next.js vs nosso Python-first. Mais uma dependência complexa
- **Escopo API key**: modelo mental diferente do nosso (pessoal, não multi-tenant)

## O que NÃO fazer / NÃO incluir

- Não substituir Sinapse Agent por OmniRoute (categorias diferentes)
- Não usar OmniRoute como "memória" quando ele é primariamente um gateway
- Não adicionar Node.js + Next.js + SQLite + Qdrant como dependência de memória

## O que podemos COPIAR do OmniRoute (sem adotar)

- **Upsert semantics**: merge por chave em vez de append. Evita crescimento infinito de memórias repetidas. Podemos implementar no claude-mem
- **Expiração de memórias**: `expires_at` para fatos temporais. Bom para decisões que perdem relevância
- **Extração regex como fallback**: complementar aos hooks, para capturar fatos em respostas normais

## Decisão sugerida

```
## 2026-05-23 — OmniRoute (módulo de memória) rejeitado para THOTH AI
Status: rejeitada
Contexto:
- OmniRoute é um gateway AI multi-provider com módulo de memória integrado
- Nosso Sinapse Agent é um sistema de memória dedicado com knowledge graph
Decisão:
- Não adotar OmniRoute como sistema de memória
- Manter Sinapse Agent como stack de memória principal
- Copiar ideias pontuais: upsert semantics e expiração de memórias para roadmap do claude-mem
Motivo:
- Categorias diferentes: gateway vs sistema de memória
- Memória do OmniRoute é regex-based e acoplada ao gateway — frágil e limitada
- Sinapse já cobre todas as funcionalidades de memória com mais profundidade
Risco:
- Nenhum em não adotar
Responsável pela aprovação:
- Michel
```

## Veredito final

O OmniRoute é um produto impressionante como gateway AI (177 providers, 14 estratégias de roteamento, dashboard completo). Mas como sistema de memória, é um addon simples — extração por regex, SQLite com FTS5, sem knowledge graph. O Sinapse Agent já faz tudo isso com mais profundidade (Graphify com Leiden clustering, NeuralMemory com 24 relações, hooks automáticos em vez de regex). A única coisa que o OmniRoute faz melhor como memória é upsert por chave (evita duplicação) e expiração de fatos — podemos copiar essas ideias sem adotar o sistema inteiro.

**Resumo seco:** gateway excelente, memória básica. Não substitui nem complementa o Sinapse. Passar.

## Fontes

- [OmniRoute GitHub](https://github.com/diegosouzapw/OmniRoute)
- [OmniRoute Memory System docs](https://github.com/diegosouzapw/OmniRoute/blob/main/docs/frameworks/MEMORY.md)
- [OmniRoute site](https://omniroute.online/)
