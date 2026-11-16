"""Shared DB-free CLIP inference, extracted from embed_images.py."""
from pathlib import Path
import torch
from PIL import Image

MODEL_NAME = "ViT-L-14-quickgelu"
PRETRAINED = "openai"
EMBED_DIM = 768
CENTER_CROP = "openclip-eval-224-centercrop"
LR_SQUARE_CROP_MEAN = "lr-square-crop-mean"
PREPROCESS_MODES = (LR_SQUARE_CROP_MEAN, CENTER_CROP)

def model_key(model_name: str, pretrained: str) -> str:
    return f"{model_name}/{pretrained}"


def resolve(root: Path, relative_path: str) -> Path:
    """Same rule as DatasetFiles.resolve: relative path only, must stay inside the dataset root."""
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError("Relative dataset path required")
    real_root = root.resolve(strict=True)
    real_file = (real_root / relative_path).resolve(strict=True)
    if not real_file.is_relative_to(real_root) or not real_file.is_file():
        raise ValueError(f"Invalid dataset file: {relative_path}")
    return real_file


def available_devices() -> list[str]:
    found = ["cuda"] if torch.cuda.is_available() else []
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        found.append("mps")
    return found + ["cpu"]


def square_crops(img: Image.Image) -> list[Image.Image]:
    """Landscape image -> left (0,0,h,h) and right (w-h,0,w,h) squares, which together cover the full width.
    Square or portrait images are returned as the single original."""
    w, h = img.size
    if w > h:
        return [img.crop((0, 0, h, h)), img.crop((w - h, 0, w, h))]
    return [img]


def image_crops(img: Image.Image, mode: str) -> list[Image.Image]:
    return square_crops(img) if mode == LR_SQUARE_CROP_MEAN else [img]


def combine_crops(features: torch.Tensor, counts: list[int]) -> torch.Tensor:
    """features holds one row per crop, grouped by image (counts[i] rows for image i).
    L2-normalize each crop, average per image, L2-normalize again -> one unit vector per image."""
    features = features / features.norm(dim=-1, keepdim=True)
    means = torch.stack([group.mean(dim=0) for group in features.split(counts)])
    return means / means.norm(dim=-1, keepdim=True)


def load_model(device: str):
    import open_clip

    model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED, device=device)
    model.eval()
    tokenizer = open_clip.get_tokenizer(MODEL_NAME)
    return model, preprocess, tokenizer


def preprocess_crops(preprocess, image, mode=LR_SQUARE_CROP_MEAN) -> torch.Tensor:
    """CPU half of encode_image: crops of one image -> stacked model input. Split out so callers can time it."""
    if mode not in PREPROCESS_MODES:
        raise ValueError("Unsupported image preprocessing")
    return torch.stack([preprocess(crop) for crop in image_crops(image.convert("RGB"), mode)])


@torch.no_grad()
def encode_crops(model, crops: torch.Tensor, device) -> torch.Tensor:
    """GPU half of encode_image for one image's crops. .cpu() waits for the device, so a wall timer around this
    call covers the copy to the device, the forward pass and the copy back."""
    return combine_crops(model.encode_image(crops.to(device)).float(), [len(crops)])[0].cpu()


@torch.no_grad()
def encode_image(model, preprocess, image, device, mode=LR_SQUARE_CROP_MEAN):
    return encode_crops(model, preprocess_crops(preprocess, image, mode), device)


@torch.no_grad()
def encode_text(model, tokenizer, text, device):
    features = model.encode_text(tokenizer([text]).to(device)).float()
    return (features / features.norm(dim=-1, keepdim=True))[0].cpu()
