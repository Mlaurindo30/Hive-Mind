from pydantic import BaseModel, Field
from typing import List

class VisionAnalysis(BaseModel):
    description: str = Field(description="Detailed description of the visual content of the image.")
    ocr: str = Field(description="All text found in the image, transcribed exactly.")
    inferred_topics: List[str] = Field(description="List of relevant topics or keywords related to the image content.")
    importance_score: float = Field(description="A score from 0.0 to 1.0 indicating how important this visual memory is for long-term storage.")
