from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.enums import SourcePlatformEnum
from src.main import app
from src.db.session import get_session_factory
from src.models.capture_inbox import CaptureSession, CapturedItem


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="POST one full-modal-harvest payload into the backend and verify DB fields update for a known aweme_id."
    )
    parser.add_argument("--session-id", type=str, default=None)
    parser.add_argument("--aweme-id", type=str, default="7633842656648416518")
    parser.add_argument("--duration-seconds", type=float, default=563.3)
    parser.add_argument("--like-count", type=int, default=392)
    parser.add_argument("--comment-count", type=int, default=10)
    parser.add_argument("--share-count", type=int, default=1)
    return parser.parse_args()


def _resolve_target(session_id: str | None, aweme_id: str | None) -> tuple[CaptureSession, CapturedItem]:
    session_factory = get_session_factory()
    with session_factory() as db:
        if session_id:
            session = db.execute(select(CaptureSession).where(CaptureSession.id == UUID(session_id))).scalar_one_or_none()
        else:
            session = db.execute(
                select(CaptureSession)
                .where(CaptureSession.source_platform == SourcePlatformEnum.DOUYIN)
                .order_by(CaptureSession.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        if session is None:
            raise SystemExit("No Douyin capture session found. Run a real capture first.")

        stmt = select(CapturedItem).where(CapturedItem.capture_session_id == session.id)
        if aweme_id:
            stmt = stmt.where(CapturedItem.source_video_external_id == aweme_id)
        item = db.execute(stmt.order_by(CapturedItem.created_at.asc()).limit(1)).scalar_one_or_none()
        if item is None:
            raise SystemExit("No captured item found for the target session/aweme_id.")
        if not item.source_video_external_id:
            raise SystemExit("Target item has no source_video_external_id/aweme_id to smoke-test.")
        return session, item


def _post_payload(capture_session_id: str, aweme_id: str, *, duration_seconds: float, like_count: int, comment_count: int, share_count: int) -> dict[str, Any]:
    payload = {
        "schema_version": "douyin_full_modal_harvest.v1",
        "capture_session_id": capture_session_id,
        "started_at": "2026-05-01T00:00:00Z",
        "page": {
            "url": f"https://www.douyin.com/video/{aweme_id}",
            "title": "Smoke modal harvest",
            "page_type": "video_detail_page",
            "video_link_count": 1,
        },
        "capture_context": {
            "capture_id": "smoke-full-modal-harvest",
            "page_url": f"https://www.douyin.com/video/{aweme_id}",
        },
        "items": [
            {
                "aweme_id": aweme_id,
                "source_url": f"https://www.douyin.com/video/{aweme_id}",
                "target_aweme_id": aweme_id,
                "modal_aweme_id_before_extract": aweme_id,
                "modal_aweme_id_after_extract": aweme_id,
                "extracted_aweme_id": aweme_id,
                "data_integrity_status": "ok",
                "metric_signature": f"sig:{aweme_id}:{like_count}:{comment_count}:na:{share_count}",
                "raw_dom_detail_metrics": {
                    "duration_seconds": duration_seconds,
                    "like_count": like_count,
                    "comment_count": comment_count,
                    "share_count": share_count,
                    "extraction_source": "dom_detail_modal",
                    "confidence": "high",
                },
                "raw_detail_aweme": None,
                "raw_evidence_summary": {
                    "has_network_aweme": False,
                    "has_detail_aweme": False,
                    "has_dom_snapshot": False,
                    "has_dom_detail_metrics": True,
                    "network_keys": [],
                    "detail_keys": [],
                    "dom_detail_metric_keys": [
                        "duration_seconds",
                        "like_count",
                        "comment_count",
                        "share_count",
                    ],
                    "evidence_sources": ["full_modal_auto_harvest", "dom_detail_modal"],
                    "evidence_collection_version": "phase6h_full_modal_auto_harvest",
                },
            }
        ],
        "progress": {
            "running": False,
            "target_count": 1,
            "current_aweme_id": aweme_id,
            "harvested_count": 1,
            "updated_count": 0,
            "duplicate_count": 0,
            "failed_count": 0,
            "flushed_count": 0,
            "last_error": None,
            "stopped_reason": "smoke_test",
        },
        "diagnostics": {
            "extension_source": "smoke_full_modal_harvest_ingest",
        },
    }
    with TestClient(app) as client:
        response = client.post("/douyin-extension/full-modal-harvest", json=payload)
    return {"status_code": response.status_code, "body": response.json()}


def _reload_item(capture_session_id: UUID, aweme_id: str) -> dict[str, Any]:
    session_factory = get_session_factory()
    with session_factory() as db:
        item = db.execute(
            select(CapturedItem).where(
                CapturedItem.capture_session_id == capture_session_id,
                CapturedItem.source_video_external_id == aweme_id,
            )
        ).scalar_one()
        metadata = item.metadata_json if isinstance(item.metadata_json, dict) else {}
        return {
            "item_id": str(item.id),
            "capture_session_id": str(capture_session_id),
            "aweme_id": aweme_id,
            "duration_seconds": item.duration_seconds,
            "like_count": metadata.get("like_count"),
            "comment_count": metadata.get("comment_count"),
            "share_count": metadata.get("share_count"),
            "raw_dom_detail_metrics_present": isinstance(metadata.get("raw_dom_detail_metrics"), dict),
            "has_dom_detail_metrics": bool((metadata.get("raw_evidence_summary") or {}).get("has_dom_detail_metrics")),
            "performance_status": metadata.get("performance_status"),
            "processing_fit_status": metadata.get("processing_fit_status"),
            "metadata_status": metadata.get("metadata_status"),
        }


def main() -> None:
    args = _parse_args()
    session, item = _resolve_target(args.session_id, args.aweme_id)
    response = _post_payload(
        str(session.id),
        str(item.source_video_external_id).strip(),
        duration_seconds=args.duration_seconds,
        like_count=args.like_count,
        comment_count=args.comment_count,
        share_count=args.share_count,
    )
    item_after = _reload_item(session.id, str(item.source_video_external_id).strip())
    print(
        json.dumps(
            {
                "session_id": str(session.id),
                "aweme_id": str(item.source_video_external_id).strip(),
                "post_result": response,
                "item_after": item_after,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
