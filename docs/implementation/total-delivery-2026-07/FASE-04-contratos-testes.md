# FASE 04 — Contratos e suíte de testes

**Defeitos:** D-12, D-13, D-14, D-15, D-23
**Owner:** Claude (decide contrato) · Codex (aplica)
**Depende de:** Fase 00

**Gate de saída:** `pytest tests/unit` = **0 failed**, com o Supervisor real
rodando (a suíte tem que ser hermética).

Linha de base da auditoria: **15 failed / 1627 passed / 18 skipped / 277,99 s**.

---

## T04.1 — Contrato do owner de jobs (D-14)

**Decisão arquitetural** (a registrar em `docs/operations/no-console-contract.md`,
junto com T01.1):

> Todo job agendado no Windows usa `pythonw.exe -m hive_mind.cli <subcomando>`.
> Console entrypoints (`hive-mind.exe`, PE subsystem 3) são exclusivamente para
> uso interativo humano.

Justificativa: `hive-mind.exe` é subsystem 3; apontar a task para ele
reintroduziria a janela que a migração eliminou. O código (`windows_jobs.py`)
está correto; o teste e o `runtime.yaml` é que ficaram para trás.

Aplicar:
- `tests/unit/test_cutover_owner_contract.py:74` — passa a exigir `pythonw.exe` +
  `-m hive_mind.cli backup run --apply`.
- `tests/unit/test_manifest_job_parity.py` — idem.
- `config/runtime.yaml`, job `backup-databases`:
  `hive-mind backup run --apply` → `python -m hive_mind.cli backup run --apply`.

**Teste mais forte que substitui a comparação de string:** nenhum
`WindowsJobSpec.execute` pode ter PE Subsystem 3 (usa o leitor de T01.3). Isso
transforma a regra em invariante verificável em vez de literal frágil.

---

## T04.2 — Corrigir `_WindowsLock` (D-12) — defeito real, não ruído de teste

`src/hive_mind/daemon/lock.py:127` constrói `_WindowsLock()` **sem** `state_dir` e
usa um mutex nomeado global do host, enquanto `_PosixLock(self.lock_path)` é
escopado por caminho.

Consequências:
1. Os 6 testes de `test_daemon_lock` falham enquanto o Supervisor real roda —
   suíte não-hermética;
2. Duas raízes distintas de Hive-Mind na mesma máquina **não conseguiriam
   coexistir**, o que contradiz o próprio conceito de `--project-root`.

**Correção:** `_WindowsLock(state_dir)` deriva o nome do mutex de um hash estável
do caminho absoluto — `Local\HiveMind-<sha1(str(state_dir.resolve()))[:16]>`.

**Testes:**
- dois locks com `state_dir` diferentes coexistem;
- dois com o mesmo `state_dir` se excluem, com mensagem clara;
- a suíte inteira passa **com o Supervisor rodando**;
- paridade semântica POSIX/Windows verificada pelo mesmo teste parametrizado.

---

## T04.3 — Testes de instalador alinhados ao inventário pós-remoção (D-13)

`test_installer_does_not_install_capture_hooks[register-mcp.ps1]` e
`test_both_installers_agree` referenciam `.ps1` que deixaram de existir.
Reescrever contra `install.bat` + `hive-mind install`.

---

## T04.4 — Regressão de identidade de projeto (D-15)

`test_capture_project_identity::test_legacy_provider_application_and_profile_labels_do_not_become_project_id`
e `test_project_identity::test_generic_conversation_never_activates_mentioned_project`.

Suspeitos: `src/hive_mind/capture/identity_store.py` e
`src/hive_mind/projects/identity.py` (ambos modificados na Fase 00).
Investigar individualmente; **não** relaxar o teste sem provar que o
comportamento novo é o desejado.

---

## T04.5 — Governança temporal (D-15)

`test_temporal_governance::WriterFrontmatterTests::test_decision_with_evidence_is_verified`.
Relacionado a `core/memory/writers.py` (modificado). O contrato
`evidence ⇒ confidence: verified` é parte do protocolo do cérebro — precisa
voltar a valer.

---

## T04.6 — Encoding de saída de subprocesso (D-23)

`UnicodeDecodeError: 'utf-8' codec can't decode byte 0x87` em threads de leitura
de `subprocess` — saída Windows em CP-1252/CP-850 lida como UTF-8.

**Correção:** helper central `hive_mind.platform.run()` com
`encoding="utf-8", errors="replace"` (ou `locale.getpreferredencoding(False)`).

**Teste:** proíbe `subprocess.run`/`Popen` cru fora de `hive_mind/platform/` e
`daemon/managed.py`; helper testado com bytes inválidos.

---

## T04.7 — Suíte hermética por construção

Nenhum teste pode depender de estado da máquina (Supervisor rodando, portas
ocupadas, tasks registradas). Varrer a suíte por dependências implícitas e
isolá-las com fixtures.

**Teste:** rodar `pytest tests/unit` duas vezes — com e sem o Supervisor — e
exigir resultado idêntico.

---

## T04.8 — Cobertura dos módulos recém-commitados

Os 27 módulos da Fase 00 nunca tiveram cobertura medida. Estabelecer piso de
cobertura para `hive_mind/windows/`, `install/`, `services/`, `validation/`,
`maintenance/windows_*`.

---

## T04.9 — Suíte de integração separada

`tests/unit` deve ser rápido e hermético. Mover o que toca disco/rede/processo
para `tests/integration`, com marcador próprio, rodado no CI da Fase 07.

---

## T04.10 — Tempo de suíte

277,99 s para `tests/unit` é alto demais para o loop de desenvolvimento.
Perfilar, identificar os testes lentos (provavelmente os que spawnam
subprocessos) e movê-los para integração.

**Meta:** `tests/unit` < 60 s.
