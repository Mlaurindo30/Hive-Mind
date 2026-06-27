---
name: sinapse-consulta
description: "Consulta o knowledge graph do Sinapse Agent (Graphify) para buscar conexões entre conceitos, arquivos e decisões no vault Obsidian."
version: 1.0.0
author: Sinapse Agent
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [memory, knowledge-graph, obsidian, sinapse]
  trigger: >
    Quando perguntarem sobre arquitetura, decisões passadas, conexão entre
    conceitos, localização de informação no vault, ou qualquer pergunta
    que comece com "onde está", "como se conecta", "qual a relação entre".
---

# Sinapse — Consulta ao Knowledge Graph

## Overview

Esta skill consulta o knowledge graph gerado pelo Graphify a partir do vault
Obsidian (`cerebro/`). Use-a quando precisar de:

- Relações entre conceitos ("Como X se conecta com Y?")
- Localizar decisões ("Onde está a decisão sobre pricing?")
- Entender a estrutura do conhecimento ("Quais projetos usam Go?")
- Descobrir conexões não óbvias entre áreas do vault

## Como usar

No Hermes, Claude Code, Codex ou OpenCode:

```
/consulta "decisão sobre migração VPS"
/consulta "auth flow database"
/consulta "quais projetos usam TypeScript"
```

## Comando equivalente (terminal)

```bash
cd ~/Documentos/Projects/sinapse_agent
python3 -c "
import json, sys
graph = json.load(open('cerebro/cortex/occipital/grafo/graph.json'))
query = sys.argv[1].lower()

# Busca em nodes
for node in graph.get('nodes', []):
    if query in node.get('name', '').lower():
        print(f\"Node: {node['name']} (tipo: {node.get('type', 'desconhecido')})\")

# Busca em edges
print()
print('Conexões encontradas:')
for edge in graph.get('edges', []):
    if query in str(edge.get('source', '')).lower() or query in str(edge.get('target', '')).lower():
        print(f\"  {edge['source']} → {edge['target']} ({edge.get('relationship', 'relacionado')})\")
" "<query>"
```

## MCP tools disponíveis

Se o MCP server do Graphify estiver rodando, estas tools estão disponíveis:

| Tool | Descrição |
|------|-----------|
| `query_graph(query)` | Busca semântica no grafo completo |
| `get_node(name)` | Detalhes de um nó específico |
| `get_neighbors(name)` | Todos os vizinhos de um nó |
| `shortest_path(a, b)` | Caminho mais curto entre dois conceitos |

## Observações

- O graph.json é regenerado automaticamente (modo watch) quando arquivos
  do vault são modificados
- Primeira execução pode ser lenta (build do grafo). Consultas subsequentes
  são instantâneas
- Se o grafo estiver desatualizado, execute `./scripts/build-graph.sh --force`
