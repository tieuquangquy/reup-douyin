from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.downloaders.base import DownloadedObject
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.source_video_primary_fetcher import PrimaryVideoFetchResult
from src.render_pipeline.types import VideoProbe
from src.services.download_service import DownloadService
from src.storage.path_strategy import VideoStorageContext


def _context() -> VideoStorageContext:
    return VideoStorageContext(
        workspace_id=str(uuid4()),
        source_platform="DOUYIN",
        source_profile_external_id="profile-1",
        source_video_external_id="7654321098765432100",
        profile_handle="creator",
    )


def _service(*, probe: object) -> tuple[DownloadService, MagicMock]:
    storage = MagicMock()
    storage.write_bytes.return_value = SimpleNamespace(
        storage_key="workspace/temp/download-probe.mp4",
    )
    service = DownloadService(
        MagicMock(),
        storage=storage,
        downloader=MagicMock(),
        primary_fetcher=MagicMock(),
        media_probe=probe,  # type: ignore[arg-type]
    )
    return service, storage


def _valid_probe(*, audio_codec: str | None = "aac") -> VideoProbe:
    return VideoProbe(
        width=1080,
        height=1920,
        fps=30.0,
        duration_seconds=12.5,
        video_codec="h264",
        audio_codec=audio_codec,
        raw={"probe_strategy": "ffprobe"},
    )


def test_post_fetch_probe_accepts_video_and_always_removes_temp_asset() -> None:
    probe = MagicMock(return_value=_valid_probe())
    service, storage = _service(probe=probe)

    result = service._validate_downloaded_primary_video(
        _context(),
        DownloadedObject(content=b"downloaded-video-bytes", filename="source.mp4"),
        filename="source.mp4",
    )

    assert result.video_codec == "h264"
    storage.write_bytes.assert_called_once()
    probe.assert_called_once_with("workspace/temp/download-probe.mp4")
    storage.delete.assert_called_once()


def test_post_fetch_probe_rejects_audio_only_payload_before_raw_persistence() -> None:
    audio_only = VideoProbe(
        width=None,
        height=None,
        fps=None,
        duration_seconds=12.5,
        video_codec=None,
        audio_codec="aac",
        raw={"probe_strategy": "ffprobe"},
    )
    service, storage = _service(probe=MagicMock(return_value=audio_only))

    with pytest.raises(DownloadError) as caught:
        service._validate_downloaded_primary_video(
            _context(),
            DownloadedObject(content=b"audio-only-bytes", filename="source.m4a"),
            filename="source.m4a",
        )

    assert caught.value.code == DownloadErrorCode.VALIDATION_FAILED
    assert "audio-only" in caught.value.message
    storage.delete.assert_called_once()


def test_post_fetch_probe_rejects_ffprobe_failure_and_cleans_temp_asset() -> None:
    service, storage = _service(probe=MagicMock(side_effect=RuntimeError("invalid data found")))

    with pytest.raises(DownloadError) as caught:
        service._validate_downloaded_primary_video(
            _context(),
            DownloadedObject(content=b"<html>challenge</html>", filename="source.mp4"),
            filename="source.mp4",
        )

    assert caught.value.code == DownloadErrorCode.VALIDATION_FAILED
    assert "failed ffprobe validation" in caught.value.message
    storage.delete.assert_called_once()


def test_primary_persistence_probes_first_and_persists_bounded_metadata() -> None:
    probe = MagicMock(return_value=_valid_probe())
    service, _storage = _service(probe=probe)
    persisted = object()
    service._persist_bytes_asset = MagicMock(return_value=persisted)  # type: ignore[method-assign]
    source_video = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        source_video_external_id="7654321098765432100",
        caption="sample",
        posted_at=None,
    )
    primary = PrimaryVideoFetchResult(
        downloaded=DownloadedObject(
            content=b"downloaded-video-bytes",
            mime_type="video/mp4",
            filename="video.mp4",
        ),
        resolver_name="playwright_browser",
        source_url="https://www.douyin.com/video/7654321098765432100",
        watermark_free=True,
        height=1920,
        width=1080,
        format_id="play_addr|1920p",
    )

    result = service._persist_primary_video(
        source_video,
        _context(),
        primary,
        job_id=uuid4(),
        force_refresh=True,
    )

    assert result is persisted
    probe.assert_called_once()
    kwargs = service._persist_bytes_asset.call_args.kwargs
    metadata = kwargs["extra_metadata"]
    assert metadata["media_probe"] == {
        "probe_strategy": "ffprobe",
        "width": 1080,
        "height": 1920,
        "fps": 30.0,
        "duration_seconds": 12.5,
        "video_codec": "h264",
        "audio_codec": "aac",
        "audio_stream_count": 1,
        "has_audio": True,
    }
