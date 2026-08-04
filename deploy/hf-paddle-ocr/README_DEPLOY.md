# Deploy PaddleOCR-VL-1.6 API lên Google Cloud Run

Thư mục này chứa `app.py`, `requirements.txt`, `Dockerfile` (port **8080**).

Image cài **PaddleOCR từ GitHub** (`git+https://github.com/PaddlePaddle/PaddleOCR.git` + `doc-parser`) và chạy engine **PaddleOCR-VL-1.6** (`pipeline_version=v1.6`). Contract HTTP giữ nguyên: `POST /predict`.

> **Region:** mặc định **`us-central1`** (quota memory cao hơn). `asia-southeast1` thường không đủ `MemAllocPerProjectRegion` cho 16Gi.

## Điều kiện trước khi chạy

1. Đã cài [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`).
2. Đăng nhập và chọn project:

```bash
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID
```

3. Bật API cần thiết (một lần):

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

## Auto-deploy (khuyến nghị)

```bash
# Từ repo root — profile tiết kiệm (min-instances 0):
python deploy/hf-paddle-ocr/auto_deploy.py

# Session Analyze OCR hàng loạt — giữ 1 instance ấm:
python deploy/hf-paddle-ocr/auto_deploy.py --warm

# Dry-run:
python deploy/hf-paddle-ocr/auto_deploy.py --dry-run
```

Kết quả: `OCR_ENDPOINT_URL=https://…a.run.app/predict` trong `.env` (root / api / worker).

## Deploy thủ công

```bash
cd deploy/hf-paddle-ocr

gcloud run deploy paddle-ocr-vl16 \
  --source . \
  --region us-central1 \
  --platform managed \
  --memory 16Gi \
  --cpu 4 \
  --concurrency 1 \
  --min-instances 0 \
  --max-instances 1 \
  --allow-unauthenticated \
  --port 8080 \
  --timeout 3600 \
  --set-env-vars OCR_PADDLE_ENGINE=vl16,OCR_PADDLE_NO_FALLBACK=1,OCR_PADDLE_VL_DEVICE=cpu,OCR_PADDLE_VL_SKIP_PROBE=1
```

### Profile batch (giữ ấm)

```bash
gcloud run deploy paddle-ocr-vl16 \
  --source . \
  --region us-central1 \
  --platform managed \
  --memory 16Gi \
  --cpu 4 \
  --concurrency 1 \
  --min-instances 1 \
  --max-instances 1 \
  --allow-unauthenticated \
  --port 8080 \
  --timeout 3600 \
  --set-env-vars OCR_PADDLE_ENGINE=vl16,OCR_PADDLE_NO_FALLBACK=1,OCR_PADDLE_VL_DEVICE=cpu,OCR_PADDLE_VL_SKIP_PROBE=1
```

### Giải thích flags quan trọng

| Flag | Ý nghĩa |
|------|---------|
| `--region us-central1` | Quota memory thường đủ cho VL 16Gi (asia-southeast1 dễ bị `MemAllocPerProjectRegion`) |
| `--source .` | Cloud Build từ Dockerfile; cài PaddleOCR từ GitHub |
| `--memory 16Gi` | **VL-1.6 cần ≥16Gi** |
| `--cpu 4` | 4 vCPU / 1 predict VL |
| `--concurrency 1` | 1 request / instance |
| `--max-instances 1` | Khớp soft quota memory khi 16Gi |
| `--timeout 3600` | Cold start + OCR VL có thể rất lâu trên CPU |
| `--set-env-vars …ENGINE=vl16,NO_FALLBACK=1,SKIP_PROBE=1` | Ép VL-1.6; không fallback classic; không probe đôi (tiết kiệm RAM) |

## Bake weights (khuyến nghị)

Để tránh tải ~1.8GB `model.safetensors` lúc cold start, copy weights vào `models/PaddleOCR-VL-1.6/` trước khi deploy (Dockerfile sẽ nướng vào image):

```powershell
docker cp paddle-ocr-local:/root/.paddlex/official_models/PaddleOCR-VL-1.6/. deploy/hf-paddle-ocr/models/PaddleOCR-VL-1.6/
```

File `*.safetensors` không commit git (xem `deploy/hf-paddle-ocr/.gitignore`) nhưng **phải** có mặt khi `gcloud run deploy --source`.

## Kiểm tra đúng VL-1.6

```bash
curl "https://YOUR_SERVICE_URL/health"
# Sau predict đầu: active=vl16, fallback=false, reason=vl16_ok

curl -X POST "https://YOUR_SERVICE_URL/predict" -F "file=@frame.jpg"
```

## Nối Phase 2 client

```text
OCR_ENDPOINT_URL=https://YOUR_SERVICE_URL/predict
OCR_HTTP_TIMEOUT_SECONDS=900
OCR_ASYNC_CONCURRENCY=1
```

Restart API/worker sau khi đổi URL.
