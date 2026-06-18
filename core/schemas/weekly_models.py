"""Pydantic models for the Weekly Synthesis (Fase 2 — Memória Viva §11).

Reusado por `scripts/weekly_synthesizer.py`.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class ProjectStatus(BaseModel):
    """Status de um projeto específico para o resumo semanal."""
    name: str = Field(description="Nome ou link do projeto")
    status: str = Field(description="Status atual (ex: active, blocked, completed)")
    blockers: str = Field(description="Impedimentos ou 'Nenhum'")
    delta: str = Field(description="O que mudou/avançou nesta semana")


class WeeklySummaryModel(BaseModel):
    """Saída estruturada do sintetizador semanal (papel `weekly_synthesizer`)."""

    overview: str = Field(
        description="Visão Geral (3-4 frases): tema dominante + ritmo + signal de drift (setores silenciosos)."
    )
    top_atoms: List[str] = Field(
        description="Top 5 Átomos (fatos/insights) mais relevantes criados na semana."
    )
    decisions_closed: List[str] = Field(
        default_factory=list,
        description="Decisões que foram tomadas/fechadas nesta semana."
    )
    decisions_open: List[str] = Field(
        default_factory=list,
        description="Decisões que permanecem em aberto ou rascunho."
    )
    projects: List[ProjectStatus] = Field(
        description="Lista de projetos ativos e seu progresso semanal."
    )
    patterns: List[str] = Field(
        description="Padrões emergentes ou observações cross-day (2-3 pontos)."
    )
    next_week_priorities: List[str] = Field(
        description="Próxima Semana: 3-5 prioridades recomendadas."
    )
