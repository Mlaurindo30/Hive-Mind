from pydantic import BaseModel, Field

class AliasMinerOutput(BaseModel):
    slug: str = Field(description="O slug kebab-case gerado para o neurônio.")
