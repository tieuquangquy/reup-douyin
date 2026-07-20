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
# Từ repo root (Windows / Linux) — profile tiết kiệm (min-instances 0):
python deploy/hf-paddle-ocr/auto_deploy.py

# Session Analyze OCR hàng loạt — giữ 1 instance ấm (tránh cold start):
python deploy/hf-paddle-ocr/auto_deploy.py --warm

# Hết session batch — hạ lại scale-to-zero:
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
  --region asia-southeast1 \
  --platform managed \
  --memory 8Gi \
  --cpu 4 \
  --concurrency 2 \
  --min-instances 0 \
  --max-instances 5 \
  --allow-unauthenticated \
  --port 8080 \
  --timeout 300
```

### Profile batch (giữ ấm)

Khi chạy nhiều job `ANALYZE_OCR` liên tiếp, dùng `--min-instances 1` (hoặc `auto_deploy.py --warm`):

```bash
gcloud run deploy paddle-ocr-api \
  --source . \
  --region asia-southeast1 \
  --platform managed \
  --memory 8Gi \
  --cpu 4 \
  --concurrency 2 \
  --min-instances 1 \
  --max-instances 5 \
  --allow-unauthenticated \
  --port 8080 \
  --timeout 300
```

Hết session → redeploy với `--min-instances 0` để tiết kiệm idle.

### Giải thích flags quan trọng

| Flag | Ý nghĩa |
|------|---------|
| `--region asia-southeast1` | Singapore — gần VN hơn `us-central1` (RTT thấp hơn; chất lượng OCR không đổi) |
| `--source .` | Cloud Build build image từ Dockerfile thư mục hiện tại |
| `--memory 8Gi` | **Bắt buộc ≥8Gi** — PaddleOCR vượt ~4.2Gi → OOM/503 nếu chỉ 4Gi |
| `--cpu 4` | 4 vCPU — đủ cho 1–2 predict nặng/instance |
| `--concurrency 2` | Tối đa **2 request đồng thời / instance** (Paddle CPU-bound) |
| `--min-instances 0` | Scale to Zero — tiết kiệm idle; cold start lần đầu chậm |
| `--min-instances 1` | **Batch session:** giữ instance ấm |
| `--max-instances 5` | Trần scale-out trong quota ~20 vCPU + ~40Gi (5×4CPU/8Gi) |
| `--allow-unauthenticated` | Public URL, không cần identity token |
| `--port 8080` | Khớp `EXPOSE` / `CMD` trong Dockerfile |
| `--timeout 300` | Request timeout 300s — cold start + download model + OCR |

**Quota note:** Muốn `max-instances 10` với **8Gi** phải xin tăng `MemAllocPerProjectRegion` (+ CPU). Đừng hạ memory xuống 4Gi chỉ để tăng max — sẽ OOM.

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
`503`). Model loads on first `/predict`. API client warmups `/health` + predict, timeout
120s/request, retries 502/503/504 (tenacity).

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

Client Phase 2 (tối ưu hiện tại):

- Full-frame OCR + preprocess local: max edge **1280px**, JPEG **q80** (BytesIO)
- `asyncio.Semaphore` default **8** (`OCR_ASYNC_CONCURRENCY`) — khớp scale-out `max-instances 5` × `--concurrency 2`
- `ClientTimeout(total=300)` + tenacity retry (timeout / 502 / 503 / 504)
- Optional: `OCR_PREPROCESS_MAX_EDGE=720` (nhanh hơn) hoặc `960` (nhẹ hơn mặc định)
- Optional: `OCR_ASYNC_CONCURRENCY=2` để hạ song song (tiết kiệm / debug)

## Ghi chú chi phí / throughput batch

- Cold start lần đầu sau idle có thể chậm (download/load model).
- **Idle / tiết kiệm:** `--min-instances 0` + client retry.
- **Analyze OCR hàng loạt:** `python deploy/hf-paddle-ocr/auto_deploy.py --warm` (`--min-instances 1`, **8Gi / 4 CPU / max 5**). Hết session: deploy lại không `--warm`.
- Đừng hạ memory xuống 4Gi để tăng `max-instances` — PaddleOCR OOM → `OCR HTTP 503`. Muốn 10×8Gi: xin tăng quota region trước.
- Phase sau (ngoài scope): GPU Cloud Run, LaMa inpaint, hoặc queue job (HTTP dài → async).
