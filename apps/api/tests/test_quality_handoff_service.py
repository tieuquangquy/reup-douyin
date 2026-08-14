from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.services.quality_handoff_service import (
    QualityHandoffError,
    QualityHandoffService,
)


def _service(tmp_path):
    source = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        source_video_external_id="video-001",
    )
    db = MagicMock()
    db.get.return_value = source
    db.scalar.return_value = None
    storage = SimpleNamespace(root=tmp_path.resolve())
    service = QualityHandoffService(db, storage=storage)
    return service, source


def test_quality_handoff_summary_exposes_all_phase5_gates(tmp_path) -> None:
    service, source = _service(tmp_path)
    package = tmp_path / "export_packages" / "pkg"
    package.mkdir(parents=True)
    (tmp_path / "phase5_final_approval.json").write_text(
        '{"status":"FINAL_APPROVED"}', encoding="utf-8"
    )
    (tmp_path / "phase5_metadata_approval.json").write_text(
        '{"status":"METADATA_APPROVED"}', encoding="utf-8"
    )
    (tmp_path / "phase5_rights_music_approval.json").write_text(
        '{"status":"SOURCE_RIGHTS_AND_MUSIC_APPROVED"}', encoding="utf-8"
    )
    (tmp_path / "phase5_export_handoff.json").write_text(
        json.dumps(
            {
                "status": "MANUAL_EXPORT_READY",
                "package": {"path": "export_packages/pkg"},
                "next_gate": "OPERATOR_MANUAL_UPLOAD",
                "external_publish_triggered": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "phase5_manual_export_handoff.json").write_text(
        json.dumps(
            {
                "status": "MANUAL_EXPORT_READY",
                "archive": {
                    "path": "manual_exports/pkg.zip",
                    "sha256": "a" * 64,
                    "size_bytes": 123,
                },
            }
        ),
        encoding="utf-8",
    )
    (package / "publish_draft.json").write_text(
        '{"status":"METADATA_APPROVED","title":"Title"}', encoding="utf-8"
    )
    with patch(
        "src.services.quality_handoff_service.QualityLocalizationService.active_root",
        return_value=tmp_path.resolve(),
    ):
        summary = service.summary(source.id)

    assert summary["final_approval_status"] == "FINAL_APPROVED"
    assert summary["metadata_status"] == "METADATA_APPROVED"
    assert summary["rights_status"] == "SOURCE_RIGHTS_AND_MUSIC_APPROVED"
    assert summary["manual_export_status"] == "MANUAL_EXPORT_READY"
    assert summary["archive_path"] == "manual_exports/pkg.zip"
    assert summary["external_publish_triggered"] is False


def test_rights_gate_requires_all_explicit_attestations(tmp_path) -> None:
    service, source = _service(tmp_path)
    with pytest.raises(QualityHandoffError, match="All source-rights"):
        service.approve_rights(
            source.id,
            operator_id="operator",
            source_video_reuse_authorized=True,
            retained_music_use_authorized=False,
            operator_accepts_responsibility=True,
        )


def test_final_approval_is_idempotent_when_handoff_exists(tmp_path) -> None:
    service, source = _service(tmp_path)
    (tmp_path / "phase5_export_handoff.json").write_text(
        '{"status":"READY_FOR_OPERATOR"}', encoding="utf-8"
    )
    with patch.object(service, "_root", return_value=tmp_path.resolve()), patch.object(
        service,
        "summary",
        return_value={"final_approval_status": "FINAL_APPROVED"},
    ), patch(
        "src.services.quality_handoff_service.create_local_final_handoff"
    ) as create:
        result = service.approve_final(source.id, operator_id="operator")

    create.assert_not_called()
    assert result["final_approval_status"] == "FINAL_APPROVED"
