# Live provider capture recovery — 2026-07-27

Status: em andamento

## Escopo atual

Este relatório registra o estado real do host depois da restauração do fluxo
de captura em tempo real e depois da limpeza controlada do legado histórico.
Ele não declara conclusão da missão maior de consolidação; serve como snapshot
operacional para as próximas fases de cutover.

## Estado atual do runtime observado

| Campo | Valor |
|---|---|
| Root canônica em uso | `D:\Hive-Mind` |
| Branch ativa | `codex/universal-provider-capture` |
| HEAD ativo | `52a8441b3b661c15a9385a98d042f2e3c70d0277` |
| Outbox histórico | `0` linhas |
| `unclassified/legacy` no UMC | `0` linhas |
| `default` no UMC | `537` linhas |
| `observations` no UMC | `2612` |
| `canonical` no UMC | `2075` |

## Leitura do bloco histórico remanescente `default/ins`

Validação adicional em 27 de julho de 2026:

- as `139` linhas ativas em `workspace_id=default` pertencem todas ao mesmo
  `memory_session_id`;
- a sessão correspondente no `claude-mem.db` tem:
  - `platform_source = codex`
  - `project = ins`
  - `user_prompt = "Instale para voce npx agentic-awesome-skills --codex"`
  - janela: `2026-07-16T15:15:22.648Z` até `2026-07-16T15:20:50.393Z`
- o registry canônico atual não declara alias para `ins`.

Conclusão operacional:

- `default/ins` não é backlog ativo do runtime;
- `default/ins` é um bloco histórico de label livre preservado de propósito;
- qualquer migração futura desse bloco exige regra canônica explícita; o
  migrador controlado atual não deve adivinhar destino.

## Evidência de componentes ativos

| Componente | PID | Origem |
|---|---:|---|
| `capture-realtime` | `41912` | runtime canônico |
| `supervisor.js` | `41960` | `D:\Hive-Mind\npm\lib\supervisor.js` |
| `sinapse-api.py` | `39744` | runtime canônico |
| `sinapse-mcp-http.py` | `39404` | runtime canônico |
| `graphify watch launcher` | `48236` | watchdog/supervisor canônico |
| `graphify watch` | `51184` | runtime canônico |

## Leitura operacional

No snapshot atual deste host, a leitura forte já não é mais “runtime duplicado”.
O que está provado agora é:

- os launchers de bootstrap observados apontam para `D:\Hive-Mind`;
- o auditor de runtime path retorna `findings = []`;
- o validador pós-reboot mantém `canonical_runtime_paths = true`.

O risco remanescente não é um segundo runtime operacional ativo comprovado, e
sim o fato de a task protegida `HiveMind-Supervisor` ainda existir como wrapper
legado compatível em vez de definição regravada in-place.

## Tarefas agendadas ainda relevantes

| Task | Launcher |
|---|---|
| `HiveMind-Backup` | `D:\Hive-Mind\.venv\Scripts\hive-mind.exe backup run --apply` |
| `HiveMind-ClaudeMemBridge` | `python.exe D:\Hive-Mind\scripts\services\claude_mem_bridge.py` |
| `HiveMind-DreamCycle` | `python.exe D:\Hive-Mind\scripts\dream\dream_cycle.py` |
| `HiveMind-KnowledgeHealth` | `python.exe D:\Hive-Mind\scripts\health\audit_memory.py` |
| `HiveMind-PostRebootValidation` | `python.exe D:\Hive-Mind\scripts\health\validate_after_reboot_windows.py` |
| `HiveMind-Supervisor` | `wscript.exe ... start-windows-supervisor-hidden.vbs` |
| `HiveMind-Supervisor-Watchdog` | `powershell.exe ... start-windows-supervisor-watchdog.ps1` |

## Atualização do bootstrap Windows

Validação aplicada em 27 de julho de 2026:

- a task protegida `HiveMind-Supervisor` continua em `wscript.exe`, mas o
  wrapper `start-windows-supervisor-hidden.vbs` aponta para a mesma raiz
  canônica `D:\Hive-Mind` e apenas encadeia
  `scripts\setup\start-windows-supervisor.ps1`;
- a task `HiveMind-Supervisor-Watchdog` também aponta para `D:\Hive-Mind`;
- o registrador nativo foi ajustado para tratar esse wrapper legado como
  compatível com o bootstrap canônico;
- depois da reaplicação do registrador, o fallback redundante em Startup
  (`HiveMind-Supervisor-Watchdog.cmd`) deixou de existir.

Leitura operacional atual:

- ainda não há reescrita in-place da task protegida;
- porém o host não depende mais de um fallback extra de Startup para manter a
  raiz canônica;
- isso reduz uma fonte de bootstrap redundante sem tocar na task protegida.

## Validação pós-reboot do runtime canônico

Execução validada em 27 de julho de 2026:

- `D:\Hive-Mind\.venv\Scripts\python.exe D:\Hive-Mind\scripts\health\validate_after_reboot_windows.py`
- relatório gerado:
  [post-reboot-validation.json](D:\Hive-Mind\logs\post-reboot-validation.json)

Resultado:

- `status = pass`
- `scheduled_supervisor = true`
- `services_healthy = true`
- `canonical_runtime_paths = true`
- `unhealthy_required_services = []`

Leitura operacional:

- todos os serviços obrigatórios declarados para o perfil atual `local-full`
  ficaram `healthy`;
- o auditor de runtime paths não encontrou nenhuma referência operacional a
  roots não canônicas do Hive-Mind;
- isso reduz bastante a incerteza sobre o cutover real já ativo em
  `D:\Hive-Mind`.

## Situação dos providers

Estado atual comprovado em 27 de julho de 2026:

- o fluxo novo voltou a capturar;
- Claude Mem voltou a receber;
- o bridge e o UMC estão aceitando entradas novas com identidade canônica;
- o backlog antigo inseguro foi saneado sem drenar dados históricos vivos.

### Matriz objetiva de providers no host canônico

Providers com fonte real encontrada e prova atual de ingestão (`validate agents = PASSED`):

- `antigravity`
- `codex`
- `copilot`
- `hermes`
- `kilo`
- `kimi`
- `mimo`
- `qwen`

Providers sem prova atual de fonte real no host (`validate agents = SKIPPED`):

- `openclaw`
  - há diretório `C:\Users\miche\.openclaw`, mas não há `tasks\runs.sqlite`
- `roo`
  - não há `ui_messages.json` nas localizações reais esperadas do Roo/Cline
- `screenpipe`
  - adapter é `timer/REST`; nenhuma fonte viva foi comprovada neste host
- `swarmclaw`
  - não há `data\swarmclaw.db`

Leitura correta desta matriz:

- `SKIPPED` aqui não significa “quebrado”;
- significa “não existe fonte real suficiente neste host, nesta data, para
  provar captura operacional end-to-end”.

Ainda não comprovado nesta etapa:

- revalidação individual de todos os providers esperados após cutover único;
- substituição in-place da task protegida `HiveMind-Supervisor`.

## Próximo bloco obrigatório

Antes de qualquer declaração de conclusão, ainda falta:

1. preservação externa completa da raiz e das worktrees;
2. comparação `ACTIVE` versus `DEVELOPMENT`;
3. consolidação do código canônico;
4. staging verde sem paths proibidos;
5. cutover único do runtime;
6. revalidação provider por provider no runtime consolidado.
