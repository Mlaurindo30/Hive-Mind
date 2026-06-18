"""Schemas do pattern_distiller (Memória Viva F4.3) — memória procedural."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class Pattern(BaseModel):
    title: str = Field(..., description="Nome curto do padrão (ex.: 'Validar contra DB real antes do commit')")
    slug: str = Field(..., description="kebab-case identificador estável")
    context: str = Field(..., description="Quando/onde esse padrão aparece")
    steps: List[str] = Field(default_factory=list, description="Passos que compõem o padrão")
    when_to_use: str = Field("", description="Sinal de quando aplicar")
    confidence: float = Field(0.5, ge=0.0, le=1.0)


class PatternOutput(BaseModel):
    patterns: List[Pattern] = Field(default_factory=list)
