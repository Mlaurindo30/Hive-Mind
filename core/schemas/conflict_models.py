"""Schema do conflict_detector (Memória Viva F4.4)."""
from __future__ import annotations
from pydantic import BaseModel, Field


class ConflictJudgement(BaseModel):
    is_conflict: bool = Field(..., description="True se as duas notas se contradizem")
    explanation: str = Field("", description="Por que (ou por que não) há conflito")
