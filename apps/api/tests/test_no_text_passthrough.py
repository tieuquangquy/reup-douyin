from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.services.no_text_passthrough import (
    NoTextPassthroughError,
    build_no_text_contract,
    load_no_text_authority,
)


def _sha_json(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_authority(root: Path) -> Path:
    source = root / "source.webm"
    source.write_bytes(b"source")
    review = {
        "status": "NO_TEXT_OPERATOR_REVIEW_REQUIRED",
        "source_video": {
            "path": str(source),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "size_bytes": source.stat().st_size,
        },
    }
    review["review_sha256"] = _sha_json(review)
    review_path = root / "phase1_no_text_review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    approval = {
        "status": "NO_TEXT_OPERATOR_APPROVED",
        "decision": "NO_TEXT_CONFIRMED",
        "review_ref": {
            "path": review_path.name,
            "sha256": review["review_sha256"],
        },
    }
    approval["approval_sha256"] = _sha_json(approval)
    (root / "phase1_no_text_approval.json").write_text(
        json.dumps(approval), encoding="utf-8"
    )
    return source


def test_loads_hash_bound_no_text_authority() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _write_authority(root)
        authority = load_no_text_authority(root)
        assert authority["source"] == source.resolve()
        assert len(authority["approval_sha256"]) == 64


def test_rejects_source_drift() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _write_authority(root)
        source.write_bytes(b"changed")
        with pytest.raises(NoTextPassthroughError, match="source video authority"):
            load_no_text_authority(root)


def test_builds_empty_render_contract() -> None:
    authority = {
        "source": Path("source.webm"),
        "source_sha256": "a" * 64,
        "approval_sha256": "b" * 64,
        "approval_file_sha256": "c" * 64,
    }
    contract = build_no_text_contract(
        authority=authority,
        probe={
            "width": 1920,
            "height": 1080,
            "frame_count": 24,
            "fps": 24.0,
            "video": {},
        },
    )
    assert contract["render_tracks"] == []
    assert contract["counts"]["render_tracks"] == 0
    assert contract["authorities"]["audio"]["strategy"] == (
        "drop_verified_silent_or_absent_source_audio"
    )
