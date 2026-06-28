#!/usr/bin/env python3
"""
core/paths.py — Ponto ÚNICO de verdade para os caminhos do vault (modelo anatômico).

O vault `cerebro/` espelha a anatomia do cérebro: cada região mapeia uma função
real do órgão para uma função do sistema (ver docs/08-memoria-viva-design.md §2).

Substitui todos os `Path(SINAPSE_HOME) / "cerebro" / "..."` espalhados nos scripts.
Uso: `from core.paths import TEMPORAL, neuron_path, project_moc, ...`
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

# Raiz do projeto (mesma resolução de core/database.py)
SINAPSE_HOME = Path(os.environ.get(
    "SINAPSE_HOME", str(Path(__file__).resolve().parent.parent)))

# Raiz do vault Obsidian
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
FRONTAL_BRAIN = FRONTAL / "brain"
CURRENT_STATE = FRONTAL_BRAIN / "Current State.md"
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
SAUDE_ROOT = INSULA / "saude"               # dashboard + métricas
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
MONTHLY_ROOT = CEREBELO / "mensal"
YEARLY_ROOT = CEREBELO / "anual"
PADROES_ROOT = CEREBELO / "padroes"         # memória procedural

# ===== TRONCO CEREBRAL — funções vitais (infra) =====
TRONCO = VAULT_ROOT / "tronco"
META_ROOT = TRONCO / "meta"
MODELOS_ROOT = TRONCO / "modelos"           # templates Obsidian
PAINEIS_ROOT = TRONCO / "paineis"           # bases (.base)

ATTACHMENTS_ROOT = VAULT_ROOT / "attachments"


# ===== INTEGRATIONS — vendors (órgãos externos) =====
# Cada projeto em `integrations/<nome>/` é um vendor — código clonado que
# serve como órgão do cérebro. Graphiti, Graphify, RTK, Neural Memory e
# claude-mem vivem aqui. Use as constantes em vez de paths hardcoded.
INTEGRATIONS_ROOT = SINAPSE_HOME / "integrations"
GRAPHITI_INTEGRATION = INTEGRATIONS_ROOT / "graphiti"      # lóbulo temporal
GRAPHIFY_INTEGRATION = INTEGRATIONS_ROOT / "graphify"      # lóbulo occipital
NEURAL_MEMORY_INTEGRATION = INTEGRATIONS_ROOT / "neural-memory"  # córtex (associação)
RTK_INTEGRATION = INTEGRATIONS_ROOT / "rtk"               # tronco (otimização)
CLAUDE_MEM_INTEGRATION = INTEGRATIONS_ROOT / "claude-mem-plugins"  # lóbulo temporal (eventos)


# ===== Helpers de path =====
def neuron_path(project: str, topic: str, hash16: str) -> Path:
    """cortex/temporal/{projeto}/{topico}/neuronio-{hash16}.md (eixo por projeto)."""
    return TEMPORAL / project / topic / f"neuronio-{hash16}.md"


def project_moc(project: str) -> Path:
    """cortex/temporal/{projeto}/_{projeto}.md (MOC do projeto, auto-gerado)."""
    return TEMPORAL / project / f"_{project}.md"


def topic_moc(project: str, topic: str) -> Path:
    """cortex/temporal/{projeto}/{topico}/_{topico}.md (MOC do tópico)."""
    return TEMPORAL / project / topic / f"_{topic}.md"


def sector_moc(sector: str) -> Path:
    """diencefalo/setores/_{setor}.md (MOC de setor, cruza projetos)."""
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


def monthly_path(year: int, month: int) -> Path:
    """cerebelo/mensal/YYYY-MM.md"""
    return MONTHLY_ROOT / f"{year:04d}-{month:02d}.md"


def yearly_path(year: int) -> Path:
    """cerebelo/anual/YYYY.md"""
    return YEARLY_ROOT / f"{year:04d}.md"


def rel_to_vault(p: Path) -> str:
    """Caminho relativo a SINAPSE_HOME (convenção de neurons.source_file)."""
    try:
        return str(Path(p).resolve().relative_to(SINAPSE_HOME))
    except ValueError:
        return str(p)
