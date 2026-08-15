# FASE 03 — Falhas silenciosas

**Defeitos:** D-02, D-09
**Owner:** Codex (implementação) · Claude (validação)
**Depende de:** Fase 00

> Três funções de manutenção estão falhando sem que ninguém saiba. Isso é pior
> do que estarem paradas: o sistema *parece* saudável.

**Gate de saída:** `HiveMind-Backup` e `HiveMind-DreamCycle` com 3 execuções
naturais consecutivas `LastTaskResult = 0x0` **e** artefato/`status: ok`
correspondente. Nenhum job pode sair 0 com falha interna.

---

## T03.1 — Redirecionamento obrigatório de log para todo job (pré-requisito da Fase 01)

`pythonw.exe` **não tem stdout/stderr válidos**. Qualquer `print()` ou traceback
no caminho de um job levanta `OSError`/`ValueError` ao escrever em handle
inválido — que é a hipótese principal para o `0x1` do backup.

Implementar em `src/hive_mind/cli.py` (ou num wrapper `hive_mind/jobs/runner.py`):
antes de qualquer I/O, redirecionar `sys.stdout`/`sys.stderr` para
`logs/jobs/<job>-<YYYYmmddTHHMMSSZ>.log`, com fallback para `os.devnull` se o
diretório não existir.

**Teste:** `tests/unit/test_scheduled_job_io_contract.py`
- todo job de `windows_job_specs()` declara destino de log;
- executar um job sob `pythonw` simulado (stdout fechado) não levanta.

**Instalação limpa:** o registro das tasks cria `logs/jobs/`.

---

## T03.2 — Diagnosticar `HiveMind-Backup` (D-02)

Sequência:
1. `python -m hive_mind.cli backup status` (read-only) — o que existe hoje.
2. `python -m hive_mind.cli backup run --dry-run` sob console, capturando saída.
3. Se o dry-run passar, `--apply` uma vez sob observação, com saída capturada.
4. Comparar com a execução real: o job roda com `pythonw` **e** com
   `WorkingDirectory=D:\Hive-Mind` **e** como `miche` `RunLevel=Limited`.
   Testar as três variáveis isoladamente.

Hipóteses ordenadas:
- **H1** stdout inválido sob `pythonw` (mais provável, coberto por T03.1);
- **H2** permissão de escrita no destino de backup sob `RunLevel=Limited`;
- **H3** lock de SQLite: o backup tenta copiar `claude-mem.db` (247,9 MB) com o
  worker ativo em `:37700`;
- **H4** espaço em disco / caminho longo.

**Validação:** artefato novo em `logs/backup/` + `LastTaskResult = 0x0`.

---

## T03.3 — Backup consistente com bancos vivos

Se H3 se confirmar: usar a API de backup online do SQLite
(`sqlite3.Connection.backup()`) em vez de cópia de arquivo, ou quiescer via o
endpoint do worker. Nunca copiar `.db` com `-wal` ativo por `shutil.copy`.

**Teste:** teste de integração que escreve no DB durante o backup e verifica a
integridade do artefato (`PRAGMA integrity_check`).

---

## T03.4 — Verificação pós-backup obrigatória

`backup run` já tem `verify`. Torná-lo parte do fluxo `--apply`: o job só sai 0
se o manifest verificar.

**Teste:** corromper um artefato em sandbox e confirmar exit ≠ 0.

---

## T03.5 — Alerta de backup obsoleto

Regra: se o backup mais recente tiver > 36 h, alertar. Hoje o gap é de 2 dias e
ninguém soube.

**Teste:** relógio simulado, artefato antigo ⇒ alerta disparado.

---

## T03.6 — Exit code do Dream Cycle (D-09)

`scripts/dream/dream_cycle.py` deve retornar **≠ 0** quando `status == "failed"`.
Hoje grava `status: failed` e sai 0.

**Teste:** `tests/unit/test_dream_cycle_exit_contract.py` — estágio falho ⇒
`SystemExit` com código ≠ 0 **e** `dream_cycle_latest.json` com `status: failed`.

---

## T03.7 — Backpressure no estágio `distill_validate`

39,5 min em um único estágio, com 3 928 discoveries pendentes, indica loop sem
limite. Implementar:
- lote máximo por execução (configurável, default conservador);
- timeout duro por lote;
- checkpoint persistido para retomar de onde parou;
- métrica de itens processados por execução.

**Teste:** com N itens e lote M, o ciclo processa exatamente M e registra o
checkpoint.

---

## T03.8 — Contrato de exit code para os 18 jobs

Generalizar: suíte parametrizada sobre `config/runtime.yaml` verificando que cada
entrypoint termina com `sys.exit(code)` derivado do resultado, nunca com queda
implícita para 0.

**Teste:** `tests/unit/test_all_jobs_exit_contract.py`.

---

## T03.9 — Registro estruturado de resultado por job

Cada job grava `logs/jobs/<job>-latest.json` com
`{status, started_at, finished_at, duration_ms, error, artifacts}`. É a fonte
única para o dashboard e para os alertas da Fase 08.

**Teste:** todo job produz o arquivo, mesmo em falha.

---

## T03.10 — Reabilitar o log operacional do Task Scheduler

O canal `Microsoft-Windows-TaskScheduler/Operational` está desabilitado — foi o
que impediu o post-mortem do `0x1`. Reabilitar e documentar como parte do setup.

**Validação:** `Get-WinEvent` retorna eventos das tasks HiveMind-*.
**Nota:** implementar via API nativa (`wevtutil` é executável do SO, não script
do projeto — permitido, mas preferir `ctypes`/API se viável).

---

## T03.11 — Três execuções verdes consecutivas

Gate final da fase: observar as execuções naturais das 02:00 por 3 dias, ou
disparar manualmente 3 vezes com intervalo, exigindo em cada uma
`LastTaskResult = 0x0` **e** artefato correspondente **e**
`logs/jobs/<job>-latest.json` com `status: ok`.
