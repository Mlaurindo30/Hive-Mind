from pydantic import BaseModel, Field

class TopicMergeProposal(BaseModel):
    should_merge: bool = Field(description="Se os tópicos devem ser fundidos.")
    new_topic_name: str = Field(description="O nome sugerido para o tópico consolidado (lowercase, snake_case).")
    rationale: str = Field(description="Justificativa para a decisão.")
