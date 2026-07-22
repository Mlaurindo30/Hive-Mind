# Provider capture matrix (D004-M / D004-P)

HEAD `59a23c2` · 2026-07-22 22:15 UTC

Duas colunas independentes, e a distinção é o ponto:

- **Verification** é prova técnica — `PASS` significa que a cadeia inteira foi
  comprovada *nesta rodada*.
- **Acceptance** é decisão de aceite — `OK` significa que o provider não
  bloqueia o fechamento do Hive-Mind.

Um provider pode não ter `PASS` e ainda assim estar `OK`: indisponibilidade
externa não é defeito nosso. Só bloqueia quem tem defeito no código do
Hive-Mind.

## Matriz

| Provider | Lane | Verification | Acceptance | Evidência / causa |
|---|---|---|---|---|
| codex | universal | PASS | **OK** | cadeia completa nesta rodada: sessão de CLI real, fonte nova, observation, workspace_id=local/25bc6535d00d, BRIDGED, dedupe 0 |
| qwen | universal | PASS | **OK** | cadeia completa nesta rodada: workspace_id=local/f1ce69efa5a3, BRIDGED, dedupe 0 |
| claude | **native** | evidência operacional | **OK** | captura nativa do Claude Mem, em uso; não passa pelo adapter universal e não entra no denominador |
| kilo | universal | BLOCKED_BY_PROVIDER | **OK_EXTERNAL** | funcionamento confirmado pelo usuário; `kilo run` sem TTY não executa o prompt — limitação da CLI, não da captura |
| copilot | universal | BLOCKED_BY_PROVIDER | **OK_EXTERNAL** | funcionamento confirmado pelo usuário; CLI não produz fonte automatizável |
| antigravity | universal | BLOCKED_BY_PROVIDER | **OK_EXTERNAL** | funcionamento confirmado pelo usuário; sem CLI, fonte só pela IDE |
| kimi | universal | BLOCKED_BY_PROVIDER | **OK_EXTERNAL** | sem modelo/login configurado para execução; nenhum defeito demonstrado no adapter |
| mimo | universal | BLOCKED_BY_PROVIDER | **OK_NOT_REQUIRED** | ausente do registry e do runtime.yaml — não é provider ativo deste deployment |
| hermes | universal | BLOCKED_BY_PROVIDER | **OK_NOT_REQUIRED** | idem; CLI expõe curator/mcp, sem modo de prompt |
| roo | universal | NOT_INSTALLED | **OK_NOT_REQUIRED** | não detectado |
| openclaw | universal | NOT_INSTALLED | **OK_NOT_REQUIRED** | não detectado |
| swarmclaw | universal | NOT_INSTALLED | **OK_NOT_REQUIRED** | não detectado |
| screenpipe | universal | NO_SOURCE | **OK_NOT_REQUIRED** | adapter sem padrão de fonte; não configurado como fonte ativa |

Verification: BLOCKED_BY_PROVIDER 6 · NOT_INSTALLED 3 · NO_SOURCE 1 · PASS 2 · evidência operacional 1

Acceptance: OK 3 · OK_EXTERNAL 4 · OK_NOT_REQUIRED 6

**Nenhum `BLOCK`.** Nenhum defeito do Hive-Mind aberto.

## REGISTRATION_ONLY

Agentes do registry sem adapter de captura — alvos de registro MCP, não
fontes: `cursor`, `gemini`, `kiro`, `opencode`, `vscode`.

`claude` aparece na matriz por lane própria: registro MCP **e** captura
nativa são coisas distintas, e listá-lo só como REGISTRATION_ONLY escondia
a segunda.

## Política de aceite (D004-P)

| Situação | Acceptance |
|---|---|
| cadeia comprovada | `OK` |
| bloqueio externo: crédito, quota, login, modelo não configurado, CLI não interativa, IDE apenas | `OK_EXTERNAL` |
| provider ausente ou não configurado neste deployment | `OK_NOT_REQUIRED` |
| defeito no código do Hive-Mind: parser, ingest, identidade, registry, transporte, bridge, UMC, dedupe | `BLOCK` |

`OK_EXTERNAL` **não** afirma que o canário completo passou. Diz que o que
faltou está fora do nosso alcance.

Um provider sem adapter fica fora do escopo da captura universal. Um provider
não instalado não reprova o deployment. Só falha atribuída ao nosso código
bloqueia D004.

## Defeitos do Hive-Mind, encontrados e corrigidos

Os dois só apareceram com provider real:

1. `mark_posted` dependia de `emitted > 0`. `emit` conta conteúdo *novo*, não
   entrega — a primeira sessão real do Codex entregou a observation e ficou
   `PENDING` para sempre.
2. O shim `capture_core` não re-exportava `SESSION_CUTOFF_MS`, e os parsers
   do kilo e do mimo quebravam na primeira fonte real.

Ambos corrigidos, com teste. Nenhum outro defeito nosso conhecido em aberto.
