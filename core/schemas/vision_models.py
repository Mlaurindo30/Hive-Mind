from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List

class VisionAnalysis(BaseModel):
    description: str = Field(description="Detailed description of the visual content of the image.")
    ocr: str = Field(description="All text found in the image, transcribed exactly.")
    inferred_topics: List[str] = Field(description="List of relevant topics or keywords related to the image content.")
    importance_score: float = Field(description="A score from 0.0 to 1.0 indicating how important this visual memory is for long-term storage.")

    @field_validator("importance_score")
    @classmethod
    def importance_score_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"importance_score deve ser 0.0–1.0, recebido: {v}")
        return v

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("description não pode ser vazio ou apenas whitespace")
        return v.strip()

    @model_validator(mode="after")
    def inferred_topics_not_empty(self) -> "VisionAnalysis":
        if not self.inferred_topics:
            raise ValueError("inferred_topics deve conter ao menos 1 item")
        return self
