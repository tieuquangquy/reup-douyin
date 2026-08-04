# =============================================================================
# Dockerfile — PaddleOCR API cho Google Cloud Run
# Build local:
#   docker build -t paddle-ocr-api .
# Chạy local:
#   docker run --rm -p 8080:8080 paddle-ocr-api
# =============================================================================

# Base slim (Bookworm) — tránh Debian Trixie thiếu libgl1-mesa-glx.
FROM python:3.9-slim-bookworm

# Không ghi .pyc; log ra stdout ngay; tắt oneDNN/MKLDNN (Paddle 3.3 PIR crash).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLAGS_use_mkldnn=0 \
    FLAGS_onednn=0 \
    FLAGS_enable_pir_api=0 \
    FLAGS_enable_pir_in_executor=0 \
    PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=0 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    OCR_PADDLE_ENGINE=vl16 \
    OCR_PADDLE_NO_FALLBACK=1 \
    OCR_PADDLE_VL_DEVICE=cpu \
    OCR_PADDLE_VL_SKIP_PROBE=1

# Thư mục làm việc trong container.
WORKDIR /app

# Thư viện hệ thống Linux cần cho OpenCV headless + Paddle (không có GUI).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Sao chép dependency list trước (tận dụng Docker layer cache).
COPY requirements.txt /app/requirements.txt

# Cài Python packages; --no-cache-dir giữ image gọn.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# Sao chép mã nguồn FastAPI.
COPY app.py /app/app.py

# Optional bake of PaddleOCR-VL-1.6 weights (skip download on Cloud Run cold start).
# Host path: deploy/hf-paddle-ocr/models/PaddleOCR-VL-1.6/
COPY models/ /tmp/vl_models/
RUN mkdir -p /root/.paddlex/official_models \
    && if [ -f /tmp/vl_models/PaddleOCR-VL-1.6/inference.yml ]; then \
         cp -a /tmp/vl_models/PaddleOCR-VL-1.6 /root/.paddlex/official_models/PaddleOCR-VL-1.6 ; \
         echo "Baked PaddleOCR-VL-1.6 weights into image" ; \
       else \
         echo "No baked VL weights; model will download on first /predict" ; \
       fi \
    && rm -rf /tmp/vl_models

# Google Cloud Run mặc định route tới cổng 8080.
EXPOSE 8080

# Khởi chạy Uvicorn trên 0.0.0.0:8080 (Cloud Run).
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
