---
tags: [atom, loop, protocol, mandatory]
status: active
created: 2026-05-30
updated: 2026-05-30
---

# Agent Loop Protocol

Ciclo de execução obrigatório de 6 etapas:

1. **Analyze Events** — entender pedido + estado atual via session_search
2. **Brain-First Lookup** — consultar vault antes de APIs externas
3. **Select Tool** — UMA tool call por iteração
4. **Observe & Verify** — No Fixes Without Root Cause
5. **Iterate** — até conclusão, sem batch completions
6. **Submit Results** — entrega final

## Regras de Ouro

- **Boil the Lake**: implementação completa, sem atalhos
- **Evidence Before Claims**: testar antes de afirmar
- **User Sovereignty**: Michel decide sempre
- **No Slop**: só o resultado, sem enrolação
- **File Integrity**: write_file/patch/MCP, nunca shell

Links: [[RESOLVER-Skill-Dispatcher]], [[Current State]]
