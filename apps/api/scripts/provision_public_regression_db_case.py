"""Provision a public local-regression source into canonical DB boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from src.core.settings import get_settings
from src.db.session import get_session_factory
from src.enums import (
    CandidateStatus,
    MediaAssetStatus,
    MediaAssetType,
    ReupQueueMediaPrepStatus,
    ReupQueueStatus,
    SourcePlatformEnum,
    SourceProfileStatus,
    SourceVideoStatus,
)
from src.models.ingestion import SourceProfile, SourceVideo
from src.models.media import MediaAsset
from src.models.review import VideoCandidate
from src.models.reup_queue import ReupQueueItem
from src.storage.local import LocalStorageBackend
from src.storage.path_strategy import VideoStorageContext, asset_logical_key


class PublicRegressionProvisionError(RuntimeError):
    pass


API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_public_source(manifest_path: Path, external_id: str) -> dict:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PublicRegressionProvisionError("Public source manifest is invalid")
    unsigned = dict(payload)
    claimed = str(unsigned.pop("manifest_sha256", "") or "")
    encoded = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(claimed) != 64 or hashlib.sha256(encoded).hexdigest() != claimed:
        raise PublicRegressionProvisionError("Public source manifest hash is invalid")
    matches = [
        dict(row)
        for row in list(payload.get("sources") or [])
        if Path(str(dict(row).get("filename") or "")).stem == external_id
    ]
    if len(matches) != 1:
        raise PublicRegressionProvisionError("Public source entry was not found")
    source = matches[0]
    path = (WORKSPACE_ROOT / str(source.get("source_path") or "")).resolve()
    if (
        not path.is_relative_to(WORKSPACE_ROOT)
        or not path.is_file()
        or path.stat().st_size != int(source.get("size_bytes") or -1)
        or _sha256_file(path) != str(source.get("sha256") or "")
    ):
        raise PublicRegressionProvisionError("Public source file authority drifted")
    source["absolute_path"] = path
    source["manifest_sha256"] = claimed
    return source


def provision(*, manifest_path: Path, external_id: str, workspace_id: UUID) -> dict:
    entry = load_public_source(manifest_path.resolve(), external_id)
    storage = LocalStorageBackend(get_settings().local_storage_root)
    profile_external_id = "local-public-regression-fixtures"
    with get_session_factory()() as db:
        profile = db.scalar(
            select(SourceProfile).where(
                SourceProfile.source_platform == SourcePlatformEnum.DOUYIN,
                SourceProfile.source_profile_external_id == profile_external_id,
            )
        )
        if profile is None:
            profile = SourceProfile(
                workspace_id=workspace_id,
                source_platform=SourcePlatformEnum.DOUYIN,
                source_profile_external_id=profile_external_id,
                profile_url="https://commons.wikimedia.org/",
                display_name="Local public regression fixtures",
                handle="local_public_regression",
                status=SourceProfileStatus.ACTIVE,
                metadata_json={
                    "source_kind": "PUBLIC_REGRESSION_FIXTURE",
                    "local_regression_only": True,
                },
            )
            db.add(profile)
            db.flush()
        elif profile.workspace_id != workspace_id:
            raise PublicRegressionProvisionError(
                "Regression fixture profile belongs to another workspace"
            )

        source = db.scalar(
            select(SourceVideo).where(
                SourceVideo.source_platform == SourcePlatformEnum.DOUYIN,
                SourceVideo.source_video_external_id == external_id,
            )
        )
        if source is None:
            source = SourceVideo(
                workspace_id=workspace_id,
                source_profile_id=profile.id,
                source_platform=SourcePlatformEnum.DOUYIN,
                source_video_external_id=external_id,
                source_url=str(entry.get("source_page_url") or ""),
                caption=None,
                duration_seconds=float(dict(entry.get("probe") or {}).get("duration_seconds") or 0.0),
                status=SourceVideoStatus.DOWNLOADED,
                metadata_json={
                    "source_kind": "PUBLIC_REGRESSION_FIXTURE",
                    "local_regression_only": True,
                    "license": entry.get("license"),
                    "license_url": entry.get("license_url"),
                    "attribution_required": bool(entry.get("attribution_required")),
                    "public_source_manifest_sha256": entry["manifest_sha256"],
                },
                raw_payload_json={"public_regression_source": True},
            )
            db.add(source)
            db.flush()
        elif source.workspace_id != workspace_id:
            raise PublicRegressionProvisionError("Source belongs to another workspace")

        candidate = db.scalar(
            select(VideoCandidate).where(VideoCandidate.source_video_id == source.id)
        )
        if candidate is None:
            candidate = VideoCandidate(
                workspace_id=workspace_id,
                source_video_id=source.id,
                status=CandidateStatus.APPROVED,
                score=100.0,
                score_version="public_regression_fixture_v1",
                score_label="regression_control",
                priority=0,
                metadata_json={"local_regression_only": True},
            )
            db.add(candidate)
            db.flush()

        queue = db.scalar(
            select(ReupQueueItem).where(
                ReupQueueItem.workspace_id == workspace_id,
                ReupQueueItem.video_candidate_id == candidate.id,
            )
        )
        if queue is None:
            queue = ReupQueueItem(
                workspace_id=workspace_id,
                video_candidate_id=candidate.id,
                source_video_id=source.id,
                status=ReupQueueStatus.READY_FOR_PROCESSING,
                media_prep_status=ReupQueueMediaPrepStatus.NOT_STARTED,
                priority=0,
                queued_reason="public_regression_fixture",
                metadata_json={"local_regression_only": True},
            )
            db.add(queue)
            db.flush()

        assets = list(
            db.scalars(
                select(MediaAsset).where(
                    MediaAsset.source_video_id == source.id,
                    MediaAsset.asset_type == MediaAssetType.SOURCE_VIDEO_RAW,
                )
            )
        )
        checksum = str(entry["sha256"])
        asset = next((row for row in assets if row.checksum_sha256 == checksum), None)
        asset_reused = asset is not None
        if asset is None:
            context = VideoStorageContext(
                workspace_id=str(workspace_id),
                source_platform=SourcePlatformEnum.DOUYIN,
                source_profile_external_id=profile_external_id,
                source_video_external_id=external_id,
                profile_handle=profile.handle,
                profile_display_name=profile.display_name,
            )
            logical_key = asset_logical_key(
                context,
                MediaAssetType.SOURCE_VIDEO_RAW,
                filename=str(entry["filename"]),
            )
            written = storage.write_bytes(logical_key, Path(entry["absolute_path"]).read_bytes())
            if written.checksum_sha256 != checksum:
                raise PublicRegressionProvisionError("Stored source checksum drifted")
            for row in assets:
                row.is_current = False
            asset = MediaAsset(
                workspace_id=workspace_id,
                source_video_id=source.id,
                asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
                status=MediaAssetStatus.AVAILABLE,
                version=max((row.version for row in assets), default=0) + 1,
                storage_provider=written.storage_provider,
                storage_key=written.storage_key,
                logical_key=logical_key,
                relative_path=written.relative_path,
                manifest_group="public_regression_fixture",
                is_current=True,
                source_url=str(entry.get("download_url") or ""),
                mime_type="video/webm",
                size_bytes=written.size_bytes,
                checksum_sha256=written.checksum_sha256,
                metadata_json={
                    "local_regression_only": True,
                    "license": entry.get("license"),
                    "public_source_manifest_sha256": entry["manifest_sha256"],
                },
            )
            db.add(asset)
        else:
            asset.is_current = True
        db.commit()
        return {
            "status": "PUBLIC_REGRESSION_DB_CASE_READY",
            "source_video_id": str(source.id),
            "video_candidate_id": str(candidate.id),
            "queue_item_id": str(queue.id),
            "source_asset_id": str(asset.id),
            "source_video_external_id": external_id,
            "source_video_sha256": checksum,
            "asset_reused": asset_reused,
            "local_regression_only": True,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.provision_public_regression_db_case"
    )
    parser.add_argument("manifest")
    parser.add_argument("external_id")
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        result = provision(
            manifest_path=Path(args.manifest),
            external_id=str(args.external_id),
            workspace_id=UUID(str(args.workspace_id)),
        )
    except (OSError, ValueError, PublicRegressionProvisionError) as exc:
        print(f"[PUBLIC-REGRESSION-DB][FAIL] {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
