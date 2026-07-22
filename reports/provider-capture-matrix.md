# Provider capture matrix (D004-M)

Executada em 2026-07-22 21:44 UTC · HEAD `8426c50`

Ambiente descartável: worker Claude Mem em porta livre, `CLAUDE_MEM_DATA_DIR`,
HOME/USERPROFILE/APPDATA, IdentityStore, Claude Mem e UMC todos temporários;
Ollama local com `qwen2.5:3b` já instalado. Nada ativo alterado.

## Capture providers

| Provider | Instalado | Evento novo | Observation | UMC | Status | Causa |
|---|:-:|:-:|:-:|:-:|---|---|
| codex | sim | sim | sim | sim | **PASS** | cadeia completa; workspace_id=local/25bc6535d00d, BRIDGED, dedupe 0 |
| qwen | sim | sim | sim | sim | **PASS** | cadeia completa; workspace_id=local/f1ce69efa5a3, BRIDGED, dedupe 0 |
| kimi | sim | não | — | — | **FAIL** | AUTHENTICATION: `No model configured. Run kimi and use /login`. Login proibido nesta entrega |
| kilo | sim | não | — | — | **BLOCKED_BY_PROVIDER** | `kilo run` sai 0 sem executar o prompt com stdin fechado; marcador ausente em 3.057 linhas do kilo.db |
| mimo | sim | não | — | — | **BLOCKED_BY_PROVIDER** | `mimo run` idem; marcador ausente em 7.588 linhas do mimocode.db |
| copilot | sim | não | — | — | **BLOCKED_BY_PROVIDER** | `copilot -p` sai 0 sem produzir fonte nova no globalStorage |
| antigravity | sim | não | — | — | **BLOCKED_BY_PROVIDER** | sem CLI; fonte só é produzida pela IDE, exige interação |
| hermes | sim | não | — | — | **BLOCKED_BY_PROVIDER** | CLI existe mas expõe curator/mcp; sem modo de prompt não-interativo |
| roo | não | — | — | — | **NOT_INSTALLED** | não detectado; globalStorage ausente |
| openclaw | não | — | — | — | **NOT_INSTALLED** | não detectado; runs.sqlite ausente |
| swarmclaw | não | — | — | — | **NOT_INSTALLED** | não detectado; swarmclaw.db ausente |
| screenpipe | — | — | — | — | **NO_SOURCE** | adapter sem padrão de fonte declarado |

**12 adapters de captura.** BLOCKED_BY_PROVIDER: 5 · FAIL: 1 · NOT_INSTALLED: 3 · NO_SOURCE: 1 · PASS: 2

## REGISTRATION_ONLY (fora do denominador)

Agentes do registry **sem adapter de captura**. São alvos de registro MCP,
não fontes, e não recebem PASS/FAIL/NO_SOURCE/BLOCKED_BY_PROVIDER.

| Agente |
|---|
| claude |
| cursor |
| gemini |
| kiro |
| opencode |
| vscode |

`claude` tem captura nativa própria e não passa pelo adapter universal —
produzir evento novo por ela exige uma sessão de Claude Code, que não pode
ser isolada com segurança nesta rodada.

## Defeitos do Hive-Mind corrigidos durante a matriz

Ambos só apareceram com provider real; nenhum teste sintético os pegava.

1. **`mark_posted` condicionado à contagem do `emit`.** `emit` conta conteúdo
   *novo*, não entrega. A primeira sessão real do Codex entregou a observation
   e ficou `PENDING` para sempre, e o bridge não podia avançá-la.
2. **O shim `capture_core` não re-exportava `SESSION_CUTOFF_MS`.** Ficou de
   fora quando o motor mudou para o pacote (D004-R2); os parsers do kilo e do
   mimo quebravam com `AttributeError` na primeira fonte real.

## Comandos executados

Uma sessão mínima por CLI, com a configuração existente, em projeto Git
temporário, com uma leitura read-only de `canary.txt`:

```
codex exec "<marcador> …"
qwen  -p   "<marcador> …"
kimi  -p   "<marcador> …"
kilo  run  "<marcador> …"
mimo  run  "<marcador> …"
copilot -p "<marcador> …" --allow-all-tools
```

Nenhum modelo trocado, nenhum login, nenhuma config editada, nenhum backlog tocado.

## Próximo trabalho

`kimi` é o único FAIL, e a causa é externa (sem modelo configurado). Os cinco
`BLOCKED_BY_PROVIDER` precisam de um modo não-interativo que o provider não
oferece hoje — não de código Hive-Mind. Nenhuma subentrega `D004-M-<PROVIDER>`
é necessária: não há defeito nosso pendente.
