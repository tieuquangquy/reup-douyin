import logging
import os

# Must run before JobRunner/OCR imports paddleocr (Paddle 3.3.x oneDNN/PIR crash on Windows).
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_onednn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

try:
    from .handlers.mock_handlers import build_mock_handler_registry
    from .runtime import LocalPollingWorker
except ImportError:  # Allows `python src/main.py` from apps/worker during local dev.
    from handlers.mock_handlers import build_mock_handler_registry
    from runtime import LocalPollingWorker


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    worker_id = os.getenv("WORKER_ID", "local-worker-1")
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
    worker.run_forever()


if __name__ == "__main__":
    main()
