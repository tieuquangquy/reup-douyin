"""Process-local lifecycle for optional local audio models.

The API/worker normally keeps one Python process alive for many jobs.  Loading
Silero and FunASR for every video defeats that model and can exhaust VRAM when
two requests arrive together.  This module deliberately owns only model
lifecycle; providers still own inference policy and error handling.
"""

from __future__ import annotations

import logging
import multiprocessing
import time
import traceback
from collections.abc import Callable
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_silero_lock = Lock()
_silero_model: Any | None = None
_funasr_lock = Lock()
_funasr_models: dict[tuple[str, str], Any] = {}
_funasr_worker_lock = Lock()
_funasr_worker_process: Any | None = None
_funasr_worker_connection: Any | None = None


def get_silero_model() -> Any:
    global _silero_model
    if _silero_model is None:
        with _silero_lock:
            if _silero_model is None:
                from silero_vad import load_silero_vad  # type: ignore

                logger.info("audio_model_loading", extra={"model": "silero_vad"})
                _silero_model = load_silero_vad()
                logger.info("audio_model_ready", extra={"model": "silero_vad"})
    return _silero_model


def get_funasr_model(model_name: str = "paraformer-zh", device: str = "") -> Any:
    key = (str(model_name), str(device or "auto"))
    model = _funasr_models.get(key)
    if model is not None:
        return model
    with _funasr_lock:
        model = _funasr_models.get(key)
        if model is None:
            from funasr import AutoModel  # type: ignore

            logger.info(
                "audio_model_loading",
                extra={"model": model_name, "device": device or "auto"},
            )
            kwargs: dict[str, Any] = {"model": model_name, "disable_update": True}
            if device and device != "auto":
                kwargs["device"] = device
            model = AutoModel(**kwargs)
            _funasr_models[key] = model
            logger.info(
                "audio_model_ready",
                extra={"model": model_name, "device": device or "auto"},
            )
    return model


def _funasr_worker_main(connection: Any, model_name: str, device: str) -> None:
    """Long-lived, killable inference boundary used by the production provider."""
    try:
        model = get_funasr_model(model_name, device)
        connection.send(("ready", None))
        while True:
            command = connection.recv()
            if command is None:
                return
            request_id, audio_path = command
            try:
                raw = model.generate(input=audio_path)
                connection.send(("result", request_id, raw))
            except BaseException as exc:  # process boundary must return an actionable error
                connection.send(
                    (
                        "error",
                        request_id,
                        type(exc).__name__,
                        str(exc)[:800],
                        traceback.format_exc(limit=8),
                    )
                )
    except BaseException as exc:
        try:
            connection.send(("startup_error", type(exc).__name__, str(exc)[:800]))
        except Exception:
            pass
    finally:
        try:
            connection.close()
        except Exception:
            pass


def generate_funasr_killable(
    audio_path: str,
    *,
    model_name: str = "paraformer-zh",
    device: str = "auto",
    timeout_seconds: float,
    warmup_timeout_seconds: float | None = None,
    on_tick: Callable[[], None] | None = None,
    tick_seconds: float = 15.0,
) -> Any:
    """Generate with a persistent child process that is terminated on timeout.

    A normal thread timeout only stops waiting; it leaves the inference thread
    and its VRAM alive.  The isolated worker survives successful requests (warm
    model) but can be terminated and recreated after a hard timeout.
    """
    global _funasr_worker_process, _funasr_worker_connection
    with _funasr_worker_lock:
        _ensure_funasr_worker(
            model_name=model_name,
            device=device,
            timeout_seconds=(
                float(warmup_timeout_seconds)
                if warmup_timeout_seconds is not None
                else timeout_seconds
            ),
        )
        process = _funasr_worker_process
        connection = _funasr_worker_connection
        if process is None or connection is None:
            raise RuntimeError("funasr_worker_not_started")
        request_id = f"{time.monotonic_ns()}"
        connection.send((request_id, str(audio_path)))
        deadline = time.monotonic() + max(0.1, float(timeout_seconds))
        poll = max(0.05, float(tick_seconds or 15.0))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop_funasr_worker()
                raise TimeoutError(f"funasr_timed_out_after_{timeout_seconds:.0f}s")
            if connection.poll(min(poll, remaining)):
                message = connection.recv()
                kind = message[0] if isinstance(message, tuple) and message else "invalid"
                if kind == "result" and message[1] == request_id:
                    return message[2]
                if kind == "error" and message[1] == request_id:
                    raise RuntimeError(f"funasr_worker_{message[2]}:{message[3]}")
                raise RuntimeError(f"funasr_worker_protocol_error:{kind}")
            if not process.is_alive():
                _stop_funasr_worker()
                raise RuntimeError("funasr_worker_exited")
            if on_tick is not None:
                on_tick()


def _ensure_funasr_worker(*, model_name: str, device: str, timeout_seconds: float) -> None:
    global _funasr_worker_process, _funasr_worker_connection
    if _funasr_worker_process is not None and _funasr_worker_process.is_alive():
        return
    _stop_funasr_worker()
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=True)
    process = context.Process(
        target=_funasr_worker_main,
        args=(child, model_name, device),
        name="reup-funasr",
        daemon=True,
    )
    process.start()
    child.close()
    _funasr_worker_process = process
    _funasr_worker_connection = parent
    startup_timeout = max(30.0, float(timeout_seconds))
    if not parent.poll(startup_timeout):
        _stop_funasr_worker()
        raise TimeoutError(f"funasr_model_warmup_timed_out_after_{startup_timeout:.0f}s")
    message = parent.recv()
    if not isinstance(message, tuple) or not message or message[0] != "ready":
        _stop_funasr_worker()
        detail = message[2] if isinstance(message, tuple) and len(message) > 2 else str(message)
        raise RuntimeError(f"funasr_worker_startup_failed:{detail}")


def _stop_funasr_worker() -> None:
    global _funasr_worker_process, _funasr_worker_connection
    connection = _funasr_worker_connection
    process = _funasr_worker_process
    _funasr_worker_connection = None
    _funasr_worker_process = None
    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass
    if process is not None and process.is_alive():
        process.terminate()
        process.join(timeout=5.0)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=2.0)


def clear_audio_model_cache() -> None:
    """Test/maintenance hook; production callers should not call per request."""
    global _silero_model
    with _silero_lock:
        _silero_model = None
    with _funasr_lock:
        _funasr_models.clear()
    _stop_funasr_worker()
