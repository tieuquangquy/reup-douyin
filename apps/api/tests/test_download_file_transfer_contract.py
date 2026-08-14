from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.downloaders.api_bridged_playwright_douyin_resolver import (
    ApiBridgedPlaywrightDouyinResolver,
    _read_bridge_response,
)
from src.downloaders.base import DownloadedObject
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.playwright_douyin_video_resolver import staging_path_for_aweme
from src.downloaders.source_video_primary_fetcher import PrimaryVideoFetchResult
from src.downloaders.yt_dlp_douyin_resolver import YtDlpDouyinVideoResolver
from src.enums import MediaAssetType, SourcePlatformEnum
from src.services.download_service import DownloadService, _remove_staging_path
from src.storage.local import LocalStorageBackend
from src.storage.path_strategy import VideoStorageContext


class _JsonResponse:
    status = 200

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self._body


class _Probe:
    def __init__(self):
        self.path_calls: list[str] = []

    def probe(self, _storage_key: str):
        raise AssertionError("path transfer must use probe_path, not storage-key probe")

    def probe_path(self, path: str | Path):
        self.path_calls.append(str(path))
        return SimpleNamespace(
            width=1080,
            height=1920,
            fps=30.0,
            duration_seconds=4.0,
            video_codec="h264",
            audio_codec="aac",
            raw={"probe_strategy": "ffprobe", "video_stream_count": 1, "audio_stream_count": 1},
        )


def _source_video():
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        source_platform=SourcePlatformEnum.DOUYIN,
        source_video_external_id="7647480428480563048",
        source_url="https://www.douyin.com/video/7647480428480563048",
        caption=None,
        posted_at=None,
        metadata_json={},
        raw_payload_json=None,
        source_profile=SimpleNamespace(
            source_profile_external_id="profile-1",
            handle="creator",
            display_name="Creator",
        ),
    )


def _managed_file(root: Path, *, name: str = "video.mp4") -> Path:
    path = root / "workspace" / "account" / "aweme" / "transfer" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"file-transfer-video")
    return path


def test_source_video_raw_path_probe_and_persist_avoid_read_bytes(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    source_path = _managed_file(staging_root)
    storage = LocalStorageBackend(tmp_path / "storage")
    # Guard the contract: path transfer should use write_file/open, never read the
    # complete source into Python memory through the storage adapter.
    storage.read_bytes = MagicMock(side_effect=AssertionError("read_bytes is forbidden"))
    probe = _Probe()
    db = MagicMock()
    db.scalar.side_effect = [None, None]  # current asset, then storage-key owner
    service = DownloadService(
        db,
        storage=storage,
        downloader=MagicMock(),
        primary_fetcher=MagicMock(),
        media_probe=probe.probe,
    )
    source = _source_video()
    context = VideoStorageContext(
        workspace_id=str(source.workspace_id),
        source_platform=SourcePlatformEnum.DOUYIN,
        source_profile_external_id="profile-1",
        source_video_external_id=source.source_video_external_id,
        profile_handle="creator",
    )
    result = PrimaryVideoFetchResult(
        downloaded=DownloadedObject(
            content=None,
            mime_type="video/mp4",
            filename="video.mp4",
            local_path=str(source_path),
            size_bytes=source_path.stat().st_size,
            cleanup_local_path=True,
        ),
        resolver_name="playwright_browser",
        source_url=source.source_url,
        watermark_free=True,
    )

    with patch("src.downloaders.download_staging.download_staging_root", return_value=staging_root):
        asset = service._persist_primary_video(source, context, result, job_id=None, force_refresh=True)

    assert probe.path_calls == [str(source_path)]
    storage.read_bytes.assert_not_called()
    assert not source_path.exists(), "successful persist must remove only its managed staging file"
    persisted_path = storage.resolve(asset.storage_key).absolute_path
    assert persisted_path.read_bytes() == b"file-transfer-video"


def test_run_download_does_not_cleanup_staging_before_database_commit(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    source_path = _managed_file(staging_root)
    source = _source_video()
    result = PrimaryVideoFetchResult(
        downloaded=DownloadedObject(
            local_path=str(source_path),
            size_bytes=source_path.stat().st_size,
            mime_type="video/mp4",
            filename="video.mp4",
            cleanup_local_path=True,
        ),
        resolver_name="test",
        source_url=source.source_url,
        watermark_free=True,
    )
    db = MagicMock()
    db.commit.side_effect = RuntimeError("commit failed")
    service = DownloadService(
        db,
        storage=MagicMock(),
        downloader=MagicMock(),
        primary_fetcher=MagicMock(),
        media_probe=MagicMock(),
    )
    service._get_source_video = MagicMock(return_value=source)
    service._current_asset = MagicMock(return_value=None)
    service._storage_context = MagicMock(return_value=SimpleNamespace())
    service._fetch_primary_video = MagicMock(return_value=result)
    service._persist_primary_video = MagicMock(return_value=SimpleNamespace())
    service._persist_json_asset = MagicMock(return_value=SimpleNamespace())

    with (
        patch(
            "src.services.download_service.resolve_douyin_download_session",
            return_value=SimpleNamespace(),
        ),
        patch("src.services.download_service._remove_staging_path") as remove_staging,
        pytest.raises(RuntimeError, match="commit failed"),
    ):
        service.run_download(source.id)

    remove_staging.assert_not_called()
    assert source_path.exists()


def test_staging_cleanup_is_contained_to_managed_root(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    managed = _managed_file(staging_root, name="managed.mp4")
    companion = managed.with_name("managed.mp4.resume.json")
    companion.write_text("{}", encoding="utf-8")
    unrelated_same_prefix = managed.with_name("managed_backup.mp4")
    unrelated_same_prefix.write_bytes(b"must-stay")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"must-stay")

    with patch("src.downloaders.download_staging.download_staging_root", return_value=staging_root):
        _remove_staging_path(managed)
        _remove_staging_path(outside)

    assert not managed.exists()
    assert not companion.exists()
    assert unrelated_same_prefix.exists()
    assert outside.exists()
    assert outside.read_bytes() == b"must-stay"


def test_playwright_bridge_returns_managed_local_path_without_reading_body(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    workspace_id = uuid4()
    account_id = uuid4()
    transfer_id = uuid4()
    from src.downloaders.playwright_douyin_video_resolver import staging_path_for_aweme

    with patch("src.downloaders.download_staging.download_staging_root", return_value=staging_root):
        source_path = staging_path_for_aweme(
            "7647480428480563048",
            workspace_id=workspace_id,
            account_connection_id=account_id,
            transfer_id=transfer_id,
        )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"playwright-video")
    payload = {
        "aweme_id": "7647480428480563048",
        "staging_path": str(source_path),
        "size_bytes": source_path.stat().st_size,
        "format_id": "bit_rate|1080p|br100",
        "watermark_free": True,
        "height": 1080,
        "account_connection_id": str(account_id),
    }
    settings = SimpleNamespace(
        douyin_playwright_download_enabled=True,
        douyin_download_api_base_url="http://127.0.0.1:8000",
        douyin_playwright_download_timeout_ms=90_000,
    )
    request = DouyinVideoResolveRequest(
        aweme_id="7647480428480563048",
        page_url="https://www.douyin.com/video/7647480428480563048",
        session_cookie=None,
        user_agent=None,
        workspace_id=workspace_id,
        account_connection_id=account_id,
        transfer_id=transfer_id,
    )
    resolver = ApiBridgedPlaywrightDouyinResolver()

    with (
        patch("src.downloaders.download_staging.download_staging_root", return_value=staging_root),
        patch("src.downloaders.api_bridged_playwright_douyin_resolver.get_settings", return_value=settings),
        patch(
            "src.downloaders.api_bridged_playwright_douyin_resolver.urlrequest.urlopen",
            return_value=_JsonResponse(payload),
        ) as opener,
        patch.object(Path, "read_bytes", side_effect=AssertionError("bridge must not read the video body")),
    ):
        result = resolver.resolve(request)

    assert result.content is None
    assert result.local_path == str(source_path.resolve())
    assert result.size_bytes == source_path.stat().st_size
    assert result.cleanup_local_path is True
    sent = json.loads(opener.call_args.args[0].data.decode("utf-8"))
    assert sent["transfer_id"] == str(transfer_id)


def test_playwright_bridge_rejects_path_outside_managed_root(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    payload = {"staging_path": str(outside), "size_bytes": outside.stat().st_size}
    settings = SimpleNamespace(
        douyin_playwright_download_enabled=True,
        douyin_download_api_base_url="http://127.0.0.1:8000",
        douyin_playwright_download_timeout_ms=90_000,
    )
    request = DouyinVideoResolveRequest(
        aweme_id="1",
        page_url="https://www.douyin.com/video/1",
        session_cookie=None,
        user_agent=None,
        workspace_id=uuid4(),
    )

    with (
        patch("src.downloaders.download_staging.download_staging_root", return_value=staging_root),
        patch("src.downloaders.api_bridged_playwright_douyin_resolver.get_settings", return_value=settings),
        patch(
            "src.downloaders.api_bridged_playwright_douyin_resolver.urlrequest.urlopen",
            return_value=_JsonResponse(payload),
        ),
    ):
        with pytest.raises(DownloadError) as exc_info:
            ApiBridgedPlaywrightDouyinResolver().resolve(request)

    assert exc_info.value.code == DownloadErrorCode.RESOLVE_FAILED
    assert outside.exists()


def test_playwright_bridge_accepts_server_resolved_default_account_namespace(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    workspace_id = uuid4()
    resolved_account_id = uuid4()
    transfer_id = uuid4()
    from src.downloaders.playwright_douyin_video_resolver import staging_path_for_aweme

    with patch("src.downloaders.download_staging.download_staging_root", return_value=staging_root):
        source_path = staging_path_for_aweme(
            "7647480428480563048",
            workspace_id=workspace_id,
            account_connection_id=resolved_account_id,
            transfer_id=transfer_id,
        )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"playwright-video")
    payload = {
        "staging_path": str(source_path),
        "size_bytes": source_path.stat().st_size,
        "format_id": "bit_rate|1080p",
        "watermark_free": True,
        "account_connection_id": str(resolved_account_id),
    }
    settings = SimpleNamespace(
        douyin_playwright_download_enabled=True,
        douyin_download_api_base_url="http://127.0.0.1:8000",
        douyin_playwright_download_timeout_ms=90_000,
    )
    request = DouyinVideoResolveRequest(
        aweme_id="7647480428480563048",
        page_url="https://www.douyin.com/video/7647480428480563048",
        session_cookie=None,
        user_agent=None,
        workspace_id=workspace_id,
        account_connection_id=None,
        transfer_id=transfer_id,
    )

    with (
        patch("src.downloaders.download_staging.download_staging_root", return_value=staging_root),
        patch("src.downloaders.api_bridged_playwright_douyin_resolver.get_settings", return_value=settings),
        patch(
            "src.downloaders.api_bridged_playwright_douyin_resolver.urlrequest.urlopen",
            return_value=_JsonResponse(payload),
        ),
    ):
        result = ApiBridgedPlaywrightDouyinResolver().resolve(request)

    assert result.local_path == str(source_path.resolve())


def test_playwright_bridge_polling_propagates_cancel_to_shared_marker(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    request = DouyinVideoResolveRequest(
        aweme_id="7647480428480563048",
        page_url="https://www.douyin.com/video/7647480428480563048",
        session_cookie=None,
        user_agent=None,
        workspace_id=uuid4(),
        account_connection_id=uuid4(),
        transfer_id=uuid4(),
    )
    release = threading.Event()

    def blocking_open(*_args, **_kwargs):
        release.wait(timeout=2)
        return _JsonResponse({"ok": True})

    class Cancelled(Exception):
        pass

    request = DouyinVideoResolveRequest(
        **{
            **request.__dict__,
            "on_progress": lambda _done, _total: (_ for _ in ()).throw(Cancelled()),
        }
    )
    with (
        patch("src.downloaders.download_staging.download_staging_root", return_value=staging_root),
        patch(
            "src.downloaders.api_bridged_playwright_douyin_resolver.urlrequest.urlopen",
            side_effect=blocking_open,
        ),
        pytest.raises(Cancelled),
    ):
        _read_bridge_response(
            SimpleNamespace(),
            timeout=5,
            resolve_request=request,
        )
    release.set()

    with patch("src.downloaders.download_staging.download_staging_root", return_value=staging_root):
        expected = staging_path_for_aweme(
            request.aweme_id,
            workspace_id=request.workspace_id,
            account_connection_id=request.account_connection_id,
            transfer_id=request.transfer_id,
        )
    cancel_marker = expected.with_name(f".{expected.stem}.cancel")
    assert cancel_marker.exists()


def test_yt_dlp_returns_staged_local_path_without_reading_video(tmp_path: Path) -> None:
    resolver = YtDlpDouyinVideoResolver(binary="yt-dlp", format_selector="best", timeout_seconds=30)
    request = DouyinVideoResolveRequest(
        aweme_id="7647480428480563048",
        page_url="https://www.douyin.com/video/7647480428480563048",
        session_cookie="sessionid=abc",
        user_agent="Mozilla/5.0",
    )

    def fake_run(command, **_kwargs):
        output_template = command[command.index("-o") + 1]
        output_path = Path(output_template.replace("%(ext)s", "mp4"))
        output_path.write_bytes(b"yt-dlp-video")
        info_path = output_path.with_name(f"{output_path.stem}.info.json")
        info_path.write_text('{"format_id":"play","height":1080,"width":1920}', encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with (
        patch.object(resolver, "is_available", return_value=True),
        patch("src.downloaders.yt_dlp_douyin_resolver.subprocess.run", side_effect=fake_run),
        patch("src.downloaders.yt_dlp_douyin_resolver.staging_directory", return_value=tmp_path),
        patch(
            "src.downloaders.yt_dlp_douyin_resolver.get_settings",
            return_value=SimpleNamespace(douyin_download_allow_watermarked_fallback=False),
        ),
        patch.object(Path, "read_bytes", side_effect=AssertionError("yt-dlp resolver must not read video bytes")),
    ):
        result = resolver.resolve(request)

    assert result.content is None
    assert result.local_path is not None
    assert Path(result.local_path).is_file()
    assert result.size_bytes == len(b"yt-dlp-video")
    assert result.cleanup_local_path is True
