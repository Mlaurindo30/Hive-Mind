# Operação e Manutenção — Hive-Mind

> **Hive-Mind v3.10.1** — rotinas de operação do dia a dia: diagnóstico de
> saúde, backup verificado, recuperação de desastres, comandos de manutenção e
> sincronização P2P.
>
> Referências: [runtime.md](runtime.md) (daemon/serviços/scheduler),
> [instalacao.md](instalacao.md), [cli.md](cli.md),
> [operacao.md](operacao.md) (auditoria do motor de backup),
> [07-p2p-sync-setup.md](07-p2p-sync-setup.md).

---

## 1. Diagnóstico de saúde

### 1.1 Pré-checagem de backends (MCP)

Sempre que houver dúvida sobre o estado dos backends, use `sinapse_health()` —
ela devolve o status dos 7 backends federados por `sinapse_query` (UMC,
NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem) e as
métricas `knowledge_health`.

### 1.2 `hive-mind doctor`

Diagnóstico **read-only** das integrações de agentes (escreve nada):

```powershell
hive-mind doctor                 # todos os providers detectados
hive-mind doctor --only claude   # um provider
hive-mind doctor --json
```

Exit `0` só quando **todos os providers detectados** estão totalmente
configurados. Um agente não instalado **não** é falha — não há o que
configurar para um provider ausente.

### 1.3 `hive-mind service status` / `service ping`

```powershell
hive-mind service status          # observação shadow/legacy/state
hive-mind service status --json
hive-mind service ping            # pong se o socket de controle está vivo
```

`service status` lê `state_dir/services.shadow.json` (ou o state legado do
supervisor Node em `logs/supervisor/state.json`) e imprime `mode`, `profile`,
`required`, e por serviço: `ownership`, `required`, `readiness`, `startup_order`.
Sem observação, sai `1` com mensagem clara — nunca inventa "healthy".

### 1.4 Daemon HTTP loopback

Com `hive-mindd run --shadow --serve` (ou `--serve` managed):

```powershell
curl http://127.0.0.1:37780/health     # {"state": ..., "services": {...}}
curl http://127.0.0.1:37780/ready      # 200 (ready) ou 503 (fail-closed)
curl http://127.0.0.1:37780/metrics    # Prometheus
```

### 1.5 Validadores de pipeline

```powershell
hive-mind validate vault      # audit de Markdown/links/encoding (read-only)
hive-mind validate delivery   # backlog de captura e buckets legados (read-only)
hive-mind validate topology   # worktrees/cópias + sugestão de cleanup
hive-mind validate agents     # canário de captura multi-agente
```

Ver [cli.md](cli.md) §validate para a semântica completa de cada um.

---

## 2. Backup verificado

O backup real é o motor nativo `hive-mind backup`, portado de
`scripts/health/backup_databases.py` (entrega D008-R1B). Ele usa
`sqlite3.Connection.backup()` sobre origem `mode=ro` (cópia consistente com o
banco em uso) e soma as garantias que faltavam ao legado:

| Garantia | Detalhe |
|---|---|
| Lock de execução única | `MaintenanceLock` (exclusive-create) — sem duas execuções simultâneas |
| Finalização atômica | `.partial` + `os.replace` |
| Verificação | `integrity_check` + `foreign_key_check` + SHA-256 |
| Retenção segura | poda **só após** o novo backup ser verificado (um backup novo corrompido nunca despeja um antigo bom) |
| Manifesto de conteúdo | JSON com artefatos, hashes, tamanhos, cobertura |
| Dry-run por padrão | `run` não escreve sem `--apply` |
| Restore protegido | grava em diretório alternativo por padrão |

### 2.1 Comandos

```powershell
hive-mind backup run [--apply]                  # dry-run por padrão
hive-mind backup status
hive-mind backup verify [--manifest <path>]
hive-mind backup restore --manifest <path> --into <dir> [--overwrite-live]
```

`restore` grava em **diretório alternativo** por padrão; sobrescrever exige
`--overwrite-live` explícito (destrutivo).

### 2.2 Cobertura por componente

| Componente | Cobertura |
|---|---|
| claude-mem SQLite | BACKED_UP |
| UMC / `hive_mind.db` | BACKED_UP |
| swarmclaw / hermes SQLite | BACKED_UP |
| Markdown do `cerebro/` | NOT_SUPPORTED (fora do backup SQLite; ver P2P §6) |
| Milvus / FalkorDB / RAGFlow | REQUIRES_SERVICE_SNAPSHOT |
| LightRAG | EXTERNALLY_MANAGED (regenerável via Dream Cycle) |
| `.env` / segredos | NOT_SUPPORTED (deliberado) |

Copiar volume Docker em uso **não** é backup consistente e não é feito.

### 2.3 Subcomandos de saneamento (`backup scrub-*` / arquivamento)

O grupo `backup` também expõe saneamento de dados legados — todos dry-run por
padrão:

| Comando | O que faz |
|---|---|
| `backup archive-historical-outbox` | Arquiva linhas inertes do `capture_outbox` (`--cutoff-occurred-at`) |
| `backup scrub-capture-outbox` | Redige material com formato de segredo do outbox |
| `backup scrub-runtime-artifacts` | Redige segredos de artefatos de log/auditoria |
| `backup scrub-env-backups` | Redige valores de segredo de `.env` legados em `backups/` |
| `backup archive-topology` | Arquiva paths de topologia classificados como ARCHIVE |
| `backup cleanup-topology-stale` | Arquiva/remove resíduos stale marcados `REMOVE_AFTER_APPROVAL` |

---

## 3. Recuperação de desastres (`recover.sh`)

Se `hive_mind.db` for corrompido ou perdido, ele é **totalmente reconstruível**
a partir do vault. O wrapper `scripts/utils/recover.sh` delega ao
`scripts/utils/recovery.py`:

```bash
./scripts/utils/recover.sh verify                    # checa integridade
./scripts/utils/recover.sh backup                    # snapshot consistente
./scripts/utils/recover.sh rebuild-indexes           # reconstrói índices
./scripts/utils/recover.sh restore BACKUP_DB [--rebuild-indexes]
```

Fluxo clássico de reconstrução completa do índice a partir dos `.md`:

1. Para o Watcher (`sinapse-graphify-watch`).
2. Faz backup do DB corrompido (se existir).
3. Cria um novo `hive_mind.db` do zero (schema do zero).
4. Reindexa todos os arquivos de `cerebro/` via Graphify.
5. Reinicia o Watcher.

Tempo estimado: 2–10 minutos conforme o tamanho do vault.

> O `restore` para `sinapse-graphify-watch.service`/`sinapse-api.service`
> antes de restaurar e os religa depois (trap `EXIT`), evitando escrita
> concorrente durante a restauração.

---

## 4. Comandos de manutenção

### 4.1 Watcher (sincronização em tempo real)

```bash
./scripts/services/start-watcher.sh          # sobe o watcher em background
pgrep -f "start-watcher" && echo "OK"        # confere se está rodando
pkill -f "start-watcher"                     # para
```

O Watcher usa `watchdog` sobre `cerebro/`. A cada mudança `.md`: fila o evento
(debounce 500ms), chama Graphify para reindexar e atualiza o grafo estrutural;
o caminho UMC/FTS/vector é do `WriteIndexer`. **Não** deve ser o único caminho
de escrita síncrona (ver [runtime.md](runtime.md) e
[04-infrastructure.md](04-infrastructure.md) §3.1).

### 4.2 Dream Cycle (consolidação)

```bash
python scripts/dream/dream_cycle.py --once --real     # uma execução real
python scripts/dream/dream_cycle.py                   # dry-run
```

Consolida observações → fatos validados → Atlas (`cortex/temporal/`). O go-live
automático é gated por M9 verde ≥ 7 dias (ver [runtime.md](runtime.md) §15.2).

### 4.3 Auditoria de memória

```bash
python scripts/health/audit_memory.py            # read-only
python scripts/health/audit_memory.py --fix      # reindexa divergências
python scripts/health/audit_memory.py --fix --verbose
python scripts/health/audit_memory.py --trace "nome-do-arquivo.md"
```

Audita apenas neurônios reais do córtex temporal; arquivos `type: moc` ficam
fora do índice (e são removidos se uma versão antiga os indexou).

### 4.4 Portal visual

```bash
python scripts/knowledge/generate_portal.py      # gera portal.canvas (Obsidian Canvas)
```

### 4.5 Backfills e drenagem (FASE 2)

| Comando | Uso | Efeito |
|---|---|---|
| `python scripts/maintenance/vector-backfill.py [--limit N] [--batch B]` | corrige o gap de neurônios fora do `search_vec` | indexa via `core.indexing.index_neuron_ids` (embed + search_vec + HNSW) |
| `python scripts/maintenance/data-backfill.py [--dry-run]` | integridade de dados | `consumed_by='legacy'` (archived), `project='unclassified'`, `topic` derivado de `source_file` |
| `python scripts/maintenance/drain-candidates.py [--dry-run] [--limit N]` | drena `knowledge_candidates` presos | promove `verified+low`, segura `hypothesis`/`risk=high` |
| `python scripts/knowledge/backfill_decisions.py` | backfill de decisões | consolida decisões legadas |
| `python scripts/maintenance/backfill_document_parents_chunks.py` | backfill de documentos | pais/chunks do K6 |
| `python scripts/maintenance/backfill_review_dates.py` | backfill de datas de revisão | `review_date`/`next_review` |

Todos são idempotentes e não-destrutivos; os que mutam usam `--dry-run` por
padrão quando aplicável.

### 4.6 Rotinas agendadas

Consulte [runtime.md](runtime.md) §14–15 para o inventário completo de jobs
(cron no manifesto, Task Scheduler no Windows, systemd timers no POSIX).

---

## 5. Sincronização P2P (Syncthing)

### 5.1 Arquitetura do swarm

```
  Máquina A (PC)           Máquina B (Laptop)         VPS
  cerebro/                 cerebro/                   cerebro/
     │                         │                         │
     └──────── Syncthing ───────┴──────── Syncthing ─────┘
                (TLS, P2P, sem servidor central)

  Cada máquina tem hive_mind.db próprio, Watcher em background e
  audit_memory.py via cron (1x/hora).
```

O Syncthing transporta os `.md` entre máquinas. `hive_mind.db` **não** é
sincronizado — cada máquina mantém seu índice local, reconstruído a partir dos
Markdown recebidos.

### 5.2 Configuração

1. Instalar Syncthing (`apt install syncthing` / `brew install syncthing` /
   download em syncthing.net).
2. UI em `http://localhost:8384` → **Add Folder**.
3. Folder Path = caminho absoluto de `cerebro/`; Folder Type = "Send &
   Receive"; File Versioning = "Simple File Versioning" (≥ 5 versões).
4. Compartilhar com as outras máquinas via **Device ID**.

### 5.3 Prevenção de colisão (UUID v4)

Todas as chaves primárias do UMC usam UUID v4 gerado localmente:

```python
import uuid
neuron_id = str(uuid.uuid4())   # "550e8400-e29b-41d4-a716-446655440000"
```

IDs sequenciais colidiriam entre máquinas (ambas criariam `id=1`). UUID v4 tem
probabilidade de colisão de 1 em 10^36 — irrelevante na prática.

### 5.4 Integridade por hash (SHA-256)

Cada arquivo indexado recebe um hash no momento da indexação, armazenado em
`neurons.hash` e no frontmatter (`integrity_hash`). O `audit_memory.py` compara
o hash do arquivo físico com `neurons.hash`; divergência indica arquivo
modificado em outra máquina e índice local desatualizado.

### 5.5 Síntese Dialética (resolução de conflitos)

Quando dois textos do mesmo `source_file` têm conteúdo semântico
**irreconciliável** (conflito factual, não só hash diferente), o sistema
registra uma **ambiguidade** e agenda resolução autônoma via LLM
(`semantic_diff.py`):

```
  cosine(embed(A), embed(B))
  ├── > 0.92: quase idêntico → reindex simples
  ├── 0.70–0.92: complementares → merge candidato
  └── < 0.70: divergentes → LLM para análise semântica
```

Resoluções possíveis: `merge` (nota combinada), `choose_a`/`choose_b` (mantém
uma, arquiva a outra), `branch` (mantém ambas com sufixo `-version-a`/
`-version-b`). Resultados gravados na tabela `ambiguities`
(`pending | resolved | escalated`).

### 5.6 Metadados de proveniência

```yaml
---
title: Decisão de migrar para Hetzner
agent: claude-fable-5
trust_level: 2           # 1=baixo, 2=médio, 3=alto
machine_id: laptop-home
integrity_hash: a3b4c5d6e7f8...
created: 2026-06-10
source_observation_ids: ["550e8400-...", "6ba7b810-..."]
---
```

Para rastrear um fato suspeito: `audit_memory.py --trace "arquivo.md"`.

---

## 6. Cross-references

- **Runtime/daemon**: [runtime.md](runtime.md)
- **Instalação**: [instalacao.md](instalacao.md)
- **CLI completa**: [cli.md](cli.md)
- **Backup (auditoria e estado real)**: [operacao.md](operacao.md)
- **P2P (referência original)**: [07-p2p-sync-setup.md](07-p2p-sync-setup.md)
- **Observabilidade (métricas/alertas)**: [observabilidade.md](observabilidade.md)
- **Incidentes (runbook de recuperação)**: [incidentes.md](incidentes.md)
- **Pipeline de dados (Dream Cycle, promoção)**: [pipeline-dados.md](pipeline-dados.md)
