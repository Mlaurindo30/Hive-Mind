"""Knowledge intake and promotion pipeline (K3)."""

from core.knowledge.claude_mem_bridge import bridge as bridge_claude_mem
from core.knowledge.intake import KnowledgeCandidate, normalize_observation
from core.knowledge.promotion import promote_files, promote_pending_observations

__all__ = [
    "KnowledgeCandidate",
    "bridge_claude_mem",
    "normalize_observation",
    "promote_files",
    "promote_pending_observations",
]
