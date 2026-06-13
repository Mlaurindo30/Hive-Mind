from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional

class SynthesisOutput(BaseModel):
    """Contrato para a saída do Estágio de Síntese Dialética."""
    final_content: str = Field(..., description="O conteúdo final sintetizado (Síntese).")
    logic_applied: str = Field(..., description="Explicação da lógica usada para resolver a ambiguidade (ex: Fusão, Substituição, Evolução).")
    provenance_summary: str = Field(..., description="Resumo da origem das informações (fontes originais).")
    parent_hashes: List[str] = Field(..., description="Lista de hashes de integridade das versões que foram fundidas.")
    conflict_resolved: bool = Field(..., description="Indica se o conflito foi resolvido com sucesso.")

    @field_validator("final_content")
    @classmethod
    def final_content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("final_content não pode ser vazio ou apenas whitespace")
        return v.strip()

    @field_validator("logic_applied")
    @classmethod
    def logic_applied_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("logic_applied não pode ser vazio ou apenas whitespace")
        return v.strip()

    @field_validator("provenance_summary")
    @classmethod
    def provenance_summary_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("provenance_summary não pode ser vazio ou apenas whitespace")
        return v.strip()

    @model_validator(mode="after")
    def parent_hashes_not_empty(self) -> "SynthesisOutput":
        if not self.parent_hashes:
            raise ValueError("parent_hashes deve conter ao menos 1 item")
        return self

class SynthesisTask(BaseModel):
    """Contexto para uma tarefa de síntese."""
    topic: str
    version_a_content: str
    version_b_content: str
    diff_category: str
    diff_reasoning: str

    @field_validator("topic")
    @classmethod
    def topic_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("topic não pode ser vazio ou apenas whitespace")
        return v.strip()

    @field_validator("version_a_content")
    @classmethod
    def version_a_content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("version_a_content não pode ser vazio ou apenas whitespace")
        return v.strip()

    @field_validator("version_b_content")
    @classmethod
    def version_b_content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("version_b_content não pode ser vazio ou apenas whitespace")
        return v.strip()

    @field_validator("diff_reasoning")
    @classmethod
    def diff_reasoning_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("diff_reasoning não pode ser vazio ou apenas whitespace")
        return v.strip()
