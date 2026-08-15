# FASE 00 — Reprodutibilidade (BLOQUEANTE)

**Defeitos:** D-01, D-03, D-11, D-16
**Owner:** Claude (curadoria) · Kimi (varredura) · Codex (execução)
**Bloqueia:** todas as demais fases

> Enquanto o runtime não estiver em um commit, qualquer correção é
> irreproduzível e qualquer incidente é irrecuperável. Nada mais começa antes
> disto fechar.

**Gate de saída:** `git status --porcelain --untracked-files=all` vazio; HEAD
publicado com upstream; `CLEAN_INSTALL` sai de `NOT_PROVEN` para `PARTIAL`.

---

## T00.1 — Snapshot de segurança

Antes de qualquer `git add`.

- Copiar `D:\Hive-Mind` para `D:\Hive-Mind-Snapshots\<timestamp>\repo\`,
  excluindo `.venv`, `.uv`, `node_modules`, `.git/objects`.
- Exportar as 7 Scheduled Tasks (`Export-ScheduledTask`) para
  `<timestamp>\tasks\<nome>.xml`.
- Copiar `.hive-mind/state/`, `logs/post-reboot-validation.json`,
  `logs/metrics/dream_cycle_latest.json`.
- Registrar SHA-256 dos 4 binários GUI em `<timestamp>\launchers.sha256`.

**Validação:** o snapshot contém os 7 XML, `services.managed.json` e o arquivo de
hashes. Restauração testada em diretório temporário.

---

## T00.2 — Varredura de segredos (Kimi + Codex)

- `hive-mind backup scrub-capture-outbox --dry-run`
- `hive-mind backup scrub-env-backups --dry-run`
- `hive-mind backup scrub-runtime-artifacts --dry-run`
- Varredura própria dos **108 paths untracked** por: chaves de API, tokens
  Bearer, `.env`, connection strings, cookies de sessão, caminhos com nome de
  usuário real em fixtures.

**Validação:** relatório `phase-00-secret-scan.json` com zero achados **ou** lista
explícita do que vai para `.gitignore` em vez de ser commitado.
**Fecha:** D-16 (parcial — a auditoria completa é a Fase 10).

---

## T00.3 — Triagem dos 231 paths

Classificar cada path em quatro baldes:

| Balde | Critério |
|---|---|
| `COMMIT` | código do runtime vivo, testes, config carregada |
| `GITIGNORE` | artefato gerado em runtime (`logs/`, `.hive-mind/state/`, `reports/` derivados) |
| `DELETE_CONFIRMED` | as 39 deleções de `.ps1/.vbs` — intencionais |
| `HOLD` | qualquer coisa não reconhecida |

**Validação:** `phase-00-triage.json` com os 231 paths classificados e revisados
antes do primeiro `git add`. Nenhum path pode ficar sem balde.

---

## T00.4 — `.gitignore` para artefatos de runtime

Garantir que estes nunca voltem a sujar o working tree:

```
.hive-mind/state/
logs/
reports/*.json      (os gerados; os versionados ficam)
*.db-shm
*.db-wal
```

**Teste:** `tests/unit/test_gitignore_covers_runtime_artifacts.py` — após uma
execução do supervisor em sandbox, `git status --porcelain` continua vazio.

---

## T00.5 — Commits atômicos e semânticos

Um commit por unidade coerente, nesta ordem (cada um deve compilar e passar
`pytest tests/unit -x` até onde a fase 04 ainda não corrigiu):

| # | Mensagem | Conteúdo |
|---|---|---|
| 1 | `feat(windows): native GUI launcher entrypoints` | `src/hive_mind/windows/`, `install/windows_launchers.py` |
| 2 | `feat(windows): native installer and prerequisites` | `install/windows.py`, `windows_prereqs.py`, `windows_support.py`, `snapshot.py`, `fullstack_readiness.py`, `install/__init__.py` |
| 3 | `feat(runtime): managed supervisor and native claude-mem launcher` | `daemon/state.py`, `daemon/managed.py`, `services/claude_mem_launcher.py`, `services/__init__.py` |
| 4 | `feat(runtime): native windows jobs and runtime services` | `maintenance/windows_jobs.py`, `windows_runtime.py`, `runtime_services.py` |
| 5 | `feat(validation): post-reboot windows validation` | `validation/post_reboot_windows.py`, `validation/topology.py`, `validation/vault.py` |
| 6 | `chore(maintenance): scrub, topology and vault utilities` | restante de `maintenance/` |
| 7 | `test: windows-native contract suites` | os 28 testes untracked |
| 8 | `refactor(windows)!: retire PS1/VBS/CMD owners` | as 39 deleções |
| 9 | `chore: ignore runtime artifacts` | `.gitignore` |

**Validação:** após o commit 9, `git status --porcelain --untracked-files=all`
**vazio**.
**Fecha:** D-01, D-03 (parcial).

---

## T00.6 — Publicar e alinhar

```
git push -u origin codex/universal-provider-capture
```

**Validação:** `git ls-remote origin refs/heads/codex/universal-provider-capture`
== `git rev-parse HEAD`; `git branch -vv` mostra upstream.

---

## T00.7 — Poda de branches e worktrees mortas

Após o push, avaliar: `codex/control-plane-redesign`,
`codex/runtime-consolidation`, `codex/windows-zero-install`,
`fix/hive-mind-post-audit-stabilization`. Deletar as superadas para eliminar
ambiguidade de "qual é o código canônico".

**Validação:** `git branch -a` reflete só o que está vivo.

---

## T00.8 — Registro da linha de base

Gravar em `docs/implementation/total-delivery-2026-07/BASELINE.md` o commit
resultante, os SHA-256 dos launchers e o resultado de `pytest tests/unit` nesse
commit — a régua contra a qual todas as fases seguintes são medidas.
