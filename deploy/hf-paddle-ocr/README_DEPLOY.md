# Deploy PaddleOCR API lên Google Cloud Run

Thư mục này chứa `app.py`, `requirements.txt`, `Dockerfile` (port **8080**).

Hugging Face Spaces Docker miễn phí đã bị khóa — dùng **Google Cloud Run** (scale-to-zero).

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

Script đọc flags từ file này, chạy `gcloud run deploy`, extract URL, ghi repo-root `.env`:

```bash
# Từ repo root (Windows / Linux):
python deploy/hf-paddle-ocr/auto_deploy.py

# Dry-run (không gọi gcloud):
python deploy/hf-paddle-ocr/auto_deploy.py --dry-run

# Chỉ lấy URL service đã deploy sẵn + cập nhật .env:
python deploy/hf-paddle-ocr/auto_deploy.py --skip-deploy
```

Kết quả: `OCR_ENDPOINT_URL=https://…a.run.app/predict` trong `.env` ở thư mục gốc repo.

## Deploy thủ công từ thư mục hiện tại

Chạy **trong** thư mục chứa `Dockerfile` (ví dụ `deploy/hf-paddle-ocr`):

```bash
cd deploy/hf-paddle-ocr

gcloud run deploy paddle-ocr-api \
  --source . \
  --region us-central1 \
  --platform managed \
  --memory 4Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --allow-unauthenticated \
  --port 8080 \
  --timeout 300
```

### Giải thích flags quan trọng

| Flag | Ý nghĩa |
|------|---------|
| `--source .` | Cloud Build build image từ Dockerfile thư mục hiện tại |
| `--memory 4Gi` | 4GB RAM — tránh OOM khi load PaddleOCR / PP-OCR models |
| `--allow-unauthenticated` | Public URL, không cần identity token |
| `--min-instances 0` | Scale to Zero — tiết kiệm chi phí khi idle (client retry 503) |
| `--port 8080` | Khớp `EXPOSE` / `CMD` trong Dockerfile |
| `--timeout 300` | Request timeout 300s — cold start + download model + OCR |

Sau khi deploy xong, CLI in ra URL dạng:

```text
https://paddle-ocr-api-xxxxx-xx.a.run.app
```

## Paddle 3.3.x / oneDNN

Cloud Run CPU builds can hit `ConvertPirAttribute2RuntimeAttribute` / `onednn_instruction`
on `/predict`. The image sets `FLAGS_use_mkldnn=0` (and related) and `app.py` passes
`enable_mkldnn=False` — same fix as local `ocr_pipeline` providers. Redeploy after
changing `app.py` / `Dockerfile`.

**Cold start:** do **not** preload Paddle on container startup (blocks readiness → client
`503`). Model loads on first `/predict`. API client uses long HTTP timeout (300s) and
retries 503 with multi-second backoff (`RetryingOcrProvider`).

## Kiểm tra

```bash
# Health
curl "https://YOUR_SERVICE_URL/health"

# OCR (upload ảnh)
curl -X POST "https://YOUR_SERVICE_URL/predict" -F "file=@frame.jpg"
```

## Nối Phase 2 client

```text
OCR_ENDPOINT_URL=https://YOUR_SERVICE_URL/predict
```

## Ghi chú chi phí / throughput batch

- Cold start lần đầu sau idle có thể chậm (download/load model).
- `--min-instances 0` tiết kiệm idle; client retry 502/503/504 (15s × 3).
- **Khi chạy Analyze OCR hàng loạt (SLL):** tạm thời redeploy `--min-instances 1` để giữ instance ấm — tránh ~1 phút/frame vì cold/retry. Hết session hạ lại `--min-instances 0`.
- Client Phase 2 mặc định: crop bottom band + `OCR_HTTP_CONCURRENCY=4` + probe stride 2 (early-exit khi không thấy hard-sub).
