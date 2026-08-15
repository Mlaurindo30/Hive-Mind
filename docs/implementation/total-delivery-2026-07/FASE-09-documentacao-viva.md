# FASE 09 — Documentação viva

**Defeitos:** D-17
**Owner:** Claude (escrita) · Kimi (levantamento da dívida)
**Depende de:** Fases 01–06 estabilizadas

Classificação da auditoria:

| Documento | Classificação | Problema |
|---|---|---|
| `.hive-mind/state/services.managed.json` | CURRENT | — |
| `logs/post-reboot-validation.json` | CURRENT | — |
| `config/runtime.yaml` | CURRENT | exceto o job `backup-databases` (T04.1) |
| `docs/implementation/WINDOWS-NATIVE-MIGRATION.md` | PARTIAL | descreve `.psm1/.ps1` como `THIN_WRAPPER`; foram removidos |
| `docs/implementation/CURRENT-STATE.md` | **STALE** | afirma "reboot NÃO executado", "capture REGRESSÃO", "1359 passed" |
| `docs/implementation/DELIVERY-LEDGER.md` | **STALE** | mesma safra (25/07) |
| `logs/supervisor/manifest.json` | **HISTORICAL** | descreve owner `powershell.exe` + `claude-mem-local.ps1` — **autoridade-chamariz** |

**Gate de saída:** zero documento marcado CURRENT que contradiga o runtime vivo.

---

## T09.1 — Reescrever `CURRENT-STATE.md`

A partir do estado vivo, com commit e data de referência no topo. Nunca mais um
documento CURRENT sem commit de âncora.

---

## T09.2 — Reescrever `DELIVERY-LEDGER.md`

Consolidar o que efetivamente foi entregue, com evidência por item.

---

## T09.3 — Atualizar `WINDOWS-NATIVE-MIGRATION.md`

`.ps1`/`.psm1` saem de `THIN_WRAPPER` para `REMOVED`. A tabela de owners passa a
refletir o estado pós-Fase 02.

---

## T09.4 — Aposentar autoridades-chamariz

`logs/supervisor/manifest.json` (27/07) ainda descreve o owner PowerShell. Mover
para `logs/_archive/` **ou** inserir cabeçalho `DEPRECATED — não é autoridade;
ver .hive-mind/state/services.managed.json`.

Varrer `reports/` e `logs/` por outros artefatos que possam ser confundidos com
estado atual.

---

## T09.5 — Marcador de classificação obrigatório

Todo documento em `docs/implementation/` passa a ter frontmatter:

```yaml
status: CURRENT | PARTIAL | STALE | HISTORICAL
anchor_commit: <sha>
verified_at: <ISO8601>
```

---

## T09.6 — Validador de documento vivo

Estender `src/hive_mind/implementation/validate.py`: um documento marcado
`CURRENT` cujo `anchor_commit` não seja ancestral do HEAD, ou cujo
`verified_at` seja mais velho que N dias, **reprova**.

**Teste:** documento com âncora obsoleta ⇒ validação falha.

---

## T09.7 — Documentar os contratos criados

- `docs/operations/no-console-contract.md` (T01.1 + T04.1)
- `docs/capture/providers.md` (T05.10)
- `docs/capture/formats/*.md` (T05.1)
- `docs/operations/job-io-contract.md` (T03.1)

---

## T09.8 — Atualizar `CLAUDE.md` / `AGENTS.md`

Ambos estão modificados e não commitados. Após a Fase 00, revisar para refletir
o runtime real (owners nativos, sem PowerShell) e o protocolo de memória vigente.

---

## T09.9 — README e docs de instalação

`README.md`, `docs/installation.md`, `docs/15-windows-clean-install.md` — todos
modificados e não commitados. Alinhar ao fluxo provado na Fase 07.

---

## T09.10 — Runbook de incidente

Documento curto: "o Supervisor não subiu", "o backup falhou", "aparece janela de
console" — o que olhar, em que ordem, com os comandos exatos. A ordem de
autoridade da auditoria (processo vivo → task → `services.managed.json` → PE →
config → código → testes → logs → doc) vira o runbook oficial.
