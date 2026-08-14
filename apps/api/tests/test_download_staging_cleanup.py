from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.downloaders.download_staging import (
    cleanup_stale_staging,
    download_staging_root,
    is_managed_staging_path,
    staging_directory,
)


def test_cleanup_stale_staging_removes_only_expired_files(tmp_path: Path) -> None:
    old_file = tmp_path / "a" / "old.mp4"
    fresh_file = tmp_path / "b" / "fresh.mp4"
    old_file.parent.mkdir(parents=True)
    fresh_file.parent.mkdir(parents=True)
    old_file.write_bytes(b"old")
    fresh_file.write_bytes(b"fresh")
    now = time.time()
    os.utime(old_file, (now - 86_400, now - 86_400))

    with patch("src.downloaders.download_staging.download_staging_root", return_value=tmp_path):
        freed = cleanup_stale_staging(ttl_seconds=3600, now=now)

    assert freed == 3
    assert not old_file.exists()
    assert fresh_file.exists()


def test_cleanup_does_not_touch_legacy_sibling_root(tmp_path: Path) -> None:
    """The v2 sweeper must not delete historical regression-source files."""
    managed = tmp_path / "download_staging_v2"
    legacy = tmp_path / "download_staging"
    managed_file = managed / "workspace" / "account" / "aweme" / "transfer" / "old.part"
    legacy_file = legacy / "old-source.mp4"
    managed_file.parent.mkdir(parents=True)
    legacy.mkdir(parents=True)
    managed_file.write_bytes(b"partial")
    legacy_file.write_bytes(b"source")
    now = time.time()
    os.utime(managed_file, (now - 86_400, now - 86_400))
    os.utime(legacy_file, (now - 86_400, now - 86_400))

    with patch("src.downloaders.download_staging.download_staging_root", return_value=managed):
        freed = cleanup_stale_staging(ttl_seconds=3600, now=now)

    assert freed == len(b"partial")
    assert not managed_file.exists()
    assert legacy_file.exists()


def test_download_staging_root_prefers_canonical_override() -> None:
    canonical = Path("C:/tmp/reup-download-v2")
    alias = Path("C:/tmp/legacy-playwright-staging")
    settings = SimpleNamespace(
        douyin_download_staging_dir=str(canonical),
        douyin_playwright_download_staging_dir=str(alias),
    )

    with patch("src.downloaders.download_staging.get_settings", return_value=settings):
        assert download_staging_root() == canonical.resolve()


def test_download_staging_root_accepts_deprecated_alias() -> None:
    alias = Path("C:/tmp/legacy-playwright-staging")
    settings = SimpleNamespace(
        douyin_download_staging_dir=None,
        douyin_playwright_download_staging_dir=str(alias),
    )

    with patch("src.downloaders.download_staging.get_settings", return_value=settings):
        assert download_staging_root() == alias.resolve()


def test_managed_path_boundary_does_not_match_prefix_sibling(tmp_path: Path) -> None:
    managed = tmp_path / "download_staging_v2"
    sibling = tmp_path / "download_staging_v20" / "video.mp4"
    sibling.parent.mkdir(parents=True)
    sibling.write_bytes(b"legacy")

    with patch("src.downloaders.download_staging.download_staging_root", return_value=managed):
        assert not is_managed_staging_path(sibling)


def test_staging_directory_is_namespaced_and_confined(tmp_path: Path) -> None:
    with patch("src.downloaders.download_staging.download_staging_root", return_value=tmp_path):
        path = staging_directory(
            aweme_id="aweme/with spaces",
            workspace_id="workspace-1",
            account_connection_id="account-1",
            transfer_id="transfer-1",
        )

    assert path == tmp_path / "workspace-1" / "account-1" / "awemewithspaces" / "transfer-1"
    assert path.is_dir()
    assert path.resolve().is_relative_to(tmp_path.resolve())
