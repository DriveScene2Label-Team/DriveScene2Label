from typing import Annotated, Literal
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

# Spring's search indexing claims this many images per round (DatasetSearchIndexService.BATCH_SIZE).
MAX_BATCH_IMAGES = 64

class ImageBatchEmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    image_paths: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1, max_length=MAX_BATCH_IMAGES,
                                                                    description="Relative paths under the same root as /embedding/image.")
    preprocess: Preprocess = "lr-square-crop-mean"
    dataset_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")

class ImageEmbeddingError(BaseModel):
    status: int
    code: str
    message: str

class ImageBatchItem(BaseModel):
    """Exactly one of embedding/error is set. error carries the status/code /embedding/image would have returned."""
    image_path: str
    embedding: list[FiniteFloat] | None = Field(default=None, min_length=768, max_length=768)
    error: ImageEmbeddingError | None = None

class ImageBatchEmbeddingResponse(BaseModel):
    model_name: Literal["ViT-L-14-quickgelu/openai"] = "ViT-L-14-quickgelu/openai"
    dimension: Literal[768] = 768
    preprocess: str
    results: list[ImageBatchItem]
