# Memória Viva — Design do Serviço Inteligente do Hive-Mind

> **Versão**: 2.0 (modelo anatômico)
> **Data**: 2026-06-17
> **Escopo**: Definição completa do comportamento inteligente do serviço de memória do Sinapse — **estrutura do vault modelada na ANATOMIA CEREBRAL** (córtex com 5 lobos + diencéfalo + cerebelo + tronco), eixo primário por **projeto**, camada de **MOCs (consciência)** e **sinapses** automáticas, cadência (diária/sessão/semanal), formação autônoma de neurônios/pastas/MOCs, nomenclatura human-readable, multi-setor, métricas de "vivo", e plano de migração.
> **Audiência**: Michel (autor do vault), futuros agentes IA, contribuidores do projeto.
> **Status**: Documento vivo. Decisões aqui são propostas até validadas na prática (Fase 0).

---

## Sumário

1. [Diagnóstico: estado atual e lacunas](#1-diagnóstico-estado-atual-e-lacunas)
2. [Hierarquia canônica de pastas](#2-hierarquia-canônica-de-pastas)
3. [Constantes centralizadas (`core/paths.py`)](#3-constantes-centralizadas-corepathspy)
4. [Nomenclatura — uma regra, cinco exceções](#4-nomenclatura--uma-regra-cinco-exceções)
5. [Estrutura interna por tipo de nota](#5-estrutura-interna-por-tipo-de-nota)
6. [Cadências — como o serviço vive](#6-cadências--como-o-serviço-vive)
   - 6.1 [Memória de sessão](#61-memória-de-sessão)
   - 6.2 [Memória diária](#62-memória-diária)
   - 6.3 [Memória semanal](#63-memória-semanal)
7. [Serviço inteligente — formação autônoma de neurônios e pastas](#7-serviço-inteligente--formação-autônoma-de-neurônios-e-pastas)
8. [Multi-setor](#8-multi-setor)
9. [Métricas de "vivo"](#9-métricas-de-vivo)
10. [Migração do filesystem atual — Fase 0](#10-migração-do-filesystem-atual--fase-0)
11. [Roadmap Fase 1-3](#11-roadmap-fase-1-3)
12. [Apêndices — auditorias que fundamentam este design](#12-apêndices--auditorias-que-fundamentam-este-design)
13. [Próximas ações imediatas](#13-próximas-ações-imediatas)

---

## 1. Diagnóstico: estado atual e lacunas

### 1.1 Inventário do que EXISTE hoje

**Pipeline Dream Cycle** (`scripts/dream_cycle.py`, 595 linhas): ETL multi-agente — Document Ingest → Visual Dreamer → Distiller (LLM) → Validator (LLM) → Router (LLM classifica `topic` lowercase) → Persistência em `cerebro/atlas/{topic}/fact-{content_hash16}.md` → Síntese Dialética.

**Pipeline Audit & Reindex** (`scripts/audit_memory.py`, 216 linhas): varre `cerebro/atlas/**/*.md`, INSERT/UPDATE em `neurons.source_file`, move `*.sync-conflict-*.md` para `cerebro/conflicts/`.

**Constantes parciais** em `plugins/hermes/sinapse-memory.py:57-62`: `VAULT_DIR`, `GRAPH_JSON`, `DECISIONS_DIR`, `MEMORY_FILE`, `PROJECTS_DIR`, `PATTERNS_FILE`.

**Bug crítico descoberto**: existem **duas convenções conflitantes de `source_file`** no SQLite `hive_mind.db`:
- `scripts/audit_memory.py:61` grava path **relativo a `SINAPSE_HOME`** → `cerebro/atlas/python_typing/fact-abc123.md`
- `core/memory/backends/filesystem.py:120` grava path **relativo a `vault_dir`** (= `cerebro`) → `atlas/python_typing/fact-abc123.md`

Resultado: `dream_cycle.py:255` (`if not atlas_path.exists()`) pula silenciosamente a síntese dialética quando o path é resolvido errado.

**Constante única existente** em `core/`: `SINAPSE_HOME` (`core/database.py:21`, `core/signing.py:28`). Nenhuma constante para sub-paths do vault — cada script recalcula `Path(SINAPSE_HOME) / "cerebro" / "..."` independentemente.

**systemd timers ativos** (`scripts/install_services.py:131-179`):
| Timer | Calendário | Função |
|---|---|---|
| `sinapse-capture-tailer.timer` | `OnBootSec=30s, OnUnitActiveSec=30s` | Captura near-realtime |
| `sinapse-maintenance.timer` | `OnCalendar=Sun 04:00` | Compacta DB claude-mem |

**Comandos slash manuais** (`cerebro/.claude/commands/`): 18 comandos — incluindo `om-wrap-up`, `om-weekly`, `om-daily` (não existe), `om-vault-audit`.

**Pastas atualmente em `cerebro/`**: `atlas/`, `atoms/`, `attachments/`, `bases/`, `brain/`, `conflicts/`, `graphify-out/`, `hive mind/`, `inbox/`, `org/`, `reference/`, `templates/`, `thinking/`, `work/`. **Não existem**: `daily/`, `sessions/`, `weekly/`, `decisoes/`, `projetos/`, `sectors/`, `indice/`.

**Pastas atuais em `cerebro/atlas/`**: `atlas/`, `documents/`, `error_handling/`, `infrastructure/`, `preferences/`, `security/`, `test_swarm/`, `test_topic/`, `testing/`, `visual/`. **Evidência de fragmentação**: `test_swarm`, `test_topic`, `testing` são próximos mas não foram mergeados.

### 1.2 Tabela de capacidades: implementado vs gap

| Capacidade | Status | Como | Gap |
|---|---|---|---|
| Extrair fatos de logs | ✅ | Distiller LLM | — |
| Validar groundedness | ✅ | Validator LLM | — |
| Rotear fatos para tópicos | ✅ | Router LLM | Fragmenta tópicos correlatos |
| Persistir fatos em atlas | ✅ | `fact-{hash16}.md` | Hash-based, não-human-readable |
| Reindexar SQLite | ✅ | `audit_memory.py` | Path inconsistency bug |
| Detectar sync-conflicts | ✅ | move para `conflicts/` | — |
| HNSW vector search | ✅ | `core/hnsw_index.py` | Wiring parcial |
| Captura near-realtime | ✅ | capture-tailer.timer | — |
| **Criar pastas por tema** | ✅ (implícito) | `mkdir parents=True` | Pasta nova sempre — fragmenta |
| **Renomear arquivos humanamente** | ❌ | — | Sempre `fact-{hash}.md` opaco |
| **Aliases human-readable** | ❌ | — | Sem campo `aliases` automático |
| **Estruturar conteúdo por tipo** | ❌ | — | Templates existem mas não são aplicados |
| **Memória diária automática** | ❌ | — | Sem cron que cria `daily/` |
| **Memória de sessão automática** | ❌ | — | `om-wrap-up` é manual |
| **Resumo semanal automático** | ❌ | — | `om-weekly` é manual e transient |
| **Consolidação de tópicos fragmentados** | ❌ | — | Sem merge automático |
| **Multi-sector tagging** | ❌ | — | Tag `sector` não existe |
| **Decaimento/cold-storage** | ❌ | — | Sem cron de purga |
| **Métricas de "vivo"** | ❌ | — | Sem dashboard/alerta |
| **Decision staleness check** | ❌ | — | Decisões nunca expiram |
| **Drift detector** | ❌ | — | Atoms sem uso >90d não marcados |

**Síntese**: dos 22 capacidades necessárias para um serviço "vivo", **7 estão implementadas** (todas no Dream Cycle), **1 está parcialmente quebrada** (reindex com paths inconsistentes), e **14 estão completamente ausentes**.

---

## 2. Hierarquia canônica de pastas — MODELO ANATÔMICO CEREBRAL

### 2.0 Princípio: cada região faz o que o cérebro real faz

O vault deixa de ser um "atlas" genérico e passa a **espelhar a anatomia do cérebro**. Cada
estrutura mapeia uma função real do órgão para uma função do sistema — a função biológica
bate com a função da pasta. Isso dá um modelo mental único, escalável e visualmente coerente
(o graph view do Obsidian vira um cérebro de fato).

| Estrutura cerebral | Função biológica | Função no sistema |
|---|---|---|
| **Córtex Temporal** | audição, **memória**, linguagem | 🧠 núcleo da MEMÓRIA — os neurônios (fatos), por projeto |
| **Córtex Frontal** | raciocínio, **decisão**, planejamento, ação | decisões, projetos, trabalho/entregas |
| **Córtex Parietal** | **sensorial** (tato, dor), integração de sentidos | captura bruta (inbox), referências externas |
| **Córtex Occipital** | **visão**, cor, forma | capturas de tela, o grafo (a "imagem" do cérebro) |
| **Córtex Ínsula** | **interocepção**, sentir o próprio estado | saúde/métricas (autoconsciência), conflitos internos |
| **Diencéfalo (tálamo)** | **relay** sensorial, roteamento | o Router LLM, setores (cruzam regiões) |
| **Cerebelo** | **ritmo**, timing, automação procedural | cadências (diário/sessão/semanal), padrões |
| **Tronco cerebral** | funções **vitais** autonômicas | infra do sistema (serviços, config, templates) |
| **Hipocampo** | **consolidação** curto→longo prazo | o Dream Cycle (destila observação → neurônio) |
| **Sinapses** | conexões entre neurônios | WikiLinks + `related:` + arestas do grafo |
| **Consciência** (workspace global) | integração / o "eu" | o MOC raiz (Home) |

### 2.1 Árvore completa (aplicada pós-Fase 0)

```
cerebro/
├── _Consciencia.md                     # 🧠 HOME — o "eu", workspace global (MOC raiz)
│                                        #    links p/ todos os lobos, projetos e setores
│
├── cortex/                             # CÓRTEX — cognição superior (os 5 lobos)
│   ├── _Cortex.md
│   │
│   ├── temporal/                       # 🧠 LOBO TEMPORAL — MEMÓRIA (o núcleo)
│   │   ├── _Temporal.md                #    MOC do lobo: lista projetos
│   │   ├── Hive-Mind/                  #    ⟵ EIXO PRIMÁRIO = PROJETO
│   │   │   ├── _Hive-Mind.md           #    MOC do projeto (um "giro" cortical)
│   │   │   ├── infraestrutura/
│   │   │   │   ├── _infraestrutura.md  #    MOC do tópico
│   │   │   │   └── neuronio-7a3b….md   #    ⟵ o "fact" agora é NEURÔNIO (hash + alias)
│   │   │   └── seguranca/ …
│   │   ├── Thoth/  OpenAlice/  …        #    um lobo-projeto por projeto
│   │   ├── _global/                    #    conhecimento sem projeto (preferências)
│   │   ├── hipocampo/                  #    CONSOLIDAÇÃO (Dream Cycle staging + quarentena)
│   │   └── arquivo/                    #    memória fria >90d (substância profunda)
│   │
│   ├── frontal/                        # LOBO FRONTAL — decisão, planejamento, execução
│   │   ├── _Frontal.md
│   │   ├── decisoes/                   #    decisões (ADRs, status + reversibilidade)
│   │   ├── projetos/                   #    1 nota = 1 projeto ativo
│   │   └── trabalho/{ativo,arquivo}/   #    entregas, planos, relatórios
│   │
│   ├── parietal/                       # LOBO PARIETAL — sensorial (entrada bruta)
│   │   ├── _Parietal.md
│   │   ├── inbox/{visual,documents}/   #    observações cruas (os "sentidos")
│   │   └── referencias/                #    material externo ingerido
│   │
│   ├── occipital/                      # LOBO OCCIPITAL — visão
│   │   ├── _Occipital.md
│   │   ├── capturas-visuais/           #    screenshots (PNG)
│   │   └── grafo/                      #    graphify-out (a "imagem" do cérebro)
│   │
│   └── insula/                         # LOBO DA ÍNSULA — interocepção (autoconsciência)
│       ├── _Insula.md
│       ├── saude/                      #    dashboard + métricas de "vivo" (M1-M8)
│       └── conflitos/                  #    tensões internas (sync-conflicts)
│
├── diencefalo/                        # DIENCÉFALO (tálamo) — RELAY / roteamento
│   ├── _Diencefalo.md
│   ├── setores/                        #    MOCs de setor que CRUZAM projetos
│   │   └── _ai-infra.md  _pkm.md  _direito.md  _financas.md …
│   └── roteamento/                     #    logs/decisões do Router LLM
│
├── cerebelo/                          # CEREBELO — ritmo, coordenação, automação
│   ├── _Cerebelo.md
│   ├── diario/AAAA/MM/                 #    daily logs (cadência diária)
│   ├── sessoes/AAAA/MM/                #    session logs (por sessão)
│   ├── semanal/                        #    weekly synthesis
│   └── padroes/                        #    memória procedural (Patterns.md)
│
└── tronco/                            # TRONCO CEREBRAL — funções vitais (infra)
    ├── _Tronco.md
    ├── meta/{comandos,agentes,hooks}/  #    config do sistema (era .claude, hive mind/)
    ├── modelos/                        #    templates Obsidian
    └── paineis/                        #    bases (.base views)
```

**Princípios**:
- **Eixo primário = projeto** dentro do lobo temporal; **tópico** é o segundo nível; **setor**
  é navegação cruzada (MOCs no diencéfalo), nunca pasta duplicada.
- **Storage ≠ navegação**: um neurônio mora num lugar; é alcançável de muitos MOCs.
- Nomes de pasta **ASCII sem acento** (segurança com scripts); acentos só nos títulos/MOCs.
- Hierarquia temporal real só onde faz sentido (`diario/AAAA/MM/`, `sessoes/AAAA/MM/`).

### Mapeamento da estrutura atual → anatômica

| Atual | Destino anatômico | Ação | Fase |
|---|---|---|---|
| `cerebro/atlas/{topic}/fact-*.md` | `cerebro/cortex/temporal/{projeto}/{topic}/neuronio-*.md` | `git mv` + reorg por projeto + rename `fact→neuronio` | 0 |
| `cerebro/atoms/` | `cerebro/cortex/temporal/` | merge no store único de neurônios | 0 |
| `cerebro/brain/Patterns.md` | `cerebro/cerebelo/padroes/` | `git mv` (memória procedural) | 0 |
| `cerebro/brain/Key Decisions.md` etc. | `cerebro/cortex/frontal/decisoes/` | merge semântico | 0 |
| `cerebro/brain/North Star.md` | `cerebro/_Consciencia.md` (ou link) | absorver no MOC raiz | 0 |
| `cerebro/conflicts/` | `cerebro/cortex/insula/conflitos/` | `git mv` | 0 |
| `cerebro/work/` | `cerebro/cortex/frontal/trabalho/{ativo,arquivo}/` | `git mv` + redirect notes | 1 |
| `cerebro/decisoes/` `projetos/` | `cerebro/cortex/frontal/{decisoes,projetos}/` | `git mv` | 1 |
| `cerebro/reference/` | `cerebro/cortex/parietal/referencias/` | `git mv` | 1 |
| `cerebro/inbox/` | `cerebro/cortex/parietal/inbox/` | `git mv` | 0 |
| `cerebro/atlas/visual/` + capturas | `cerebro/cortex/occipital/capturas-visuais/` | `git mv` | 0 |
| `cerebro/graphify-out/` | `cerebro/cortex/occipital/grafo/` | `git mv` | 0 |
| `cerebro/org/people/` `teams/` | `cerebro/cortex/frontal/decisoes/` (frontmatter) | absorver em tag | 1 |
| `cerebro/hive mind/` + `.claude/` | `cerebro/tronco/meta/` | absorver config | 0 |
| `cerebro/templates/` | `cerebro/tronco/modelos/` | `git mv` | 0 |
| `cerebro/bases/` | `cerebro/tronco/paineis/` | `git mv` | 0 |
| `cerebro/attachments/` | `cerebro/attachments/` | manter | 0 |
| (novo) | `cerebro/cortex/temporal/{_global,hipocampo,arquivo}/` | criar | 0 |
| (novo) | `cerebro/diencefalo/{setores,roteamento}/` | criar | 1-2 |
| (novo) | `cerebro/cerebelo/{diario,sessoes,semanal,padroes}/` | criar | 1 |
| (novo) | `cerebro/cortex/insula/saude/` (dashboard) | criar | 3 |
| (novo) | MOCs `_<região>.md` + `_<projeto>.md` + `_<topico>.md` | gerados pelo Dream Cycle | 2 |

---

## 3. Constantes centralizadas (`core/paths.py`)

**Arquivo novo** (`core/paths.py`, ~60 linhas). Substitui TODOS os `Path(SINAPSE_HOME) / "cerebro" / "..."` hardcoded em 6+ scripts Python.

```python
# core/paths.py
from pathlib import Path
import os
from datetime import date, datetime

# Raiz do projeto (já existe em core/database.py:21)
SINAPSE_HOME = Path(os.environ.get(
    "SINAPSE_HOME",
    Path(__file__).resolve().parents[1]
))

# Raiz do vault Obsidian (NOVO ponto único)
VAULT_ROOT = SINAPSE_HOME / "cerebro"

# ===== Consciência (MOC raiz / Home) =====
CONSCIENCIA = VAULT_ROOT / "_Consciencia.md"

# ===== CÓRTEX — cognição superior (5 lobos) =====
CORTEX = VAULT_ROOT / "cortex"
#  Lobo Temporal — MEMÓRIA (neurônios, eixo primário = projeto)
TEMPORAL = CORTEX / "temporal"
HIPOCAMPO = TEMPORAL / "hipocampo"          # consolidação (Dream Cycle staging)
ARQUIVO = TEMPORAL / "arquivo"              # memória fria >90d
TEMPORAL_GLOBAL = TEMPORAL / "_global"      # conhecimento sem projeto
#  Lobo Frontal — decisão/planejamento/execução
FRONTAL = CORTEX / "frontal"
DECISIONS_ROOT = FRONTAL / "decisoes"
PROJECTS_ROOT = FRONTAL / "projetos"
WORK_ROOT = FRONTAL / "trabalho"
WORK_ACTIVE = WORK_ROOT / "ativo"
#  Lobo Parietal — sensorial (entrada bruta)
PARIETAL = CORTEX / "parietal"
INBOX_ROOT = PARIETAL / "inbox"
INBOX_VISUAL = INBOX_ROOT / "visual"
INBOX_DOCUMENTS = INBOX_ROOT / "documents"
REFERENCES_ROOT = PARIETAL / "referencias"
#  Lobo Occipital — visão
OCCIPITAL = CORTEX / "occipital"
CAPTURAS_VISUAIS = OCCIPITAL / "capturas-visuais"
GRAFO_ROOT = OCCIPITAL / "grafo"
GRAPH_JSON = GRAFO_ROOT / "graph.json"
#  Lobo Ínsula — interocepção (autoconsciência)
INSULA = CORTEX / "insula"
SAUDE_ROOT = INSULA / "saude"               # dashboard + métricas (era /indice/dashboard)
CONFLICTS_ROOT = INSULA / "conflitos"

# ===== DIENCÉFALO (tálamo) — relay / roteamento =====
DIENCEFALO = VAULT_ROOT / "diencefalo"
SECTORS_ROOT = DIENCEFALO / "setores"
ROTEAMENTO_ROOT = DIENCEFALO / "roteamento"

# ===== CEREBELO — ritmo / cadências =====
CEREBELO = VAULT_ROOT / "cerebelo"
DAILY_ROOT = CEREBELO / "diario"
SESSIONS_ROOT = CEREBELO / "sessoes"
WEEKLY_ROOT = CEREBELO / "semanal"
PADROES_ROOT = CEREBELO / "padroes"         # memória procedural (Patterns.md)

# ===== TRONCO CEREBRAL — funções vitais (infra) =====
TRONCO = VAULT_ROOT / "tronco"
META_ROOT = TRONCO / "meta"
MODELOS_ROOT = TRONCO / "modelos"           # templates Obsidian
PAINEIS_ROOT = TRONCO / "paineis"           # bases (.base)

ATTACHMENTS_ROOT = VAULT_ROOT / "attachments"


# ===== Helpers de path =====
def neuron_path(project: str, topic: str, hash16: str) -> Path:
    """cortex/temporal/{projeto}/{topico}/neuronio-{hash16}.md (eixo por projeto)"""
    return TEMPORAL / project / topic / f"neuronio-{hash16}.md"

def project_moc(project: str) -> Path:
    """cortex/temporal/{projeto}/_{projeto}.md (MOC do projeto, auto-gerado)"""
    return TEMPORAL / project / f"_{project}.md"

def topic_moc(project: str, topic: str) -> Path:
    """cortex/temporal/{projeto}/{topico}/_{topico}.md (MOC do tópico)"""
    return TEMPORAL / project / topic / f"_{topic}.md"

def sector_moc(sector: str) -> Path:
    """diencefalo/setores/_{setor}.md (MOC de setor, cruza projetos)"""
    return SECTORS_ROOT / f"_{sector}.md"

def daily_path(d: date) -> Path:
    """cerebelo/diario/YYYY/MM/YYYY-MM-DD.md"""
    return DAILY_ROOT / d.strftime("%Y") / d.strftime("%m") / f"{d.isoformat()}.md"

def session_path(dt: datetime, slug: str) -> Path:
    """cerebelo/sessoes/YYYY/MM/YYYY-MM-DD-HHMM-{slug}.md"""
    return (SESSIONS_ROOT / dt.strftime("%Y") / dt.strftime("%m")
            / f"{dt.strftime('%Y-%m-%d-%H%M')}-{slug}.md")

def weekly_path(year: int, week: int) -> Path:
    """cerebelo/semanal/YYYY-W{XX}.md"""
    return WEEKLY_ROOT / f"{year}-W{week:02d}.md"
```

**Adoção**: trocar todas as referências hardcoded por `from core.paths import ATLAS_ROOT, INBOX_VISUAL, ...` em 6 scripts + 1 plugin. Validar com `grep -rn "cerebro/atlas\|cerebro/brain\|cerebro/conflicts\|cerebro/work/active" scripts/ plugins/ core/` → retorna 0.

---

## 4. Nomenclatura — uma regra, cinco exceções

### A regra

Para notas de **trabalho datadas** (decisões, projetos, sessões, daily, weekly):

```
YYYY-MM-DD-{tipo}-{slug}.md
```

Onde `tipo ∈ {a, d, p, r, t, c, s, w}`:
- `a` = atom (conhecimento destilado individual)
- `d` = decision (decisão registrada)
- `p` = project (projeto ativo)
- `r` = reference (material externo capturado)
- `t` = think (rascunho / pensamento em progresso)
- `c` = conflict (tensão aberta entre notas)
- `s` = session (log de sessão)
- `w` = weekly (síntese semanal)

**Slug**: kebab-case lowercase, sem abreviações crípticas, sem nomes de código. Exemplo: `2026-06-17-d-priorizar-atlas-renaming-fase-0.md`.

### As cinco exceções formais (E1-E5)

| # | Exceção | Razão | Tratamento |
|---|---|---|---|
| **E1** | `brain/*.md` (8 arquivos, 33 KB+) | Living documents sem evento datado (`North Star.md`, `Patterns.md`, `Skills.md`, `Current State.md`, `Gotchas.md`, `Key Decisions.md`, `Consolidated.md`, `Agent Loop Protocol.md`) | Manter sem data, kebab-case sem prefixo. Aliases no frontmatter para nomes legados. |
| **E2** | `cortex/temporal/{projeto}/{topico}/neuronio-{content_hash16}.md` | IDs content-derived do Dream Cycle (hipocampo). Renomeação quebra dedup cross-machine (Syncthing) e `neurons.source_file` no SQLite | **Nunca renomear**. Adicionar `aliases: [slug-human-readable]` no frontmatter. |
| **E3** | MOCs `_<Nome>.md` (`_Consciencia.md`, `_<projeto>.md`, `_<topico>.md`, `setores/_<setor>.md`), `modelos/*.md`, `paineis/*.base` | Prefixo `_` ordena o índice no topo da pasta (Johnny Decimal). Gerados/atualizados pelo serviço | **Nunca datar**. Title no body em PT-BR com acento; nome de arquivo ASCII. |
| **E4** | `cortex/parietal/inbox/visual/CAP-*.png` + `cortex/occipital/capturas-visuais/cap-*.md` | Pipeline visual já usa timestamp `cap-YYYYMMDD-HHMMSS-`; binário não kebab-case | Manter formato. |
| **E5** | `conflitos/*.sync-conflict-*` (gerado pelo Syncthing) | Formato do sistema de sync; sufixo `.sync-conflict-{ts}-{node}` é gerado, não editado | Não tocar. |

### Estratégia de migração

Para os ~30 arquivos em `cerebro/work/active/` que estão fora do padrão:

**Fase 1 — não destrutiva**:
1. Criar `cerebro/trabalho/{decisoes,projetos}/` vazias
2. Adicionar tag `#decision`, `#project` no frontmatter (via script `scripts/add_type_tags.py`)
3. Validar que `bases/Work Dashboard.base` agrupa por `status` + `type`

**Fase 2 — destrutiva com redirect**:
1. Para cada arquivo, gerar **redirect note** stub em `cerebro/trabalho/decisoes/`:
   ```yaml
   ---
   type: redirect
   redirects_to: "[[trabalho/decisoes/2026-06-17-d-mcp-decision]]"
   ---
   # 2026-06-17 MCP-Decision → trabalho/decisoes/2026-06-17-d-mcp-decision
   Esta nota foi movida. Atualize seus links.
   ```
2. `git mv` mantendo histórico
3. Atualizar wikilinks nos 30+ arquivos que referenciam paths antigos
4. `git commit -m "refactor(vault): migrate work/active to YYYY-MM-DD-{type}-{slug}"`

**Rollback**: `git revert <commit>` (reversível, git preserva).

### Wikilinks — paths completos vs nome-only

**Inconsistência atual**: vault mistura `[[work/active/2026-05-22-migrar-obsidian-mind]]` (path completo) e `[[North Star]]` (nome-only) e `[[Goals]]` (aliases YAML).

**Regra nova**: preferir **nome-only ou alias YAML** (Wikilink resolve em qualquer pasta). Path completo só para casos excepcionais onde duas notas têm o mesmo nome.

**Custo de migração**: 5+ wikilinks com path completo detectados em `work/active/2026-05-22-sintese-vault-estrutura.md` — corrigir manualmente ou via script `scripts/rewrite_wikilinks.py`.

---

## 5. Estrutura interna por tipo de nota

Cada tipo tem frontmatter obrigatório + seções obrigatórias. Templates vivem em `cerebro/templates/` (já existe). Validação por hook `PostToolUse` via `cerebro/.claude/scripts/validate-write.ts` (já existe).

### 5.1 `type: fact` (atom)

```yaml
---
type: fact
topic: python-typing                 # tópico roteado pelo Router LLM
integrity_hash: 7a3b2c1d4e5f6789     # SHA-256[:16] do conteúdo (mantido para dedup)
last_updated: 2026-06-17T14:22:00-03:00
source: dream-cycle | human | agent   # proveniência
sectors: [dev-tools, pkm]            # multi-tag (Seção 8)
confidence: 0.87                     # 0.0-1.0 (do Validator LLM)
aliases:                             # slug human-readable gerado por LLM
  - pyrfc-retry-strategy
  - error-handling-pyrfc-pattern
created_at: 2026-06-17T14:22:00-03:00
last_synthesized: 2026-06-17T14:22:00-03:00
groundedness_score: 0.92
evidence_quote: >                    # verbatim quote da fonte
  "RFC suggests exponential backoff with jitter for transient errors"
source_file: inbox/2026/06/2026-06-17-pyrfc-error-logs.md
quarter: Q2-2026
tags: [rfc, retry, transient-errors]
---

# pyrfc-retry-strategy

> Slug: `pyrfc-retry-strategy` · Hash: `7a3b2c1d4e5f6789`

## Conteúdo
[corpo do fato destilado, 3-10 parágrafos]

## Evidência (Groundedness)
> Source quote (verbatim): "..."
> Match score: 0.92 (Validator LLM)

## Conexões
- related_atoms: [[2026-05-30-a-circuit-breaker-pattern-rfc]]
- decisions: [[2026-06-12-d-use-pyrfc-retry-library-vs-roll-our-own]]
- projects: [[2026-Q2-p-sap-integration-refactor]]

## Proveniência
- source_file: `inbox/2026/06/2026-06-17-pyrfc-error-logs.md`
- created_by: dream-cycle (Distiller v1, Validator v1)
- synthesis_count: 1

## Métricas
- access_count_30d: 4
- hnsw_neighbors_count: 12

#consolidated #python-typing #rfc
```

### 5.2 `type: decision`

```yaml
---
type: decision
status: accepted                      # proposed | accepted | deprecated | superseded
owner: human | agent                  # quem decidiu
date: 2026-06-17
quarter: Q2-2026
iso_week: 2026-W25
sectors: [dev-tools, ai-infra]
reversibility: medium                 # easy | medium | hard | irreversible
confidence: 0.85
aliases: [priorizar-atlas-rename-fase-0]
supersedes: null
superseded_by: null
related_projects:
  - "[[2026-Q2-p-hive-mind-v2-architecture]]"
next_review: 2026-09-17               # 90 dias; staleness detector verifica
tags: [architecture, memory-service, migration]
---

# Prioritize atlas renaming in Fase 0

## Context
[Fase 0 tem 4 deliverables. Análise de impacto mostrou que (b) bloqueia (c).]

## Decision
**Fazer (b) PRIMEIRO** — atlas rename antes de SQLite migration.

## Rationale
Path inconsistency (#3190) tem 2 backends afetados; corrigir antes de unificar filesystem só adiciona complexidade.

## Alternatives Considered
- (a) primeiro: rejected — paths centralizados precisam referenciar destino final
- (c) primeiro: rejected — bandaid; addresses symptom, not cause
- (d) primeiro: rejected — atualizar scripts com paths errados é desperdício

## Consequences
- ✅ Reduz risk de partial migration
- ✅ Atlas rename isolado em branch
- ⚠️ Aumenta W25 timeline em ~3 dias
- ⚠️ Requer coordination com audit_memory.py pós-migration

## Related
- decisions: [[2026-06-15-d-stop-using-ruflo-for-local-mem-store]]
- atoms: [[2026-06-15-a-synapse-fs-categories-must-include-atlas]]
- projects: [[2026-Q2-p-hive-mind-v2-architecture]]

## Reversibility
**Medium**: `git revert` + SQLite reverse funciona. Links criados durante janela de migration podem ficar órfãos (mitigado por redirect notes).

#decision #accepted #Q2-2026
```

### 5.3 `type: project`

```yaml
---
type: project
status: active                          # proposed | active | completed | archived | abandoned
date: 2026-04-01                        # start
quarter: Q2-2026
sectors: [ai-infra, dev-tools, pkm]
owner: michel
target_date: 2026-08-31
next_action: >                           # one-line, actionable
  Implementar scripts/daily_writer.py e deploy via sinapse-daily.timer
aliases: [hive-mind-v2-architecture]
tags: [memory-service, architecture, pkm]
---

# Hive-Mind v2 Architecture

## Goal
Memória do Hive-Mind vira serviço vivo: cadência diária/sessão/semanal; formação autônoma de pastas; nomenclatura human-readable.

## Phases
- [x] Fase 0 — filesystem consolidation (W25-W27)
- [ ] Fase 1 — cadência básica (W28-W30)
- [ ] Fase 2 — memória inteligente (W31-W34)
- [ ] Fase 3 — síntese viva (W35-W38)

## Current Status
**Fase 0 em progresso** (60%).

## Blockers
- LLM budget para Sonnet no Dream Cycle (sem aprovação)
- Path inconsistency (#3190) bloqueia Fase 1

## Related
- decisions: [[2026-06-17-d-priorizar-atlas-renaming-fase-0]]
- weekly: [[2026-W25]]

#project #active #Q2-2026
```

### 5.4 `type: session-log` (NOVO)

```yaml
---
type: session-log
session_id: claude-code-9f3a2b1c       # id do runtime + plataforma
date: 2026-06-17
start: 14:22
end: 16:44
duration_min: 142
agent: claude-code | codex | hermes | kiro
project: "[[2026-Q2-p-hive-mind-v2-architecture]]"
sectors: [ai-infra, dev-tools]
topics: [hive-mind, memory-service, dream-cycle]
decisions:
  - "[[2026-06-17-d-priorizar-atlas-renaming-fase-0]]"
atoms_created:
  - "[[2026-06-17-a-hive-mind-facts-vs-decisions-taxonomy]]"
tools_used: [Read, Edit, Bash, mcp__ruflo__memory_search]
status: in-progress | completed         # placeholder até Stop hook
quarter: Q2-2026
---

# Session 2026-06-17 14:22-16:44 — atlas-renaming-phase0-planning

> Slug: `atlas-renaming-phase0-planning` (gerado por LLM no Stop hook)

## Resumo
[2-3 frases geradas via LLM a partir das observações da sessão]

## Decisões
- [[2026-06-17-d-priorizar-atlas-renaming-fase-0]] — começar por atlas, defer topic consolidator

## Átomos Criados
- [[2026-06-17-a-hive-mind-facts-vs-decisions-taxonomy]] — 6 distinct facts

## Comandos/Tools Usados
| Tool | Calls |
|---|---|
| Read | 47 |
| Bash | 31 |
| Edit | 22 |
| mcp__claude-flow__memory_search | 18 |

## Próximos Passos
- [ ] Criar `scripts/daily_writer.py`
- [ ] Validar migration atlas/ → indice/atlas/

#session #log #Q2-2026
```

### 5.5 `type: daily-log` (NOVO)

```yaml
---
type: daily-log
date: 2026-06-17
day_of_week: quarta-feira
quarter: Q2-2026
iso_week: 2026-W25
energy: medium                          # low | medium | high
mood: focused                          # free-text
weather: ensolarado-22C                 # opcional
sectors: [ai-infra, dev-tools]
tags: [daily, hive-mind, fase-0]
agent_primary: claude-code
sessions_count: 3
atoms_created: 7
decisions_count: 2
inbox_processed: 12
---

# 2026-06-17 — Quarta-feira

## Capturas
- 14:22 [[inbox/2026/06/2026-06-17-syncthing-conflict-migration]] — 12 conflitos hoje
- 16:05 [[inbox/2026/06/2026-06-17-slack-feedback-alice]] — feedback positivo

## Átomos Destilados
- [[2026-06-17-a-syncthing-merkle-tree-strategy]]
- [[2026-06-17-a-hive-mind-facts-vs-decisions-taxonomy]]

## Decisões Tomadas
- [[2026-06-17-d-priorizar-atlas-renaming-fase-0]]
- [[2026-06-17-d-defer-topic-consolidator-to-fase-2]]

## Projetos Trabalhados
- [[2026-Q2-p-hive-mind-v2-architecture]] — sprint 4 fechado

## Reflexões Abertas
- O serviço está formando "tópicos-fantasma" (3-4 fatos viram pastas separadas). Vou propor consolidação na weekly.

## Métricas do Dia
- atoms_created: 7
- decisions: 2
- sessions: 3 (manhã 47min, tarde 1h22, noite 18min)
- inbox_processed: 12 items → 7 atoms
- orphan_prevention: 0 (todos os notes linkados)

#daily #log #Q2-2026
```

### 5.6 `type: weekly-summary` (NOVO)

```yaml
---
type: weekly-summary
week: 2026-W25
quarter: Q2-2026
start_date: 2026-06-15
end_date: 2026-06-21
sectors: [ai-infra, dev-tools]
days_covered: 7
days_with_logs: 5                     # 2 dias sem log
atoms_total: 34
decisions_total: 8
sessions_total: 19
projects_active: 6
status: draft | finalized
generated_by: scripts/weekly_synthesizer.py
llm_synthesis_prompt: weekly_synthesis_v1
---

# Semana 2026-W25 (15-21 jun)

## Visão Geral
Semana de **infraestrutura de memória**. 34 atoms, 8 decisions, 6 projects ativos. Drift: nenhum trabalho em `finance`/`health` sectors.

## Daily Logs Cobertos
- [[2026-06-15]] ✅
- [[2026-06-16]] ✅
- [[2026-06-17]] ✅ (esta data)
- [[2026-06-18]] ❌ (sem log)
- [[2026-06-19]] ✅
- [[2026-06-20]] ✅
- [[2026-06-21]] ❌ (sem log)

## Top 5 Átomos
1. [[2026-06-17-a-hive-mind-facts-vs-decisions-taxonomy]] — conf=0.92
2. [[2026-06-15-a-synapse-fs-categories-must-include-atlas]] — conf=0.95
3. [[2026-06-16-a-session-log-template-needs-duration-derivation]] — conf=0.88

## Decisões
### Fechadas (5)
- [[2026-06-15-d-stop-using-ruflo-for-local-mem-store]]
### Abertas (3)
- [[2026-06-15-d-use-haiku-vs-sonnet-for-distillation]] — sem resolução

## Projetos: Status
| Projeto | Status | Blockers |
|---|---|---|
| [[2026-Q2-p-hive-mind-v2-architecture]] | active | LLM budget |

## Padrões Emergentes
- **Topic fragmentation**: 3 tópicos (`test_swarm`, `test_topic`, `testing`) representam mesmo domínio. Candidato a merge.

## Próxima Semana (W26)
1. Fase 0 implementação — migration atlas/ → indice/atlas/
2. Daily writer script
3. Session consolidator
4. Decision review (3 abertas >30d)
5. Topic consolidator (primeiro merge run)

## Métricas de Saúde
- atoms/day: 4.86 (target: >3) ✅
- daily_compliance: 71% (target: >85%) ❌
- orphan_pct: 4.2% (target: <5%) ✅

#weekly #synthesis
```

### 5.7 Schema de validação automática

Hook `PostToolUse` chama `cerebro/.claude/scripts/validate-write.ts` (já existe) que verifica:
- Frontmatter completo por tipo (campos obrigatórios presentes)
- Seções obrigatórias presentes no body
- Wikilinks apontam para notas existentes (ou marcadas como `[[forward-ref]]`)
- Hash integrity (se `integrity_hash` presente, recalcular e comparar)
- `confidence` ∈ [0.0, 1.0]
- Date em ISO 8601
- `aliases` slug-safe (kebab-case, sem caracteres especiais)

---

## 6. Cadências — como o serviço vive

### Tabela mestra de cadências

| Cadência | Quem dispara | Quando | Script (NOVO) | Saída |
|---|---|---|---|---|
| **Por tool call** | Hook `PostToolUse` (MCP) | Cada `save_decision`/`save_pattern`/`save_observation` | (inline no MCP server) | atualiza placeholder session/daily |
| **Por sessão (start)** | Hook `SessionStart` | Cada sessão Claude/Codex | `scripts/session_placeholder.py` | `cerebro/sessions/.../{session}.md` placeholder |
| **Por sessão (end)** | Hook `Stop` | Fim da sessão | `scripts/session_consolidator.py` | `cerebro/sessions/.../{session}.md` completed + update daily |
| **Diária** | `sinapse-daily.timer` | 23:55 daily | `scripts/daily_writer.py` | `cerebro/daily/YYYY/MM/YYYY-MM-DD.md` finalizado |
| **Semanal (síntese)** | `sinapse-weekly.timer` | Sun 04:00 | `scripts/weekly_synthesizer.py` | `cerebro/weekly/YYYY-W{XX}.md` |
| **Semanal (manutenção DB)** | `sinapse-maintenance.timer` (existente) | Sun 04:00 | `scripts/capture_maintenance.py` | DB claude-mem compactado |
| **Semanal (audit)** | `sinapse-audit.timer` | Sun 05:00 | `scripts/audit_memory.py --full` | SQLite reindexado, conflicts movidos |
| **Semanal (topic merge)** | `sinapse-topics.timer` | Sun 06:00 | `scripts/topic_consolidator.py` | merge proposals (log-only por padrão) |
| **Diário (dream cycle)** | `sinapse-dream.timer` | 03:00 daily | `scripts/dream_cycle.py` | atoms + atlas persistidos |
| **Mensal (drift)** | `sinapse-drift.timer` | 1º dia 04:00 | `scripts/drift_detector.py` | atoms > 90d marcados cold, decisions > 180d flagged |

### Ordem de execução semanal (Sun)
```
03:00 dream_cycle.py          (processa observations acumuladas)
04:00 weekly_synthesizer.py   (gera resumo da semana passada)
05:00 audit_memory.py --full  (reindexa DB, reconcilia paths)
06:00 topic_consolidator.py   (merge proposals — log-only)
```

**Justificativa**: dream antes de synth (synth precisa de atoms atualizados); synth antes de audit (audit valida o que synth gerou); audit antes de topic-merge (topics merged precisam ser reindexados).

### 6.1 Memória de sessão

**Definição**: intervalo entre `SessionStart` hook fire e `Stop` hook fire.

**Quando criar**: híbrida.
- **SessionStart**: cria placeholder com `status: in-progress`
- **PostToolUse (MCP)**: atualiza placeholder com novos decisions/atoms (campo `decisions[]`, `atoms_created[]`)
- **Stop**: finaliza. Calcula `duration_min` real, gera `## Resumo` via LLM summarization das últimas N observações, marca `status: completed`

**Threshold de criação**: só cria session-log se `duration_min > 5` OU `tools_used.count > 3` (evita poluir com sessões de teste `claude -p "test"`).

**Quem cria hoje**: nada automático. `/om-wrap-up` é manual. **Proposta**: substituir por hook + scripts.

### 6.2 Memória diária

**Disparador**: híbrido.
- **Hook SessionStart**: cada nova sessão cria/atualiza placeholder se ainda não existe
- **Cron fallback**: `sinapse-daily.timer` às 23:55 fecha o dia se nenhuma sessão rolou

**Estrutura de path**: `cerebro/daily/YYYY/MM/YYYY-MM-DD.md` (hierárquica — filesystem-friendly, scaling infinito).

**Campos obrigatórios**: `date`, `type: daily-log`, `day_of_week`, `quarter`, `iso_week`, `energy`, `mood`, `tags`, `sectors`, `agent_primary`, contadores (`sessions_count`, `atoms_created`, `decisions_count`, `inbox_processed`).

**Seções obrigatórias**: `## Capturas`, `## Átomos Destilados`, `## Decisões Tomadas`, `## Projetos Trabalhados`, `## Reflexões Abertas`, `## Métricas do Dia`.

**Não-recomendado**: manual-only via comando (provoca esquecimento, histórico de `om-wrap-up` mostra ~40% das sessões sem wrap-up manual).

### 6.3 Memória semanal

**Quando**: Sun 04:00 via `sinapse-weekly.timer`. Timer já existe (`scripts/install_services.py:175`); falta criar nova unit `sinapse-weekly.service` que roda `scripts/weekly_synthesizer.py`.

**Estrutura**: `cerebro/weekly/YYYY-W{XX}.md` (sem hierarquia — 52 arquivos/ano é OK).

**Quem gera hoje**: nada. `/om-weekly` é manual e transient (explícito no comando: não cria arquivo por default).

**Proposto**: novo script `scripts/weekly_synthesizer.py`:
1. Lê `cerebro/daily/YYYY/MM/YYYY-MM-DD.md` para os 7 dias da semana
2. Lê atoms filtrados por `created_at` na semana
3. Lê decisions filtradas por `date` na semana
4. Lê sessions filtradas por `date` na semana
5. Chama LLM com prompt `weekly_synthesis_v1` (papel: sumarizador executivo)
6. Gera `cerebro/weekly/YYYY-W{XX}.md`
7. Idempotente: se já existe, atualiza mas preserva edições manuais no body

**Prompt `weekly_synthesis_v1`** (rascunho):
```
Você é um sintetizador executivo de memória pessoal. Dado o contexto da semana, gere um resumo executivo em PT-BR.

INPUT: 7 daily logs, lista de atoms (com confidence), decisions (aberta/fechada), projects ativos, sessions (duração + topics).

OUTPUT (Markdown, 4-6 seções, ~500 palavras):
1. Visão Geral (3-4 frases): tema dominante + ritmo + signal de drift
2. Daily Compliance: tabela 7 dias
3. Top 5 Átomos (confidence > 0.80)
4. Decisões: abertas vs fechadas
5. Projetos: tabela projeto | status | blockers | delta
6. Padrões Emergentes (2-3 cross-day)
7. Próxima Semana: 3-5 prioridades

REGRAS: seja ANALÍTICO, não cheerleader. Sinalize DRIFT (setores silenciosos). Use linguagem executiva. Honre silêncio (1 dia sem log = "1 dia sem log"). Não invente dados.
```

---

## 7. Serviço inteligente — formação autônoma de neurônios e pastas

### 7.1 Como o serviço decide CRIAR uma pasta nova de tema

**Pipeline anatômico** (`dream_cycle.py` = hipocampo):
1. Distiller extrai fato F com label `L` e conteúdo `C`
2. Validator confirma groundedness (`C quote ∈ source`)
3. Router recebe `(L, C, projeto)` → decide **`(projeto, topico)`** (o `projeto` vem da
   observation; o `topico` é classificado pelo LLM com sliding window)
4. Persistência: `neuronio-{hash16}.md` em `cortex/temporal/{projeto}/{topico}/`
   (`mkdir parents=True, exists_ok=True` cria projeto/tópico na hora)
5. **Atualiza MOCs**: append do link no `_<topico>.md`, `_<projeto>.md`, e registra projeto
   novo no `_Consciencia.md` (Seção 7.6)
6. **Cria sinapses**: para vizinhos com cosine ≥ 0.85, escreve `related: [[…]]` bidirecional

**Problema detectado**: fragmentação. Exemplo real no vault: `atlas/test_swarm/`, `atlas/test_topic/`, `atlas/testing/` representam o mesmo domínio mas não foram mergeados.

### 7.2 Mitigações em 3 camadas

**Camada (a) — Sliding window no prompt do Router**:
```python
def classify_topic(fact_label, fact_content):
    recent_topics = self.recent_topic_window(window=20)
    prompt = f"""Classify this fact into ONE existing topic from the window
if reasonably related. Only create new topic if NO existing topic fits (>=0.7 semantic).

Recent topics (last 20):
{chr(10).join(f'  - {t}' for t in recent_topics)}

Fact: {fact_label}
Content: {fact_content}

Return ONLY the topic name (lowercase, snake_case).
"""
    return self.llm.complete(prompt)
```

**Camada (b) — Pós-processamento com embedding similarity** (semanal):
```python
def merge_candidates(threshold=0.85):
    topic_embeddings = embed_all_topics()
    clusters = agglomerative_cluster(embeddings=topic_embeddings, threshold=threshold)
    for cluster in clusters:
        if len(cluster) > 1:
            yield MergeProposal(
                topics=cluster,
                centroid=cluster_centroid,
                confidence=cluster_coherence,
                action='merge' if cluster_coherence > 0.85 else 'flag'
            )
```

**Camada (c) — Hierarquia opcional `topic/subtopic`**: Router aceita respostas com `/` → cria `cerebro/cortex/temporal/{projeto}/coding/typing/` automaticamente.

### 7.3 Quando MERGE duas pastas

**Critérios** (todos satisfeitos):
1. Embedding centroid cosine ≥ 0.85 entre os topics
2. Entity overlap ≥ 3 (compartilham 3+ entidades nomeadas)
3. Time proximity: criados no mesmo intervalo (janela 90d)
4. Size threshold: cada pasta tem ≥ 3 fatos (evitar merge prematuro)

**Quem decide**: `scripts/topic_consolidator.py` rodando semanalmente. **Log-only por padrão; flag `--apply` para executar.**

**Comportamento do merge**:
1. `shutil.move` de todos `fact-*.md` para pasta de destino
2. `UPDATE neurons SET source_file = ?` no SQLite
3. Criar `redirect note` na pasta de origem
4. `rmdir` se vazio
5. Regenerar HNSW index
6. Log em `cerebro/weekly/{week}/merges-{date}.md` para auditoria reversível

### 7.4 Quando CRIAR vs REUSAR

| Condição | Decisão |
|---|---|
| Top-3 existing topics têm cosine ≥ 0.85 com o fato | REUSAR o de maior score |
| Top-3 existing topics têm cosine 0.6-0.85 | REUSAR + criar alias se útil |
| Top-3 existing topics têm cosine < 0.6 | CRIAR nova pasta |
| Fato menciona hierarquia explícita (`x/y`) | CRIAR `x/y/` (subpasta) |

### 7.5 Nomenclatura inteligente para neurônios

**Hoje**: `fact-{content_hash16}.md` (opaco). **Novo**: `neuronio-{content_hash16}.md`.

**Solução** — manter hash + adicionar alias:
- **Camada 1 — nome técnico estável** (mantém): `cortex/temporal/{projeto}/{topico}/neuronio-{hash16}.md`
- **Camada 2 — alias human-readable** (NOVO): frontmatter `aliases: [pyrfc-retry-strategy]`
- **Camada 3 — slug auto-gerado**: LLM `extract_slug(fact.label)` no Distiller

**Regra absoluta**: nunca renomear `neuronio-{hash}.md` (quebra dedup cross-machine e SQLite `source_file`).

### 7.6 Camada MOC + sinapses — o que faz o vault parecer um cérebro

Sem esta camada, o graph view do Obsidian é poeira de nós soltos (estado atual: 2 de 16
neurônios têm link). É a **navegação** (≠ armazenamento) — síntese de LYT/Maps of Content.

**MOCs auto-gerados/atualizados pelo hipocampo** (`dream_cycle.py`, novo estágio):

| MOC | Path | Conteúdo (gerado) |
|---|---|---|
| Consciência (Home) | `_Consciencia.md` | links p/ cada lobo + cada projeto + cada setor |
| Lobo | `cortex/<lobo>/_<Lobo>.md` | links p/ projetos/conteúdo do lobo |
| Projeto | `cortex/temporal/<proj>/_<proj>.md` | tópicos do projeto + neurônios recentes + decisões |
| Tópico | `cortex/temporal/<proj>/<top>/_<top>.md` | neurônios do tópico (quando ≥ 5) |
| Setor | `diencefalo/setores/_<setor>.md` | neurônios/projetos do setor (CRUZA projetos) |

**Sinapses (arestas) — 3 obrigatórias por neurônio**: todo `neuronio-*.md` linka (a) seu MOC
de tópico, (b) seu MOC de projeto, (c) ≥1 neurônio relacionado (cosine ≥ 0.85, reusando o
cálculo de similaridade que o dedup **já faz**). Isso costura os clusters no grafo.

**Estratégia visual (Graph Settings)**: Groups por `tag:#setor/<x>` → cor por setor; MOCs
viram nós-hub (muitos backlinks → nós grandes). É o que produz os clusters coloridos.

**Idempotência**: MOCs são regerados de forma determinística a partir do índice (SQLite
`neurons`/`synapses`) — editar manualmente o body é preservado entre marcadores
`<!-- auto:start -->` / `<!-- auto:end -->`.

---

## 8. Multi-setor

### 8.1 Definição de sector

**Sector** = domínio de aplicação horizontal. Diferente de `topic` (granular, sinapse-pkm-internal) e `tag` (keyword livre). Sector é conjunto fechado e versionado.

**Setores propostos inicialmente**:
| Sector ID | Nome descritivo |
|---|---|
| `ai-infra` | AI Infrastructure (Claude Code, Codex, Hermes, MCP) |
| `dev-tools` | Developer Tools (ruflo, claude-mem, neural-memory) |
| `pkm` | Personal Knowledge Mgmt (Obsidian, dream_cycle, brain) |
| `infra` | Generic Infrastructure (syncthing, sqlite-vec, systemd) |
| `finance` | Finance (a definir — gap atual) |
| `health` | Health (a definir — gap atual) |
| `research` | Research (papers, experiments) |

### 8.2 Onde vive

Frontmatter `sectors: [pkm, dev-tools]` (multi-tag OK).

### 8.3 Como o serviço decide o sector

**3 fontes, em ordem de prioridade**:

1. **LLM inference na criação** (default para `fact` via Dream Cycle):
```python
async def assign_sectors(fact) -> List[str]:
    known_sectors = ['ai-infra', 'dev-tools', 'pkm', 'infra', 'finance', 'health', 'research']
    prompt = f"""Assign 1-3 sectors from the list below to this fact.
    Return as comma-separated lowercase-with-hyphen values.
    Sectors: {known_sectors}
    Label: {fact.label}
    Content: {fact.content[:300]}
    Sectors:"""
    response = await self.llm.complete(prompt)
    return [s.strip() for s in response.split(',') if s.strip() in known_sectors]
```

2. **Manual override** (humano seta no frontmatter) — sempre vence, marca `sector_manual_override: true`
3. **Default fallback**: `sectors: [general]` se LLM incerto (confidence < 0.6 ou sectors inválidos)

**Para `decision` e `project`**: inferência LLM + revisão manual obrigatória em 7 dias (sinaliza `sector_review_pending: true`).

### 8.4 Cross-sector policy

- Nota com `sectors: [a, b]` aparece em **todas** as Bases views filtradas por `a` ou `b`
- Backlinks cruzam sectors sem warning (cross-pollination é OK)
- Bases view `cerebro/bases/Sector Dashboard.base` lista contagem por sector

---

## 9. Métricas de "vivo"

### 9.1 Definição

Serviço de memória está **vivo** quando cresce organicamente, mantém coerência, e responde a queries com confiança. Não está vivo quando é estático (só escreve, nunca relê) ou degenera (acumula lixo).

### 9.2 Métricas primárias

**M1 — atoms_created_per_day**:
- Query: `SELECT COUNT(*) FROM neurons WHERE created_at > date('now', '-1 day') AND type='fact'`
- Target: `> 3`
- Alert se: `0` por `> 7 dias`

**M2 — daily_logs_completed_last_7d**:
- Query: count files matching `cerebro/daily/YYYY/MM/YYYY-MM-DD.md` for last 7 days
- Target: `7`
- Alert se: `< 5`

**M3 — session_logs_last_30d**:
- Query: count files in `cerebro/sessions/YYYY/MM/` modified in last 30 days
- Target: `> 20`
- Alert se: `< 10`

**M4 — orphan_neurons_pct**:
- Query: `SELECT (COUNT(*) WHERE backlinks_count = 0) * 100.0 / COUNT(*) FROM neurons`
- Target: `< 5%`
- Alert se: `> 15%`

**M5 — topic_consolidation_actions_last_90d**:
- Query: `SELECT COUNT(*) FROM merge_log WHERE merged_at > date('now', '-90 days')`
- Target: `> 0` (crescimento orgânico)
- Alert se: `0` por `> 90 dias`

**M6 — aliases_added_last_30d**:
- Query: scan frontmatter `aliases` field, count new in last 30d
- Target: `> 0`
- Alert se: `0` por `> 30 dias`

**M7 — weekly_summaries_last_12w**:
- Query: count files matching `cerebro/weekly/YYYY-W*.md` for last 12 weeks
- Target: `12`
- Alert se: `< 8`

**M8 — decision_staleness_pct**:
- Query: `SELECT (COUNT(*) WHERE julianday('now') - julianday(last_reviewed_at) > 180) * 100.0 / COUNT(*) FROM neurons WHERE type='decision'`
- Target: `< 10%`
- Alert se: `> 30%`

### 9.3 Thresholds de ação

| Métrica | Valor | Ação |
|---|---|---|
| Qualquer M1-M8 zerada > 7 dias | Warning | Adicionar ao daily como "atenção" |
| M4 (orphans) > 15% | Critical | Rodar `/om-vault-audit` automático |
| M5 (consolidation) zerada > 90d | Critical | Investigar por que topic consolidator não roda |
| M8 (decision staleness) > 30% | Warning | Listar decisões stale no próximo weekly |

### 9.4 Dashboard

Criar `cerebro/bases/Memory Health Dashboard.base` com views:
- **Hoje**: atoms criados, sessions, decisions
- **Esta semana**: M1, M2, M7 trends
- **30 dias**: M3, M4, M6
- **90 dias**: M5, M8
- **Alertas**: lista de métricas em estado de alerta

---

## 10. Migração do filesystem atual — Fase 0

### 10.1 Ordem de execução (8 passos)

| # | Passo | Sanity test | Tempo |
|---|---|---|---|
| 1 | **Backup**: `sqlite3 hive_mind.db ".backup hive_mind.db.pre-migration"` + `cp -r cerebro cerebro.bak` | `ls -la hive_mind.db.pre-migration cerebro.bak/` | 5 min |
| 2 | **Criar `core/paths.py`** + branch `feat/path-constants` | `python -c "from core.paths import ATLAS_ROOT; print(ATLAS_ROOT)"` | 10 min |
| 3 | **Atualizar Python runtime** (dream_cycle, audit_memory, sinapse-mcp, sinapse-write, sinapse-zettelkasten, visual_capture, sinapse-memory plugin) | `grep -rn "cerebro/atlas\|cerebro/brain\|cerebro/conflicts" scripts/ plugins/ core/` retorna 0 | 30 min |
| 4 | **Atualizar testes** (test_audit_memory, test_syncthing_watcher, test_synthesis) | `python -m pytest tests/unit/ -q --collect-only` sem erros de import | 20 min |
| 5 | **Rodar migração SQLite** (transação única) | `SELECT COUNT(*) FROM neurons WHERE source_file LIKE 'cerebro/atlas/%'` = 0 | 5 min |
| 6 | **Reorg anatômica** via `scripts/migrate_anatomy.py` (não é `git mv` simples — precisa do projeto por neurônio): cada `atlas/{topic}/fact-*.md` → `cortex/temporal/{projeto}/{topic}/neuronio-*.md` (projeto rastreado por `source_observation_ids` → `observations.project`); `conflicts→cortex/insula/conflitos`; `inbox→cortex/parietal/inbox`; `graphify-out→cortex/occipital/grafo`; `brain/Patterns→cerebelo/padroes`; criar esqueleto dos lobos | `ls cerebro/cortex/temporal/*/*/*.md \| wc -l` = 16 | 25 min |
| 7 | **Atualizar docs** (AGENTS.md, 01-architecture.md) + descrições de tools MCP | `grep -n "cerebro/atlas\|cerebro/brain\|cerebro/conflicts\|cerebro/work/active" cerebro/AGENTS.md docs/01-architecture.md scripts/sinapse-mcp.py` = 0 | 20 min |
| 8 | **Run full suite** + smoke test + graphify update | `python -m pytest tests/unit/ -q` verde; `python scripts/smoke.sh` verde; `python -m graphify update cerebro/` exit 0 | 30 min |

**Total estimado**: ~2h30.

### 10.2 Migração SQLite (passo 5)

**Pré-check**:
```sql
SELECT COUNT(*) AS rows_atlas FROM neurons WHERE source_file LIKE 'cerebro/atlas/%';
```

**Idempotente** — o caminho agora inclui `{projeto}`, que **não** é derivável por REPLACE puro.
O `scripts/migrate_anatomy.py` move cada arquivo e atualiza o SQLite na mesma transação,
linha a linha (mapa `old_path → new_path` construído ao mover):
```sql
BEGIN;
CREATE INDEX IF NOT EXISTS idx_neurons_source_file ON neurons(source_file);
-- para cada neurônio movido (gerado pelo script):
UPDATE neurons SET source_file = :new_path WHERE source_file = :old_path;
-- ex.: 'cerebro/atlas/infrastructure/fact-7a3b.md'
--   →  'cerebro/cortex/temporal/Hive-Mind/infrastructure/neuronio-7a3b.md'
SELECT COUNT(*) AS pendentes FROM neurons WHERE source_file LIKE 'cerebro/atlas/%';
-- Critério: pendentes == 0
COMMIT;
```

**Rollback**: o script grava `migrate_anatomy_rollback.sql` (mapa inverso `new→old`) + `git checkout HEAD -- cerebro/`.

### 10.3 Bug crítico a corrigir simultaneamente

A inconsistência de convenção `source_file` (relativo a `SINAPSE_HOME` vs relativo a `vault_dir`) **precisa ser corrigida na Fase 0**.

**Decisão**: padronizar em **relativo a `VAULT_ROOT`** (= `SINAPSE_HOME / "cerebro"`). Razão: filesystem backend (`core/memory/backends/filesystem.py:120`) já usa essa convenção; é a mais natural para o Obsidian (vault = raiz).

**Migration adicional**:
```sql
-- Para entradas que começam com "atlas/..." (relativo a vault_dir), prefixar com "cerebro/"
UPDATE neurons SET source_file = 'cerebro/' || source_file
  WHERE source_file NOT LIKE 'cerebro/%' AND source_file LIKE 'atlas/%';
```

### 10.4 Backward compatibility

**Recomendação**: symlink temporário por 15 dias após cutover.

```bash
ln -s cortex/temporal cerebro/atlas        # neurônios (agora por projeto)
ln -s cortex/insula/conflitos cerebro/conflicts
ln -s cortex/parietal/inbox cerebro/inbox
ln -s cortex/occipital/grafo cerebro/graphify-out
```

**Para MCP tools** (sem symlink possível em JSON-RPC desc): reescrever 7 descrições em `scripts/sinapse-mcp.py:54,69,141,145,153,196` removendo paths literais; usar `<vault>/atoms`, `<vault>/decisoes`.

**Clients MCP** (Kilo, Codex, Roo, Copilot) cacheiam descrições no startup — após cutover, precisam reiniciar sessão MCP para pegar nova versão.

### 10.5 Critérios Go / Rollback

**Go** (cortar):
- G1: `core/paths.py` mergeado + importado em ≥ 7 callers
- G2: Zero hardcoded `cerebro/atlas` em código de runtime
- G3: `python -m pytest tests/unit/ -q` exit 0
- G4: Pré-check SQLite > 0 (há dados para migrar)
- G5: Backup íntegro (`PRAGMA integrity_check = ok`)
- G6: Syncthing drenado nos 2 peers
- G7: Graphify cache invalidado (`rm .graphify-out/graph.json`)

**Rollback** (≤ 5 min):
```bash
sqlite3 hive_mind.db "BEGIN; UPDATE neurons SET source_file = REPLACE(source_file, 'cerebro/indice/atlas/', 'cerebro/atlas/') WHERE source_file LIKE 'cerebro/indice/atlas/%'; COMMIT;"
git checkout HEAD -- cerebro/
systemctl --user restart sinapse-watcher
```

---

## 11. Roadmap Fase 1-3

### Fase 1 — Cadência básica (2-3 sprints, W28-W30)

**Tasks**:
1. `scripts/daily_writer.py` — gera `cerebro/daily/YYYY/MM/YYYY-MM-DD.md`
2. `scripts/session_placeholder.py` — hook SessionStart
3. `scripts/session_consolidator.py` — hook Stop
4. `scripts/session_update.py` — hook PostToolUse (atualiza placeholder)
5. systemd units: `sinapse-daily.timer` (23:55), `sinapse-daily.service`
6. Hooks configuration em `cerebro/.claude/settings.json`
7. Templates: `daily-log`, `session-log` em `cerebro/templates/`

**Entregáveis**: 4 scripts Python (NOVOS), 2 systemd units, 1 hook config modificado, 2 templates.

### Fase 2 — Memória inteligente (2-3 sprints, W31-W34)

**Tasks**:
1. `scripts/topic_consolidator.py` — embedding clustering + merge proposals
2. `scripts/alias_miner.py` — batch extract_slug em facts existentes
3. Modificar `scripts/dream_cycle.py:Router` — sliding window de topics
4. Modificar `scripts/dream_cycle.py:Distiller` — gerar alias slug
5. `scripts/sector_classifier.py` — LLM sector classifier
6. `scripts/weekly_synthesizer.py` — gera `cerebro/weekly/YYYY-W{XX}.md`
7. systemd units: `sinapse-weekly.timer`, `sinapse-topics.timer`, `sinapse-dream.timer`

**Entregáveis**: 5 scripts Python (NOVOS + 2 modificados), 6 systemd units.

### Fase 3 — Síntese viva (2 sprints, W35-W38)

**Tasks**:
1. `scripts/drift_detector.py` — atoms > 90d → `cold`, decisions > 180d → flagged
2. `scripts/decision_staleness.py` — lista decisões stale
3. `scripts/health_dashboard.py` — calcula M1-M8 + snapshot
4. Bases views: `Memory Health Dashboard`, `By Sector`, `Weekly Trends`
5. Modificar `scripts/weekly_synthesizer.py` — incluir health snapshot
6. systemd units: `sinapse-drift.timer` (mensal)

**Entregáveis**: 3 scripts Python (NOVOS + 1 modificado), 1 systemd unit, 3 Bases views.

### Cronograma

| Fase | Duração | Risco principal |
|---|---|---|
| Fase 0 | 2 sprints (W25-W26) | Migration quebra links existentes |
| Fase 1 | 2-3 sprints (W27-W29) | Hooks disparam em sessões de teste |
| Fase 2 | 2-3 sprints (W30-W32) | Topic consolidator faz merge errado |
| Fase 3 | 2 sprints (W33-W34) | LLM summarizer produz weekly ruins |

**Total**: 8-10 sprints (~4-5 meses).

### Marcos de sucesso

- **M1** (final Fase 0): zero path inconsistency; todos scripts importam de `core/paths.py`
- **M2** (final Fase 1): 7/7 daily logs na semana teste; ≥ 15 session logs automáticos
- **M3** (final Fase 2): < 5 tópicos fragmentados; ≥ 80% das notas têm alias
- **M4** (final Fase 3): health dashboard renderiza; alerts dispararam ≥ 1x em teste

---

## 12. Apêndice F — Papéis LLM (provider-agnostic, configurável por papel)

### F.1 Contrato do sistema (já implementado, `core/auth.py:362-423`)

```python
def get_role_config(role: str) -> Optional[Dict[str, Optional[str]]]:
    """Resolve provider/model/fallback para um papel canônico.

    Ordem de resolução:
      1. HIVE_{ROLE}_PROVIDER + HIVE_{ROLE}_MODEL, se AMBOS definidos
      2. senão, herda HIVE_DREAMER_PROVIDER + HIVE_DREAMER_MODEL
      3. fallback: HIVE_{ROLE}_FALLBACK_PROVIDER + HIVE_{ROLE}_FALLBACK_MODEL
         (ou HIVE_DREAMER_FALLBACK_* se 1+2 ausentes)

    Retorna {"provider", "model", "fallback_provider", "fallback_model"}
    """
```

**Provedores suportados** (via `core/llm_client.py`): Anthropic, Google (Gemini/Vertex), OpenAI, DeepSeek, OpenRouter, Ollama (local), e qualquer compatível com interface OpenAI. Sem limite a 2 provedores — o usuário configura o que quiser no `.env` via `scripts/setup-brain.py` (wizard interativo).

### F.2 Papéis EXISTENTES (já em produção)

| Papel | Quem chama | Função | Configuração atual |
|---|---|---|---|
| `dreamer` | `dream_cycle.py` Distiller + Validator + Router + Synthesis | Extração + validação + roteamento + síntese dialética | `HIVE_DREAMER_PROVIDER` / `HIVE_DREAMER_MODEL` (padrão: o que o usuário configurou via `setup-brain.py`) |
| `vision` | `dream_cycle.py:run_visual_dream_stage` | Análise de imagens (OCR + descrição + topics) | `HIVE_VISION_*` ou herda do dreamer |
| `synthesis` | `dream_cycle.py:run_synthesis_cycle` | Síntese dialética (resolve ambiguidades P2P) | `HIVE_SYNTHESIS_*` ou herda |
| `claude-mem` | `claude-mem-local` | Worker de observações temporais | `HIVE_CLAUDE_MEM_PROVIDER` / `HIVE_CLAUDE_MEM_MODEL` |

### F.3 Papéis NOVOS a registrar (Fase 1-2)

Cada papel novo segue o mesmo contrato. Por padrão **herda do dreamer** se `HIVE_{ROLE}_*` ausente no `.env` — Michel pode quebrar a configuração por papel **sem alterar código**, só ajustando `.env`.

| Papel | Script (NOVO) | Função | Quando quebrar config? |
|---|---|---|---|
| `session_summarizer` | `scripts/session_consolidator.py` (Fase 1) | Gera `## Resumo` da session-log via LLM | Se o resumo precisar de modelo mais capaz que o dreamer |
| `daily_writer` | `scripts/daily_writer.py` (Fase 1) | Consolida referências e métricas do dia | Se templates precisarem de estilo mais rico |
| `weekly_synthesizer` | `scripts/weekly_synthesizer.py` (Fase 2) | Gera `cerebro/weekly/YYYY-W{XX}.md` | **Provavelmente precisa de modelo mais capaz** — síntese executiva de 7 dias. Recomenda-se modelo top-tier aqui. |
| `alias_miner` | `scripts/alias_miner.py` (Fase 2) | Gera slug human-readable para `fact-{hash}.md` existente | Tarefa trivial — pode usar modelo mais barato (mesmo rápido e barato serve) |
| `topic_router` | `scripts/topic_consolidator.py` (Fase 2) | Decisão de merge de tópicos via LLM | Modelo médio — raciocínio semântico mas em escala |
| `sector_classifier` | `scripts/sector_classifier.py` (Fase 2) | Atribui 1-3 sectors a atom/decision/project | Tarefa simples — modelo pequeno |
| `drift_detector` | `scripts/drift_detector.py` (Fase 3) | Marca atoms frios, flagga decisions stale | Pode ser heurístico + LLM pontual |

### F.4 Como registrar um papel novo

**Passo 1** — adicionar em `core/auth.py` na lista `CANONICAL_ROLES` (linha 391 mencionada no docstring):

```python
CANONICAL_ROLES = {
    "dreamer", "vision", "synthesis", "claude-mem",
    "session_summarizer", "daily_writer", "weekly_synthesizer",
    "alias_miner", "topic_router", "sector_classifier", "drift_detector",
}
```

**Passo 2** — no script que usa o papel, chamar `get_role_config("nome_do_papel")`:

```python
from core.auth import get_role_config, call_llm_with_fallback

cfg = get_role_config("weekly_synthesizer") or {}
provider = cfg.get("provider")  # pode ser None se nada configurado
model = cfg.get("model")
# fallback automático em runtime via call_llm_with_fallback("weekly_synthesizer", prompt, ...)
```

**Passo 3** (opcional) — Michel pode configurar `.env` por papel sem tocar código:

```bash
# .env
HIVE_DREAMER_PROVIDER=anthropic
HIVE_DREAMER_MODEL=claude-sonnet-4-6
HIVE_WEEKLY_SYNTHESIZER_PROVIDER=anthropic
HIVE_WEEKLY_SYNTHESIZER_MODEL=claude-opus-4-1  # mais capaz para síntese executiva
HIVE_ALIAS_MINER_PROVIDER=google
HIVE_ALIAS_MINER_MODEL=gemini-2.5-flash-lite     # mais barato para tarefa trivial
HIVE_SECTOR_CLASSIFIER_PROVIDER=ollama
HIVE_SECTOR_CLASSIFIER_MODEL=qwen2.5:7b          # local, gratuito, suficiente
```

### F.5 Fallback automático em runtime

`dream_cycle.py:84-94` já implementa `_activate_dreamer_fallback()` que troca o cérebro ativo do Dreamer para o fallback se:
- `auth/saldo` (401/402/403, quota exhausted) → switch imediato, sem consumir retry
- `transient` (timeout/conexão/429/5xx) → switch após max_retries esgotado

**Aplicar mesmo padrão aos papéis novos**: `_activate_fallback(role, reason)` switch global por papel + flag em runtime.

---

## 12. Apêndices — auditorias que fundamentam este design

Este documento é a síntese. As auditorias detalhadas que fundamentam cada seção estão em:

- **Apêndice A — Mapa do Dream Cycle** (estágios A-G, contratos Pydantic, fluxo de dados, schema SQLite): disponível no contexto da sessão, IDs `329`, `1038`, `1724`, `2663`, `2904` em claude-mem
- **Apêndice B — Inventário exaustivo de paths hardcoded** (65+ referências em 18+ arquivos): mesmas fontes
- **Apêndice C — Validação da convenção de nomenclatura** (35+ arquivos do vault real, 5 exceções formais): mesmas fontes
- **Apêndice D — Matriz de risco + ordem de execução + migração SQLite** (Tier 1-4, symlinks, critérios Go/Rollback): mesmas fontes
- **Apêndice E — Path intelligence design** (Seções 1-11 do design service, schemas por tipo, cadências, multi-sector, métricas): mesmas fontes

**Para acessar**: `get_observations([IDs])` via MCP `mcp__claude-mem-local`.

---

## 13. Próximas ações imediatas

### Esta sessão

1. ✅ Validar este design com o autor (Michel) — **em andamento**
2. ⏳ Decisão: aprovar Fase 0 + iniciar (requer OK explícito)

### Após aprovação da Fase 0

| # | Ação | Quem | Tempo |
|---|---|---|---|
| 1 | Backup `hive_mind.db` + `cerebro/` | agente | 5 min |
| 2 | Criar branch `feat/fase-0-paths-constants` | agente | 1 min |
| 3 | Criar `core/paths.py` (60 linhas) | agente | 10 min |
| 4 | Atualizar 6+ scripts Python para importar `core.paths` | agente | 30 min |
| 5 | Atualizar 2 testes (`test_audit_memory`, `test_syncthing_watcher`) | agente | 20 min |
| 6 | Rodar migration SQLite (transação) | agente | 5 min |
| 7 | `git mv` diretórios (atlas, conflicts, brain) | agente | 15 min |
| 8 | Atualizar `cerebro/AGENTS.md` + `docs/01-architecture.md` | agente | 20 min |
| 9 | Atualizar 7 descrições de tools em `scripts/sinapse-mcp.py` | agente | 15 min |
| 10 | Criar symlinks temporários (15 dias) | agente | 1 min |
| 11 | Rodar `pytest tests/unit/ -q` + `python -m graphify update cerebro/` | agente | 30 min |
| 12 | Commit + merge da branch | agente | 5 min |

**Total Fase 0**: ~2h30, reversível.

### Após Fase 0 (Fase 1)

Implementar cadência básica — daily/session/weekly scripts + hooks + systemd timers. Estimativa: 2-3 sprints.

### Pontos abertos para decisão do autor

1. **Escopo da Fase 0**: completar migração filesystem + corrigir SQLite inconsistency antes de avançar? **Recomendação: sim**.
2. **Backward compatibility**: symlinks temporários (15d) vs quebra seca? **Recomendação: symlinks**.
3. **Naming convention para `work/active/ → trabalho/{decisoes,projetos}/`**: já nesta Fase 0 ou na Fase 1? **Recomendação: Fase 1, junto com cadência**.
4. **Política de LLM por papel** (NÃO existe limitação a 2 provedores — sistema já é provider-agnostic via `core/auth.py:get_role_config(role)` linhas 362-423, com fallback automático por papel. Ver Apêndice F).
5. **Setores iniciais**: lista proposta cobre o essencial (`ai-infra`, `dev-tools`, `pkm`, `infra`, `finance`, `health`, `research`)? Falta algum?
6. **Papéis LLM novos a registrar na Fase 1-2** (ver Apêndice F): `alias_miner`, `topic_router`, `weekly_synthesizer`, `sector_classifier`, `session_summarizer`. Cada um herda do `dreamer` por padrão se `HIVE_{ROLE}_*` ausente no `.env`.

---

*Documento vivo. Versão 2.0 (modelo anatômico cerebral). Próxima revisão: após conclusão da Fase 0.*
