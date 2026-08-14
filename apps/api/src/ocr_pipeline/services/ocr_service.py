"""Hard-sub OCR orchestration: sample → detect → group → persist → optional clean."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, selectinload

from src.core.settings import get_settings
from src.enums import (
    JobStatus,
    JobType,
    MediaAssetStatus,
    MediaAssetType,
    OcrObjectStatus,
)
from src.media_pipeline.hardsub_e2e import (
    CLEAN_METHOD_SINGLE_PASS,
    PIPELINE_BACKEND,
    run_hardsub_phases_1_to_4,
)
from src.media_pipeline.ocr_filtering.errors import OcrFilteringError
from src.media_pipeline.translator.errors import TranslatorError
from src.media_pipeline.video_renderer.errors import VideoRendererError
from src.models.artifacts import OcrFrameDetection, OcrTextObject
from src.models.ingestion import SourceVideo
from src.models.jobs import Job
from src.models.media import MediaAsset
from src.ocr_pipeline.band_crop import crop_bottom_band_image, remap_box_from_band_crop
from src.ocr_pipeline.completion_advisory import ocr_run_produced_cleaned_video
from src.ocr_pipeline.errors import OcrPipelineError, OcrPipelineErrorCode
from src.ocr_pipeline.frame_sampler import sample_video_frames
from src.ocr_pipeline.hardsub_filter import group_hard_sub_events
from src.ocr_pipeline.media_ocr_adapter import (
    frame_results_from_ocr_payload,
    hardsub_events_from_ocr_payload,
)
from src.ocr_pipeline.providers import OcrProvider, build_default_ocr_provider
from src.ocr_pipeline.types import (
    OCR_PIPELINE_VERSION,
    FrameOcrResult,
    HardSubEvent,
    OcrPipelineResult,
    OcrRequest,
)
from src.services.job_service import JobService
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend
from src.storage.path_strategy import VideoStorageContext, asset_logical_key

logger = logging.getLogger(__name__)

OcrProgressCallback = Callable[[str, int | None], None]


class OcrPipelineService:
    def __init__(
        self,
        db: Session,
        *,
        storage: StorageBackend | None = None,
        ocr_provider: OcrProvider | None = None,
        ffmpeg_binary: str = "ffmpeg",
    ):
        settings = get_settings()
        self.db = db
        self.storage = storage or LocalStorageBackend(settings.local_storage_root)
        # Lazy: API create/summary must not import/init PaddleOCR (Windows oneDNN/torch).
        self._ocr_provider = ocr_provider
        self.ffmpeg_binary = ffmpeg_binary

    @property
    def ocr_provider(self) -> OcrProvider:
        if self._ocr_provider is None:
            self._ocr_provider = build_default_ocr_provider()
        return self._ocr_provider

    @ocr_provider.setter
    def ocr_provider(self, value: OcrProvider) -> None:
        self._ocr_provider = value

    def create_ocr_job(self, request: OcrRequest, *, commit: bool = True):
        source_video = self._load_source_video(request.source_video_id)
        analysis_engine = str(request.analysis_engine or "").strip()
        if request.workflow_version == "QUALITY_LOCALIZATION_V24_1":
            # Every action in one quality workflow (analyze, OCR approval and
            # later replay) must carry the same official engine authority.
            # OcrRequest retains a V58 default only for legacy media callers;
            # it must never leak into a frontend quality checkpoint job.
            from src.services.analyze_ocr_recipe import (
                load_current_analyze_ocr_recipe,
            )

            analysis_engine = load_current_analyze_ocr_recipe().analysis_engine
            if not request.force_refresh:
                live_jobs = list(
                    self.db.scalars(
                        select(Job)
                        .where(
                            Job.source_video_id == source_video.id,
                            Job.job_type == JobType.ANALYZE_OCR,
                            Job.status.in_(
                                {
                                    JobStatus.QUEUED,
                                    JobStatus.RUNNING,
                                    JobStatus.RETRYABLE,
                                }
                            ),
                        )
                        .order_by(Job.created_at.desc())
                        .limit(20)
                    ).all()
                )
                for existing in live_jobs:
                    payload = dict(existing.payload_json or {})
                    if (
                        payload.get("workflow_version")
                        == "QUALITY_LOCALIZATION_V24_1"
                        and str(payload.get("workflow_action") or "analyze")
                        == str(request.workflow_action or "analyze")
                        and not bool(payload.get("force_refresh"))
                        and bool(payload.get("auto_advance"))
                        == bool(request.auto_advance)
                        and bool(payload.get("clean_hardsub", True))
                        == bool(request.clean_hardsub)
                    ):
                        logger.info(
                            "ocr_job_reused_live",
                            extra={
                                "job_id": str(existing.id),
                                "source_video_id": str(source_video.id),
                                "workflow_action": request.workflow_action,
                            },
                        )
                        return existing
        job = JobService(self.db).create_job(
            job_type=JobType.ANALYZE_OCR,
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            payload_json={
                "source_video_id": str(source_video.id),
                "force_refresh": request.force_refresh,
                "sample_fps": request.sample_fps,
                "hard_sub_band_ratio": request.hard_sub_band_ratio,
                "clean_hardsub": request.clean_hardsub,
                "use_master_phase1": request.use_master_phase1,
                "workflow_version": request.workflow_version,
                "workflow_action": request.workflow_action,
                "review_decisions": list(request.review_decisions),
                "operator_id": request.operator_id,
                "analysis_engine": analysis_engine,
                "auto_advance": request.auto_advance,
            },
            idempotency_key=None,
            commit=commit,
        )
        if request.workflow_version == "QUALITY_LOCALIZATION_V24_1":
            from src.services.pipeline_recipe_runtime import bind_job_to_current_recipe

            bind_job_to_current_recipe(job)
            if commit:
                self.db.commit()
            else:
                self.db.flush()
        logger.info("ocr_job_created", extra={"job_id": str(job.id), "source_video_id": str(source_video.id)})
        return job

    def run_pipeline(
        self,
        request: OcrRequest,
        *,
        job_id: UUID | None = None,
        on_progress: OcrProgressCallback | None = None,
    ) -> OcrPipelineResult:
        source_video = self._load_source_video(request.source_video_id)
        context = self._storage_context(source_video)
        source_asset = self._current_asset(source_video.id, MediaAssetType.SOURCE_VIDEO_RAW)
        if source_asset is None:
            raise OcrPipelineError(
                OcrPipelineErrorCode.MISSING_SOURCE_VIDEO_ASSET,
                "Current SOURCE_VIDEO_RAW asset is missing",
            )
        video_path = self._absolute_path_for_asset(source_asset)

        # Do NOT clear OCR rows / mark events stale here — a mid-pipeline failure
        # (e.g. Windows asyncio EINVAL after a long Cloud Run batch) would leave
        # the video with zero detections. Clear only after E2E succeeds, right
        # before writing the new plate.

        if request.clean_hardsub:
            return self._run_media_e2e_pipeline(
                request,
                source_video=source_video,
                context=context,
                video_path=video_path,
                job_id=job_id,
                on_progress=on_progress,
            )
        return self._run_detect_only_pipeline(
            request,
            source_video=source_video,
            context=context,
            video_path=video_path,
            job_id=job_id,
            on_progress=on_progress,
        )

    def _run_media_e2e_pipeline(
        self,
        request: OcrRequest,
        *,
        source_video: SourceVideo,
        context: VideoStorageContext,
        video_path: Path,
        job_id: UUID | None,
        on_progress: OcrProgressCallback | None,
    ) -> OcrPipelineResult:
        """Final Review clean path: Phase 1–4 → OCR_EVENTS + CLEANED_VIDEO."""
        warnings: list[str] = []

        def _progress(phase: str, percent: int | None) -> None:
            if on_progress is not None:
                on_progress(phase, percent)

        prefer_mock = os.environ.get("OCR_FILTERING_USE_MOCK", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        anti_seed = (int(source_video.id.int % 2_147_483_647) or 42)

        def _render_progress(seconds: float | None, _raw: str) -> None:
            """Keep job heartbeat alive during Phase 3+4 (UI no longer looks stuck at 75%)."""
            if seconds is None:
                return
            # Map rendered timeline into 76–89 before persist_detections@90.
            pct = min(89, 76 + int(max(0.0, float(seconds)) / 2.0))
            _progress("phase34_render", pct)

        with tempfile.TemporaryDirectory(prefix="ocr-e2e-") as tmp:
            cleaned_path = Path(tmp) / "cleaned.mp4"
            ocr_cache_path = (
                Path(video_path).parent
                / ".ocr_cache"
                / f"{source_video.id}.ocr-authority-v3.2.json"
            )
            try:
                e2e = run_hardsub_phases_1_to_4(
                    video_path,
                    cleaned_path,
                    sample_fps=request.sample_fps,
                    prefer_mock_ocr=prefer_mock,
                    anti_seed=anti_seed,
                    db=self.db,
                    workspace_id=source_video.workspace_id,
                    ffmpeg_binary=self.ffmpeg_binary,
                    band_ratio=request.hard_sub_band_ratio,
                    on_progress=_progress,
                    render_progress=_render_progress,
                    ocr_cache_path=ocr_cache_path,
                    force_refresh=bool(request.force_refresh),
                    use_master_phase1=request.use_master_phase1,
                )
            except OcrFilteringError as exc:
                raise OcrPipelineError(
                    OcrPipelineErrorCode.OCR_PROVIDER_FAILED,
                    exc.message,
                ) from exc
            except TranslatorError as exc:
                raise OcrPipelineError(
                    OcrPipelineErrorCode.CLEAN_HARD_SUB_FAILED,
                    f"Caption AI: {exc.message}",
                ) from exc
            except VideoRendererError as exc:
                raise OcrPipelineError(
                    OcrPipelineErrorCode.CLEAN_HARD_SUB_FAILED,
                    exc.message,
                ) from exc
            except FileNotFoundError as exc:
                raise OcrPipelineError(
                    OcrPipelineErrorCode.FRAME_SAMPLE_FAILED,
                    str(exc),
                ) from exc
            except RuntimeError as exc:
                raise OcrPipelineError(
                    OcrPipelineErrorCode.FRAME_SAMPLE_FAILED,
                    str(exc),
                ) from exc

            frame_results = frame_results_from_ocr_payload(e2e.ocr_payload)
            hardsub_events = hardsub_events_from_ocr_payload(
                e2e.ocr_payload,
                band_ratio=request.hard_sub_band_ratio,
            )
            unstable_count = sum(1 for event in hardsub_events if event.unstable)
            if unstable_count:
                warnings.append("hardsub_unstable")
            if not hardsub_events:
                warnings.append("no_hardsub_detected")

            _progress("persist_detections", 90)
            # Replace prior OCR plate only after a successful Phase 1–4 run.
            self._clear_previous_ocr_rows(source_video.id)
            self._mark_previous_ocr_assets_non_current(
                source_video.id,
                include_cleaned=False,
            )
            detection_count = self._persist_detections(
                source_video,
                frame_results,
                band_ratio=request.hard_sub_band_ratio,
            )
            cleaned_asset_id: str | None = None
            clean_produced = False
            out = Path(e2e.output_path) if e2e.output_path else None
            if out is not None and out.is_file():
                _progress("clean_hardsub", 95)
                self._mark_previous_ocr_assets_non_current(
                    source_video.id,
                    include_cleaned=True,
                    only_cleaned=True,
                )
                cleaned = self._persist_file_asset(
                    source_video,
                    context,
                    MediaAssetType.CLEANED_VIDEO,
                    out.read_bytes(),
                    filename=f"{OCR_PIPELINE_VERSION}_cleaned.mp4",
                    mime_type="video/mp4",
                    manifest_group="cleaned_video",
                    job_id=job_id,
                    metadata={
                        "hardsub_event_count": len(hardsub_events),
                        "clean_method": CLEAN_METHOD_SINGLE_PASS,
                        "pipeline_backend": PIPELINE_BACKEND,
                        "caption_ai_source": e2e.caption_ai_source,
                        "vi_text_count": len(e2e.vi_texts),
                        "warnings": warnings,
                        "clean_produced": True,
                    },
                )
                cleaned_asset_id = str(cleaned.id)
                clean_produced = True
            elif request.clean_hardsub:
                warnings.append("clean_skipped_no_hardsub")
                restored = self._restore_latest_cleaned_current(source_video.id)
                if restored is not None:
                    cleaned_asset_id = str(restored.id)
                else:
                    warnings.append("no_prior_cleaned_video")

            warning_list = list(dict.fromkeys(warnings))
            clean_produced = ocr_run_produced_cleaned_video(
                warning_list,
                cleaned_asset_id=cleaned_asset_id,
            )
            events_payload = {
                "pipeline_version": OCR_PIPELINE_VERSION,
                "pipeline_backend": PIPELINE_BACKEND,
                "provider": e2e.ocr_provider_name,
                "sample_fps": e2e.sample_fps,
                "hard_sub_band_ratio": request.hard_sub_band_ratio,
                "hardsub_events": [self._event_dict(e) for e in hardsub_events],
                "vi_texts": e2e.vi_texts,
                "caption_ai_source": e2e.caption_ai_source,
                "warnings": warning_list,
                "clean_produced": clean_produced,
                "ocr_region": "overlay_zones_media_pipeline",
            }
            # Fold Phase-2 filtering diagnostics when present (e.g. probe early-exit).
            ocr_warnings = e2e.ocr_payload.get("warnings") if isinstance(e2e.ocr_payload, dict) else None
            if isinstance(ocr_warnings, list):
                for item in ocr_warnings:
                    if isinstance(item, str) and item and item not in events_payload["warnings"]:
                        events_payload["warnings"].append(item)
                warning_list = list(dict.fromkeys(events_payload["warnings"]))
                events_payload["warnings"] = warning_list

            self._persist_json_asset(
                source_video,
                context,
                MediaAssetType.OCR_EVENTS,
                events_payload,
                filename=f"{OCR_PIPELINE_VERSION}_hardsub_events.json",
                manifest_group="ocr_events",
                job_id=job_id,
            )

        self.db.commit()
        _progress("completed", 100)
        logger.info(
            "ocr_pipeline_completed",
            extra={
                "source_video_id": str(source_video.id),
                "backend": PIPELINE_BACKEND,
                "frames": len(frame_results),
                "detections": detection_count,
                "events": len(hardsub_events),
                "cleaned": cleaned_asset_id,
                "clean_produced": clean_produced,
            },
        )
        return OcrPipelineResult(
            pipeline_version=OCR_PIPELINE_VERSION,
            source_video_id=str(source_video.id),
            frame_count=len(frame_results),
            detection_count=detection_count,
            hardsub_event_count=len(hardsub_events),
            cleaned_video_asset_id=cleaned_asset_id,
            warnings=warning_list,
            hardsub_events=hardsub_events,
            clean_produced=clean_produced,
        )

    def _run_detect_only_pipeline(
        self,
        request: OcrRequest,
        *,
        source_video: SourceVideo,
        context: VideoStorageContext,
        video_path: Path,
        job_id: UUID | None,
        on_progress: OcrProgressCallback | None,
    ) -> OcrPipelineResult:
        """Events-only path (clean_hardsub=False): legacy Pilot A sample + band OCR."""
        warnings: list[str] = []

        def _progress(phase: str, percent: int | None) -> None:
            if on_progress is not None:
                on_progress(phase, percent)

        _progress("sample_frames", 5)

        with tempfile.TemporaryDirectory(prefix="ocr-frames-") as tmp:
            tmp_dir = Path(tmp)
            sampled = sample_video_frames(
                video_path,
                tmp_dir / "frames",
                sample_fps=request.sample_fps,
                ffmpeg_binary=self.ffmpeg_binary,
            )
            frame_results: list[FrameOcrResult] = []
            total = max(1, len(sampled))
            band_dir = tmp_dir / "band"
            band_dir.mkdir(parents=True, exist_ok=True)
            for index, (time_ms, frame_path) in enumerate(sampled):
                band_path = band_dir / f"band_{index:06d}.jpg"
                full_w, full_h, _top = crop_bottom_band_image(
                    frame_path,
                    band_path,
                    band_ratio=request.hard_sub_band_ratio,
                )
                raw = self.ocr_provider.detect_frame(band_path, frame_time_ms=time_ms)
                remapped = [
                    remap_box_from_band_crop(box, band_ratio=request.hard_sub_band_ratio)
                    for box in raw.boxes
                ]
                frame_results.append(
                    FrameOcrResult(
                        frame_time_ms=raw.frame_time_ms,
                        frame_width=full_w,
                        frame_height=full_h,
                        boxes=remapped,
                    )
                )
                _progress(
                    f"ocr_frame_{index + 1}/{total}",
                    int(5 + (85 * (index + 1) / total)),
                )

            hardsub_events = group_hard_sub_events(
                frame_results,
                band_ratio=request.hard_sub_band_ratio,
            )
            unstable_count = sum(1 for e in hardsub_events if e.unstable)
            if unstable_count:
                warnings.append("hardsub_unstable")
            if not hardsub_events:
                warnings.append("no_hardsub_detected")
            provider_warnings = getattr(self.ocr_provider, "warnings", None)
            if isinstance(provider_warnings, list):
                warnings.extend(str(item) for item in provider_warnings if item)

            _progress("persist_detections", 90)
            self._clear_previous_ocr_rows(source_video.id)
            self._mark_previous_ocr_assets_non_current(
                source_video.id,
                include_cleaned=False,
            )
            detection_count = self._persist_detections(
                source_video,
                frame_results,
                band_ratio=request.hard_sub_band_ratio,
            )
            events_payload = {
                "pipeline_version": OCR_PIPELINE_VERSION,
                "provider": getattr(self.ocr_provider, "provider_name", "unknown"),
                "sample_fps": request.sample_fps,
                "hard_sub_band_ratio": request.hard_sub_band_ratio,
                "hardsub_events": [self._event_dict(e) for e in hardsub_events],
                "warnings": warnings,
                "ocr_region": "bottom_band_crop",
            }
            self._persist_json_asset(
                source_video,
                context,
                MediaAssetType.OCR_EVENTS,
                events_payload,
                filename=f"{OCR_PIPELINE_VERSION}_hardsub_events.json",
                manifest_group="ocr_events",
                job_id=job_id,
            )

        self.db.commit()
        _progress("completed", 100)
        logger.info(
            "ocr_pipeline_completed",
            extra={
                "source_video_id": str(source_video.id),
                "frames": len(frame_results),
                "detections": detection_count,
                "events": len(hardsub_events),
                "cleaned": None,
            },
        )
        return OcrPipelineResult(
            pipeline_version=OCR_PIPELINE_VERSION,
            source_video_id=str(source_video.id),
            frame_count=len(frame_results),
            detection_count=detection_count,
            hardsub_event_count=len(hardsub_events),
            cleaned_video_asset_id=None,
            warnings=list(dict.fromkeys(warnings)),
            hardsub_events=hardsub_events,
        )

    def get_ocr_summary(self, source_video_id: UUID) -> dict:
        events_asset = self._current_asset(source_video_id, MediaAssetType.OCR_EVENTS)
        cleaned = self._current_asset(source_video_id, MediaAssetType.CLEANED_VIDEO)
        payload = {}
        if events_asset and isinstance(events_asset.metadata_json, dict):
            payload = events_asset.metadata_json.get("events") or events_asset.metadata_json
            if "hardsub_events" not in payload and isinstance(events_asset.metadata_json.get("manifest"), dict):
                payload = events_asset.metadata_json["manifest"]
        # Prefer JSON file content from storage when present
        if events_asset and self.storage.exists(events_asset.storage_key):
            try:
                path = Path(self.storage.resolve(events_asset.storage_key).absolute_path)
                payload = json.loads(path.read_bytes().decode("utf-8"))
            except Exception:
                pass

        text_count = self.db.scalar(
            select(func.count()).select_from(OcrTextObject).where(OcrTextObject.source_video_id == source_video_id)
        )
        frame_count = self.db.scalar(
            select(func.count()).select_from(OcrFrameDetection).where(OcrFrameDetection.source_video_id == source_video_id)
        )
        warnings = (payload.get("warnings") if isinstance(payload, dict) else []) or []
        cleaned_id = str(cleaned.id) if cleaned else None
        clean_produced = bool(payload.get("clean_produced")) if isinstance(payload, dict) else False
        if not clean_produced:
            clean_produced = ocr_run_produced_cleaned_video(warnings, cleaned_asset_id=cleaned_id)
        return {
            "source_video_id": str(source_video_id),
            "pipeline_version": payload.get("pipeline_version") if isinstance(payload, dict) else None,
            "provider": payload.get("provider") if isinstance(payload, dict) else None,
            "text_object_count": int(text_count or 0),
            "frame_detection_count": int(frame_count or 0),
            "hardsub_events": (payload.get("hardsub_events") if isinstance(payload, dict) else []) or [],
            "warnings": warnings,
            "cleaned_video_asset_id": cleaned_id,
            "ocr_events_asset_id": str(events_asset.id) if events_asset else None,
            "visual_approved": bool(
                (cleaned is not None and (cleaned.metadata_json or {}).get("visual_approved"))
                or (events_asset is not None and (events_asset.metadata_json or {}).get("visual_approved"))
            ),
            "clean_produced": clean_produced,
        }

    def approve_visual(self, source_video_id: UUID) -> dict:
        cleaned = self._current_asset(source_video_id, MediaAssetType.CLEANED_VIDEO)
        events = self._current_asset(source_video_id, MediaAssetType.OCR_EVENTS)
        if cleaned is None and events is None:
            raise OcrPipelineError(
                OcrPipelineErrorCode.PERSISTENCE_FAILED,
                "No OCR outputs to approve; run Analyze OCR first",
            )
        for asset in (cleaned, events):
            if asset is None:
                continue
            meta = dict(asset.metadata_json or {})
            meta["visual_approved"] = True
            asset.metadata_json = meta
        self.db.commit()
        return self.get_ocr_summary(source_video_id)

    def _persist_phase2_tracks(
        self,
        source_video: SourceVideo,
        *,
        phase2_contract: Mapping[str, object],
        payload: Mapping[str, object],
    ) -> tuple[int, int]:
        """Persist the Phase-2 authority as content objects plus linked frames.

        Phase 2 groups detections into temporal tracks/content objects.  The old
        compatibility adapter materialized one ``OcrTextObject`` per box per
        frame, including empty OCR candidates.  That made the relational rows
        look like an OCR authority and made long videos explode in row count.
        Here the content object is the authority; frame rows are only geometry
        evidence linked back to it.
        """
        content_rows = [
            row
            for row in list(phase2_contract.get("content_objects") or [])
            if isinstance(row, Mapping)
        ]
        track_rows = [
            row
            for row in list(phase2_contract.get("track_enrichments") or [])
            if isinstance(row, Mapping)
        ]
        protected_ids = {
            str(row.get("text_id") or "")
            for row in list(phase2_contract.get("protected_source_tracks") or [])
            if isinstance(row, Mapping) and str(row.get("text_id") or "")
        }
        text_id_to_content: dict[str, str] = {}
        for row in track_rows:
            text_id = str(row.get("text_id") or "")
            content_id = str(row.get("content_id") or "")
            if text_id and content_id and text_id not in protected_ids:
                text_id_to_content[text_id] = content_id

        object_by_content: dict[str, OcrTextObject] = {}
        object_rows: list[OcrTextObject] = []
        for row in content_rows:
            content_id = str(row.get("content_id") or "")
            if not content_id:
                continue
            status = str(row.get("review_status") or "")
            if status in {"SOURCE_INTRINSIC_APPROVED", "OCR_REJECTED_UI"}:
                continue
            candidates = [
                str(row.get("ocr_text_approved") or "").strip(),
                str(row.get("ocr_text_candidate") or "").strip(),
            ]
            candidates.extend(
                str(value or "").strip()
                for value in list(row.get("ocr_text_raw_candidates") or [])
            )
            text = next((value for value in candidates if value), "")
            # Empty candidates are review evidence, not OCR objects.  Keeping
            # them out of the authority is essential for auto policy and DB
            # correctness.
            if not text:
                continue
            assets = [
                asset
                for asset in list(row.get("review_assets") or [])
                if isinstance(asset, Mapping)
            ]
            starts = [int(asset.get("start_frame")) for asset in assets if str(asset.get("start_frame") or "").strip()]
            ends = [int(asset.get("end_frame")) for asset in assets if str(asset.get("end_frame") or "").strip()]
            fps = float(payload.get("fps") or 30.0)
            first_ms = int(round(min(starts) * 1000.0 / fps)) if starts else None
            last_ms = int(round(max(ends) * 1000.0 / fps)) if ends else None
            obj = OcrTextObject(
                workspace_id=source_video.workspace_id,
                source_video_id=source_video.id,
                text=text,
                normalized_text="".join(text.split()).lower() or None,
                language_code="zh",
                status=OcrObjectStatus.DETECTED,
                confidence=None,
                first_seen_ms=first_ms,
                last_seen_ms=last_ms,
                metadata_json={
                    "authority": "phase2_content_object",
                    "pipeline_version": str(
                        phase2_contract.get("schema_version") or "phase2_ocr_timeline_v2"
                    ),
                    "content_id": content_id,
                    "geometry_refs": list(row.get("geometry_refs") or []),
                    "review_status": status,
                    "provenance_classifications": list(
                        row.get("provenance_classifications") or []
                    ),
                },
            )
            object_rows.append(obj)
            object_by_content[content_id] = obj
        if object_rows:
            self.db.add_all(object_rows)
            self.db.flush()

        detections: list[OcrFrameDetection] = []
        for frame in list(payload.get("frames") or []):
            if not isinstance(frame, Mapping):
                continue
            frame_time_ms = int(frame.get("time_ms") or 0)
            for box in list(frame.get("boxes") or []):
                if not isinstance(box, Mapping):
                    continue
                text_id = str(box.get("text_id") or "")
                content_id = text_id_to_content.get(text_id)
                obj = object_by_content.get(content_id or "")
                if obj is None:
                    continue
                x = float(box.get("x") or 0.0)
                y = float(box.get("y") or 0.0)
                width = float(box.get("w") or box.get("width") or 0.0)
                height = float(box.get("h") or box.get("height") or 0.0)
                confidence_raw = box.get("confidence")
                confidence = float(confidence_raw) if confidence_raw is not None else None
                detections.append(
                    OcrFrameDetection(
                        workspace_id=source_video.workspace_id,
                        source_video_id=source_video.id,
                        ocr_text_object_id=obj.id,
                        frame_time_ms=frame_time_ms,
                        x=x,
                        y=y,
                        width=width,
                        height=height,
                        confidence=confidence,
                        raw_payload_json={
                            "authority": "phase2_frame_geometry",
                            "text_id": text_id,
                            "content_id": content_id,
                            "cover_only": bool(box.get("cover_only")),
                            "localization_mode": box.get("localization_mode"),
                        },
                    )
                )
        if detections:
            self.db.add_all(detections)
        return len(object_rows), len(detections)

    def _persist_detections(
        self,
        source_video: SourceVideo,
        frames: list[FrameOcrResult],
        *,
        band_ratio: float,
    ) -> int:
        del band_ratio  # frames already overlay-zone filtered upstream.
        count = 0
        for frame in frames:
            for box in frame.boxes:
                obj = OcrTextObject(
                    workspace_id=source_video.workspace_id,
                    source_video_id=source_video.id,
                    text=box.text or "",
                    normalized_text=(box.text or "").strip().lower() or None,
                    language_code="zh",
                    status=OcrObjectStatus.DETECTED,
                    confidence=box.confidence,
                    first_seen_ms=frame.frame_time_ms,
                    last_seen_ms=frame.frame_time_ms,
                    metadata_json={"band": "overlay_zone", "pipeline_version": OCR_PIPELINE_VERSION},
                )
                self.db.add(obj)
                self.db.flush()
                det = OcrFrameDetection(
                    workspace_id=source_video.workspace_id,
                    source_video_id=source_video.id,
                    ocr_text_object_id=obj.id,
                    frame_time_ms=frame.frame_time_ms,
                    x=box.x,
                    y=box.y,
                    width=box.width,
                    height=box.height,
                    confidence=box.confidence,
                    raw_payload_json={"text": box.text, "confidence": box.confidence},
                )
                self.db.add(det)
                count += 1
        return count

    def _clear_previous_ocr_rows(self, source_video_id: UUID) -> None:
        self.db.execute(delete(OcrFrameDetection).where(OcrFrameDetection.source_video_id == source_video_id))
        self.db.execute(delete(OcrTextObject).where(OcrTextObject.source_video_id == source_video_id))

    def _mark_previous_ocr_assets_non_current(
        self,
        source_video_id: UUID,
        *,
        include_cleaned: bool = True,
        only_cleaned: bool = False,
    ) -> None:
        if only_cleaned:
            asset_types = [MediaAssetType.CLEANED_VIDEO]
        else:
            asset_types = [
                MediaAssetType.OCR_EVENTS,
                MediaAssetType.OCR_FRAME,
            ]
            if include_cleaned:
                asset_types.append(MediaAssetType.CLEANED_VIDEO)
        self.db.execute(
            update(MediaAsset)
            .where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type.in_(asset_types),
            )
            .values(is_current=False)
        )

    def _restore_latest_cleaned_current(self, source_video_id: UUID) -> MediaAsset | None:
        """Re-point is_current to newest CLEANED_VIDEO when a clean pass is skipped."""
        latest = self.db.scalar(
            select(MediaAsset)
            .where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type == MediaAssetType.CLEANED_VIDEO,
            )
            .order_by(MediaAsset.version.desc())
            .limit(1)
        )
        if latest is None:
            return None
        if not latest.is_current:
            latest.is_current = True
            self.db.flush()
        return latest

    def _persist_json_asset(
        self,
        source_video: SourceVideo,
        context: VideoStorageContext,
        asset_type: MediaAssetType,
        payload: dict,
        *,
        filename: str,
        manifest_group: str,
        job_id: UUID | None,
    ) -> MediaAsset:
        content = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        return self._persist_file_asset(
            source_video,
            context,
            asset_type,
            content,
            filename=filename,
            mime_type="application/json",
            manifest_group=manifest_group,
            job_id=job_id,
            metadata={"events": payload} if asset_type == MediaAssetType.OCR_EVENTS else {},
        )

    def _persist_file_asset(
        self,
        source_video: SourceVideo,
        context: VideoStorageContext,
        asset_type: MediaAssetType,
        content: bytes,
        *,
        filename: str,
        mime_type: str,
        manifest_group: str,
        job_id: UUID | None,
        metadata: dict | None = None,
    ) -> MediaAsset:
        version = self._next_asset_version(source_video.id, asset_type)
        logical_key = asset_logical_key(context, asset_type, filename=f"v{version}_{filename}")
        write_result = self.storage.write_bytes(logical_key, content)
        asset = MediaAsset(
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            asset_type=asset_type,
            status=MediaAssetStatus.AVAILABLE,
            version=version,
            storage_provider=write_result.storage_provider,
            storage_key=write_result.storage_key,
            logical_key=logical_key,
            relative_path=write_result.relative_path,
            manifest_group=manifest_group,
            is_current=True,
            created_by_job_id=job_id,
            mime_type=mime_type,
            size_bytes=write_result.size_bytes,
            checksum_sha256=write_result.checksum_sha256,
            metadata_json={**(metadata or {}), "absolute_path": write_result.absolute_path},
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def _next_asset_version(self, source_video_id: UUID, asset_type: MediaAssetType) -> int:
        max_version = self.db.scalar(
            select(func.max(MediaAsset.version)).where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type == asset_type,
            )
        )
        return (max_version or 0) + 1

    def _current_asset(self, source_video_id: UUID, asset_type: MediaAssetType) -> MediaAsset | None:
        return self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type == asset_type,
                MediaAsset.is_current.is_(True),
            )
        )

    def _absolute_path_for_asset(self, asset: MediaAsset) -> Path:
        meta = asset.metadata_json or {}
        absolute = meta.get("absolute_path")
        if absolute and Path(str(absolute)).is_file():
            return Path(str(absolute))
        resolved = self.storage.resolve(asset.storage_key)
        path = Path(resolved.absolute_path)
        if not path.is_file():
            raise OcrPipelineError(
                OcrPipelineErrorCode.MISSING_SOURCE_VIDEO_ASSET,
                f"Source video file not found at {path}",
            )
        return path

    def _load_source_video(self, source_video_id: UUID) -> SourceVideo:
        source_video = self.db.scalar(
            select(SourceVideo)
            .where(SourceVideo.id == source_video_id)
            .options(selectinload(SourceVideo.source_profile))
        )
        if source_video is None:
            raise OcrPipelineError(OcrPipelineErrorCode.MISSING_SOURCE_VIDEO, "Source video not found")
        return source_video

    def _storage_context(self, source_video: SourceVideo) -> VideoStorageContext:
        profile = source_video.source_profile
        return VideoStorageContext(
            workspace_id=str(source_video.workspace_id),
            source_platform=source_video.source_platform,
            source_profile_external_id=profile.source_profile_external_id,
            source_video_external_id=source_video.source_video_external_id,
            profile_handle=getattr(profile, "handle", None),
            profile_display_name=getattr(profile, "display_name", None),
        )

    @staticmethod
    def _event_dict(event: HardSubEvent) -> dict:
        return {
            "start_ms": event.start_ms,
            "end_ms": event.end_ms,
            "x": event.x,
            "y": event.y,
            "width": event.width,
            "height": event.height,
            "sample_count": event.sample_count,
            "avg_confidence": event.avg_confidence,
            "texts": event.texts,
            "unstable": event.unstable,
        }
