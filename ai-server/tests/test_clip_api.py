import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import torch
from PIL import Image
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import app
from services import clip_service
import clip_core

class Model:
    def encode_text(self, tokens):
        return torch.arange(1, 769, dtype=torch.float32).repeat(len(tokens), 1)
    def encode_image(self, crops):
        # Unequal scales ensure crop normalization happens before averaging.
        return torch.arange(1, 769, dtype=torch.float32).repeat(len(crops), 1) * torch.arange(1, len(crops)+1).unsqueeze(1)

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIP_IMAGE_ROOT", str(tmp_path))
    Image.new("RGB", (1600, 900)).save(tmp_path / "image.jpg")
    (tmp_path / "broken.jpg").write_text("not an image")
    with patch.object(clip_core, "load_model", return_value=(Model(), lambda img: torch.zeros(3,224,224), lambda texts: torch.ones(len(texts),77,dtype=torch.long))) as loader:
        with TestClient(app) as client:
            yield client, loader, tmp_path


def test_load_once_and_unit_vectors(client):
    c, loader, _=client
    assert c.get("/health").json()["inference"]["clip"]=="ready"
    for url,body in [("/embedding/text",{"text":"rainy night road"}), ("/embedding/image",{"image_path":"image.jpg"}), ("/embedding/image",{"image_path":"image.jpg","preprocess":"openclip-eval-224-centercrop"})]:
        r=c.post(url,json=body)
        assert r.status_code==200, r.text
        result=r.json()
        assert result["model_name"]=="ViT-L-14-quickgelu/openai"
        assert result["dimension"]==len(result["embedding"])==768
        assert torch.isclose(torch.tensor(result["embedding"]).norm(),torch.tensor(1.0),atol=1e-6)
    assert loader.call_count==1
    assert c.get("/docs").status_code==200
    assert "psycopg" not in sys.modules and "sqlalchemy" not in sys.modules


def test_errors(client):
    c,_,root=client
    assert c.post("/embedding/text",json={"text":"  "}).status_code==422
    assert c.post("/embedding/image",json={"image_path":"missing.jpg"}).status_code==404
    assert c.post("/embedding/image",json={"image_path":str(root/"image.jpg")}).status_code==400
    assert c.post("/embedding/image",json={"image_path":"broken.jpg"}).status_code==400
    outside=root.parent/"outside.jpg"
    Image.new("RGB",(4,4)).save(outside)
    (root/"link.jpg").symlink_to(outside)
    assert c.post("/embedding/image",json={"image_path":"link.jpg"}).status_code==400
    assert c.post("/embedding/image",json={"image_path":"../outside.jpg"}).status_code==400
    with patch.object(app.state.clip_service.model,"encode_text",side_effect=RuntimeError("private detail")):
        r=c.post("/embedding/text",json={"text":"road"})
        assert r.status_code==500 and "private detail" not in r.text
    with patch.object(app.state.clip_service.model,"encode_text",return_value=torch.zeros(1,768)):
        assert c.post("/embedding/text",json={"text":"road"}).status_code==500


def test_shared_crop_math():
    features=torch.zeros(2,768)
    features[0,0]=2; features[1,1]=100
    actual=clip_core.combine_crops(features,[2])[0]
    expected=torch.zeros(768); expected[:2]=2**-0.5
    assert torch.allclose(actual,expected,atol=1e-6)
    image=Image.new("RGB",(1600,900))
    assert [c.size for c in clip_core.square_crops(image)]==[(900,900),(900,900)]


def test_startup_failure(monkeypatch):
    # Strict mode keeps the original fail-fast startup; the default (non-fatal) path is in test_capabilities.py.
    monkeypatch.setenv("AI_REQUIRE_CLIP","true")
    with patch.object(clip_core,"load_model",side_effect=RuntimeError("weights unavailable")):
        with pytest.raises(RuntimeError,match="weights unavailable"):
            with TestClient(app):
                pass


def test_uploaded_image_scope_and_traversal(client, monkeypatch):
    c, _, root = client
    uploads = root / "uploads"
    key = "12345678-1234-1234-1234-123456789abc"
    target = uploads / "datasets" / key
    target.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(target / "uploaded.jpg")
    monkeypatch.setenv("UPLOAD_ROOT", str(uploads))
    assert c.post("/embedding/image", json={"image_path": "uploaded.jpg", "dataset_key": key}).status_code == 200
    assert c.post("/embedding/image", json={"image_path": "uploaded.jpg"}).status_code == 404
    assert c.post("/embedding/image", json={"image_path": "../../../image.jpg", "dataset_key": key}).status_code == 400
    assert c.post("/embedding/image", json={"image_path": "image.jpg", "dataset_key": "../invalid"}).status_code == 422
    (target / "escape.jpg").symlink_to(root / "image.jpg")
    assert c.post("/embedding/image", json={"image_path": "escape.jpg", "dataset_key": key}).status_code == 400


@pytest.mark.parametrize("cuda,mps,expected",[(True,True,["cuda","mps","cpu"]),(False,True,["mps","cpu"]),(False,False,["cpu"])])
def test_device_preference(cuda,mps,expected):
    with patch.object(torch.cuda,"is_available",return_value=cuda), patch.object(torch.backends.mps,"is_available",return_value=mps):
        assert clip_core.available_devices()==expected


def test_image_stage_timings_are_logged_without_paths(client, caplog):
    c, _, _ = client
    with caplog.at_level("INFO", logger="uvicorn.error"):
        assert c.post("/embedding/image", json={"image_path": "image.jpg"}).status_code == 200
    lines = [r.getMessage() for r in caplog.records if "[CLIP_STAGE]" in r.getMessage()]
    assert len(lines) == 1
    for field in ("lock_wait_ms=", "decode_ms=", "preprocess_ms=", "gpu_ms=", "handler_ms="):
        assert field in lines[0]
    assert "image.jpg" not in lines[0]


def test_split_encode_matches_single_call():
    image = Image.new("RGB", (1600, 900), (40, 80, 120))
    preprocess = lambda crop: torch.full((3, 224, 224), float(crop.size[0]))
    whole = clip_core.encode_image(Model(), preprocess, image, "cpu")
    split = clip_core.encode_crops(Model(), clip_core.preprocess_crops(preprocess, image), "cpu")
    assert torch.equal(whole, split)


class ContentModel:
    """Output depends only on each crop's content, never on its position in the batch, like a real model."""
    calls = []
    def encode_image(self, crops):
        ContentModel.calls.append(len(crops))
        means = crops.float().mean(dim=(1, 2, 3)).cpu()  # the service may pick mps or cuda
        return torch.stack([torch.arange(1, 769, dtype=torch.float32) * (1 + m) + torch.arange(768).float() * m * m for m in means])


def _colored(root, name, color, size=(1600, 900)):
    Image.new("RGB", size, color).save(root / name)
    return name


@pytest.fixture
def content(client):
    c, _, root = client
    service = app.state.clip_service
    names = [_colored(root, f"c{i}.jpg", (20 * i, 255 - 30 * i, 7 * i)) for i in range(5)]
    # Left and right halves differ, so the two crops of one image differ too.
    half = Image.new("RGB", (1600, 900), (10, 10, 10)); half.paste((240, 200, 30), (800, 0, 1600, 900)); half.save(root / "halves.jpg")
    names.append("halves.jpg")
    pre = lambda crop: torch.full((3, 224, 224), sum(crop.resize((1, 1)).getpixel((0, 0))) / 765)
    with patch.object(service, "model", ContentModel()), patch.object(service, "preprocess", pre):
        ContentModel.calls.clear()
        yield c, names, service


def test_batch_matches_single_calls(content):
    c, names, _ = content
    singles = [c.post("/embedding/image", json={"image_path": n}).json()["embedding"] for n in names]
    ContentModel.calls.clear()
    r = c.post("/embedding/images", json={"image_paths": names})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model_name"] == "ViT-L-14-quickgelu/openai" and body["dimension"] == 768 and body["preprocess"] == "lr-square-crop-mean"
    assert [x["image_path"] for x in body["results"]] == names
    for single, item in zip(singles, body["results"]):
        assert item["error"] is None
        assert torch.allclose(torch.tensor(single), torch.tensor(item["embedding"]), atol=1e-6)
    assert ContentModel.calls == [2 * len(names)]  # one forward pass for every crop of every image


def test_batch_chunks_forward_passes_without_changing_vectors(content):
    c, names, service = content
    whole = c.post("/embedding/images", json={"image_paths": names}).json()["results"]
    ContentModel.calls.clear()
    with patch.object(service, "max_crops", 3):  # chunk boundaries split one image's two crops
        chunked = c.post("/embedding/images", json={"image_paths": names}).json()["results"]
    assert ContentModel.calls == [3, 3, 3, 3]
    for a, b in zip(whole, chunked):
        assert torch.allclose(torch.tensor(a["embedding"]), torch.tensor(b["embedding"]), atol=1e-6)


def test_batch_item_errors_keep_other_items(content):
    c, names, _ = content
    r = c.post("/embedding/images", json={"image_paths": [names[0], "missing.jpg", "broken.jpg", "../outside.jpg", names[1]]})
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert [x["error"] and (x["error"]["status"], x["error"]["code"]) for x in results] == [
        None, (404, "IMAGE_NOT_FOUND"), (400, "INVALID_IMAGE"), (400, "INVALID_IMAGE_PATH"), None]
    assert results[0]["embedding"] and results[4]["embedding"] and results[1]["embedding"] is None
    only_bad = c.post("/embedding/images", json={"image_paths": ["missing.jpg"]})
    assert only_bad.status_code == 200 and ContentModel.calls == [4]  # no forward pass for an all-failed batch


def test_batch_limits_and_inference_failure(content):
    c, names, service = content
    assert c.post("/embedding/images", json={"image_paths": []}).status_code == 422
    assert c.post("/embedding/images", json={"image_paths": ["x.jpg"] * 65}).status_code == 422
    assert c.post("/embedding/images", json={"image_paths": names, "dataset_key": "../x"}).status_code == 422
    with patch.object(service.model, "encode_image", side_effect=RuntimeError("private detail")):
        r = c.post("/embedding/images", json={"image_paths": names})
    assert r.status_code == 500 and "private detail" not in r.text


def test_batch_stage_log(content, caplog):
    c, names, _ = content
    with caplog.at_level("INFO", logger="uvicorn.error"):
        assert c.post("/embedding/images", json={"image_paths": names + ["missing.jpg"]}).status_code == 200
    lines = [r.getMessage() for r in caplog.records if "[CLIP_STAGE]" in r.getMessage()]
    assert len(lines) == 1 and "stage=image_embed_batch" in lines[0]
    assert f"images={len(names) + 1} count={len(names)}" in lines[0]
    for field in ("lock_wait_ms=", "decode_ms=", "preprocess_ms=", "gpu_ms=", "handler_ms="):
        assert field in lines[0]
    assert ".jpg" not in lines[0]


def test_batch_crop_math_matches_per_image():
    model = ContentModel()
    crops = [torch.full((2, 3, 224, 224), 0.1), torch.full((1, 3, 224, 224), 0.7), torch.cat([torch.full((1, 3, 224, 224), 0.3), torch.full((1, 3, 224, 224), 0.9)])]
    batch = clip_core.encode_crop_batches(model, crops, "cpu", max_crops=2)
    assert batch.shape == (3, 768)
    for row, one in zip(batch, crops):
        assert torch.allclose(row, clip_core.encode_crops(model, one, "cpu"), atol=1e-6)
    assert clip_core.encode_crop_batches(model, [], "cpu").shape == (0, 768)
