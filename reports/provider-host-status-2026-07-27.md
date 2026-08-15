# Provider host status — 2026-07-27

Status: snapshot atual do host, não fechamento final da missão

## Regra desta matriz

Esta matriz usa somente evidência atual do host e separa:

- providers com prova atual de captura/ingestão no host (`WORKING`);
- integrações detectadas no host, mas que hoje são apenas alvo de
  registro/MCP na arquitetura local (`NOT_A_CAPTURE_SOURCE`);
- integrações ausentes ou sem fonte real suficiente para prova local
  (`NOT_INSTALLED` / `NOT_CONFIGURED`).

## Evidência usada

- `hive-mind validate agents --json`
- `hive-mind agents detect --json`
- leitura atual de `~/.claude-mem/claude-mem.db`
- matriz histórica `reports/provider-capture-matrix.json`

## Matriz atual

| Provider/surface | Lane | Host evidence | Status | Leitura |
|---|---|---|---|---|
| `claude` | native | `command: claude`; `sdk_sessions.platform_source='claude'` existe com atividade recente no `claude-mem.db` | `WORKING` | lane nativa; fora do `validate agents` universal |
| `codex` | universal | `validate agents = PASSED`; `agents detect = command: codex` | `WORKING` | captura/ingestão atual provada |
| `qwen` | universal | `validate agents = PASSED`; `agents detect = command: qwen` | `WORKING` | captura/ingestão atual provada |
| `kimi` | universal | `validate agents = PASSED`; `agents detect = command: kimi` | `WORKING` | captura/ingestão atual provada |
| `kilo` | universal | `validate agents = PASSED`; `agents detect = path: C:\Users\miche\.kilocode` | `WORKING` | captura/ingestão atual provada |
| `copilot` | universal | `validate agents = PASSED`; `agents detect = command: code` / VS Code presente | `WORKING` | fonte real de captura atual provada |
| `antigravity` | universal | `validate agents = PASSED` | `WORKING` | fonte real de captura atual provada |
| `hermes` | universal | `validate agents = PASSED` | `WORKING` | fonte real de captura atual provada |
| `mimo` | universal | `validate agents = PASSED` | `WORKING` | fonte real de captura atual provada |
| `openclaw` | universal | `validate agents = SKIPPED`; `agents detect = false` | `NOT_INSTALLED` | sem fonte real utilizável no host atual |
| `roo` | universal | `validate agents = SKIPPED`; `agents detect = false` | `NOT_INSTALLED` | sem fonte real utilizável no host atual |
| `screenpipe` | universal | `validate agents = SKIPPED`; adapter timer/REST sem fonte viva provada no host | `NOT_CONFIGURED` | sem fonte local concreta para prova end-to-end |
| `swarmclaw` | universal | `validate agents = SKIPPED`; `agents detect = false` | `NOT_INSTALLED` | sem fonte real utilizável no host atual |
| `gemini` | registration-only | `agents detect = command: gemini`; `registration_only` na matriz histórica | `NOT_A_CAPTURE_SOURCE` | integração de registro/MCP, sem canary universal próprio |
| `kiro` | registration-only | `agents detect = path: C:\Users\miche\.kiro`; `registration_only` na matriz histórica | `NOT_A_CAPTURE_SOURCE` | integração de registro/MCP, sem canary universal próprio |
| `cursor` | registration-only | `agents detect = path: C:\Users\miche\.cursor`; `registration_only` na matriz histórica | `NOT_A_CAPTURE_SOURCE` | integração de registro/MCP, sem canary universal próprio |
| `vscode` | registration-only | `agents detect = command: code`; `registration_only` na matriz histórica | `NOT_A_CAPTURE_SOURCE` | alvo de registro, não provider separado no canary |
| `opencode` | registration-only | `agents detect = false`; `registration_only` na matriz histórica | `NOT_INSTALLED` | integration target ausente no host |

## Leitura correta

- `WORKING` aqui significa que há prova atual de captura/ingestão no host para
  o provider correspondente, ou lane nativa atual no caso de `claude`.
- `NOT_A_CAPTURE_SOURCE` não significa “produto quebrado”; significa que, na
  arquitetura atual do Hive-Mind, esse item não entra como fonte separada no
  canary universal de captura.
- `NOT_INSTALLED` / `NOT_CONFIGURED` não significam regressão automática do
  Hive-Mind; significam ausência de fonte real suficiente para promover esses
  itens a `WORKING` hoje.

## O que ainda continua fora de prova final

Esta matriz ainda não fecha:

- superfícies separadas como “Qwen Desktop” versus “Qwen CLI” quando o adapter
  atual mede o provider unificado `qwen`;
- revalidação manual de IDE/app quando a única geração do evento depende de
  interação humana mínima;
- promoção dos itens hoje `NOT_INSTALLED` / `NOT_CONFIGURED` para `WORKING`
  sem que a fonte real exista de fato no host.
