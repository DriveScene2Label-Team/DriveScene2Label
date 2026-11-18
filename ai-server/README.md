# DriveScene2Label AI 서버 — CLIP

Spring은 DB 저장/검색과 job을 관리합니다. AI 서버는 CLIP 벡터와 VESPA 예측 JSON을 생성하며 DB에는 접근하지 않습니다. VESPA는 subprocess wrapper로 연결되며 별도 VESPA 환경/데이터 설정이 필요합니다. [VESPA 실행 안내](VESPA.md)를 참고하세요. 원격 Slurm 클러스터 실행은 [VESPA_Seraph.md](VESPA_Seraph.md)를 참고하세요.

Rerun `.rrd` recording은 `POST /recordings`가 별도 subprocess exporter(rerun-sdk 0.38.1)로 생성합니다. [Recording exporter](RECORDING.md)를 참고하세요.

기능별 준비 상태는 `GET /capabilities`(Spring 내부용, refresh=true일 때만 VESPA local import/SSH 읽기 전용 확인), 프로세스 생존은 `GET /livez`입니다. CLIP 로딩이 실패해도 서버는 계속 떠서 recording/VESPA를 제공하고 `/health`는 503을 유지합니다(`AI_REQUIRE_CLIP=true`면 기존처럼 시작 실패). 계약은 [README_API 11장](../README_API.md)을 참고하세요.

routers=Controller, services=계산 Service, schemas=Request/Response DTO입니다. CLIP 계산은 기존 embedding/embed_images.py에서 embedding/clip_core.py로 추출했으며 기존 CLI와 FastAPI가 함께 재사용합니다. CLI의 DB 저장/검색 코드는 그대로 유지하고 AI 서버는 해당 CLI나 DB driver를 import하지 않습니다. repo 전체를 유지해야 공유 모듈 import가 됩니다.

Docker 전체 실행은 [프로젝트 README](../README.md)를 우선 참고하세요. 컨테이너에는 VESPA 별도 Python 환경이 포함됩니다.

## 설치 및 실행 (프로젝트 루트, WSL/Ubuntu)

```bash
cd ai-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CLIP_IMAGE_ROOT=/home/hyuksu/Cap_Project_Data/v1.0-mini
export HF_HOME="$(pwd)/../.local/clip-model-cache"
export TORCH_HOME="$(pwd)/../.local/torch-model-cache"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

모델: ViT-L-14-quickgelu, pretrained=openai, 768차원. 첫 실행에 가중치를 내려받을 수 있습니다. 모델 로딩 실패 시 서버 startup을 실패시킵니다. FastAPI lifespan에서 worker당 1회 로딩합니다. 요청마다 재로딩하지 않습니다. workers/reload를 늘리면 프로세스별 별도 모델이 생기므로 GPU 서버에서는 workers=1을 권장합니다. 자동 장치 선택은 기존처럼 사용 가능한 cuda -> mps -> cpu 순서이며 GPU 실행 오류를 CPU로 숨기지는 않습니다.

이미지 입력은 JSON 경로 방식으로 먼저 구현했습니다. image_path는 AI 서버의 CLIP_IMAGE_ROOT 안의 상대 경로입니다. Spring/사용자 PC의 경로가 아니라 AI 서버에서 접근 가능한 파일이어야 합니다. 절대경로·root 밖 이동·외부 symlink를 거부합니다. 파일 업로드 endpoint는 아직 없습니다.

## curl

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/embedding/text \
  -H 'Content-Type: application/json' \
  -d '{"text":"rainy night road"}'
curl -X POST http://127.0.0.1:8000/embedding/image \
  -H 'Content-Type: application/json' \
  -d '{"image_path":"samples/CAM_FRONT/your-image.jpg"}'
# Optional: use the existing center-crop mode
curl -X POST http://127.0.0.1:8000/embedding/image \
  -H 'Content-Type: application/json' \
  -d '{"image_path":"samples/CAM_FRONT/your-image.jpg","preprocess":"openclip-eval-224-centercrop"}'
```

이미지 예시 경로는 실제 파일 상대 경로로 바꾸세요. Swagger: http://127.0.0.1:8000/docs

응답: model_name="ViT-L-14-quickgelu/openai", dimension=768, embedding=[768 floats], preprocess. 이미지 기본 전처리는 기존 lr-square-crop-mean입니다: RGB 변환, 좌/우 정사각 crop, open_clip eval transform, crop별 L2 정규화 -> 평균 -> 다시 L2 정규화. 텍스트는 기존 tokenizer/encode_text/L2 정규화 사용하며 preprocess="clip-text-tokenizer"를 표시합니다. 이 텍스트 표시값은 image_embedding.preprocess 저장값이 아닙니다. Spring 검색은 동일 모델 및 원하는 이미지 preprocess에 제한해야 합니다. CLIP tokenizer의 기존 context-length/truncation 정책을 유지합니다.

성공 응답은 finite 768차원 unit vector인지 검사합니다. 빈 텍스트/잘못된 schema=422, 허용되지 않는 경로=400, 없는 파일=404, 손상된 이미지=400, 모델 미준비=503, 추론 실패=500. 응답에 내부 경로/stack trace를 노출하지 않고 서버 로그에 추론 예외를 기록합니다. 구버전 POST /embedding은 /embedding/text 또는 /embedding/image로 교체했습니다.

### 배치 이미지 임베딩 (2026-11-18)

`POST /embedding/images`는 `image_paths` 1~64개를 한 번에 받아 순서대로 `results`를 돌려줍니다. 이미지마다 디코딩·crop 전처리를 한 뒤, 모든 crop을 모델에 함께 넣고(`clip_core.encode_crop_batches`, forward 한 번에 최대 `CLIP_MAX_CROPS_PER_FORWARD`=128 crop) 이미지별로 crop 평균·L2 정규화합니다. 오프라인 CLI(`embed_images.py --batch-size`)와 같은 수학이고, 실제 가중치로 확인한 결과 단일 호출 벡터와의 최소 cosine은 0.99999982입니다(v1.0-mini keyframe 256장, Apple M5 MPS). 경로·이미지 오류는 해당 항목의 `error`에만 담고 나머지는 계속 처리하며, 모델 실행 실패는 호출 전체 500입니다. 디코딩·전처리는 모델 lock 밖에서, 모델 실행만 lock 안에서 합니다. 로그는 호출마다 `[CLIP_STAGE] stage=image_embed_batch images= count=`와 단계별 합계 ms입니다. Spring 검색 인덱싱은 `EMBEDDING_INDEX_BATCH_ENABLED=true`(C2, 기본 false)일 때 이 경로를 쓰고, 이 경로가 없는 구버전 AI 서버(404)에는 이미지별 `/embedding/image`로 되돌아갑니다.

비교 측정: `scripts/clip_batch_benchmark.py`(HTTP 없이 같은 코드 경로), `scripts/clip_http_benchmark.py`(실행 중인 AI 서버에 단일/배치 호출).

## 테스트

```bash
pip install pytest httpx
python -m pytest tests -q
```

테스트는 모델 adapter를 대체하여 네트워크/가중치 없이 실제 lifespan과 API, 전처리 수학, L2 정규화, 경로/이미지 오류를 검증합니다. 2026-10-03 검증: AI API 테스트 7개 및 기존 embedding 테스트 38개 통과. 실제 OpenAI CLIP 가중치를 CUDA에 로드한 service 추론과 실제 lifespan을 거친 /embedding/text 및 /embedding/image HTTP 200, 768차원 응답도 확인했습니다. 기존 reference.npz와의 cosine 비교는 별도 검증입니다.

FastAPI lifespan 참고: https://fastapi.tiangolo.com/advanced/events/
