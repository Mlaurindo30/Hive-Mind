from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional

class DiffCategory(str, Enum):
    ADDITIVE = "ADDITIVE"
    SUBSTITUTIVE = "SUBSTITUTIVE"
    CONTRADICTORY = "CONTRADICTORY"

class SemanticDiffResult(BaseModel):
    contradiction_score: float = Field(..., description="Score de contradição de 0.0 (sem contradição) a 1.0 (contradição total).")
    category: DiffCategory = Field(..., description="Categoria da diferença semântica.")
    reasoning: str = Field(..., description="Explicação detalhada do porquê desta classificação, citando trechos se necessário.")
    suggested_resolution: Optional[str] = Field(None, description="Uma sugestão de como fundir ou resolver os dois textos em uma única verdade.")

    @field_validator("contradiction_score")
    @classmethod
    def contradiction_score_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"contradiction_score deve ser 0.0–1.0, recebido: {v}")
        return v

    @field_validator("reasoning")
    @classmethod
    def reasoning_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reasoning não pode ser vazio ou apenas whitespace")
        return v.strip()
