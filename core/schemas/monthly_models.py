"""Pydantic models for K5 monthly cadence synthesis."""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List


class MonthlySummaryModel(BaseModel):
    """Structured output for the `monthly_synthesizer` role."""

    executive_summary: str = Field(
        description="Sintese executiva do mes em 3-5 frases, sem copiar semanais."
    )
    durable_decisions: List[str] = Field(
        default_factory=list,
        description="Decisoes duraveis do mes, com motivo e impacto.",
    )
    durable_learnings: List[str] = Field(
        default_factory=list,
        description="Aprendizados reutilizaveis com contexto e consequencia.",
    )
    persistent_risks: List[str] = Field(
        default_factory=list,
        description="Riscos estruturais/persistentes, nao incidentes passageiros.",
    )
    goals: List[str] = Field(
        default_factory=list,
        description="Metas ou proximos passos duraveis com criterio de aceite.",
    )
    strategy_drift: List[str] = Field(
        default_factory=list,
        description="Mudancas de direcao, drift estrategico ou tensoes abertas.",
    )
