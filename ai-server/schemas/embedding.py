from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

Preprocess = Literal["lr-square-crop-mean", "openclip-eval-224-centercrop"]

class TextEmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=10000)

class ImageEmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    image_path: str = Field(min_length=1, description="Relative path under CLIP_IMAGE_ROOT on the AI server.")
    preprocess: Preprocess = "lr-square-crop-mean"
    dataset_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")

class EmbeddingResponse(BaseModel):
    model_name: Literal["ViT-L-14-quickgelu/openai"] = "ViT-L-14-quickgelu/openai"
    dimension: Literal[768] = 768
    embedding: list[FiniteFloat] = Field(min_length=768, max_length=768)
    preprocess: str
