from fastapi import APIRouter, Request
from schemas.embedding import TextEmbeddingRequest, ImageEmbeddingRequest, EmbeddingResponse, ImageBatchEmbeddingRequest, ImageBatchEmbeddingResponse

router = APIRouter(prefix="/embedding", tags=["embedding"])

@router.post("/text", response_model=EmbeddingResponse)
def embed_text(body: TextEmbeddingRequest, request: Request):
    return request.app.state.clip_service.encode_text(body.text)

@router.post("/image", response_model=EmbeddingResponse)
def embed_image(body: ImageEmbeddingRequest, request: Request):
    if body.dataset_key is not None:
        return request.app.state.clip_service.encode_image_path(body.image_path, body.preprocess, body.dataset_key)
    return request.app.state.clip_service.encode_image_path(body.image_path, body.preprocess)

@router.post("/images", response_model=ImageBatchEmbeddingResponse)
def embed_images(body: ImageBatchEmbeddingRequest, request: Request):
    """Up to 64 images in one call and one batched forward pass. Per-image failures come back in results[i].error
    with the status/code /embedding/image would return; inference failure fails the whole call (500)."""
    return request.app.state.clip_service.encode_image_paths(body.image_paths, body.preprocess, body.dataset_key)
