"""Pydantic models for K5 yearly cadence synthesis."""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List


class YearlySummaryModel(BaseModel):
    """Structured output for the `yearly_synthesizer` role."""

    historical_summary: str = Field(
        description="Retrospectiva historica do ano em 4-6 frases."
    )
    major_decisions: List[str] = Field(
        default_factory=list,
        description="Grandes decisoes e seus motivos duraveis.",
    )
    durable_principles: List[str] = Field(
        default_factory=list,
        description="Principios consolidados para orientar trabalho futuro.",
    )
    learned_lessons: List[str] = Field(
        default_factory=list,
        description="Lessons learned duraveis, nao detalhes operacionais.",
    )
    strategic_risks: List[str] = Field(
        default_factory=list,
        description="Riscos estrategicos que persistem para o proximo ciclo.",
    )
    next_year_goals: List[str] = Field(
        default_factory=list,
        description="Metas de alto nivel para o proximo ano.",
    )
