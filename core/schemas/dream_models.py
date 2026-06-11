from pydantic import BaseModel, Field
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

class DistillerOutput(BaseModel):
    facts: List[ExtractedFact] = Field(description="Lista de fatos atômicos extraídos da sessão.")

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

class ValidatorOutput(BaseModel):
    validations: List[FactValidation] = Field(description="Resultado da validação para cada fato submetido.")
    global_status: Literal["pass", "retry", "abort"] = Field(
        description="Status da etapa. Se houver falhas críticas, solicita retry."
    )

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

class RouterOutput(BaseModel):
    routed_facts: List[RoutedFact]
