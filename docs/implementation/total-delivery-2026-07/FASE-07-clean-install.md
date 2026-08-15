# FASE 07 — Clean install PROVEN

**Defeitos:** D-11
**Owner:** Claude (critérios) · Codex (automação) · CI (execução)
**Depende de:** Fases 00, 01, 02, 03, 04

> A auditoria classificou `CLEAN_INSTALL = NOT_PROVEN` **por construção**: todo o
> caminho de instalação era untracked. Com a Fase 00 fechada, isto vira
> provável — e esta fase o prova.

**Gate de saída:** CI em máquina descartável verde, incluindo o teste negativo.

---

## T07.1 — Reativar o runner de máquina descartável

Base existente nos commits `99b586a` e `912dd53`. Reapontar para o commit da
Fase 00.

---

## T07.2 — Sequência canônica de instalação

O workflow executa exatamente:

```
git clone
  → components bootstrap
  → uv sync
  → ensure_gui_pythonw          (materializa pythonw subsystem 2)
  → validate_gui_launchers      (lê o PE; aborta se subsystem 3)
  → materializar wrappers
  → registrar agentes / MCP / hooks
  → registrar Scheduled Tasks
  → iniciar Supervisor
  → post-reboot validation
```

**Invariante crítica:** `ensure_gui_pythonw` e `validate_gui_launchers`
acontecem **antes** do registro das tasks. Já é o caso no código; o CI passa a
provar.

---

## T07.3 — Asserções obrigatórias do runner

1. Os 3 launchers `*w.exe` + `pythonw.exe` têm **PE Subsystem 2** (lido do PE, não
   inferido do nome).
2. As 7 tasks existem, `Hidden = true`, `WorkingDirectory = <root>`, e **nenhuma**
   aponta para binário de subsystem 3 nem para `.ps1/.psm1/.vbs/.cmd/.bat`.
3. `services.managed.json` aparece, `supervisor_pid` vivo, serviços `required`
   running.
4. `post-reboot-validation.json` = `pass`, 6/6 checks.
5. `hive-mind validate console-watch --seconds 120` = **zero** eventos Hive-Mind.
6. `pytest tests/unit` = 0 failed.
7. `git ls-files` = 0 arquivos `.ps1/.psm1/.psd1/.vbs/.cmd`, exatamente 2 `.bat`.

---

## T07.4 — Teste negativo (o mais importante da fase)

Injetar deliberadamente um `pythonw.exe` de subsystem **3** no venv e provar que
o instalador **aborta antes de registrar qualquer task**.

Isto é o que transforma "acreditamos que funciona" em "é impossível quebrar".

**Variantes do teste negativo:**
- `pythonw.exe` subsystem 3 ⇒ aborta;
- launcher `*w.exe` ausente ⇒ aborta;
- `.venv` fora da raiz canônica ⇒ aborta;
- task pré-existente apontando para `.ps1` ⇒ detectada e reportada.

---

## T07.5 — Prova de sobrevivência a reboot

O runner reinicia a máquina virtual e confirma:
- `HiveMind-Supervisor` volta pelo trigger de logon;
- `HiveMind-PostRebootValidation` roda e grava `pass`;
- os 7 serviços voltam com ancestralidade correta;
- nenhuma janela durante o boot.

---

## T07.6 — Instalação em raiz não-`D:\`

O contrato hoje tem `D:\Hive-Mind` hardcoded em vários pontos
(`test_cutover_owner_contract.py` usa `CANONICAL = r"D:\Hive-Mind"`).
O CI deve instalar em `C:\hm-test` e provar que tudo funciona — senão "raiz
canônica" virou "raiz única", e o produto não é instalável.

Ligado a T04.2: o lock global do Windows também impede múltiplas raízes.

---

## T07.7 — Instalação com o usuário sem privilégio de administrador

As tasks rodam com `RunLevel = Limited`. Provar que a instalação inteira
funciona sem elevação, ou documentar exatamente onde ela é necessária.

---

## T07.8 — Desinstalação limpa

Se instalar é reproduzível, desinstalar também precisa ser: remover as 7 tasks,
parar o Supervisor, remover hooks e entradas de MCP, sem deixar órfão.

**Teste:** instalar → desinstalar → `Get-ScheduledTask HiveMind*` vazio, nenhum
processo remanescente, configs dos agentes restauradas.

---

## T07.9 — Idempotência

Rodar o instalador duas vezes seguidas não pode duplicar tasks, hooks nem
entradas de MCP.

**Teste:** dupla execução ⇒ estado idêntico.

---

## T07.10 — Atualização sobre instalação existente

Cenário real: `git pull` + `uv sync` sobre uma instalação viva. Provar que
launchers são rematerializados, tasks reconciliadas e o Supervisor reinicia sem
perder estado.

---

## T07.11 — Registrar o resultado como PROVEN

Ao passar, atualizar `docs/implementation/CURRENT-STATE.md` (Fase 09) com o
commit, a data e o link do run — a evidência que a auditoria não pôde produzir.
