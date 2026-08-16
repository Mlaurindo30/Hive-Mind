# Registro de agentes (MCP)

Como o Hive-Mind é registrado em um agente de IA. Público-alvo: quem instala,
administra ou diagnostica a integração do Hive-Mind com agentes externos.

Registrar o Hive-Mind em um agente significa **três coisas**:

1. adicionar o servidor MCP `sinapse-memory` à configuração do agente;
2. opcionalmente, instalar o bloco de instruções operacionais no arquivo de
   prompt do agente;
3. poder verificar ou desfazer qualquer uma das duas.

Tudo isso é `hive-mind agents`.

---

## Uma única implementação

Até a entrega D009-R6 o registro vivia **duplicado** —
`scripts/setup/register-mcp.ps1` (456 linhas) e
`scripts/setup/register-mcp.sh` (444 linhas) — e os dois divergiram. O `.sh`
continuava religando um caminho de captura obsoleto que o `.ps1` já tinha
removido; o `.ps1` suportava três alvos enquanto o `.sh` suportava treze.

Hoje os dois são **wrappers**: localizam o executável `hive-mind`, encaminham os
argumentos, preservam `stdout` e `stderr` e retornam o exit code. Nada além
disso. O comportamento vive em `src/hive_mind/agents/`, então existe **uma
resposta por pergunta**, independente de plataforma.

```bash
./scripts/setup/register-mcp.sh --only codex --apply       # POSIX
```

```powershell
python scripts/setup/register_mcp.py --only codex --apply  # Windows
```

```bash
hive-mind agents register --only codex --apply             # o comando real
```

A tradução das opções antigas (compatibilidade) vive em
`src/hive_mind/agents/compat.py`, não nos wrappers.

---

## Comandos

| Comando | O que faz |
|---|---|
| `hive-mind agents detect` | descobre quais agentes estão instalados nesta máquina |
| `hive-mind agents list` | lista todos os providers que o registry conhece |
| `hive-mind agents register` | adiciona o servidor MCP — **só relata, exceto com `--apply`** |
| `hive-mind agents doctor` | diagnóstico somente-leitura; não escreve nada |
| `hive-mind agents unregister` | remove a entrada do Hive-Mind — `--apply` para escrever |

### Nada é escrito sem você pedir

`register` e `unregister` são **dry-run por padrão**. Isso difere dos scripts
antigos, que escreviam imediatamente. Os chamadores que dependiam do padrão
antigo — `install.ps1`, `install.sh`, `npm/bin/hive-mind.js` — agora passam
`--apply` explicitamente, para que a intenção fique visível no local da chamada
em vez de implícita num default.

---

## Opções

Toda opção que os scripts antigos aceitavam continua funcionando, porque os
chamadores ainda as usam.

| Opção | Significado |
|---|---|
| `--only <agent>` (também `--self`, `--agent`, ou um nome de agente solto) | um provider em vez de todos os detectados |
| `--apply` | realmente escrever |
| `--instructions` | instalar também o bloco de instruções gerenciado |
| `--no-instructions`, `HIVE_SKIP_PROMPT=1` | nunca tocar nos arquivos de prompt |
| `--check` | apenas diagnosticar (roteia para `doctor`) |
| `--list` | imprimir as chaves de agente válidas |
| `--claude-only`, `--codex-only` | atalhos que o script PowerShell tinha |
| `--project-root <path>` | resolver os arquivos do projeto a partir de outro lugar |
| `--json` | saída legível por máquina |

Chaves de agente válidas:

```
claude codex gemini qwen kimi kiro kilo roo vscode cursor opencode openclaw swarmclaw
```

---

## Exit codes

| Código | Significado |
|---|---|
| 0 | sucesso; para `--check` / `doctor`, **todo provider detectado** está totalmente configurado |
| 1 | o diagnóstico está incompleto — algo detectado não está configurado |
| 2 | chave de agente desconhecida |

Um agente que **não está instalado** não é falha: não há nada a configurar para
um provider ausente. Uma máquina nova sem agentes sai 0. Uma máquina com agentes
que nunca foram registrados sai 1 — que é a resposta honesta, e o motivo de o
contrato antigo (`--check` sempre saía 0) ter sido substituído. Aquele contrato
tornava `--check` inútil como gate.

---

## O que o registro toca

| Provider | Config | Arquivo de prompt |
|---|---|---|
| claude | `~/.claude.json`, `.mcp.json` | `CLAUDE.md` |
| codex | `~/.codex/config.toml`, `~/.codex/mcp.json` | `AGENTS.md` |
| gemini | `~/.gemini/settings.json` | `GEMINI.md` |
| vscode | `.vscode/mcp.json` (chave raiz `servers`, `type: stdio`) | `.github/copilot-instructions.md` |
| cursor | `~/.cursor/mcp.json` | `.cursor/rules/hive-mind.md` |
| outros | veja `hive-mind agents list` | — |

### Escrita transacional

As escritas são transacionais:

1. o arquivo é **parseado antes** de qualquer escrita;
2. um arquivo existente é copiado para backup `*.hive-bak`;
3. o novo conteúdo vai para um **arquivo temporário no mesmo volume** e é
   renomeado para o lugar;
4. o resultado é **re-parseado**.

Uma configuração que falha no parse é **recusada** em vez de ser gravada pela
metade.

### O que é registrado

Apenas o orquestrador `sinapse-memory` é registrado. Ele federa os backends
brutos internamente, então `claude-mem-local` e `neural-memory-local` são
**removidos** se uma instalação mais antiga os deixou para trás. Servidores MCP
de terceiros **nunca são tocados**.

### Bloco de instruções delimitado

O bloco de instruções é delimitado por
`<!-- BEGIN HIVE-MIND SINAPSE -->` / `<!-- END HIVE-MIND SINAPSE -->`.
Reexecutar **substitui** o bloco em vez de anexar um segundo, incluindo blocos
escritos pelo script da era PowerShell. Tudo fora dos marcadores é seu e é
preservado.

---

## Desfazer

```bash
hive-mind agents unregister --only codex --apply                  # só a config
hive-mind agents unregister --only codex --apply --instructions   # e o bloco de prompt
```

Apenas a entrada `sinapse-memory` é removida. Servidores de terceiros, chaves
de config não relacionadas, comentários TOML e o seu próprio texto de prompt
**sobrevivem** — verificado em
`tests/integration/test_registration_through_wrappers.py`.

---

## Relacionado

- [instalacao.md](instalacao.md) — onde o registro se encaixa numa instalação completa
- [captura.md](captura.md) — o que os hooks/parsers capturam (independente do registro MCP)
- [cli.md](cli.md) — o CLI nativo do qual `agents` é um subgrupo
- [desenvolvimento.md](desenvolvimento.md) — como testar mudanças no registro
-  — D009-R6
