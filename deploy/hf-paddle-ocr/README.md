# PaddleOCR API (Google Cloud Run)

FastAPI bọc PaddleOCR (`lang=ch`), Docker, cổng **8080**.

> Hugging Face Spaces Docker miễn phí đã khóa — xem hướng dẫn deploy Cloud Run trong [`README_DEPLOY.md`](README_DEPLOY.md).

## Files

| File | Vai trò |
|------|---------|
| `app.py` | FastAPI + `POST /predict` |
| `requirements.txt` | deps + **opencv-python-headless** |
| `Dockerfile` | `python:3.9-slim`, `EXPOSE 8080` |
| `README_DEPLOY.md` | lệnh `gcloud run deploy` |

## Engines

| Env | Meaning |
|-----|---------|
| `OCR_PADDLE_ENGINE=auto` | **Default.** classic if MemTotal &lt; 20 GiB; else try VL-1.6 |
| `OCR_PADDLE_ENGINE=vl16` | Force try **PaddleOCR-VL-1.6**; on failure → classic |
| `OCR_PADDLE_ENGINE=classic` | Force classic PP-OCR only |
| `OCR_PADDLE_VL_DEVICE=cpu` | Device for VL (`gpu` only with NVIDIA container runtime) |
| `OCR_PADDLE_VL_INPROCESS=1` | Override the **≥20 GiB RAM** guard |

`requirements.txt` installs `paddleocr[doc-parser]` from GitHub so VL-1.6 APIs are available.
`GET /health` reports requested / resolved / active / fallback / ram_gb / reason.

On this operator PC (Docker MemTotal ≈ 7.7 GiB), **auto → classic** so Analyze works without manual steps. Raise Docker RAM ≥ 20 GiB later to unlock VL.

## Build & chạy local

```powershell
# One-shot: build (if needed) + run detached on :8080
powershell -ExecutionPolicy Bypass -File deploy/hf-paddle-ocr/run_local.ps1

# Or manual:
cd deploy\hf-paddle-ocr
docker build -t paddle-ocr-api .
docker run --rm -p 8080:8080 paddle-ocr-api
```

Point the app at local OCR (keep Cloud URL commented in `.env` to switch back):

```text
OCR_ENDPOINT_URL=http://127.0.0.1:8080/predict
```

```powershell
curl -X POST "http://127.0.0.1:8080/predict" -F "file=@frame.jpg"
```

Response mẫu:

```json
[
  {
    "bbox": [[10, 100], [200, 100], [200, 140], [10, 140]],
    "text": "硬字幕",
    "score": 0.97
  }
]
```

Parser (v1.0.1): unwraps PaddleOCR 3.x `Result.json` **property** and nested `{"res": {...}}` (older builds returned HTTP 200 with `[]`).

## Health

```text
GET /health → {"status":"ok"}
```
