# Runtime & Daemon

O control plane nativo do Hive-Mind: o daemon `hive-mindd` e o manifesto
declarativo `config/runtime.yaml`.

Referências: [spec §15](../specs/control-plane-redesign-v2.md),
Anexo D.2 (lock), D.4 (pureza shadow), D.5 (project root),
[ADR-001](implementation/ARCHITECTURE-DECISIONS.md).

## Manifesto declarativo (F2 / D006)

`config/runtime.yaml` (schema v3) é a fonte única de verdade sobre
serviços, serviços externos, jobs e compose projects. Validado por
Pydantic v2 em [manifest.py](../src/hive_mind/daemon/manifest.py).

```powershell
hive-mind config validate     # erros de schema/invariantes
hive-mind config show --json  # manifesto normalizado
```

## Modelo de ownership

Cada serviço tem um estado de ownership (spec §9):

| Estado | Significado |
|---|---|
| `legacy` | o launcher antigo (Task Scheduler, Node, systemd) ainda é o dono |
| `shadow` | o daemon **observa** o serviço, sem agir |
| `managed` | o daemon é o dono (inicia, monitora, reinicia) — F4+ |

A transição é sempre por cutover explícito, um serviço por vez, com
rollback automático. Nada é adotado silenciosamente.

## Daemon `hive-mindd`

### Instância única (Anexo D.2)

Exatamente um `hive-mindd` por host, garantido por
[lock.py](../src/hive_mind/daemon/lock.py):

- **Windows**: named mutex `Local\Hive-Mind-hive-mindd`
- **Linux/macOS**: `flock(LOCK_EX | LOCK_NB)` em `state_dir/daemon.lock`

Uma segunda instância falha imediatamente com `SingleInstanceLockError`.

> Nota: o nome literal da spec (`Local\Hive-Mind\hive-mindd`) tem dois
> backslashes; objetos de kernel Win32 aceitam apenas um após o prefixo
> `Local\`, então os segmentos são unidos com hífen.

### Modo shadow (F3 / D007)

```powershell
hive-mindd run --shadow [--project-root <dir>] [--manifest <file>] [--state-dir <dir>]
```

Uma passada **passiva**: adquire o lock, lê o manifesto, calcula
readiness e ordem topológica dos serviços do perfil ativo, grava o
resultado e libera o lock. Sai 0.

Pureza absoluta ([supervisor.py](../src/hive_mind/daemon/supervisor.py),
garantida por `test_shadow_purity.py`): em shadow o daemon **não**

- inicia nenhum processo (`subprocess.Popen`/`run`/`call`);
- escreve em `runtime.yaml`;
- cria qualquer arquivo de state além de `services.shadow.json`;
- dispara jobs ou executa cutover.

O estado observado fica em `state_dir/services.shadow.json`:

```json
{
  "mode": "shadow",
  "profile": "local-min",
  "service_count": 7,
  "ready": false,
  "services": [
    {
      "name": "sinapse-claude-mem",
      "ownership": "legacy",
      "required": true,
      "dependencies": [],
      "startup_order": 10,
      "readiness": "unknown",
      "readiness_probe": "tcp",
      "would_start": true
    }
  ]
}
```

`readiness` é `ready` / `not_ready` (com um prober injetado) ou
`unknown` (sem prober). `ready` no topo é `true` só quando todos os
serviços `required: true` estão `ready`.

### Modo managed

`hive-mindd run` (sem `--shadow`) retorna `EX_UNAVAILABLE` (69): o
daemon gerenciado — que de fato inicia e supervisiona serviços — chega
na F4 (D008+). Shadow nunca vira managed sozinho.

## Infraestrutura Docker e autostart

**CURRENT.** Docker Desktop inicia com o Windows pela chave
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. O autostart do
Hive-Mind vem de tarefas do Task Scheduler registradas em `AtLogon`
(`HiveMind-Supervisor`, `HiveMind-PostRebootValidation`).

Os três compose projects obrigatórios são:

| Projeto | Compose | Containers |
|---|---|---|
| falkordb | `docker-compose.falkordb.yml` | `sinapse-falkordb` |
| milvus | `integrations/milvus/docker-compose.yml` | `hive-mind-milvus` |
| ragflow | `integrations/ragflow/docker-compose.yml` | `hive-mind-ragflow`, `-mysql`, `es01`, `redis`, `minio` |

`langfuse` é `required: false` — opcional.

### Restart policy é o que faz a stack voltar

Docker iniciar **não** basta: um container só retorna se o serviço
declarar `restart`. Um incidente real mostrou a diferença — `falkordb`
tinha `unless-stopped` e voltava, enquanto milvus e os cinco containers
do ragflow tinham `restart: no` e ficavam fora. A stack parecia
habilitada com dois dos três projetos obrigatórios ausentes.

Todo serviço de compose obrigatório declara `restart: unless-stopped`.
`tests/unit/test_compose_restart_policy.py` lê os projetos obrigatórios
do manifesto e falha se algum serviço não voltar após um restart do
Docker — inclusive em projeto novo.

A restart policy está presente nos compose consumidos pela instalação
limpa — `install.ps1` e `install.sh` executam `docker compose up -d`
sobre os arquivos do próprio repositório e não geram compose. **O fluxo
completo de instalação limpa e reboot ainda não foi executado**, então a
recuperação após reboot permanece não comprovada (gate W2/W3).

## State directory

`state_dir` (default `<project-root>/.hive-mind/state/`, ignorado pelo
git) guarda:

| Arquivo | Fase | Conteúdo |
|---|---|---|
| `daemon.lock` | D007 | lock de instância única (POSIX) |
| `services.shadow.json` | D007 | observação shadow, read-only sobre o legado |
| `services.managed.json` | D008 | estado dos processos managed (PIDs, restarts) |
| `schedule.shadow.json` | D008 | next-run calculado dos jobs (shadow, não dispara) |
| `cutover.journal` | F4 | journal transacional de cutover (ainda não) |
| `jobs.db` | F7 | persistência SQLite do scheduler (ainda não) |

## HTTP loopback de leitura (spec §15.1 / §15.4 — D007 fatia 2)

```powershell
hive-mindd run --shadow --serve [--host 127.0.0.1] [--port 37780]
```

Após a passada shadow, o daemon serve exatamente três rotas de leitura em
[http_api.py](../src/hive_mind/daemon/http_api.py), bind loopback, sem TLS,
sem auth, sem body de escrita:

| Rota | Resposta |
|---|---|
| `GET /health` | `{"state": "healthy"\|"degraded"\|"unknown", "services": {...}, "jobs": {}}` |
| `GET /ready` | 200 se todos os `required` estão ready; 503 caso contrário (fail-closed) |
| `GET /metrics` | Prometheus (`hive_service_count`, `hive_service_ready`, `hive_daemon_ready`) |

Sem observação shadow ainda, `/ready` é **503** (fail-closed, nunca
fail-open). Nenhuma rota de mutação existe: `POST /start`, `/stop`,
`/reload`, `/run-job` retornam 404. O invariante é testado
(`READ_ONLY_HTTP_ROUTES` em `test_daemon_http_routes.py`).

## CLI de leitura

```powershell
hive-mind service status [--project-root <dir>] [--state-dir <dir>] [--json]
```

Lê `state_dir/services.shadow.json` e imprime a observação shadow (mode,
profile, required, e por serviço: ownership, required, readiness, ordem).
Sem observação ainda, sai 1 com mensagem clara — nunca inventa "healthy".
É leitura pura; não muta nada.

## Socket de controle (spec §15.2/§15.3 — D008 fatia 1)

Toda mutação passa por um canal de controle local autenticado, nunca por
HTTP ([control.py](../src/hive_mind/daemon/control.py)):

- **Windows**: named pipe `\\.\pipe\hive-mindd` com DACL que concede
  acesso só ao usuário que o criou (owner + `GENERIC_ALL` via pywin32);
  outros usuários recebem `ACCESS_DENIED`.
- **POSIX**: Unix socket `state_dir/daemon.sock` com `0o600` dentro de um
  `state_dir` `0o700`.

Protocolo: um objeto JSON por mensagem —
`{"command", "args"}` → `{"ok", "data", "error"}`.

`run --shadow --serve` sobe o socket junto do HTTP, sob o lock de
instância única. O dispatcher em shadow
([control_dispatch.py](../src/hive_mind/daemon/control_dispatch.py))
honra `ping`/`status` e **recusa** toda mutação
(`start`/`stop`/`restart`/`reload`/`run-job`) — shadow nunca age
(Anexo D.4). As operações managed chegam na fatia 2 do D008.

```powershell
hive-mind service ping   # pong se o socket está vivo
```

Dependência: `pywin32` (Windows), decidido no ledger DH-002.

## Estado de implementação

Ver [CURRENT-STATE.md](implementation/CURRENT-STATE.md) e
[ACCEPTANCE-MATRIX.md](implementation/ACCEPTANCE-MATRIX.md) (grupo Runtime).

## O worker do Claude Mem (achado D004-R2W)

`config/runtime.yaml` declara o serviço `sinapse-claude-mem` como
`python -m claude_mem.worker`. **Esse módulo não existe** — não é
importável. O processo vivo é `bun` executando `worker-service.cjs` do cache
de plugins do Claude Code.

O manifesto nomeia um comando que ninguém executa, então não pode ser o
catálogo único que a D006 pretende. Registrado como M10 `FAILED`, atribuído
a **D006-R2**.

A correção **não** é apontar para o path do cache. Ele depende do usuário,
da versão do plugin e do cache, não é instalável e quebra em qualquer
atualização. D006-R2 deve entregar um launcher nativo que descubra a
instalação, valide o entrypoint, respeite `CLAUDE_MEM_DATA_DIR`, aceite
porta configurável e falhe com erro claro — e o manifesto aponta para o
launcher.

