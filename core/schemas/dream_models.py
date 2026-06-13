from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Literal, Optional

# ==============================================================================
# 1. Distiller Models (Extração Bruta)
# ==============================================================================
class ExtractedFact(BaseModel):
    id: str = Field(description="Slug único para o fato. Ex: pref-python-typing")
    label: str = Field(description="Título curto e conciso do fato (máximo 5 palavras).")
    content: str = Field(description="O fato, decisão ou preferência detalhada.")
    integrity_hash: Optional[str] = Field(None, description="Hash SHA256 do conteúdo para garantir unicidade e integridade.")
    type: Literal["fact", "preference", "decision", "lore"] = Field(
        description="Categoria semântica do fato extraído."
    )
    source_quotes: List[str] = Field(
        description="Citações exatas (literais) dos logs que provam este fato. Obrigatório para aterramento (grounding)."
    )

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content não pode ser vazio ou apenas whitespace")
        return v.strip()

    @field_validator("label")
    @classmethod
    def label_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("label não pode ser vazio ou apenas whitespace")
        return v.strip()

class DistillerOutput(BaseModel):
    facts: List[ExtractedFact] = Field(description="Lista de fatos atômicos extraídos da sessão.")

    @model_validator(mode="after")
    def facts_not_empty(self) -> "DistillerOutput":
        if not self.facts:
            raise ValueError("facts deve conter ao menos 1 item")
        return self

# ==============================================================================
# 2. Validator Models (Verificação de Alucinação)
# ==============================================================================
class FactValidation(BaseModel):
    fact_id: str = Field(description="O ID do fato sendo avaliado.")
    groundedness_valid: bool = Field(description="O fato é integralmente suportado pelas source_quotes?")
    hallucination_detected: bool = Field(description="O fato contém entidades, prazos ou regras inventadas não presentes nos logs?")
    status: Literal["pass", "warning", "fail"] = Field(
        description="Veredito final. Pass (Perfeito), Warning (Precisa revisão mas aceitável), Fail (Alucinação ou mentira)."
    )
    reason_summary: str = Field(description="Uma frase auditável justificando a decisão. Sem chain-of-thought.")

    @field_validator("reason_summary")
    @classmethod
    def reason_summary_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason_summary não pode ser vazio ou apenas whitespace")
        return v.strip()

class ValidatorOutput(BaseModel):
    validations: List[FactValidation] = Field(description="Resultado da validação para cada fato submetido.")
    global_status: Literal["pass", "retry", "abort"] = Field(
        description="Status da etapa. Se houver falhas críticas, solicita retry."
    )

    @model_validator(mode="after")
    def validations_not_empty(self) -> "ValidatorOutput":
        if not self.validations:
            raise ValueError("validations deve conter ao menos 1 item")
        return self

# ==============================================================================
# 3. Router Models (Taxonomia Determinística)
# ==============================================================================
class RoutedFact(BaseModel):
    fact_id: str
    topic: str = Field(
        description="Pasta de destino (minúsculo, sem espaços). Ex: 'coding', 'architecture', 'user_profile'."
    )
    action: Literal["append", "create_new", "merge"] = Field(
        description="append (juntar a uma nota existente), create_new (nova nota âncora), merge (fundir com fato existente)."
    )

    @field_validator("topic")
    @classmethod
    def topic_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("topic não pode ser vazio ou apenas whitespace")
        return v.strip()

class RouterOutput(BaseModel):
    routed_facts: List[RoutedFact]

    @model_validator(mode="after")
    def routed_facts_not_empty(self) -> "RouterOutput":
        if not self.routed_facts:
            raise ValueError("routed_facts deve conter ao menos 1 item")
        return self
