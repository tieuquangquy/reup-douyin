FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps/worker:/app/apps/api

WORKDIR /app

COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml
COPY apps/worker/pyproject.toml /app/apps/worker/pyproject.toml

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /app/apps/api \
    && pip install --no-cache-dir /app/apps/worker

COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker

WORKDIR /app/apps/worker

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

CMD ["python", "-m", "src.main"]
