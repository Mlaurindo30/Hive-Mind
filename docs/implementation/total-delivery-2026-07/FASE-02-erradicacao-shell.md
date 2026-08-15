# FASE 02 — Erradicação total de shell

**Defeitos:** D-03, D-04
**Owner:** Codex (execução) · Kimi (varredura de referências)
**Depende de:** Fase 00

> **Requisito do dono:** o projeto trabalha ligado ao Python. Nenhum `.ps1`,
> `.psm1`, `.vbs`, `.cmd`. Únicas exceções: `install.bat` e `setup-brain.bat`,
> wrappers de instalação/configuração executados manualmente.

**Gate de saída:** `git ls-files` retorna **zero** arquivos `.ps1/.psm1/.psd1/.vbs/.cmd`;
exatamente 2 `.bat`; `test_architecture_boundaries` 100 % verde.

---

## T02.1 — Inventário definitivo pós-Fase 00

Após os commits, recontar. Estado esperado no HEAD:

| Extensão | Alvo |
|---|---:|
| `.ps1` | 0 |
| `.psm1` / `.psd1` | 0 |
| `.vbs` | 0 |
| `.cmd` | 0 |
| `.bat` | 2 (`install.bat`, `setup-brain.bat`) |

Sobrevivências toleradas, com justificativa explícita:
- `backups/**` — snapshots históricos, não são código vivo. Decidir: manter
  congelado ou mover para fora do repo.
- `integrations/graphify/tests/fixtures/sample.ps1|.psd1` — **fixtures do parser
  de PowerShell do Graphify**. Não são código executável do Hive-Mind; são dados
  de teste de um analisador de linguagem. Manter, mas mover para
  `fixtures/languages/powershell/` e documentar a exceção no teste de fronteira.

---

## T02.2 — Aposentar `scripts/lib/HiveMind.Windows.psm1`

Hoje referenciado **apenas** por `tests/unit/test_windows_install_contract.py`,
`test_windows_runtime_contract.py` e docs. Nenhum owner vivo.

1. Reescrever os dois testes contra os owners Python nativos
   (`hive_mind.install.windows_support`, `hive_mind.maintenance.windows_runtime`).
2. Deletar o `.psm1`.

**Teste:** os dois testes passam sem referência a PowerShell.
**Validação:** `git ls-files "*.psm1"` vazio.

---

## T02.3 — Remover o literal morto em `runtime_services.py`

`src/hive_mind/maintenance/runtime_services.py:1007` — `powershell = "powershell.exe"`
é uma variável **nunca usada**, dentro do ramo `else:` (não-Windows). Deletar.

**Teste:** `test_no_module_spawns_powershell_or_bash` passa.
**Fecha:** D-04.

---

## T02.4 — Decidir sobre `scripts/capture/visual_capture.py` (ramo WSL)

Linha 79 invoca `powershell.exe` do host quando rodando sob WSL. Inalcançável no
Windows nativo.

Opções:
- **(a)** Remover o ramo WSL — o projeto é Windows-native, `mss` já é o caminho
  primário. *Recomendado.*
- **(b)** Isolar em `hive_mind/platform/wsl.py` com exceção nomeada no teste de
  fronteira.

**Teste:** `test_no_module_spawns_powershell_or_bash` verde sem exceções ad-hoc.

---

## T02.5 — `audit_runtime_paths_windows.py` sem PowerShell

Linha 55 invoca `powershell.exe` (com `CREATE_NO_WINDOW`) para consultar
processos. Substituir por leitura nativa via `ctypes`/`wmi` em
`hive_mind/platform/processes.py` — a mesma primitiva que T01.6 vai precisar.

**Teste:** `tests/unit/test_platform_processes.py` — enumera processos, resolve
PPID, sem spawn de shell.
**Benefício colateral:** elimina a `UnicodeDecodeError` de CP-1252 (D-23) nessa
rota.

---

## T02.6 — Limpar as docstrings que citam scripts retirados

`src/hive_mind/agents/{compat,instructions,mcp_config,register,registry,toml_config}.py`
citam `register-mcp.ps1` em comentários. Atualizar para descrever o owner Python,
não o script morto — senão a próxima varredura por "powershell" volta a
disparar falso positivo.

Atenção especial: `instructions.py:32` embute o texto
`"auto-managed by register-mcp.ps1 -- do not edit"` **no arquivo gerado**. Isso é
conteúdo de saída, não comentário — precisa mudar para
`"auto-managed by hive-mind agents register"` e ter migração para os arquivos já
escritos com o marcador antigo.

**Teste:** teste de migração que reconhece o marcador antigo e o substitui
idempotentemente.

---

## T02.7 — Contrato executável: `install.bat` e `setup-brain.bat` são finos

Definir e testar:
- Máximo ~40 linhas cada.
- Nenhuma lógica de negócio: apenas localizar o Python/uv, repassar argumentos,
  preservar exit code.
- Nenhuma Scheduled Task, serviço, MCP, hook ou processo permanente pode
  referenciá-los.

**Teste:** `tests/unit/test_bat_wrappers_are_thin.py` — conta linhas, proíbe
palavras-chave de lógica (`for`, `goto`, `if not exist` com ramificação
complexa), e varre tasks/serviços/hooks/MCP por referência a `.bat`.

---

## T02.8 — Teste de fronteira definitivo

Reescrever `tests/unit/test_architecture_boundaries.py` para ser a lei:

1. Nenhum módulo Python cita `powershell`, `pwsh`, `bash -c`, `cmd.exe`
   (exceto uma allowlist vazia).
2. `git ls-files` não retorna `.ps1/.psm1/.psd1/.vbs/.cmd`.
3. Exatamente 2 `.bat`, ambos na raiz, ambos finos.
4. Nenhum `subprocess` fora de `hive_mind/platform/` e `daemon/managed.py`
   (+ a allowlist documentada de leitura de `git`).

**Fecha:** D-03, D-04, D-13 (parcial).
