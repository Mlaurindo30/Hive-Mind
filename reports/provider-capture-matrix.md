# Provider capture matrix (D004-M)

Estado: **IN_PROGRESS**. Este documento é o inventário medido antes da
execução, não o resultado dela. Nenhum provider está classificado `PASS`
ainda, porque `PASS` exige **evento novo** e a cadeia inteira até o UMC.

## Ambiente de destino

Toda a matriz usa o mesmo ambiente descartável já provado em M14: worker
Claude Mem em porta livre, `CLAUDE_MEM_DATA_DIR` temporário, HOME/USERPROFILE/
APPDATA temporários, Ollama local com `qwen2.5:3b` já instalado, IdentityStore
temporária, Claude Mem e UMC temporários, projetos Git A e B temporários.

Nada ativo é tocado: `D:\Hive-Mind`, o worker na 37700, `settings.json`,
setup-brain, config do Ollama, modelos, configs de provider, hooks, outboxes e
bancos históricos ficam como estão.

## Inventário de fontes reais (medido, não presumido)

`hive-mind agents detect`: **9 de 13** providers detectados.

| Provider | Detectado | Fonte real | Arquivos | Fonte mais recente | Situação |
|---|:-:|---|--:|--:|---|
| antigravity | — | `~/.gemini/antigravity-ide/conversations` | 27 | **1,4 h** | fonte viva |
| codex | ✅ | `~/.codex/sessions/**/rollout-*.jsonl` | 156 | 47 h | fonte histórica |
| copilot | ✅ (vscode) | `AppData/Roaming/Code/User/globalStorage` | 2 | 141 h | fonte histórica |
| hermes | — | `AppData/Local/hermes/state.db` | 1 | 5,7 h | fonte histórica |
| kilo | ✅ | `~/.local/share/kilo/kilo.db` | 1 | 46,6 h | fonte histórica |
| mimo | — | `~/.local/share/mimocode/mimocode.db` | 1 | 117 h | fonte histórica |
| qwen | ✅ | `~/.qwen/projects/**` | 9 | 94 h | fonte histórica |
| kimi | ✅ | `~/.kimi/sessions/*/*/context.js` | **0** | — | `NO_SOURCE` |
| roo | ❌ | globalStorage do VS Code | 0 | — | `NOT_INSTALLED` |
| openclaw | ❌ | `~/.openclaw/tasks/runs.sqlite` | 0 | — | `NOT_INSTALLED` |
| swarmclaw | ❌ | `~/.swarmclaw/data/swarmclaw.db` | 0 | — | `NOT_INSTALLED` |
| screenpipe | — | sem padrão de fonte no adapter | 0 | — | `NO_SOURCE` |
| claude | ✅ | captura nativa própria | — | — | linha separada |

**Kiro e Cursor** são detectados pelo registry mas **não têm adapter de
captura** — são alvos de registro MCP, não fontes. Registrado como lacuna a
classificar.

## O que isto já decide

Sete providers têm fonte real utilizável, e **seis delas são históricas** —
horas ou dias atrás. A regra da entrega é explícita: fonte histórica não vira
`PASS` de evento novo. Então `PASS` para esses seis exige **executar uma
sessão mínima** com o CLI do provider, usando a configuração que já existe.

Três providers estão `NOT_INSTALLED` e um está `NO_SOURCE` — nenhum deles
reprova um perfil onde é opcional, o que depende da política do item seguinte.

## Lacuna bloqueante: não existe política de providers obrigatórios

O item 14 pede derivar do registry/manifesto quais providers são obrigatórios
por perfil. **Essa política não existe declarativamente.** O registry
(`hive_mind.agents.registry`) lista 13 providers sem marcar obrigatoriedade, e
o `runtime.yaml` tem perfis (`local-min`, `local-full`) para *serviços*, não
para providers de captura.

Consequência, conforme a instrução: não tratar os 13 como obrigatórios, não
inventar a política durante o teste, e **manter D004 `PARTIAL`** até ela
existir. Subentrega declarativa curta a criar: **D004-P — política de
providers por perfil**.

## Próximo passo exato

Para cada provider com CLI executável (codex, qwen, kimi, gemini), rodar uma
sessão mínima com marcador `HM-D004-M-<provider>-<ts>-<uuid>`, `cwd` num
projeto Git temporário, uma tool call read-only e uma resposta curta — usando
a configuração existente, sem alterar nada. Depois, a cadeia completa até o
UMC, provider a provider.

Para os de IDE/desktop sem automação segura (antigravity, kilo, mimo,
hermes, copilot): se não for possível produzir evento novo sem interação,
classificar `BLOCKED_BY_PROVIDER` com evidência — não converter fonte
histórica em `PASS`.
