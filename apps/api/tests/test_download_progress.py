"""Focused contracts for the Download Video progress/cancellation boundary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.base import DownloadedObject
from src.downloaders.douyin_download_session import DouyinDownloadSession
from src.downloaders.source_video_primary_fetcher import PrimaryVideoFetchResult
from src.enums import JobStatus, JobStepStatus, JobType
from src.services.download_service import DownloadService
from src.services.job_progress import apply_job_progress
from src.services.job_runner import JobRunner, StepHandlerRegistry
from src.services.job_templates import get_step_templates


def _source_video():
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        source_platform="DOUYIN",
        source_url="https://www.douyin.com/video/123",
        source_video_external_id="123",
        metadata_json={},
        raw_payload_json=None,
        caption=None,
        source_profile=SimpleNamespace(
            source_profile_external_id="profile-1",
            handle=None,
            display_name=None,
        ),
        status="DISCOVERED",
    )


def test_new_download_jobs_start_with_real_transfer_step() -> None:
    templates = get_step_templates(JobType.DOWNLOAD_VIDEO)
    assert [step.key for step in templates] == ["register_assets", "finalize_manifest"]


def test_download_service_emits_ordered_monotonic_phases_and_byte_progress() -> None:
    source = _source_video()
    service = DownloadService(
        MagicMock(),
        storage=MagicMock(),
        downloader=MagicMock(),
        primary_fetcher=MagicMock(),
        media_probe=MagicMock(),
    )
    service._get_source_video = MagicMock(return_value=source)
    service._storage_context = MagicMock(return_value=SimpleNamespace())
    service._current_asset = MagicMock(return_value=None)
    service._enrich_profile_identity_from_download = MagicMock()
    service._persist_primary_video = MagicMock(return_value=SimpleNamespace(asset_type="SOURCE_VIDEO_RAW"))
    service._persist_json_asset = MagicMock(return_value=SimpleNamespace(asset_type="METADATA_JSON"))
    service.get_manifest = MagicMock(return_value={"assets": []})

    def fetch_primary(
        _source,
        _session,
        *,
        job_id=None,
        account_connection_id=None,
        on_transfer_progress=None,
    ):
        assert job_id is not None
        assert on_transfer_progress is not None
        for done in (0, 25, 50, 100):
            on_transfer_progress(done, 100)
        return PrimaryVideoFetchResult(
            downloaded=DownloadedObject(content=b"video", mime_type="video/mp4", filename="123.mp4"),
            resolver_name="fake",
            source_url="https://www.douyin.com/video/123",
            watermark_free=True,
        )

    service._fetch_primary_video = MagicMock(side_effect=fetch_primary)
    progress: list[tuple[str, int | None]] = []
    session = DouyinDownloadSession(
        session_cookie="sessionid=test",
        user_agent="ua",
        proxy_url=None,
        cookie_source="browser_store",
    )

    with patch("src.services.download_service.resolve_douyin_download_session", return_value=session):
        service.run_download(
            source.id,
            job_id=uuid4(),
            on_progress=lambda phase, percent: progress.append((phase, percent)),
        )

    names = [phase.split("|", 1)[0] for phase, _ in progress]
    assert names == [
        "cache_validate",
        "resolve_session",
        "resolve_candidates",
        "transfer_primary",
        "transfer_primary",
        "transfer_primary",
        "transfer_primary",
        "validate_primary",
        "atomic_promote",
        "persist_sidecars",
        "finalize_manifest",
    ]
    percentages = [int(percent) for _, percent in progress if percent is not None]
    assert percentages == sorted(percentages)
    transfer = [(phase, percent) for phase, percent in progress if phase.startswith("transfer_primary|")]
    assert transfer == [
        ("transfer_primary|0|100", 15),
        ("transfer_primary|25|100", 31),
        ("transfer_primary|50|100", 46),
        ("transfer_primary|100|100", 77),
    ]


def test_job_runner_download_heartbeat_persists_byte_metadata_and_never_moves_back() -> None:
    step = SimpleNamespace(
        step_key="register_assets",
        step_order=5,
        status=JobStepStatus.RUNNING,
        progress_percent=0,
        metadata_json={},
    )
    job = SimpleNamespace(
        id=uuid4(),
        job_type=JobType.DOWNLOAD_VIDEO,
        status=JobStatus.RUNNING,
        progress_percent=0,
        steps=[step],
    )
    runner = JobRunner(MagicMock(), handlers=StepHandlerRegistry())
    runner.service.refresh_progress = apply_job_progress

    snapshots: list[tuple[int, int]] = []
    for phase, percent in (
        ("transfer_primary|4096|8192", 40),
        ("transfer_primary|6144|8192", 60),
        # A late/stale callback must not lower the displayed percentage.
        ("transfer_primary|5120|8192", 50),
    ):
        runner._live_heartbeat(
            job,
            step,
            metadata_key="download_phase",
            phase=phase,
            progress_percent=percent,
            job_progress_percent=percent,
        )
        snapshots.append((job.progress_percent, step.progress_percent))

    assert snapshots == [(40, 40), (60, 60), (60, 60)]
    assert step.metadata_json["download_phase"] == "transfer_primary"
    assert step.metadata_json["download_phase_current"] == 6144
    assert step.metadata_json["download_phase_total"] == 8192


class _CancelAwareJobService:
    def __init__(self, job):
        self.job = job

    def get_job(self, _job_id):
        return self.job

    def transition_step(self, step, status, *, progress_percent=None, **_kwargs):
        step.status = status
        if progress_percent is not None:
            step.progress_percent = progress_percent

    def transition_job(self, job, status, **_kwargs):
        job.status = status

    def refresh_progress(self, job):
        return apply_job_progress(job)


def test_job_runner_aborts_download_when_progress_callback_observes_cancel() -> None:
    job_id = uuid4()
    steps = [
        SimpleNamespace(
            step_key=key,
            step_order=index,
            status=JobStepStatus.PENDING,
            progress_percent=0,
            metadata_json={},
        )
        for index, key in enumerate(
            (
                "validate_input",
                "resolve_storage",
                "fetch_primary_video",
                "fetch_thumbnail",
                "persist_metadata_mirror",
                "register_assets",
                "finalize_manifest",
            )
        )
    ]
    job = SimpleNamespace(
        id=job_id,
        job_type=JobType.DOWNLOAD_VIDEO,
        status=JobStatus.RUNNING,
        source_video_id=uuid4(),
        payload_json={"source_video_id": str(uuid4())},
        steps=steps,
        progress_percent=0,
        attempts=1,
        max_attempts=3,
        retryable=True,
        locked_by="worker",
        locked_at=None,
        error_code=None,
        error_message=None,
    )
    db = MagicMock()
    runner = JobRunner(db, handlers=StepHandlerRegistry())
    runner.service = _CancelAwareJobService(job)

    def cancel_then_emit(*_args, on_progress=None, **_kwargs):
        job.status = JobStatus.CANCELLED
        for pending in job.steps:
            if pending.status in {JobStepStatus.PENDING, JobStepStatus.RUNNING}:
                pending.status = JobStepStatus.SKIPPED
                pending.progress_percent = 100
        assert on_progress is not None
        on_progress("transfer_primary|1|10", 20)
        raise AssertionError("cancellation callback should abort before this line")

    with (
        patch("src.services.download_service.DownloadService.run_download", side_effect=cancel_then_emit),
        patch("src.services.job_runner.sync_reup_queue_from_download_job"),
    ):
        result = runner.run_job(job_id)

    assert result.status == JobStatus.CANCELLED
    assert result.locked_by is None
    assert [step.status for step in result.steps[:5]] == [JobStepStatus.COMPLETED] * 5
    assert [step.status for step in result.steps[5:]] == [JobStepStatus.SKIPPED] * 2
