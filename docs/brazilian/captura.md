# Captura

Como o Hive-Mind captura sessões de agentes, normaliza os eventos, entrega com
garantia de durabilidade e decide a qual projeto cada evento pertence.

Público-alvo: quem escreve ou mantém um parser/hook de provider, e quem
diagnostica por que um evento chegou (ou não) ao cérebro.

Referências: [capture/providers.md](capture/providers.md),
[captura.md](captura.md),
[`scripts/capture/capture_events.py`](../scripts/capture/capture_events.py),
[`scripts/capture/capture_queue.py`](../scripts/capture/capture_queue.py).

---

## Caminho canônico

```
provider source → parser → hive_mind.capture.ingest → Claude Mem
```

`ingest` é o **único** lugar que decide a identidade de projeto. Os entrypoints
fornecem **evidências** — um diretório de trabalho, uma raiz de workspace, um
nome de provider, uma surface. Eles não decidem o que o projeto é, e não podem
sobrescrever essa decisão.

Isso é deliberado. Até a entrega D004-R2 o resolver era chamado pelo entrypoint,
o que significava que cada entrypoint tinha que lembrar de chamá-lo. Um chamava
(`capture-realtime.py`), um não (`capture-tailer.py`), e o que não chamava
escrevia rótulos livres direto no campo pelo qual o Claude Mem agrupa. O
resultado medido: texto de prompt virou nome de projeto, e a worktree deste
repositório virou um projeto separado da própria raiz.

---

## Providers universais

A camada de captura é **agnóstica a provider**: qualquer fonte que emita um
`ProviderEvent` normalizado é aceita. Os providers previstos na superfície de
captura são:

```
codex, copilot, hermes, antigravity, kimi, qwen, kilo, roo, vscode/cursor,
opencode, openclaw, swarmclaw
```

A matriz de verificação **por provider ainda não foi executada** (D004): um
evento verde prova o caminho, não os 13 providers. Verificação e aceitação são
colunas independentes — ver [capture/providers.md](capture/providers.md),
seção "Verification is not acceptance" (D004-P). A matriz completa vive em
[`reports/provider-capture-matrix.md`](../reports/provider-capture-matrix.md).

> Relação com o registro MCP: o conjunto de **chaves de agente** registráveis
> (`claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode openclaw
> swarmclaw`) é distinto do conjunto de **providers de captura**. Registrar um
> agente no MCP (ver [agentes.md](agentes.md)) não instala captura, e capturar
> um provider não exige registro MCP — são camadas independentes.

---

## Contrato de evento normalizado

Todo evento de captura vira um `ProviderEvent` imutável, neutro quanto ao
provider, pronto para entrega durável
([`capture_events.py`](../scripts/capture/capture_events.py)).

### Campos

| Campo | Tipo | Obrigatório | Nota |
|---|---|---|---|
| `provider` | `str` | sim | nome do provider que emitiu o evento |
| `session_id` | `str` | sim | identifica a sessão |
| `event_type` | `EventType` | sim | uma das seis categorias abaixo |
| `content` | `str` | sim | o corpo do evento |
| `event_id` | `str` | sim (gerado se omitido) | identidade estável por fallback (hash) |
| `occurred_at` | `str` ISO-8601 UTC | normalizado | sempre convertido para UTC |
| `source_position` | `str` \| `None` | não | posição no arquivo de origem |
| `project` | `str` \| `None` | não | preenchido pela resolução de identidade |
| `cwd` | `str` \| `None` | não | diretório de trabalho |
| `metadata` | `object` \| `None` | não | normalizado (JSON serializável, chaves ordenadas) |

### `EventType`

| Valor | Significado |
|---|---|
| `session_start` | início de sessão |
| `prompt` | prompt do usuário |
| `tool_use` | chamada de ferramenta |
| `tool_result` | resultado de ferramenta |
| `assistant` | resposta do assistente |
| `session_end` | fim de sessão |

### Validação e normalização

- Campos obrigatórios (`provider`, `session_id`, `content`, `event_id`) devem
  ser strings não vazias — senão `ValueError`.
- `occurred_at` aceita `datetime`, string ISO-8601 ou `None`; converte para UTC;
  strings sem fuso são tratadas como UTC; offsets não-UTC são convertidos.
- `event_id`, se omitido, é derivado por SHA-256 canônico de
  `{provider, session_id, event_type, content, source_position}` — estável.
- `metadata` é serializado/resserializado com chaves ordenadas
  (`sort_keys=True`) para garantir forma canônica.

### Chave de deduplicação

`dedupe_key()` é um hash SHA-256 **escopado por provider** de
`{provider, session_id, event_type, event_id}`. É a chave única do outbox — um
evento re-entregue não duplica.

---

## Outbox durável com leases

O `CaptureQueue` ([`capture_queue.py`](../scripts/capture/capture_queue.py))
persiste eventos até que sejam entregues ou movidos a dead-letter.

### Garantias

- **Durabilidade**: SQLite com `journal_mode=WAL`, `synchronous=NORMAL`,
  `busy_timeout=10000`, transações `BEGIN IMMEDIATE`.
- **Deduplicação**: índice `UNIQUE` em `dedupe_key`; re-inserção é ignorada
  (`INSERT OR IGNORE`).
- **Leases**: cada evento é reivindicado por uma instância de fila com
  `claim_owner` (UUID da instância) e `claim_until` (prazo do lease,
  `lease_seconds=30.0` por padrão). Só o dono da reivindicação, com lease não
  expirado, pode marcar entrega/retry/dead-letter.
- **Ordenação por sessão**: um evento só é elegível quando nenhum predecessor
  (mesmo `provider` + `session_id`, `occurred_at`/`id` anterior) está pendente —
  a "cabeça" da sessão é entregue antes do resto.

### Esquema (`capture_outbox`)

| Coluna | Nota |
|---|---|
| `dedupe_key` | chave única de deduplicação |
| `provider`, `session_id`, `occurred_at` | indexados (`capture_outbox_pending`) |
| `payload` | JSON do `ProviderEvent.as_payload()` |
| `attempts` | contador de tentativas (default 0) |
| `next_retry_at` | timestamp do próximo retry (default 0) |
| `last_error` | última mensagem de erro |
| `created_at`, `delivered_at`, `dead_letter_at` | marcos de ciclo de vida |
| `claim_owner`, `claim_until` | lease (adicionados por migração de schema se ausentes) |

### Operações

| Método | Efeito |
|---|---|
| `enqueue(event)` | insere uma vez; retorna `False` se a chave já existe |
| `pending(limit)` | reivindica atomicamente as cabeças de sessão elegíveis |
| `mark_delivered(item_id)` | marca entrega se o lease desta instância estiver válido |
| `mark_retry(item_id, error, retry_at)` | incrementa `attempts`, libera o lease |
| `move_dead_letter(item_id, error)` | para de tentar após falha permanente |
| `health()` | contagem de estados mutuamente exclusivos |

### Estados (`health()`)

| Estado | Significado |
|---|---|
| `pending` | entregável agora, sem predecessor pendente |
| `claimed` | reivindicado (lease não expirado) |
| `retrying` | aguardando `next_retry_at` |
| `blocked` | predecessor da mesma sessão ainda não entregue |
| `delivered` | entregue |
| `dead_letter` | falha permanente, sem novo retry |

---

## Caminho deprecado

O caminho antigo **não deve ser religado** (ADR-004):

```
provider hook → ProviderEvent → CaptureQueue → capture_outbox  (sem drainer)
```

Duas bases de outbox sobreviveram dele, e nenhuma jamais tentou uma entrega —
`attempts=0`, `last_error=0`, `dead_letter_at=0` em todas as linhas. São uma
**fila sem dono**, o que é diferente de uma entrega que falhou.

| Outbox | Linhas | Providers | Escritor | Estado |
|---|---:|---|---|---|
| `<SINAPSE_HOME>/logs/capture-outbox.db` | 2.070 | claude | `capture-hook.py`, ligado em `~/.claude/settings.json` | `LEGACY_ACTIVE_WRITER` — ainda crescendo |
| `~/.claude-mem/capture.db` | 18.579 | codex, antigravity, mimo | `capture-hook.py`, ligado em `~/.codex/hooks.json` | `LEGACY_INACTIVE_WRITER` — nada desde 2026-07-20 |

`~/.claude-mem/capture.db` **não** é o store do Claude Mem, apesar de viver
naquele diretório. O store é `~/.claude-mem/claude-mem.db`, ao lado.

Nenhum escritor foi desabilitado aqui. Removê-los é um cutover, e um cutover é
uma entrega própria. Manutenção dessas bases: `hive-mind backup
archive-historical-outbox` e `hive-mind backup scrub-capture-outbox`
(ambos dry-run por padrão — ver [cli.md](cli.md)).

---

## Identidade canônica de projeto

O Claude Mem indexa e agrupa por `observations.project`. O contrato:

| Campo | Valor |
|---|---|
| `observation.project` | `identity.project_name` — sempre canônico |
| `metadata.project_identity` | o envelope canônico completo |
| `metadata.project_identity.project_id` | `identity.project_id` |
| `metadata.capture.raw_project_label` | o que o parser disse — **apenas auditoria** |

O rótulo do parser **nunca** é autoridade. Nunca é usado como `project`,
`project_id`, `project_name`, `workspace_id`, caminho Markdown, filtro de vetor
ou namespace de grafo. É isso que impede valores como
`preciso-que-verifique-o-por-que`, `shadow-run-clean`, `miche` ou
`Microsoft VS Code` de virarem projetos de novo.

### Os dois campos

| Campo | Significado | Onde vive |
|---|---|---|
| `project_id` | identificador estável para banco, filtros, Dream Cycle e vetores | `observations.workspace_id`; frontmatter `project_id` |
| `project_name` | nome humano exibido na interface | `observations.project`; frontmatter `project_name` |

Worktree, branch, provider e surface são **metadados**, nunca identidade.

### Ordem de resolução

`ProjectIdentityResolver` ([`scripts/capture/project_identity.py`](../scripts/capture/project_identity.py))
aplica, em ordem:

| # | Evidência | Método | Confiança |
|---|---|---|---|
| 1 | projeto explícito fornecido e validado | `explicit` | — |
| 2 | `HIVE_PROJECT_ID` / `HIVE_PROJECT_ROOT` | `environment_id` | — |
| 3 | workspace oficial fornecido pelo aplicativo | — | — |
| 4 | `git rev-parse --show-toplevel` | `git_root` | 0.96 |
| 5 | `git rev-parse --git-common-dir` | `git_common_dir` | 0.96 |
| 6 | remote Git normalizado | `git_remote` | 0.95 |
| 7 | mapa explícito de aliases | `alias_root` | 0.90 |
| 8 | markers conhecidos do projeto | `marker` | 0.80 |
| 9 | `unclassified/<provider>` | `unclassified_provider` | 0.0 |

`Path(cwd).name` **nunca** é identidade canônica.

**Regra do git common dir:** raiz e worktrees que compartilham o mesmo
`git-common-dir` recebem o **mesmo** `project_id`:

```
D:\Hive-Mind                                        → hive-mind
D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install → hive-mind
```

A branch (`codex/control-plane-redesign`) e o nome da worktree
(`hive-mind-windows-zero-install`) ficam apenas em metadados. O `project_name`
também deriva do git common dir — corrigir só o `id` não corrigia nada de
visível, porque o `name` é o campo que o Claude Mem indexa (D004-R2).

### Política de identidade

Uma sessão sem repositório Git **não é erro**. Muita captura legítima acontece
fora de um, e recusá-la perderia dado real para proteger um dropdown.

| Status | Significado | Entrega |
|---|---|---|
| `CLASSIFIED` | identidade resolvida a partir de evidência | permitida |
| `UNCLASSIFIED` | evidência insuficiente; resolve para `unclassified/<provider>` | permitida, sinalizada, health degradado |
| `INVALID` | envelope malformado, inconsistente ou irresolvível | **recusada antes de gravar** |

`UNCLASSIFIED` é determinístico: o mesmo provider com a mesma evidência ausente
sempre produz o mesmo id. É auditável, e nunca toma emprestado um nome de texto
de prompt ou de basename de diretório.

### Validação de envelope

Uma sessão pode chegar com `metadata.project_identity` já anexado — o hook
computa um. O `ingest` **não confia nele às cegas**:

- o schema é validado;
- `project_id` e `resolution_method` são verificados;
- o envelope é comparado com a evidência da mesma sessão;
- os campos são normalizados.

Um envelope que discorda da própria evidência é `INVALID`. Uma sessão sem
envelope é resolvida. De qualquer forma, os dois entrypoints chegam à mesma
resposta, porque a resposta é computada em um único lugar.

### Entrypoints

| Entrypoint | Declarado como | Papel |
|---|---|---|
| `scripts/capture/capture-realtime.py` | serviço `sinapse-capture-realtime` | observa fontes de provider continuamente |
| `scripts/capture/capture-tailer.py` | job `capture-tailer` | varredura periódica dos arquivos de provider |

Ambos importam `hive_mind.capture.ingest`. Nenhum resolve identidade sozinho —
garantido por `tests/unit/test_capture_canonical_identity.py`, que falha se
qualquer um voltar a chamar `attach_project_identity`.

### Projeto ativo vs. projeto mencionado

Mencionar um projeto na conversa **não** o torna o projeto ativo:

```
Qwen aberto em C:\Users\miche\Documents\Qwen, conversa cita Hive-Mind
→ active_project:      unclassified/qwen
→ referenced_projects: [hive-mind]
```

A resolução semântica só ocorre com a política habilitada, acima do limiar
configurado, registrada como `semantic_reference` e auditável. Nunca há
classificação silenciosa. (Correção registrada no CHANGELOG v3.10.1:
"referenced projects no longer activate the primary id".)

### Propagação

```
parser → sessão normalizada → ProjectIdentityResolver
       → capture_core.ingest() → Claude Mem
       → bridge (workspace_id = project_id) → UMC
       → Dream Cycle → Markdown → índices → consulta
```

O bridge ([`core/knowledge/claude_mem_bridge.py`](../core/knowledge/claude_mem_bridge.py))
grava `workspace_id = project_id` e preserva o envelope `project_identity` em
`observations.metadata`.

### Dados legados

Registros anteriores carregam `workspace_id='default'`. Eles **não são
reescritos nem apagados** (ADR-012). Continuam legíveis e são classificados como
`legacy_label`. Para inventariá-los sem alterar nada:

```powershell
hive-mind projects audit
hive-mind projects audit --json
```

---

## Fronteiras

O que esta camada **faz** e o que ela **não faz**:

| Faz | Não faz |
|---|---|
| normaliza e valida eventos de qualquer provider | não decide o projeto fora de `ingest` |
| entrega com durabilidade, lease e dead-letter | não é um banco de memória (o store é o Claude Mem) |
| resolve identidade em um único lugar, a partir de evidência | não usa texto de prompt nem basename como identidade |
| recusa envelope inconsistente antes de gravar | não religa o caminho deprecado (ADR-004) |
| preserva o rótulo do parser apenas para auditoria | não reescreve nem apaga dados legados |

Relacionado:

- [agentes.md](agentes.md) — registro MCP (camada independente da captura)
- [captura.md](captura.md) — o resolver e sua cadeia de precedência
- [pipeline-dados.md](pipeline-dados.md) — o que acontece depois do ingest
-  — D004-R2 e errata
