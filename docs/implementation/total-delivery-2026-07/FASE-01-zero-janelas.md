# FASE 01 — Zero janelas (garantia por binário, não por flag)

**Defeitos:** D-18, D-19, D-20, D-05
**Owner:** Claude (contrato) · Codex (implementação)
**Depende de:** Fase 00

> **Requisito do dono do projeto:** nenhuma janela pode aparecer enquanto o
> projeto roda.

## Diagnóstico da auditoria

A auditoria de 400 s provou que **zero** processos de console descendem do
Supervisor. Mas isso é hoje uma garantia **frágil**, e há fontes fora do
Supervisor que a auditoria identificou:

| Fonte | Natureza | Situação |
|---|---|---|
| Serviços gerenciados | rodam `.venv\Scripts\python.exe` (**PE subsystem 3**) protegidos só por `CREATE_NO_WINDOW` | **frágil** — basta um caminho de código esquecer a flag |
| `~/.claude/settings.json` hooks Hive-Mind | `python.exe` (subsystem 3) | **assimétrico** com o Codex, que já usa `hive-mind-capture-hookw.exe` |
| `C:\Users\miche\.orca\agent-hooks\claude-hook.cmd` | **`.cmd`** disparado em PreToolUse/PostToolUse/Stop/SubagentStart/SubagentStop/TeammateIdle/PermissionRequest/StopFailure | **fonte externa confirmada** — chama `curl.exe` e `more.com`, cada disparo cria `cmd.exe` + `conhost.exe` |
| plugin `claude-mem@13.12.4` | `powershell.exe` a cada ~40 s | usa `windowsHide:!0` — **não** pisca janela |
| `disp.exe` (NVIDIA) | 14 `conhost` na janela de 400 s | ruído do SO, fora de escopo |

**Gate de saída:** 0 eventos de console em janela de **30 min com nenhum agente
aberto**, e 0 binário de PE Subsystem 3 referenciado por task/serviço/hook/MCP.

---

## T01.1 — Contrato: nenhum artefato persistente aponta para subsystem 3

Registrar formalmente em `docs/operations/no-console-contract.md`:

> Toda Scheduled Task, todo serviço gerenciado, todo hook e toda entrada de MCP
> do Hive-Mind no Windows **deve** apontar para um executável de **PE Subsystem
> 2**. Executáveis de subsystem 3 (`python.exe`, `hive-mind.exe`) são
> exclusivamente para uso interativo humano no terminal.

**Prós:** a garantia passa a vir do binário; a classe inteira do bug morre por
construção; é verificável mecanicamente lendo o PE.
**Contras:** `pythonw.exe` descarta stdout/stderr — exige o redirecionamento
obrigatório de log da Fase 03 (por isso T03.1 vem junto).

---

## T01.2 — Migrar os serviços gerenciados para `pythonw.exe`

Hoje `managed.py` resolve o interpretador para `.venv\Scripts\python.exe`.
Trocar por `.venv\Scripts\pythonw.exe` (subsystem 2), mantendo
`CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` como **defesa em profundidade**,
não como única garantia.

**Pré-requisito:** T03.1 (redirecionamento de log) precisa estar pronto, senão
perde-se toda a saída dos 7 serviços.

**Teste:** `tests/unit/test_no_console_subsystem_contract.py` — para cada serviço
de `runtime.yaml`, o executável resolvido tem PE Subsystem 2.
**Validação viva:** reiniciar o Supervisor e confirmar 7/7 serviços running com
`Get-CimInstance` mostrando `pythonw.exe`.

---

## T01.3 — Leitor de PE Subsystem nativo em Python

Criar `src/hive_mind/platform/pe.py` com `read_subsystem(path) -> int`, lendo o
header PE (offset `0x3C` → assinatura `PE\0\0` → `+24+68`). Sem dependência
externa, sem shell.

**Teste:** `tests/unit/test_pe_subsystem_reader.py` — `pythonw.exe` = 2,
`python.exe` = 3, arquivo não-PE levanta erro claro.

---

## T01.4 — Migrar os hooks do Claude para o GUI launcher

`~/.claude/settings.json`: trocar
`"D:\Hive-Mind\.venv\Scripts\python.exe" "...\capture-hook.py"`
por
`"D:\Hive-Mind\.venv\Scripts\hive-mind-capture-hookw.exe"`,
igualando o contrato já aplicado ao Codex.

Aplicar em `scripts/setup/install-capture-hooks.py` para que a instalação limpa
já materialize assim.

**Teste:** `test_install_capture_hooks` exige, no Windows, que todo hook do
Hive-Mind aponte para binário de subsystem 2.
**Validação viva:** disparar um evento natural e confirmar no monitor que nenhum
console nasce sob `claude.exe` por causa do hook.
**Fecha:** D-20.

---

## T01.5 — Jobs agendados em `pythonw.exe` com entrypoint de módulo

Já é o caso hoje (`pythonw.exe -m hive_mind.cli ...`). Consolidar como invariante
testado, não como coincidência.

**Teste:** nenhum `WindowsJobSpec.execute` pode ter subsystem 3 (usa T01.3).

---

## T01.6 — Monitor de console permanente e reutilizável

Portar o monitor da auditoria para
`src/hive_mind/validation/console_watch.py`, exposto como
`hive-mind validate console-watch --seconds N --json <path>`.

Registra criação de `cmd/conhost/powershell/pwsh/wscript/cscript`, resolve
ancestralidade PID/PPID **no instante da criação** (antes do pai morrer) e
classifica por dono.

**Teste:** teste de integração que gera um processo de console conhecido e
confirma que ele é detectado e atribuído corretamente.

---

## T01.7 — Validação de 30 min sem agente (o gate de verdade)

Procedimento operacional:

1. Fechar Claude Code, Codex, VS Code, Orca — **todos** os agentes.
2. Deixar apenas o Supervisor e os 7 serviços rodando.
3. `hive-mind validate console-watch --seconds 1800 --json logs/console-watch-<ts>.json`
4. **Critério:** zero eventos com ancestralidade do Hive-Mind. Qualquer evento
   restante é classificado e atribuído ao dono externo.

Este é o gate que responde diretamente à queixa "abrem janelas de cmd no
monitor". Se sobrar evento, ele será nominalmente identificado.

---

## T01.8 — Neutralizar o hook `.cmd` do Orca (fora do repo, dentro do problema)

`claude-hook.cmd` não é código Hive-Mind, mas é `.cmd` disparando em cada evento
de ferramenta. Opções, em ordem de preferência:

1. Remover as entradas do Orca de `~/.claude/settings.json` se o Orca não estiver
   em uso ativo.
2. Se em uso: reportar upstream e, no interim, substituir o `.cmd` por um
   executável GUI equivalente.

**Validação:** após a mudança, T01.7 roda com Claude Code aberto e não registra
`cmd.exe` de origem Orca.

---

## T01.9 — Documentar o que é ruído externo

`disp.exe` (NVIDIA) e processos do SO vão continuar criando `conhost`. O
relatório do `console-watch` precisa separar isso explicitamente para que o dono
do projeto não atribua ao Hive-Mind o que não é dele.

---

## T01.10 — Regressão permanente no CI

Adicionar ao runner da Fase 07 uma janela de 120 s de `console-watch` com
asserção de zero eventos Hive-Mind. Assim a propriedade não pode regredir sem
quebrar o build.
