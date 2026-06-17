"""Pydantic models for the Session Cadence (Fase 1 — Memória Viva §11).

Reusado por `scripts/session_consolidator.py` (gera SessionSummary no hook Stop)
e `scripts/daily_writer.py` (gera DailySummary no timer 23:55).
"""
from pydantic import BaseModel, Field
from typing import List


class SessionSummary(BaseModel):
    """Saída estruturada do consolidator de sessão (papel `session_summarizer`)."""

    bullets: List[str] = Field(
        description=(
            "3-7 bullets resumindo o que rolou na sessão. "
            "Verbos no passado, foco no que foi FEITO/ENCONTRADO/DECIDIDO."
        )
    )
    decisions: List[str] = Field(
        default_factory=list,
        description=(
            "Decisões explícitas tomadas durante a sessão (ou [] se nenhuma). "
            "Formato: 'Decidiu-se X porque Y'."
        )
    )
    open_questions: List[str] = Field(
        default_factory=list,
        description=(
            "Perguntas em aberto que ficaram sem resposta (ou [] se nenhuma). "
            "Útil para Daily/Weekly consolidators puxarem o fio."
        )
    )


class DailySummary(BaseModel):
    """Saída estruturada do daily writer (papel `daily_writer`)."""

    highlights: List[str] = Field(
        description=(
            "3-5 bullets de conquistas/decisões relevantes do dia. "
            "Foco no que AVANÇOU, não em rotina."
        )
    )
    learnings: List[str] = Field(
        description=(
            "Padrões, insights ou lessons learned observados no dia. "
            "Conectar observações em abstração reutilizável."
        )
    )
