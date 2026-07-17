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

## Build & chạy local

```powershell
cd deploy\hf-paddle-ocr
docker build -t paddle-ocr-api .
docker run --rm -p 8080:8080 paddle-ocr-api
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

## Health

```text
GET /health → {"status":"ok"}
```
