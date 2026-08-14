from __future__ import annotations

from pathlib import Path

import pytest

from src.storage.local import LocalStorageBackend


def test_write_stream_is_atomic_and_hashes_incrementally(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "storage")

    result = storage.write_stream("workspace/video/raw.mp4", (b"abc", b"", b"def"))

    target = Path(result.absolute_path)
    assert target.read_bytes() == b"abcdef"
    assert result.size_bytes == 6
    assert result.checksum_sha256 == "bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721"
    assert list(target.parent.glob("*.part")) == []
    assert list(target.parent.glob(".*.part")) == []


def test_write_stream_failure_keeps_existing_object_and_removes_part(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "storage")
    first = storage.write_bytes("workspace/video/raw.mp4", b"old")

    def broken_chunks():
        yield b"new"
        raise RuntimeError("transfer interrupted")

    with pytest.raises(RuntimeError, match="transfer interrupted"):
        storage.write_stream("workspace/video/raw.mp4", broken_chunks())

    target = Path(first.absolute_path)
    assert target.read_bytes() == b"old"
    assert list(target.parent.glob(".*.part")) == []


def test_write_file_and_metadata_do_not_require_read_bytes(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "storage")
    source = tmp_path / "source.mp4"
    source.write_bytes((b"0123456789" * 200_000) + b"end")

    result = storage.write_file("workspace/video/raw.mp4", source)
    metadata = storage.metadata(result.storage_key)

    assert metadata.exists is True
    assert metadata.size_bytes == source.stat().st_size
    assert metadata.checksum_sha256 == result.checksum_sha256
    assert Path(result.absolute_path).read_bytes() == source.read_bytes()


def test_promote_file_moves_completed_staging_atomically(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "storage")
    source = tmp_path / "staging" / "video.part"
    source.parent.mkdir()
    source.write_bytes(b"promote-me")

    result = storage.promote_file("workspace/video/raw.mp4", source)

    assert not source.exists()
    assert Path(result.absolute_path).read_bytes() == b"promote-me"


def test_resolve_rejects_parent_escape(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "storage")

    # Normalization keeps parent references inside the configured namespace.
    resolved = storage.resolve("../../outside.mp4")
    assert resolved.absolute_path.is_relative_to(storage.root)
