# Dream Cycle

Pipeline ETL determinístico que transforma observações brutas em
neurônios do córtex: **Ingestão → Distiller → Validator → Router →
Persistência**.

Implementação: [scripts/dream/dream_cycle.py](../scripts/dream/dream_cycle.py).
Referências: [ADR-007](implementation/ARCHITECTURE-DECISIONS.md),
[project-identity.md](project-identity.md).

## Agrupamento por projeto

O ciclo processa **um pipeline Distiller→Validator→Router por projeto**,
para não contaminar o córtex de um projeto com fatos de outro.

A chave de agrupamento é o `project_id` canônico, lido de
`observations.workspace_id` (gravado pelo bridge a partir do
`ProjectIdentityResolver`) — **não** o rótulo livre `observations.project`.

```python
identity = resolve_observation_project(row)
# identity.project_id    → chave de agrupamento e diretório
# identity.project_name  → exibição
# identity.canonical     → True se veio do resolver; False se é rótulo legado
```

Precedência em `resolve_observation_project()`:

1. `workspace_id` canônico → identidade canônica
2. rótulo `project` → identidade legada, preservada como está
3. `HIVE_DEFAULT_PROJECT` (padrão `Hive-Mind`) → legada sem rótulo

`workspace_id` igual a `default` ou vazio significa "nenhuma identidade
canônica registrada", não um projeto chamado *default*.

### O que isso corrige

Antes, raiz e worktree do mesmo repositório eram projetos distintos:

```
cortex/temporal/Hive-Mind/...
cortex/temporal/hive-mind-windows-zero-install/...
cortex/temporal/Hive-Mind/hive-mind-windows-zero-install/...
```

Agora convergem para um único diretório:

```
cortex/temporal/hive-mind/<topic>/neuronio-*.md
```

Isso também afeta a **janela balanceada**: `fetch_balanced_observations`
faz round-robin particionando por `project_id`, então três rótulos do
mesmo projeto não disputam mais três slots do rodízio.

## Janela balanceada

```sql
ROW_NUMBER() OVER (PARTITION BY <project_id> ORDER BY created_at, id)
```

Pega a observação mais antiga de **cada** projeto primeiro, depois a 2ª
de cada, respeitando o teto `HIVE_MAX_OBS_PER_CYCLE` (padrão 30). Sem
isso, um backlog grande faria um único projeto consumir todos os ciclos.

## Frontmatter dos neurônios

```yaml
---
type: fact
project: Hive-Mind            # rótulo humano (retrocompatível)
project_id: hive-mind         # chave canônica de filtro
project_name: Hive-Mind
identity_source: canonical    # canonical | legacy_label
topic: hivemind
integrity_hash: <hash>
aliases: ["..."]
last_updated: 2026-07-19 19:40
source: hive-dreamer
---
```

`project` permanece para não quebrar leitores existentes do vault.
`project_id` é a chave de filtro. `identity_source` torna auditável se a
identidade veio do resolver ou é rótulo legado.

## Dados legados

Observações sem `project_id` canônico **não são reescritas nem movidas**
(ADR-012). Seguem agrupadas pelo rótulo e o ciclo registra:

```
[Plumbing] N projeto(s) sem project_id canônico (agrupados pelo rótulo, preservados): ...
```

## Resiliência

Falha de um projeto (LLM, `database is locked`, IO) não aborta o ciclo:
as observações daquele projeto ficam `archived=0` para reprocessamento;
os demais projetos seguem. Roteador que falha coloca as observações em
quarentena (`archived=2`).

Distiller e Validator de projetos distintos rodam em paralelo
(`HIVE_DREAM_DISTILL_WORKERS`, padrão 4) porque são I/O-bound; **toda**
escrita no SQLite acontece na thread principal.

## Variáveis de ambiente

| Variável | Padrão | Efeito |
|---|---|---|
| `HIVE_MAX_OBS_PER_CYCLE` | 30 | teto de observações por ciclo |
| `HIVE_MAX_CYCLE_SECONDS` | 600 | deadline do ciclo |
| `HIVE_MAX_AMBIGUITIES` | 50 | teto de ambiguidades |
| `HIVE_DREAM_DISTILL_WORKERS` | 4 | paralelismo por projeto (1 = série) |
| `HIVE_DEFAULT_PROJECT` | `Hive-Mind` | projeto de observações legadas sem rótulo |

## Testes

| Arquivo | Cobertura |
|---|---|
| [tests/unit/test_dream_project_identity.py](../tests/unit/test_dream_project_identity.py) | resolução de identidade, particionamento, frontmatter |
| [tests/integration/test_dream_project_isolation.py](../tests/integration/test_dream_project_isolation.py) | isolamento A/B em SQLite real |
| [tests/unit/test_dream_project_segregation.py](../tests/unit/test_dream_project_segregation.py) | segregação original por projeto |
| [tests/unit/test_dream_balanced_window.py](../tests/unit/test_dream_balanced_window.py) | janela balanceada |
| [tests/unit/test_dream_resilience.py](../tests/unit/test_dream_resilience.py) | isolamento de falhas |

## Pendente

A validação operacional do ciclo completo (Distiller/Validator/Router
reais com modelos, reindexação e consulta filtrada) é a entrega D005.
Ver [ACCEPTANCE-MATRIX.md](implementation/ACCEPTANCE-MATRIX.md) gates
DC1–DC9.
