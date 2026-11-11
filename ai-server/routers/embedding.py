from fastapi import APIRouter, Request
from schemas.embedding import TextEmbeddingRequest, ImageEmbeddingRequest, EmbeddingResponse

router = APIRouter(prefix="/embedding", tags=["embedding"])

@router.post("/text", response_model=EmbeddingResponse)
def embed_text(body: TextEmbeddingRequest, request: Request):
    return request.app.state.clip_service.encode_text(body.text)

@router.post("/image", response_model=EmbeddingResponse)
def embed_image(body: ImageEmbeddingRequest, request: Request):
    if body.dataset_key is not None:
        return request.app.state.clip_service.encode_image_path(body.image_path, body.preprocess, body.dataset_key)
    return request.app.state.clip_service.encode_image_path(body.image_path, body.preprocess)
