import logging
import os
from pathlib import Path

# Must run before JobRunner/OCR imports paddleocr (Paddle 3.3.x oneDNN/PIR crash on Windows).
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_onednn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"


def _load_worker_dotenv() -> None:
    """Put apps/worker/.env into os.environ (pydantic Settings alone ignores OCR_*)."""
    worker_root = Path(__file__).resolve().parents[1]
    env_path = worker_root / ".env"
    if not env_path.is_file():
        return
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


_load_worker_dotenv()

try:
    from .handlers.mock_handlers import build_mock_handler_registry
    from .instance_lock import worker_instance_lock
    from .runtime import LocalPollingWorker
except ImportError:  # Allows `python src/main.py` from apps/worker during local dev.
    from handlers.mock_handlers import build_mock_handler_registry
    from instance_lock import worker_instance_lock
    from runtime import LocalPollingWorker


def resolve_worker_id() -> str:
    """Stable id for this process; crash recovery requeues jobs by ``locked_by``."""
    configured = (os.getenv("WORKER_ID") or "").strip()
    if configured:
        return configured
    return f"local-worker-{os.getpid()}"


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    worker_id = resolve_worker_id()
    poll_interval = float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "5"))
    redis_url = os.getenv("REDIS_URL")
    redis_queue_name = os.getenv("WORKER_REDIS_QUEUE_NAME", "reup-douyin:jobs")
    worker = LocalPollingWorker(
        worker_id=worker_id,
        poll_interval_seconds=poll_interval,
        handlers=build_mock_handler_registry(),
        redis_url=redis_url,
        redis_queue_name=redis_queue_name,
    )
    with worker_instance_lock(worker_id):
        worker.run_forever()


if __name__ == "__main__":
    main()
