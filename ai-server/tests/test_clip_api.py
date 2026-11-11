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
