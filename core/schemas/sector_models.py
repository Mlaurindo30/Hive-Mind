from pydantic import BaseModel, Field
from typing import List, Literal

SectorType = Literal["ai-infra", "dev-tools", "pkm", "infra", "finance", "health", "research"]

class SectorClassifierOutput(BaseModel):
    sectors: List[SectorType] = Field(
        description="Lista de 1 a 3 setores canônicos classificados para o neurônio.",
        min_length=1,
        max_length=3
    )


class SectorBatchResult(BaseModel):
    """F3-otimização (2026-08-13): um item do lote de classificação setorial."""
    id: int = Field(description="Índice do neurônio no prompt do lote (0..N-1).")
    sectors: List[SectorType] = Field(
        description="1 a 3 setores canônicos para esse neurônio.",
        min_length=1,
        max_length=3,
    )


class SectorBatchOutput(BaseModel):
    """F3-otimização: resultado de classificação de um lote de neurônios."""
    results: List[SectorBatchResult] = Field(
        description="Um resultado por neurônio do lote, com id = índice original."
    )
