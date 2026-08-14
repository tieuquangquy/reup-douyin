from __future__ import annotations

import unittest
from datetime import UTC, datetime
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.downloaders.base import DownloadedObject
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.source_video_primary_fetcher import PrimaryVideoFetchResult
from src.enums import JobType, MediaAssetStatus, MediaAssetType, SourceVideoStatus
from src.services.download_service import (
    DownloadRequest,
    DownloadService,
    _local_file_fingerprint,
    _stable_transfer_id,
)
from src.storage.local import LocalStorageBackend


CHECKSUM = "a" * 64


def _asset(asset_type: MediaAssetType, *, checksum: str = CHECKSUM, size: int = 100):
    return SimpleNamespace(
        id=uuid4(),
        asset_type=asset_type,
        status=MediaAssetStatus.AVAILABLE,
        is_current=True,
        storage_key=f"cache/{asset_type.value.lower()}",
        size_bytes=size,
        checksum_sha256=checksum,
    )


def _source_video(*, thumbnail: bool = True):
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        source_platform="DOUYIN",
        source_video_external_id="7647480428480563048",
        source_url="https://www.douyin.com/video/7647480428480563048",
        caption=None,
        metadata_json={"thumbnail_url": "https://cdn.example/thumb.jpg"} if thumbnail else {},
        raw_payload_json=None,
        source_profile=SimpleNamespace(
            source_profile_external_id="profile-1",
            handle="creator",
            display_name="Creator",
        ),
        status=SourceVideoStatus.DISCOVERED,
    )


def _storage(*, checksum: str = CHECKSUM, size: int = 100):
    storage = MagicMock()
    storage.metadata.return_value = SimpleNamespace(
        exists=True,
        size_bytes=size,
        checksum_sha256=checksum,
    )
    return storage


def _video_probe(*, usable: bool = True):
    if usable:
        return SimpleNamespace(
            width=1080,
            height=1920,
            duration_seconds=20.0,
            video_codec="h264",
        )
    return SimpleNamespace(
        width=None,
        height=None,
        duration_seconds=20.0,
        video_codec=None,
    )


class DownloadServiceCacheFirstTests(unittest.TestCase):
    def test_valid_primary_and_thumbnail_cache_skip_all_network_fetches(self) -> None:
        source = _source_video(thumbnail=True)
        raw = _asset(MediaAssetType.SOURCE_VIDEO_RAW)
        thumbnail = _asset(MediaAssetType.THUMBNAIL)
        storage = _storage()
        downloader = MagicMock()
        primary_fetcher = MagicMock()
        media_probe = MagicMock(return_value=_video_probe())
        service = DownloadService(
            MagicMock(),
            storage=storage,
            downloader=downloader,
            primary_fetcher=primary_fetcher,
            media_probe=media_probe,
        )
        service._get_source_video = MagicMock(return_value=source)
        service._storage_context = MagicMock(return_value=SimpleNamespace())
        service._current_asset = MagicMock(
            side_effect=lambda _source_id, asset_type: {
                MediaAssetType.SOURCE_VIDEO_RAW: raw,
                MediaAssetType.THUMBNAIL: thumbnail,
            }.get(asset_type)
        )
        service._persist_json_asset = MagicMock(return_value=SimpleNamespace())
        service.get_manifest = MagicMock(return_value={"assets": ["cached"]})

        with patch("src.services.download_service.resolve_douyin_download_session") as resolve_session:
            manifest = service.run_download(source.id)

        self.assertEqual(manifest, {"assets": ["cached"]})
        resolve_session.assert_not_called()
        primary_fetcher.fetch.assert_not_called()
        downloader.fetch.assert_not_called()
        media_probe.assert_called_once_with(raw.storage_key)
        self.assertEqual(source.status, SourceVideoStatus.DOWNLOADED)

    def test_checksum_mismatch_rejects_cache_before_media_probe(self) -> None:
        source = _source_video(thumbnail=False)
        raw = _asset(MediaAssetType.SOURCE_VIDEO_RAW, checksum=CHECKSUM)
        media_probe = MagicMock(return_value=_video_probe())
        service = DownloadService(
            MagicMock(),
            storage=_storage(checksum="b" * 64),
            downloader=MagicMock(),
            primary_fetcher=MagicMock(),
            media_probe=media_probe,
        )

        self.assertIsNone(service._validate_cached_asset(source, raw, require_video=True))
        media_probe.assert_not_called()

    def test_audio_only_probe_rejects_nonempty_cached_mp4(self) -> None:
        source = _source_video(thumbnail=False)
        raw = _asset(MediaAssetType.SOURCE_VIDEO_RAW)
        service = DownloadService(
            MagicMock(),
            storage=_storage(),
            downloader=MagicMock(),
            primary_fetcher=MagicMock(),
            media_probe=MagicMock(return_value=_video_probe(usable=False)),
        )

        self.assertIsNone(service._validate_cached_asset(source, raw, require_video=True))

    def test_invalid_current_primary_is_downloaded_and_persisted_as_refresh(self) -> None:
        source = _source_video(thumbnail=False)
        raw = _asset(MediaAssetType.SOURCE_VIDEO_RAW)
        service = DownloadService(
            MagicMock(),
            storage=_storage(checksum="b" * 64),
            downloader=MagicMock(),
            primary_fetcher=MagicMock(),
            media_probe=MagicMock(return_value=_video_probe()),
        )
        service._get_source_video = MagicMock(return_value=source)
        service._storage_context = MagicMock(return_value=SimpleNamespace())
        service._current_asset = MagicMock(return_value=raw)
        primary_result = PrimaryVideoFetchResult(
            downloaded=DownloadedObject(b"fresh-video", "video/mp4", "fresh.mp4"),
            resolver_name="test",
            source_url=source.source_url,
            watermark_free=True,
        )
        service._fetch_primary_video = MagicMock(return_value=primary_result)
        service._persist_primary_video = MagicMock(return_value=SimpleNamespace())
        service._persist_json_asset = MagicMock(return_value=SimpleNamespace())
        service.get_manifest = MagicMock(return_value={"assets": ["fresh"]})

        with patch(
            "src.services.download_service.resolve_douyin_download_session",
            return_value=SimpleNamespace(),
        ):
            service.run_download(source.id)

        service._fetch_primary_video.assert_called_once()
        self.assertTrue(service._persist_primary_video.call_args.kwargs["force_refresh"])

    def test_selected_account_is_preserved_from_session_to_primary_resolver(self) -> None:
        source = _source_video(thumbnail=False)
        selected_account_id = uuid4()
        primary_fetcher = MagicMock()
        primary_fetcher.fetch.return_value = PrimaryVideoFetchResult(
            downloaded=DownloadedObject(b"video", "video/mp4", "video.mp4"),
            resolver_name="test",
            source_url=source.source_url,
            watermark_free=True,
        )
        service = DownloadService(
            MagicMock(),
            storage=_storage(),
            downloader=MagicMock(),
            primary_fetcher=primary_fetcher,
            media_probe=MagicMock(return_value=_video_probe()),
        )

        service._fetch_primary_video(
            source,
            SimpleNamespace(
                session_cookie="sessionid=x",
                user_agent="ua",
                proxy_url=None,
                playwright_cookies=(),
                cookie_source="browser_store",
            ),
            account_connection_id=selected_account_id,
        )

        self.assertEqual(
            primary_fetcher.fetch.call_args.kwargs["account_connection_id"],
            selected_account_id,
        )


if __name__ == "__main__":
    unittest.main()


def test_recent_unchanged_local_cache_skips_full_hash_and_ffprobe() -> None:
    source = _source_video(thumbnail=False)
    with TemporaryDirectory() as temp_dir:
        storage = LocalStorageBackend(temp_dir)
        written = storage.write_bytes("workspace/video/raw.mp4", b"cached-video")
        asset = _asset(
            MediaAssetType.SOURCE_VIDEO_RAW,
            checksum=written.checksum_sha256,
            size=written.size_bytes,
        )
        asset.storage_key = written.storage_key
        asset.metadata_json = {
            "local_file_fingerprint": _local_file_fingerprint(written.absolute_path),
            "integrity_verified_at": datetime.now(UTC).isoformat(),
            "media_probe": {
                "width": 1080,
                "height": 1920,
                "duration_seconds": 5.0,
                "video_codec": "h264",
            },
        }
        original_metadata = storage.metadata
        storage.metadata = MagicMock(side_effect=AssertionError("full SHA-256 must be skipped"))
        path_probe = MagicMock(side_effect=AssertionError("ffprobe must be skipped"))
        service = DownloadService(
            MagicMock(),
            storage=storage,
            downloader=MagicMock(),
            primary_fetcher=MagicMock(),
            media_probe=MagicMock(),
            media_path_probe=path_probe,
        )

        assert service._validate_cached_asset(source, asset, require_video=True) is asset
        storage.metadata.assert_not_called()
        path_probe.assert_not_called()
        storage.metadata = original_metadata


def test_idempotency_replay_compares_effective_account_binding() -> None:
    source = _source_video(thumbnail=False)
    selected_account = uuid4()
    existing = SimpleNamespace(
        id=uuid4(),
        job_type=JobType.DOWNLOAD_VIDEO,
        source_video_id=source.id,
        payload_json={"account_connection_id": str(uuid4()), "force_refresh": False},
        status="QUEUED",
    )
    db = MagicMock()
    db.scalar.return_value = existing
    service = DownloadService(
        db,
        storage=_storage(),
        downloader=MagicMock(),
        primary_fetcher=MagicMock(),
        media_probe=MagicMock(return_value=_video_probe()),
    )
    service._resolve_source_video = MagicMock(return_value=source)

    with patch(
        "src.services.download_service._account_for_workspace",
        return_value=SimpleNamespace(id=selected_account),
    ):
        with pytest.raises(DownloadError) as caught:
            service.create_download_job(
                DownloadRequest(
                    source_video_id=source.id,
                    account_connection_id=selected_account,
                ),
                idempotency_key="download-command",
            )

    assert caught.value.code == DownloadErrorCode.VALIDATION_FAILED
    assert "different Douyin account" in caught.value.message


def test_default_idempotency_key_uses_canonical_source_and_effective_account() -> None:
    source = _source_video(thumbnail=False)
    selected_account = uuid4()
    created_job = SimpleNamespace(id=uuid4(), status="QUEUED")
    db = MagicMock()
    db.scalar.return_value = None
    service = DownloadService(
        db,
        storage=_storage(),
        downloader=MagicMock(),
        primary_fetcher=MagicMock(),
        media_probe=MagicMock(return_value=_video_probe()),
    )
    # Both public selectors resolve to this same canonical source object.
    service._resolve_source_video = MagicMock(return_value=source)
    service.get_manifest = MagicMock(return_value={"assets": []})

    with patch(
        "src.services.download_service._account_for_workspace",
        return_value=SimpleNamespace(id=selected_account),
    ), patch(
        "src.services.download_service.sync_download_cookie_store_from_live_browser"
    ), patch("src.services.download_service.JobService") as job_service_type:
        job_service_type.return_value.create_job.return_value = created_job
        service.create_download_job(DownloadRequest(candidate_id=uuid4()))

    create_kwargs = job_service_type.return_value.create_job.call_args.kwargs
    assert create_kwargs["source_video_id"] == source.id
    assert create_kwargs["idempotency_key"] == f"download:{source.id}:{selected_account}"
    assert create_kwargs["payload_json"]["account_connection_id"] == str(selected_account)
    assert create_kwargs["payload_json"]["transfer_id"] == _stable_transfer_id(
        source.id,
        selected_account,
        create_kwargs["idempotency_key"],
    )


def test_invalid_source_account_binding_fails_before_idempotency_replay() -> None:
    source = _source_video(thumbnail=False)
    source.metadata_json = {"douyin_account_connection_id": "not-a-uuid"}
    service = DownloadService(
        MagicMock(),
        storage=_storage(),
        downloader=MagicMock(),
        primary_fetcher=MagicMock(),
        media_probe=MagicMock(return_value=_video_probe()),
    )
    service._resolve_source_video = MagicMock(return_value=source)

    with pytest.raises(DownloadError) as caught:
        service.create_download_job(
            DownloadRequest(source_video_id=source.id),
            idempotency_key="download-command",
        )

    assert caught.value.code == DownloadErrorCode.VALIDATION_FAILED
    assert "invalid Douyin account binding" in caught.value.message
