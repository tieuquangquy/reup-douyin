"""In-memory async TTS speech preview jobs (Ops browser Preview).

OmniVoice (and similar local models) may download weights + run inference for
minutes on first use. Holding the Next.js /api rewrite open that long yields an
opaque HTTP 500 — so Preview returns immediately and the UI polls status.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

PreviewStatus = str  # "running" | "succeeded" | "failed" | "cancelled"


@dataclass
class TtsPreviewJobSnapshot:
    workspace_id: str
    status: PreviewStatus
    detail: str = ""
    provider: str = ""
    mime_type: str = "audio/wav"
    duration_seconds: float = 0.0
    audio_base64: str = ""
    warnings: list[str] = field(default_factory=list)
    text: str = ""
    requested_voice_id: str = ""
    resolved_voice_id: str = ""
    ok: bool = False


@dataclass
class _JobRecord:
    snapshot: TtsPreviewJobSnapshot
    cancel: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Bumped on cancel/replace so a stale worker cannot overwrite a newer job.
    generation: int = 0


_REGISTRY_LOCK = threading.Lock()
_JOBS: dict[str, _JobRecord] = {}


def _key(workspace_id: UUID | str) -> str:
    return str(workspace_id)


def _copy_snapshot(snap: TtsPreviewJobSnapshot) -> TtsPreviewJobSnapshot:
    return TtsPreviewJobSnapshot(
        workspace_id=snap.workspace_id,
        status=snap.status,
        detail=snap.detail,
        provider=snap.provider,
        mime_type=snap.mime_type,
        duration_seconds=snap.duration_seconds,
        audio_base64=snap.audio_base64,
        warnings=list(snap.warnings),
        text=snap.text,
        requested_voice_id=snap.requested_voice_id,
        resolved_voice_id=snap.resolved_voice_id,
        ok=snap.ok,
    )


def get_tts_preview_job(workspace_id: UUID | str) -> TtsPreviewJobSnapshot | None:
    with _REGISTRY_LOCK:
        record = _JOBS.get(_key(workspace_id))
        if record is None:
            return None
        with record.lock:
            return _copy_snapshot(record.snapshot)


def cancel_tts_preview_job(workspace_id: UUID | str) -> TtsPreviewJobSnapshot | None:
    """Mark the workspace preview as cancelled and unlock for a new Preview.

    Does not forcibly kill model download / inference threads (Python cannot
    safely interrupt them). The worker ignores results after cancel.
    """
    ws_key = _key(workspace_id)
    with _REGISTRY_LOCK:
        record = _JOBS.get(ws_key)
        if record is None:
            return None
        with record.lock:
            if record.snapshot.status != "running":
                return _copy_snapshot(record.snapshot)
            record.cancel.set()
            record.generation += 1
            record.snapshot.status = "cancelled"
            record.snapshot.ok = False
            record.snapshot.detail = "Preview cancelled"
            record.snapshot.audio_base64 = ""
            record.snapshot.duration_seconds = 0.0
            snap = _copy_snapshot(record.snapshot)
        logger.info("tts_preview_job_cancelled", extra={"workspace_id": ws_key})
        return snap


def start_tts_preview_job(
    *,
    workspace_id: UUID,
    workspace_tts: Any,
    text: str,
    max_chars: int = 280,
    replace_if_running: bool = True,
) -> TtsPreviewJobSnapshot:
    """Start background synthesize.

    By default, a new Preview replaces any in-flight job for the workspace
    (Ops UI timeout left locks that blocked retry with 409).
    """
    ws_key = _key(workspace_id)
    snapshot = TtsPreviewJobSnapshot(
        workspace_id=ws_key,
        status="running",
        detail="TTS preview synthesis is running.",
        provider=str(getattr(workspace_tts, "provider", "") or "").strip(),
        text=(text or "").strip()[: max(20, min(int(max_chars or 280), 500))],
        requested_voice_id=str(getattr(workspace_tts, "voice_id", "") or "").strip(),
        ok=False,
    )

    with _REGISTRY_LOCK:
        existing = _JOBS.get(ws_key)
        if existing is not None:
            with existing.lock:
                if existing.snapshot.status == "running" and not replace_if_running:
                    raise RuntimeError(
                        "A TTS speech preview is already running for this workspace"
                    )
                # Cancel leftover / in-flight worker so it cannot overwrite the new job.
                existing.cancel.set()
                existing.generation += 1
                if existing.snapshot.status == "running":
                    existing.snapshot.status = "cancelled"
                    existing.snapshot.ok = False
                    existing.snapshot.detail = "Preview replaced by a new request"
                    existing.snapshot.audio_base64 = ""
                    logger.info(
                        "tts_preview_job_replaced",
                        extra={"workspace_id": ws_key},
                    )
        record = _JobRecord(snapshot=snapshot, generation=0)
        _JOBS[ws_key] = record
        generation = record.generation

    thread = threading.Thread(
        target=_run_preview_job,
        kwargs={
            "workspace_id": ws_key,
            "workspace_tts": workspace_tts,
            "text": text,
            "max_chars": max_chars,
            "generation": generation,
        },
        name=f"tts-preview-{ws_key[:8]}",
        daemon=True,
    )
    thread.start()
    return get_tts_preview_job(workspace_id) or snapshot


def _run_preview_job(
    *,
    workspace_id: str,
    workspace_tts: Any,
    text: str,
    max_chars: int,
    generation: int,
) -> None:
    from src.tts_pipeline.errors import TtsPipelineError
    from src.tts_pipeline.preview import PreviewTtsError, preview_tts_speech

    record = _JOBS.get(workspace_id)
    if record is None:
        return
    if record.cancel.is_set() or record.generation != generation:
        return

    try:
        result = preview_tts_speech(
            workspace_tts=workspace_tts,
            text=text,
            max_chars=max_chars,
        )
        with record.lock:
            if record.cancel.is_set() or record.generation != generation:
                return
            # Registry may have been replaced by a newer Preview after cancel.
            current = _JOBS.get(workspace_id)
            if current is not record:
                return
            record.snapshot.status = "succeeded"
            record.snapshot.ok = True
            record.snapshot.detail = str(result.get("detail") or "Preview ready")
            record.snapshot.provider = str(result.get("provider") or "")
            record.snapshot.mime_type = str(result.get("mime_type") or "audio/wav")
            record.snapshot.duration_seconds = float(result.get("duration_seconds") or 0.0)
            record.snapshot.audio_base64 = str(result.get("audio_base64") or "")
            record.snapshot.warnings = list(result.get("warnings") or [])
            record.snapshot.text = str(result.get("text") or "")
            record.snapshot.requested_voice_id = str(result.get("requested_voice_id") or "")
            record.snapshot.resolved_voice_id = str(result.get("resolved_voice_id") or "")
        logger.info(
            "tts_preview_job_ok",
            extra={"workspace_id": workspace_id, "provider": record.snapshot.provider},
        )
    except (PreviewTtsError, TtsPipelineError) as exc:
        message = getattr(exc, "message", None) or str(exc)
        with record.lock:
            if record.cancel.is_set() or record.generation != generation:
                return
            if _JOBS.get(workspace_id) is not record:
                return
            record.snapshot.status = "failed"
            record.snapshot.ok = False
            record.snapshot.detail = message
            record.snapshot.audio_base64 = ""
        logger.warning(
            "tts_preview_job_failed",
            extra={"workspace_id": workspace_id, "error": message[:300]},
        )
    except Exception as exc:
        message = f"TTS preview failed: {exc}"
        with record.lock:
            if record.cancel.is_set() or record.generation != generation:
                return
            if _JOBS.get(workspace_id) is not record:
                return
            record.snapshot.status = "failed"
            record.snapshot.ok = False
            record.snapshot.detail = message
            record.snapshot.audio_base64 = ""
        logger.exception("tts_preview_job_error", extra={"workspace_id": workspace_id})


def reset_tts_preview_jobs_for_tests() -> None:
    with _REGISTRY_LOCK:
        for record in _JOBS.values():
            record.cancel.set()
        _JOBS.clear()
