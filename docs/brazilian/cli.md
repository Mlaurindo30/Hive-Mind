# CLI — `hive-mind`

> **Hive-Mind v3.10.1** — referência completa do CLI nativo do control plane.
> Entry point: [cli.py](../src/hive_mind/cli.py) (argparse). A versão vem de
> `pyproject.toml::project.version` via `importlib.metadata` (fonte única de
> verdade, casada com o wheel).
>
> Referências: [runtime.md](runtime.md) (daemon/serviços/scheduler),
> [instalacao.md](instalacao.md), [operacao.md](operacao.md).

---

## 1. Visão geral

```powershell
hive-mind --version            # "hive-mind 3.10.1"
hive-mind --help               # ajuda do parser
hive-mind <comando> [subcomando] [opções]
```

Princípios transversais do CLI:

- **Dry-run por padrão** em tudo que muta: `register`/`unregister`,
  `windows-jobs`, `windows-runtime`, `backup run`, `vault repair-*`,
  `backup scrub-*`, `projects migrate-legacy`, `archive-topology`. Nada é
  escrito sem `--apply`.
- **`--json`** em quase todos os subcomandos para saída machine-readable.
- **`--project-root <dir>`** para resolver os arquivos do projeto a partir de
  outro lugar (default: auto-detecção — ver §1.1).

### 1.1 Resolução do project root

A resolução tenta, em ordem: `--project-root` → `HIVE_MIND_HOME` (ou
`SINAPSE_HOME`) → arquivo `project-root` no user config dir → subir diretórios
a partir do CWD procurando marcadores (`pyproject.toml`, `AGENTS.md`,
`config/sinapse.yaml`; ≥ 2 presentes). Falha com `ProjectRootNotFound` e exit
`78` (`EX_CONFIG`).

### 1.2 Exit codes

| Código | Significado |
|---|---|
| `0` | Sucesso. Em `doctor`/`--check`: todo provider **detectado** está configurado |
| `1` | Diagnóstico incompleto / falha / arquivo ausente |
| `2` | Chave de agente desconhecida / uso inválido |
| `69` | `EX_UNAVAILABLE` (daemon managed não implementado na fatia) |
| `78` | `EX_CONFIG` (project root não resolvido) |

---

## 2. Tabela-mestre de comandos

| Grupo | Subcomandos | Propósito |
|---|---|---|
| `project-root` | — | Imprime o project root resolvido |
| `projects` | `audit`, `migrate-legacy` | Inspeciona/migra identidade canônica de projeto |
| `config` | `validate`, `show` | Manifesto declarativo `config/runtime.yaml` |
| `service` | `status`, `ping`, `windows-jobs`, `windows-runtime`, `manifest` | Estado do daemon e tarefas Windows |
| `doctor` | — | Diagnóstico read-only das integrações de agentes |
| `agents` | `detect`, `list`, `register`, `doctor`, `unregister` | Detecção e gestão de integrações de agentes |
| `validate` | `agents`, `delivery`, `topology`, `vault` | Validação do pipeline contra dados reais |
| `vault` | `repair-frontmatter`, `repair-project-id`, `repair-encoding` | Manutenção controlada do vault |
| `backup` | `run`, `status`, `verify`, `restore`, `archive-historical-outbox`, `scrub-capture-outbox`, `scrub-runtime-artifacts`, `scrub-env-backups`, `archive-topology`, `cleanup-topology-stale` | Backup verificado + saneamento de dados legados |
| `implementation` | `status`, `validate` | Estado/vigência dos documentos de implementação |

---

## 3. `hive-mind project-root`

```powershell
hive-mind project-root [--project-root <dir>]
```

Imprime o caminho absoluto do project root resolvido. Exit `78` se não
resolver.

---

## 4. `hive-mind projects`

### 4.1 `projects audit`

Inventário **read-only** de rótulos de projeto legados (não altera dados).

| Opção | Descrição |
|---|---|
| `--claude-mem-db <path>` | SQLite claude-mem (read-only) |
| `--hive-db <path>` | SQLite Hive-Mind (read-only) |
| `--vault-root <path>` | Raiz do vault Markdown (read-only) |
| `--registry <path>` | Registro canônico de aliases de projeto |
| `--json` | JSON |

### 4.2 `projects migrate-legacy`

Migração controlada de linhas legadas do UMC — **dry-run por padrão**.

| Opção | Descrição |
|---|---|
| `--claude-mem-db <path>` | SQLite claude-mem para recuperar labels de sessão preservados |
| `--hive-db <path>` | SQLite Hive-Mind a inspecionar/mutar |
| `--registry <path>` | Registro canônico de aliases |
| `--source-workspace <w>` | Bucket legado a inspecionar (default `unclassified/legacy`) |
| `--target-project <id>` | Restringe a um único `project_id` canônico |
| `--apply` | Reescreve as linhas correspondentes (default: dry-run) |
| `--json` | JSON |

---

## 5. `hive-mind config`

### 5.1 `config validate`

```powershell
hive-mind config validate [--manifest <file>]
```

Valida `config/runtime.yaml` (schema v3, Pydantic v2). Rejeita dependência
inexistente, auto-referência e ciclos. Imprime `Manifesto válido.` e sai `0`;
caso contrário lista os erros em stderr e sai `1`.

### 5.2 `config show`

```powershell
hive-mind config show [--manifest <file>] [--json]
```

Imprime o manifesto normalizado (YAML por padrão, JSON com `--json`).

---

## 6. `hive-mind service`

### 6.1 `service status`

```powershell
hive-mind service status [--state-dir <dir>] [--project-root <dir>] [--json]
```

Lê o estado do daemon (managed → control socket → state legado do supervisor
Node) e imprime `mode`, `profile`, `required`, e por serviço: `ownership`,
`required`, `readiness`, `startup_order`. Sem estado, sai `1` com mensagem
clara — nunca inventa "healthy".

### 6.2 `service ping`

```powershell
hive-mind service ping [--state-dir <dir>] [--project-root <dir>]
```

Pinga o socket de controle do daemon (timeout 3s). Imprime `pong` e sai `0` se
vivo; `1` se inalcançável.

### 6.3 `service windows-jobs`

```powershell
hive-mind service windows-jobs [--project-root <dir>] [--backup-dir <dir>] [--apply] [--json]
```

Registra as tarefas agendadas de conhecimento no Task Scheduler
(`HiveMind-DreamCycle`, `HiveMind-ClaudeMemBridge`, `HiveMind-KnowledgeHealth`,
`HiveMind-Backup`, e os jobs da cadência). Dry-run por padrão; `--apply`
escreve. Exporta o XML anterior para `logs/scheduled-tasks/` (rollback).
Ver [runtime.md](runtime.md) §15.1.

### 6.4 `service windows-runtime`

```powershell
hive-mind service windows-runtime [--project-root <dir>] [--apply] [--json]
```

Registra as runtime tasks `HiveMind-Supervisor` e
`HiveMind-PostRebootValidation` (trigger `logon`). Dry-run por padrão;
`--apply` escreve com backup transacional das definições anteriores em
`.hive-mind/backups/windows-runtime/`.

### 6.5 `service manifest`

```powershell
hive-mind service manifest [--project-root <dir>] [--json]
```

Emite o manifesto nativo dos serviços (`manifest_version`, `root`,
`claude_mem_plugin_available`, lista de serviços) para o supervisor Node.

---

## 7. `hive-mind doctor`

```powershell
hive-mind doctor [--only <id>|--self <id>|--agent <id>] [--project-root <dir>] [--json]
```

Diagnóstico **read-only** das integrações de agentes (não escreve nada).
Equivalente a `hive-mind agents doctor`. Exit `0` só quando todo provider
**detectado** está totalmente configurado; `1` se algo detectado está
incompleto. Um agente não instalado **não** é falha.

---

## 8. `hive-mind agents`

Implementação única em `src/hive_mind/agents/` (D009-R6). Chaves válidas de
agente: `claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode
openclaw swarmclaw`.

### 8.1 `agents detect`

```powershell
hive-mind agents detect [--json]
```

Detecta quais agentes estão instalados nesta máquina (com evidência).

### 8.2 `agents list`

```powershell
hive-mind agents list [--json]
```

Lista todos os providers que o registro conhece (`id` + `name`).

### 8.3 `agents register`

```powershell
hive-mind agents register [<provider>] [--only <id>] [--apply] [--instructions]
                          [--project-root <dir>] [--json]
```

Registra o servidor MCP `sinapse-memory` nos providers detectados. **Relata
apenas, a menos de `--apply`.** `--instructions` também instala o bloco
gerenciado (`config/sinapse-agent-prompt.md`).

Flags de compatibilidade (do `compat.py`): `--self`/`--agent` (idem `--only`),
`--check` (roteia para `doctor`), `--list` (imprime as chaves válidas),
`--no-instructions`, `--claude-only`, `--codex-only`.

### 8.4 `agents doctor`

```powershell
hive-mind agents doctor [--only <id>] [--project-root <dir>] [--json]
```

Idem ao `doctor` de topo (§7).

### 8.5 `agents unregister`

```powershell
hive-mind agents unregister [--only <id>] [--apply] [--instructions] [--project-root <dir>] [--json]
```

Remove a entrada Hive-Mind da config do provider. `--apply` para escrever;
`--instructions` remove também o bloco de instruções. Remove apenas o entry
`sinapse-memory`; servidores de terceiros e texto próprio são preservados.

### 8.6 O que o registro toca

| Provider | Config | Prompt file |
|---|---|---|
| claude | `~/.claude.json`, `.mcp.json` | `CLAUDE.md` |
| codex | `~/.codex/config.toml`, `~/.codex/mcp.json` | `AGENTS.md` |
| gemini | `~/.gemini/settings.json` | `GEMINI.md` |
| vscode | `.vscode/mcp.json` (`servers`, `type: stdio`) | `.github/copilot-instructions.md` |
| cursor | `~/.cursor/mcp.json` | `.cursor/rules/hive-mind.md` |
| outros | ver `agents list` | — |

Writes são transacionais: parse antes de escrever, backup em `*.hive-bak`,
temp file no mesmo volume, rename atômico, re-parse. Config que falha o parse é
recusada, não escrita pela metade.

---

## 9. `hive-mind validate`

### 9.1 `validate agents`

```powershell
hive-mind validate agents [--only <id>...] [--marker <m> --since <epoch>] [--json]
```

Canário de captura multi-agente sobre fontes reais e estado de entrega real
(read-only). Com `--marker`/`--since`/`--only`, valida uma cadeia de marcador
fresco já emitida pelo provider (sem executá-lo). Sai `0` se o relatório estiver
`ok`.

### 9.2 `validate delivery`

```powershell
hive-mind validate delivery [--outbox-db <path>] [--hive-db <path>] [--json]
```

Inspeciona buckets legados do UMC e backlog histórico de captura (read-only):
`outbox` (total/delivered/undelivered/dead_letter), `umc`
(observations/canonical/legacy), `recovery` (sessões bridged recoverable).

### 9.3 `validate topology`

```powershell
hive-mind validate topology [--project-root <dir>] [--json]
```

Inventaria worktrees/cópias e sugere disposição segura de limpeza (read-only):
`classification`, `disposition`, `exists`, `dirty`, `branch`, `head`, `reason`.

### 9.4 `validate vault`

```powershell
hive-mind validate vault [--vault-root <dir>] [--json]
```

Audita Markdown/links/encoding do vault (read-only): `total_md`, `empty_md`,
`invalid_frontmatter`, `missing_project_id`, `mojibake_files`,
`broken_wikilinks`, `orphan_notes`.

---

## 10. `hive-mind vault`

Manutenção controlada do vault. Todos **dry-run por padrão**; `--apply`
reescreve as notas candidatas.

| Comando | O que faz |
|---|---|
| `vault repair-frontmatter [--vault-root <d>] [--apply] [--json]` | Repara YAML frontmatter inválido legado |
| `vault repair-project-id [--vault-root <d>] [--apply] [--json]` | Repara `project_id` ausente em neurônios temporais legados |
| `vault repair-encoding [--vault-root <d>] [--apply] [--json]` | Repara bytes cp1252 legados preservados em notas Markdown |

---

## 11. `hive-mind backup`

Backup verificado de SQLite + saneamento de dados legados. `run` e os `scrub-*`
/ `archive-*` são dry-run por padrão. Ver [operacao.md](operacao.md) §2 e
[operacao.md](operacao.md).

| Comando | Opções | O que faz |
|---|---|---|
| `backup run` | `--apply`, `--json` | Cria backup verificado (dry-run sem `--apply`) |
| `backup status` | `--json` | Lista backups existentes e cobertura por componente |
| `backup verify` | `--manifest <p>`, `--json` | Re-verifica um manifesto de backup |
| `backup restore` | `--manifest <p>`, `--into <d>`, `--overwrite-live`, `--json` | Restaura em diretório alternativo (nunca in-place por padrão) |
| `backup archive-historical-outbox` | `--outbox-db <p>`, `--cutoff-occurred-at <iso>`, `--apply`, `--json` | Arquiva linhas inertes do `capture_outbox` |
| `backup scrub-capture-outbox` | `--outbox-db <p>`, `--apply`, `--json` | Redige segredos do outbox de captura legado |
| `backup scrub-runtime-artifacts` | `--project-root <d>`, `--apply`, `--json` | Redige segredos de artefatos de log/auditoria |
| `backup scrub-env-backups` | `--project-root <d>`, `--apply`, `--json` | Redige segredos de `.env` legados em `backups/` |
| `backup archive-topology` | `--project-root <d>`, `--archive-root <d>`, `--apply`, `--json` | Arquiva paths de topologia classificados ARCHIVE |
| `backup cleanup-topology-stale` | `--project-root <d>`, `--archive-root <d>`, `--apply`, `--json` | Arquiva/remove resíduos stale `REMOVE_AFTER_APPROVAL` |

---

## 12. `hive-mind implementation`

```powershell
hive-mind implementation status [--json]      # dashboard derivado de git + docs
hive-mind implementation validate             # falha se um doc discorda do repo
```

`status` sai `1` se houver findings; `validate` lista divergências entre os
documentos de implementação e o repositório.

---

## 13. Flags comuns

| Flag | Onde | Significado |
|---|---|---|
| `--json` | quase todos | Saída machine-readable |
| `--apply` | mutações | Executa a escrita (default é dry-run) |
| `--project-root <d>` | transversal | Resolve arquivos do projeto de outro lugar |
| `--only <id>` / `--self` / `--agent` | agents/doctor/validate | Restringe a um provider |
| `--instructions` / `--no-instructions` | agents register/unregister | Bloco de instruções gerenciado |
| `--check` | agents register | Diagnóstico (roteia para `doctor`) |

---

## 14. Cross-references

- **Daemon e serviços** (o que o CLI inspeciona): [runtime.md](runtime.md)
- **Instalação** (uso do CLI no install): [instalacao.md](instalacao.md)
- **Operação** (rotinas com o CLI): [operacao.md](operacao.md)
- **Agentes** (registro/detecção): [agentes.md](agentes.md)
- **Pipeline de dados** (`validate`, `projects`): [pipeline-dados.md](pipeline-dados.md)
- **Segurança** (`backup scrub-*`, fail-closed): [seguranca.md](seguranca.md)
