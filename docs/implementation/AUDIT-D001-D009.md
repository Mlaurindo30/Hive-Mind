# Auditoria retrospectiva D001 → HEAD — propriedade nativa

Entrega: **D009-R1**. Data: 2026-07-20.

Objetivo: comprovar, contra o código e não contra o ledger, que a
arquitetura aprovada foi respeitada — lógica de produto no pacote Python,
`.ps1`/`.sh` apenas como wrappers.

## 1. Branch e HEAD

| Campo | Valor |
|---|---|
| Branch | `codex/control-plane-redesign` |
| HEAD auditado | `c4ef7d5` |
| Commit base da D001 | `ae32195` (`docs(implementation): establish living execution plan`) |
| `git status` | limpo, exceto 16 untracked em `.tmp/` (LOCAL TEST ARTIFACT, DH-001) |

## 2. Commits por entrega (fonte: git, não o ledger)

| Delivery | Commits | Trailer `Delivery:` |
|---|---|---|
| D001 | `ae32195`, `834e405` | ✅ ambos |
| D002 | `2ae8558` | ✅ |
| D003 | `fca4c5a` | ✅ |
| D004 | `f85d8ea` | ❌ **ausente** (só no assunto) |
| D005 | `d793353` | ❌ **ausente** |
| D006 | `1db2523` | ❌ **ausente** |
| D007 | `26ab2ff`, `bcaa961`, `cb4c66d` | ✅ |
| D008 | `3d9020a`, `c2c9d0c`, `9064897`, `566f469`, `1857869` | ✅ |
| D009 | `98f6ec1`, `3501e6e`, `c4ef7d5` | ✅ |

**A-01 (P4):** D004/D005/D006 violam a regra do README ("toda mensagem de
commit cita o ID no corpo ou trailer"). São exatamente os três commits
feitos fora do contexto visível. Não retroagível sem reescrever histórico
— registrado, não corrigido.

## 3. Scripts alterados desde a D001

```
git diff --name-status ae32195~1..HEAD -- "*.ps1" "*.psm1" "*.sh" "*.bat" "*.cmd" "*.vbs" "npm/**/*.js"
→ (vazio)
```

**Resultado positivo:** desde que a documentação viva começou, **nenhum**
`.ps1`, `.sh`, `.bat`, `.cmd`, `.vbs` ou arquivo Node foi alterado.
Nenhuma lógica nova entrou em script de shell. A regra "não continuar
adicionando comportamento a scripts" foi respeitada.

> **Correção pós-remediação (2026-07-20).** A frase acima descreve o
> estado **no momento da auditoria** (`c4ef7d5`). Depois dela,
> `register-mcp.sh` foi alterado em `fef5383` (D009-R3). Precisão:
>
> | Categoria | Estado |
> |---|---|
> | lógica **nova** adicionada a scripts | **zero** (invariante mantido) |
> | scripts alterados para **remover/isolar** legado | `register-mcp.sh` (D009-R3) |
> | estado final desejado | wrapper mínimo |
> | remoção definitiva | D009-R5 / D009-R6 |
>
> A alteração é aceitável **somente** porque removeu lógica e desligou um
> caminho legado — não porque scripts voltaram a ser destino de código.

Python sob `scripts/` alterado:

| Arquivo | Mudança | Entrega | Classificação |
|---|---|---|---|
| `scripts/capture/project_identity.py` | M | D003, D004 | **biblioteca de produto em local legado** |
| `scripts/dream/dream_cycle.py` | M | D002 | **job ainda não portado** |
| `scripts/health/canary_multiagent_runner.py` | **A (novo)** | D004 | **lógica de produto nova criada em `scripts/`** |

**A-02 (P0):** `canary_multiagent_runner.py` (225 linhas) foi **criado**
em `scripts/health/` na D004, não no pacote nativo. É orquestração de
produto (roda o pipeline de canário por provider). Destino: `hive_mind`.

**A-03 (P1):** `project_identity.py` recebeu lógica nova de produto
(normalização de remote na D003, guard `is_non_project_root` na D004)
enquanto continua fora do pacote. É a única fonte de identidade — deve
ser portada.

## 4. Código nativo delegando a script legado

```
grep -rE "register-mcp\.(ps1|sh)|install_services\.py|supervisor\.js|powershell|pwsh" src/hive_mind/
```

Ocorrências: **4, todas em docstrings** (`mcp_config.py`, `register.py`,
`registry.py`) documentando a origem do comportamento portado — uso
permitido como referência histórica.

`subprocess` no pacote nativo: **apenas** `daemon/managed.py`, spawnando
comandos declarados no manifesto — função legítima do supervisor.

**Resultado positivo:** nenhum comando nativo é um invólucro que chama
script legado. Travado por `test_architecture_boundaries.py`.

## 5. Lógica de produto ainda viva em scripts de shell

Nenhum destes foi alterado desde a D001 — são dívida herdada, mas
precisam de destino nativo declarado.

| Arquivo | Linhas | Responsabilidade | Wrapper puro | Destino nativo | Ação |
|---|---:|---|:---:|---|---|
| `install.sh` | 1319 | instalação completa, Docker, MCP | ❌ | `hive-mind install` | PORT TO NATIVE (P7/D011) |
| `install.ps1` | 568 | idem Windows | ❌ | `hive-mind install` | PORT TO NATIVE (P7/D011) |
| `scripts/setup/register-mcp.ps1` | 456 | detecção, paths, merge JSON/TOML, prompts | ❌ | `hive_mind.agents` | REMOVE AFTER PORT (D009) |
| `scripts/setup/register-mcp.sh` | 439 | idem + **instala capture hook** | ❌ | `hive_mind.agents` | REMOVE AFTER PORT (D009) |
| `scripts/lib/HiveMind.Windows.psm1` | 388 | utilidades Windows | ❌ | `hive_mind.platform` | PORT TO NATIVE (D011) |
| `scripts/setup/bootstrap-prerequisites.ps1` | 178 | pré-requisitos, Docker | ❌ | `hive-mind install` | PORT TO NATIVE (D011) |
| `scripts/setup/register-windows-jobs.ps1` | 17 | **lista de jobs + agendamento** | ❌ | `hive-mindd` scheduler | PORT TO NATIVE (D008-R1) |
| `scripts/setup/register-windows-runtime.ps1` | 14 | **lista de tarefas de runtime** | ❌ | `hive-mindd` | PORT TO NATIVE (D008-R1) |
| `scripts/maintenance/install-backup-cron.ps1` | 26 | agendamento de backup | ❌ | `hive-mindd` job | PORT TO NATIVE (D008-R1) |

Nenhum arquivo classificado UNKNOWN.

**A-04 (P1) — divergência POSIX/Windows:** `register-mcp.sh:357` **ainda
invoca `install-capture-hooks.py`**, religando o caminho outbox
deprecado no Linux. O `.ps1` teve isso removido em `b329e84`. Viola o
ADR-004 (dono único da entrega) fora do Windows.

**A-05 (P1) — schedulers concorrentes com horários divergentes:**

| Fonte | dream-cycle |
|---|---|
| `config/runtime.yaml` (D006) | cron `0 3 * * *` → **03:00** |
| `register-windows-jobs.ps1` | Daily **02:00** |

Duas listas de jobs independentes, com **agendamentos diferentes para o
mesmo job**. Não é só duplicação: é divergência de comportamento.

## 6. Duplicação de manifesto de serviços (D006)

| Fonte | Linhas | Serviços |
|---|---:|---:|
| `config/runtime.yaml` (D006, nova) | 331 | 7 |
| `scripts/setup/install_services.py::unit_definitions` | 1232 | 35 refs |
| `npm/lib/services.js` | 74 | 3 refs |
| `register-windows-jobs.ps1` | 17 | 4 jobs |

**A-06 (P1):** **quatro** listas independentes. A seção 9 da instrução é
explícita: "Se ainda existir duplicação, D006 é PARTIAL".

## 7. Estado real por entrega

| Delivery | Estado declarado | Estado real | Motivo |
|---|---|---|---|
| D001 | DONE | **DONE** | documentação viva existe, links válidos, gates presentes |
| D002 | PARTIAL | **PARTIAL** | correto; Dream Cycle segue em `scripts/` (job não portado) |
| D003 | PARTIAL | **PARTIAL** | correto; resolver segue fora do pacote (A-03) |
| D004 | DONE | **PARTIAL** ⬇ | criou lógica de produto em `scripts/` (A-02); sem trailer (A-01) |
| D005 | DONE | **PARTIAL** ⬇ | testes reais em `tests/real`, mas o pipeline provado depende de `scripts/` não portados |
| D006 | DONE | **PARTIAL** ⬇ | 4 listas de serviços concorrentes (A-06) |
| D007 | PARTIAL | **PARTIAL** | correto; implementação 100% em `src/hive_mind/daemon`, shadow passivo verificado |
| D008 | PARTIAL | **PARTIAL** | correto; mas scheduler paralelo no Task Scheduler segue ativo (A-05) — `LEGACY OWNER — NOT YET CUT OVER` |
| D009 | PARTIAL | **PARTIAL** | correto; falta TOML, doctor, unregister, instruções, captura, wrappers |

Três rebaixamentos: **D004, D005, D006**.

## 8. Testes arquiteturais adicionados

`tests/unit/test_architecture_boundaries.py` — 9 testes, todos passando:

- nenhum módulo nativo executa script legado (ignora docstrings, que
  podem citar a origem histórica);
- nenhum módulo nativo invoca powershell/pwsh/bash/cmd;
- só `daemon/managed.py` usa `subprocess`;
- `hive_mind.agents` existe e `hive_mind.integrations` **não** (ADR-013);
- ids de provider únicos; bases de config válidas;
- `register_providers` tem `dry_run=True` por padrão;
- `register-mcp.ps1` não religa o capture hook (ADR-004).

## 9. Plano de remediação

| ID | Origem | Arquivo | Defeito | Destino nativo | Prioridade |
|---|---|---|---|---|---|
| A-02 | D004 | `scripts/health/canary_multiagent_runner.py` | lógica de produto criada em `scripts/` | `hive_mind.health` | **P0** |
| A-04 | herdado | `register-mcp.sh:357` | religa outbox no POSIX | remover invocação | **P1** |
| A-05 | herdado | `register-windows-jobs.ps1` | scheduler paralelo, horário divergente | `hive-mindd` scheduler | **P1** |
| A-06 | D006 | `install_services.py`, `services.js` | 4 listas de serviços | `config/runtime.yaml` único | **P1** |
| A-03 | D003/D004 | `scripts/capture/project_identity.py` | biblioteca de produto fora do pacote | `hive_mind.projects` | **P1** |
| A-01 | D004–D006 | histórico | sem trailer `Delivery:` | — | **P4** |

Entregas de remediação propostas:

```
D009-R1  auditoria (este documento)              ← esta entrega
D009-R2  testes arquiteturais                    ← esta entrega
D009-R3  paridade POSIX: remover capture hook do register-mcp.sh (A-04)
D008-R1  scheduler único: portar jobs do Task Scheduler (A-05)
D006-R1  manifesto único: eliminar unit_definitions/services.js (A-06)
D004-R1  portar canary runner para o pacote nativo (A-02)
D003-R1  portar ProjectIdentityResolver para hive_mind.projects (A-03)
D009-R4  writer TOML nativo (Codex)
D009-R5  doctor, unregister, instruções, captura
D009-R6  reduzir register-mcp.{ps1,sh} a wrappers mínimos
```

## 10. Decisão

```
NATIVE CONTROL PLANE COMPLIANCE: PARTIAL
D009: PARTIAL
D010: BLOCKED
```

**Compliance PARTIAL, não FAILED**, porque o que foi construído desde a
D001 está no lugar certo (`src/hive_mind/**`, sem delegar a script) e
nenhum script de shell recebeu lógica nova. O PARTIAL vem de dívida
herdada ainda não portada (A-04, A-05, A-06) e de dois desvios reais
introduzidos durante o período auditado (A-02, A-03).

**D010 bloqueada** até D009 fechar e o scheduler paralelo (A-05) ser
resolvido — fazer cutover com dois schedulers ativos em horários
diferentes produziria execução dupla do Dream Cycle.
