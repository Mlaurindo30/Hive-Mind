from pydantic import BaseModel, Field
from typing import List, Optional

class SynthesisOutput(BaseModel):
    """Contrato para a saída do Estágio de Síntese Dialética."""
    final_content: str = Field(..., description="O conteúdo final sintetizado (Síntese).")
    logic_applied: str = Field(..., description="Explicação da lógica usada para resolver a ambiguidade (ex: Fusão, Substituição, Evolução).")
    provenance_summary: str = Field(..., description="Resumo da origem das informações (fontes originais).")
    parent_hashes: List[str] = Field(..., description="Lista de hashes de integridade das versões que foram fundidas.")
    conflict_resolved: bool = Field(..., description="Indica se o conflito foi resolvido com sucesso.")

class SynthesisTask(BaseModel):
    """Contexto para uma tarefa de síntese."""
    topic: str
    version_a_content: str
    version_b_content: str
    diff_category: str
    diff_reasoning: str
