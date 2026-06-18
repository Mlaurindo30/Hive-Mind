from pydantic import BaseModel, Field
from typing import List, Literal

SectorType = Literal["ai-infra", "dev-tools", "pkm", "infra", "finance", "health", "research"]

class SectorClassifierOutput(BaseModel):
    sectors: List[SectorType] = Field(
        description="Lista de 1 a 3 setores canônicos classificados para o neurônio.",
        min_length=1,
        max_length=3
    )
