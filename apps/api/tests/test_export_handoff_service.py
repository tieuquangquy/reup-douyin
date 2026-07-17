from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from uuid import uuid4

from src.enums import PublishTargetPlatform, ReupQueueBatchAction, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.models.export_handoff import ExportPackage, PublishHandoff
from src.services.export_handoff_service import ExportHandoffService


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def unique(self):
        return self.values

    def __iter__(self):
        return iter(self.values)


class FakeExportHandoffDb:
    def __init__(self, items):
        self.items = items
        self.added = []
        self.commits = 0
        self.refreshed = []
        self.flushes = 0
        self.packages = []
        self.handoffs = []

    def scalars(self, _stmt):
        return FakeScalarResult(self.items)

    def scalar(self, _stmt):
        for item in reversed(self.added):
            if isinstance(item, ExportPackage):
                return item
        return None

    def add(self, item):
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        now = datetime(2026, 4, 27, tzinfo=UTC)
        if getattr(item, "created_at", None) is None:
            item.created_at = now
        if getattr(item, "updated_at", None) is None:
            item.updated_at = now
        self.added.append(item)
        if isinstance(item, ExportPackage):
            item.items = []
            item.publish_handoffs = []
            self.packages.append(item)
        elif isinstance(item, PublishHandoff):
            self.handoffs.append(item)
        elif hasattr(item, "export_package"):
            item.reup_queue_item = next((queue_item for queue_item in self.items if queue_item.id == item.reup_queue_item_id), None)
            item.export_package.items.append(item)

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def refresh(self, item):
        self.refreshed.append(item)


def queue_item(**overrides):
    defaults = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "video_candidate_id": uuid4(),
        "source_video_id": uuid4(),
        "render_output_id": uuid4(),
        "publish_draft_id": uuid4(),
        "status": ReupQueueStatus.READY_TO_EXPORT,
        "media_prep_status": ReupQueueMediaPrepStatus.READY_FOR_EXPORT,
        "media_prep_notes": "ready",
        "blocked_reason": None,
        "last_action_at": None,
        "last_action_note": None,
        "metadata_json": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class ExportHandoffServiceTests(unittest.TestCase):
    def test_create_export_package_includes_only_ready_to_export_items(self) -> None:
        workspace_id = uuid4()
        ready = queue_item(workspace_id=workspace_id)
        ineligible = queue_item(workspace_id=workspace_id, status=ReupQueueStatus.PROCESSING)
        fake_db = FakeExportHandoffDb([ready, ineligible])

        package, result = ExportHandoffService(fake_db).create_export_package(
            item_ids=[ready.id, ineligible.id],
            label="Operator package",
            operator_note="Package ready rows",
        )

        self.assertEqual(result.requested_count, 2)
        self.assertEqual(result.succeeded_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(package.item_count, 1)
        self.assertEqual(ready.status, ReupQueueStatus.EXPORT_PACKAGE_CREATED)
        self.assertEqual(ready.metadata_json["export_package_id"], str(package.id))
        self.assertEqual(result.export_package_id, package.id)
        self.assertEqual(result.results[1].reason_code, "INELIGIBLE_STATUS")
        self.assertEqual(fake_db.commits, 1)
        self.assertGreaterEqual(fake_db.flushes, 1)

    def test_create_publish_handoff_marks_packaged_items_for_handoff_without_external_publish(self) -> None:
        workspace_id = uuid4()
        ready = queue_item(workspace_id=workspace_id)
        fake_db = FakeExportHandoffDb([ready])
        package, _result = ExportHandoffService(fake_db).create_export_package(item_ids=[ready.id], label="Package")

        handoff = ExportHandoffService(fake_db).create_publish_handoff(
            export_package_id=package.id,
            target_platform=PublishTargetPlatform.FACEBOOK_REELS,
            operator_note="Manual handoff",
        )

        self.assertEqual(handoff.export_package_id, package.id)
        self.assertEqual(handoff.payload_json["target_platform"], "FACEBOOK_REELS")
        self.assertFalse(handoff.diagnostics_json["external_publish_triggered"])
        self.assertEqual(ready.status, ReupQueueStatus.PUBLISH_HANDOFF_CREATED)
        self.assertEqual(ready.metadata_json["publish_handoff_id"], str(handoff.id))
        self.assertEqual(fake_db.commits, 2)

    def test_batch_create_export_package_returns_mixed_eligibility_results(self) -> None:
        workspace_id = uuid4()
        ready = queue_item(workspace_id=workspace_id)
        media_not_ready = queue_item(workspace_id=workspace_id, media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA)
        fake_db = FakeExportHandoffDb([ready, media_not_ready])

        result = ExportHandoffService(fake_db).run_batch_action(
            action=ReupQueueBatchAction.CREATE_EXPORT_PACKAGE,
            item_ids=[ready.id, media_not_ready.id, uuid4()],
            note="Batch package",
        )

        self.assertEqual(result.requested_count, 3)
        self.assertEqual(result.succeeded_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.results[1].reason_code, "MEDIA_NOT_READY")
        self.assertEqual(result.results[2].reason_code, "ITEM_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
