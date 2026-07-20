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

## State directory

`state_dir` (default `<project-root>/.hive-mind/state/`, ignorado pelo
git) guarda:

| Arquivo | Fase | Conteúdo |
|---|---|---|
| `daemon.lock` | D007 | lock de instância única (POSIX) |
| `services.shadow.json` | D007 | observação shadow, read-only sobre o legado |
| `cutover.journal` | F4 | journal transacional de cutover (ainda não) |
| `jobs.db` | F7 | persistência do scheduler (ainda não) |

## Controle e leitura (spec §15 — planejado)

| Operação | Canal |
|---|---|
| `GET /health` `/ready` `/metrics` | HTTP loopback `127.0.0.1:37780` (só leitura) |
| `service start/stop/restart`, `reload`, `run-job` | named pipe / Unix socket com ACL |

O HTTP loopback nunca expõe mutação; toda mutação passa pelo socket de
controle autenticado. Ambos são fatias seguintes do D007/D008.

## Estado de implementação

Ver [CURRENT-STATE.md](implementation/CURRENT-STATE.md) e
[ACCEPTANCE-MATRIX.md](implementation/ACCEPTANCE-MATRIX.md) (grupo Runtime).
