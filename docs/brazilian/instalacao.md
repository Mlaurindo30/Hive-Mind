# Instalação — Hive-Mind

> **Hive-Mind v3.10.1** — guia de instalação completa: perfis, instalação
> nativa Windows, instalação Linux, Docker greenfield e rollback.
>
> Referências: [runtime.md](runtime.md) (serviços/scheduler),
> [operacao.md](operacao.md) (pós-instalação e manutenção),
> [cli.md](cli.md) (registro de agentes e jobs),
> [15-windows-clean-install.md](15-windows-clean-install.md) (aceitação de
> instalação limpa Windows), [04-infrastructure.md](04-infrastructure.md)
> (requisitos e variáveis).

---

## 1. Perfis de instalação

A instalação é parametrizada por **perfil**. O perfil define o contrato de
pré-requisitos e quais serviços são `required`.

| Perfil | Descrição | Backends | Serviços obrigatórios |
|---|---|---|---|
| `local-min` | Caminho local SQLite/vetor. Mínimo para uso diário. | SQLite + `sqlite-vec` + claude-mem + Graphify + FalkorDB (Graphiti) | `sinapse-claude-mem`, `sinapse-sqlite-vec`, `sinapse-capture-realtime` |
| `local-full` | Stack completa com Docker. | + Milvus, RAGFlow, FalkorDB, Syncthing | os de `local-min` + `docker-desktop`, `falkordb`, `milvus`, `ragflow`, `syncthing-watcher` |

O contrato de perfil vive em `config/profiles/<perfil>.env.example`. O
instalador **falha** (exit não-zero) se algum serviço `required` do perfil
selecionado não ficar `healthy`.

> A fonte canônica do catálogo de serviços e da semântica `required` é
> `config/runtime.yaml` — ver [runtime.md](runtime.md) §12–13.

---

## 2. Pré-requisitos

### 2.1 Tabela geral

| Dependência | Versão mínima | Uso | Obrigatório? |
|---|---|---|---|
| Python | 3.12 (Windows) / 3.10+ (POSIX) | Core, UMC, Dream Cycle, MCP, API | Sim |
| uv | 0.4+ | Gestor de pacotes canônico | Sim |
| SQLite | 3.44+ (com `sqlite-vec`) | UMC | Sim (via pip) |
| Node.js | 18+ | Supervisor de serviços e claude-mem | Sim |
| Bun | 1.0+ | claude-mem (TypeScript) | Sim |
| Rust / Cargo | 1.70+ | Compilação do RTK | Sim |
| Ollama | — | LLM/embeddings locais | Sim (validação) |
| Docker Desktop | — | Milvus/RAGFlow/FalkorDB | Apenas `local-full` |
| Syncthing | 1.27+ | P2P do vault | Apenas `local-full` |
| WSL 2 | — | `local-full` (validação) | Apenas `local-full` |
| Visual Studio Build Tools | 2022 | MSBuild (pré-requisito de build) | Apenas `local-full` |
| Git | — | Bootstrap de integrações pinned | Sim |
| Obsidian | — | Interface visual do vault | Opcional |

### 2.2 Python dependencies

`fastapi`, `uvicorn`, `pydantic≥2.7`, `cryptography≥42`, `watchdog≥4`,
`pypdf`, `python-docx`, `PyMuPDF`, `mss`, `pyyaml`, `httpx`, `hnswlib≥0.8`,
`duckdb≥0.10`, `fastembed` (legacy/fallback). Resolvidas por `uv sync
--frozen` a partir de `uv.lock`.

---

## 3. Instalação Windows (nativa)

### 3.1 Cadeia de entrypoints

O caminho nativo Windows não usa WSL2 e roda contra um `.venv` project-local:

```
install.bat
  └─> scripts/setup/windows_install_entry.py   (normaliza switches -foo -> --foo)
        └─> src/hive_mind/install/windows.py   (instalador canônico Python)
```

`install.bat` é um wrapper fino: usa o `.venv\Scripts\python.exe` se já
existir, senão `py.exe -3`.

### 3.2 Comando rápido

```powershell
git clone <repo-url> Hive-Mind
cd Hive-Mind
install.bat --profile local-min --install-prerequisites
```

Para a stack completa:

```powershell
install.bat --profile local-full --install-prerequisites
```

### 3.3 Switches

`install.bat` aceita o spelling antigo do PowerShell (`-Profile`,
`-WithTests`, …), traduzido em
[windows_install_entry.py](../scripts/setup/windows_install_entry.py). O
instalador Python aceita o spelling `--`:

| Switch | `--` equivalente | Efeito |
|---|---|---|
| `-Profile local-min\|local-full` | `--profile` | Perfil de instalação (default `local-min`) |
| `-InstallPrerequisites` | `--install-prerequisites` | Instala pré-requisitos via winget |
| `-PrerequisitesOnly` | `--prerequisites-only` | Só prepara pré-requisitos e sai |
| `-SkipPrerequisites` | `--skip-prerequisites` | Pula o bootstrap de pré-requisitos |
| `-WithTests` | `--with-tests` | Roda `pytest tests/unit tests/integration tests/e2e` |
| `-WithRealTests` | `--with-real-tests` | Roda `tests/real -m real` (JUnit em `logs/`) |
| `-SkipAgents` | `--skip-agents` | Não registra MCP nos agentes |
| `-SkipServices` | `--skip-services` | Não instala serviços/jobs/autostart |
| `-NonInteractive` | `--non-interactive` | Sem prompts |
| `-Force` | `--force` | Reinstala (não apaga `.venv` automaticamente) |
| `-DryRun` | `--dry-run` | Valida só o contrato de pré-requisitos |
| `-Repair` | `--repair` | Repara instalação existente |
| `-Update` | `--update` | Atualiza |
| `-Uninstall` | `--uninstall` | Desinstala |
| `-PreserveVault` | `--preserve-vault` | Mantém o vault |
| `-PreserveDatabase` | `--preserve-database` | Mantém o `hive_mind.db` |
| `-SystemService` | `--system-service` | Instala como serviço de sistema |

### 3.4 Pré-requisitos Windows (winget)

Detectados/instalados por
[windows_prereqs.py](../src/hive_mind/install/windows_prereqs.py):

| Pré-requisito | winget ID | Required |
|---|---|---|
| Git | `Git.Git` | sim |
| uv | `astral-sh.uv` | sim |
| Bun | `Oven-sh.Bun` | sim |
| Node LTS | `OpenJS.NodeJS.LTS` | sim |
| Rustup | `Rustlang.Rustup` | sim |
| Ollama | `Ollama.Ollama` | sim |
| Docker Desktop | `Docker.DockerDesktop` | `local-full` |
| Syncthing | `Syncthing.Syncthing` | `local-full` |
| WSL 2 | — (`wsl --install`) | `local-full` |
| Visual Studio Build Tools | `Microsoft.VisualStudio.2022.BuildTools` | `local-full` |

Se um pré-requisito exigir restart (código `3010`/`1641` do winget), o
instalador grava `backups/install-state/prerequisites.json` e pede reexecução.

### 3.5 Fluxo de instalação (passo a passo)

O instalador nativo Windows executa, em ordem:

1. **Snapshot protegido de memória** — `backups/` (verificação pré-instalação).
2. **Host prerequisites** — bootstrap winget (quando `local-full` ou
   `--install-prerequisites`).
3. **Preflight** — confere `uv`, `git`, `node`.
4. **Project virtual environment** — `ensure_python_runtime` (`.venv`).
5. **Environment file** — copia `.env.example` → `.env`, aplica o contrato do
   perfil e gera `HIVE_MIND_API_KEY` (se ausente).
6. **Container stack** (`local-full`) — sobe FalkorDB, Milvus, RAGFlow via
   `docker compose up -d --quiet-pull`, inicia Syncthing e escreve
   `VECTOR_BACKEND=milvus`, `MILVUS_URI`, `FALKORDB_*`, `RAGFLOW_BASE`; valida
   readiness (`local-min` escreve `VECTOR_BACKEND=sqlite_vec`).
7. **Ollama local models** — `ollama pull` dos modelos configurados
   (`snowflake-arctic-embed2:latest`, `qwen2.5:3b`, …).
8. **Pinned integrations** — `scripts/setup/components.py bootstrap`
   (Graphify, NeuralMemory, RTK; `git safe.directory`).
9. **Python dependencies** — `uv sync --frozen --all-groups`; cria
   `pythonw` GUI launchers e valida `pydantic`, `watchdog`.
10. **Wrapper and UMC setup** — `verify_wrappers.py` (com `--require-docker`
    no `local-full`) + `setup_umc.py`.
11. **Vault materialization** — `sync_vault_templates` + cria a árvore
    anatômica (`cortex/`, `cerebelo/`, `diencefalo/`, `tronco/`, `90-intake`).
12. **Graph/index bootstrap** — `python -m graphify update cerebro`.
13. **MCP registration** — `hive-mind agents register --apply --instructions`
    (a menos de `--skip-agents`).
14. **claude-mem native runtime** — `npx claude-mem@13.6 install --ide codex-cli`.
15. **RTK** — `cargo build --locked --release` em `integrations/rtk`.
16. **Services** — `service manifest`, `node npm/bin/hive-mind.js services
    restart/wait/status`.
17. **Scheduled knowledge jobs** — `hive-mind service windows-jobs --apply`.
18. **Windows autostart** — `hive-mind service windows-runtime --apply`.
19. **Done**.

### 3.6 Aceitação de instalação limpa

Procedimento de aceitação (detalhado em
[15-windows-clean-install.md](15-windows-clean-install.md)):

1. `install.bat --profile local-min --install-prerequisites`.
2. `node npm/bin/hive-mind.js services status` — exit 0 só se todo serviço
   `required` estiver `healthy`.
3. `node npm/bin/hive-mind.js doctor` — exit 0 só com API + serviços saudáveis.
4. Reiniciar o Windows e inspecionar `logs/post-reboot-validation.json`
   (`unhealthy_required_services` vazio).

Checks de release (offline, `windows-latest`):

```powershell
python scripts/release/validate_package.py --source-root .
./tests/install/test_windows_bootstrap.ps1
install.bat --profile local-min --dry-run
install.bat --profile local-full --dry-run
node --test npm/test/supervisor.test.js npm/test/doctor.test.js
```

---

## 4. Instalação Linux (`install.sh`)

### 4.1 Comando rápido

```bash
git clone <repo-url> ~/Documentos/Projects/Hive-Mind
cd ~/Documentos/Projects/Hive-Mind
./install.sh
```

Headless / CI (sem terminal interativo):

```bash
HIVE_DREAMER_PROVIDER=google HIVE_DREAMER_MODEL=gemini-2.0-flash \
GOOGLE_API_KEY=<your_key> ./install.sh --non-interactive
```

### 4.2 O que `install.sh` faz (12 passos)

```
  [1/12]  Prerequisites and Python 3.12 managed by uv
  [2/12]  Reproducible Python environment (.venv + uv.lock)
  [3/12]  Local Graphify and FTS / sqlite-vec / HNSW indexes
  [4/12]  Skills into detected agents
  [5/12]  Global Claude-Mem via npx / marketplace
  [6/12]  Local NeuralMemory
  [7/12]  RTK pinned and compiled
  [8/12]  Hermes MCP
  [9/12]  Single synchronization cron
  [10/12] Hermes sinapse-memory plugin
  [11/12] Intelligence configuration
  [12/12] Three managed MCPs into external agents and services
```

Ao final, o instalador pergunta se deve configurar o provider de LLM via
`setup-brain.sh` (Gemini, OpenAI, Anthropic, Ollama…). Responda **Y** e siga o
menu, depois reinicie o agente.

### 4.3 Serviços user-level (systemd)

O instalador de serviços
([runtime_services.py](../src/hive_mind/maintenance/runtime_services.py))
instala units user-level idempotentes em `~/.config/systemd/user/` e habilita
os timers seguros (bridge, daily, weekly, topics, health, alert, decisions,
projects, patterns, conflicts, work, review, backup). O `dream` **não** é
habilitado por padrão — seu go-live é gated por M9 verde ≥ 7 dias. Ver
[runtime.md](runtime.md) §15.2.

### 4.4 WSL2

O Hive-Mind roda bem em WSL2 (Ubuntu 22.04+). O `visual_capture.py` detecta o
WSL2 e invoca `powershell.exe` do host para capturar telas físicas do Windows.
Abra `C:\Projects\Hive-Mind\cerebro` no Obsidian do host para editar o vault
em tempo real.

---

## 5. Docker greenfield

Implantação em container para um host limpo, sem instalação Python/Node local.

### 5.1 Componentes

| Arquivo | Papel |
|---|---|
| `Dockerfile` | Imagem `python:3.12-slim` + `uv`; copia source completo (`core/`, `scripts/`, `integrations/`, `plugins/`, `config/`, `templates/`); `uv sync --frozen --no-dev` |
| `docker-compose.yml` | Orquestração unificada: FalkorDB + app (núcleo `local-min`) + Milvus + RAGFlow (`--profile full`) |
| `docker/entrypoint.sh` | Materializa o vault na primeira execução do volume, depois delega ao `hive-mindd` |

### 5.2 Materialização do vault (primeira execução)

O `entrypoint.sh` replica o `materialize_vault()` do `install.sh` de forma
idempotente:

- Se `vault-manifest.json` e `cortex/temporal` já existem → **não faz nada**.
- Caso contrário, copia `templates/vault/` para `cerebro/` e cria a árvore
  anatômica completa (`cortex/{temporal,frontal,insula,occipital,parietal}`,
  `cerebelo/{diario,semanal,mensal,anual,sessoes,padroes}`,
  `diencefalo/{roteamento,setores}`, `tronco/infra`) + `.gitignore`.

### 5.3 Uso

```bash
docker build -t hive-mind .
docker compose up -d                     # núcleo local: FalkorDB + app
docker compose --profile full up -d      # + Milvus + RAGFlow (produção)
```

O container `app` roda o daemon control-plane em modo managed:

```dockerfile
CMD ["uv", "run", "hive-mindd", "run", "--serve", "--host", "0.0.0.0", "--port", "37780"]
```

Volumes e portas:

| Item | Mapeamento |
|---|---|
| `./cerebro` | `:/app/cerebro` (vault montado) |
| `hive-mind-data` | `:/app/data` (hive_mind.db) |
| `./logs` | `:/app/logs` |
| `./config` | `:/app/config:ro` |
| `.env` | montado só se existir no host (`env_file required: false`) |
| Portas | `37702` (API), `37780` (daemon HTTP) |

Variáveis de ambiente do container: `SINAPSE_HOME=/app`,
`FALKORDB_URL=redis://falkordb:6379`, `HIVE_MIND_API_KEY` (do host).

> **Nota:** a API (:37702) exige `HIVE_MIND_API_KEY` — fail-closed: sem a
> chave, a API não inicia. Ver [seguranca.md](seguranca.md).

---

## 6. Pós-instalação

1. **Configurar LLM por papel** — `./scripts/setup/setup-brain.sh` (ou
   `setup-brain.bat`) escolhe provider/modelo/API key de cada papel.
2. **Registrar o MCP** — `hive-mind agents register --apply --instructions`
   (ver [cli.md](cli.md) §agents). Reinicie o agente.
3. **Validar** — `hive-mind doctor`, `hive-mind service status`,
   `sinapse_health`.
4. **Armed post-reboot validation** — `python -m
   hive_mind.maintenance.runtime_services arm-post-reboot` (POSIX).

---

## 7. Rollback e desinstalação

### 7.1 Snapshot protegido

O instalador cria um snapshot verificado em `backups/` **antes** de qualquer
mutação (`create_install_snapshot`). Em caso de falha, o snapshot é o ponto de
retorno.

### 7.2 Desinstalar (Windows)

```powershell
install.bat --uninstall --preserve-vault --preserve-database
```

`--preserve-vault` e `--preserve-database` mantêm o conteúdo do cérebro;
omitir ambos remove a instalação por completo.

### 7.3 Registrar de novo os agentes

Para registrar/desregistrar MCP sem reinstalar tudo:

```powershell
hive-mind agents register --only claude --apply     # ou --only codex, etc.
hive-mind agents unregister --only claude --apply   # remove a entrada
```

### 7.4 Restaurar tarefas do Task Scheduler

O registro de jobs exporta o XML anterior para `logs/scheduled-tasks/` e
`~/.hive-mind/backups/windows-runtime/` antes de sobrescrever. Para restaurar,
reimporte o XML com `schtasks /create /tn <nome> /xml <backup> /f`. Ver
[runtime.md](runtime.md) §15.1.

---

## 8. Cross-references

- **Runtime/daemon/scheduler**: [runtime.md](runtime.md)
- **Operação/manutenção**: [operacao.md](operacao.md)
- **CLI completa**: [cli.md](cli.md)
- **Aceitação Windows**: [15-windows-clean-install.md](15-windows-clean-install.md)
- **Infra/portas/variáveis**: [04-infrastructure.md](04-infrastructure.md)
- **Arquitetura**: [arquitetura.md](arquitetura.md)
- **Segurança (fail-closed, chaves)**: [seguranca.md](seguranca.md)
