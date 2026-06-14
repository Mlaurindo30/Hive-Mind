# Sinapse Agent — Test Suite

## Estrutura

```
tests/
├── smoke/
│   └── test_smoke.sh              # Smoke tests (diagnóstico rápido)
├── fixtures/
│   ├── sample_graph.json          # Knowledge graph mínimo
│   └── sample_vault/              # Vault de exemplo
├── unit/
│   ├── test_backend_graphify.py   # U1: Backend Graphify
│   ├── test_backend_claude_mem.py # U2: Backend claude-mem
│   ├── test_backend_nmem.py       # U3: Backend NeuralMemory
│   ├── test_write_helpers.py      # U4: Helpers de escrita
│   ├── test_query_engine.py       # U5: Motor de busca
│   └── test_format_context.py     # U6: Formatação de contexto
├── integration/
│   ├── test_read_flow.py          # I1: Fluxo de leitura
│   ├── test_write_read_cycle.py   # I2: Ciclo escrita/leitura
│   ├── test_mcp.py                # I3: Interface MCP/plugin
│   └── test_cron.py               # I4: Interação cron/build
├── e2e/
│   ├── test_full_session.py       # E1: Ciclo completo de sessão
│   ├── test_degradation.py        # E2: Degradação graceful
│   ├── test_concurrency.py        # E3: Concorrência
│   ├── test_recovery.py           # E4: Recuperação de falhas
│   └── test_edge_cases.py         # E5: Casos de borda
└── run_all.sh                     # Runner completo
```

## Como rodar

### Smoke tests (rápido, < 5 min)
```bash
bash tests/smoke/test_smoke.sh
```

### Testes unitários
```bash
uv run pytest tests/unit/ -v
```

### Testes de integração (requer backends reais)
```bash
HIVE_RUN_INTEGRATION=1 uv run pytest tests/integration/ -v
```

### Testes end-to-end (sistema completo)
```bash
uv run pytest tests/e2e/ -v
```

### Suite completa
```bash
./tests/run_all.sh
```

## Fixtures

| Fixture | Scope | Descrição |
|---------|-------|-----------|
| `sample_graph` | function | Knowledge graph com 5 nodes e 3 edges |
| `temp_vault` | function | Diretório temporário isolado para testes de escrita |
| `sample_graph_file` | function | sample_graph salvo em arquivo temporário |

## Convenções

- **Nomes de classe**: `Test<NomeDoComponente>` (ex: `TestBackendGraphify`)
- **Nomes de método**: `test_<descricao_snake_case>` (ex: `test_graph_json_missing`)
- **Docstrings**: Primeira linha descreve o que o teste verifica com o ID (ex: `U1.1: descrição`)
- **IDs de teste**: `U{n}.{m}` (unitário), `I{n}.{m}` (integração), `E{n}.{m}` (E2E)
- **Mocking**: `monkeypatch.setattr()` para módulo; `unittest.mock.patch()` para stdlib

## Como adicionar novos testes

1. Identifique a suíte correta (unit/integration/e2e)
2. Crie classe `Test<Nome>` no arquivo correspondente
3. Use fixtures de `tests/conftest.py` para `temp_vault` e `sample_graph`
4. Use `monkeypatch.setattr("sinapse_memory.CONSTANTE", valor)` para injeção
5. Execute `uv run pytest tests/unit/test_meu_teste.py -v` para validar
