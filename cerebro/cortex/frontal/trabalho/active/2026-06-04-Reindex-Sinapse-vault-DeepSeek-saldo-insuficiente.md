---
tags: [decision]
status: active
created: 2026-06-04
updated: 2026-06-04
source: hermes-session
---

# Reindex Sinapse vault — DeepSeek saldo insuficiente

## Problema
Cron de reindex do vault Sinapse com Graphify falhou: DeepSeek API retornou 402 (Insufficient Balance). Os 3 chunks semânticos não foram processados. O graphify caiu para AST-only, gerando apenas 394 nodes sem edges.

## Ação
Backup restaurado automaticamente (graph.json.bak → graph.json). Version backup: 1427 nodes, 1476 links, 0 communities (formato mais antigo do Graphify sem Leiden).

## Recomendação
1. Recarregar saldo da DeepSeek OU
2. Trocar backend para Ollama local (qwen2.5-coder:3b) para indexação sem custo recorrente OU
3. Usar `graphify update cerebro/` (sem `--backend`) que só faz AST + regex, suficiente para a maioria dos casos
