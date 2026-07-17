from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from src.enums import (
    ExportPackageStatus,
    PublishHandoffStatus,
    PublishTargetPlatform,
    ReupQueueAction,
    ReupQueueBatchAction,
    ReupQueueMediaPrepStatus,
    ReupQueueStatus,
)
from src.core.settings import get_settings
from src.models.export_handoff import ExportPackage, ExportPackageItem, PublishHandoff
from src.models.reup_queue import ReupQueueItem
from src.services.reup_queue_batch_limits import apply_start_processing_batch_cap
from src.services.reup_queue_service import ReupQueueError, ReupQueueService


class ExportHandoffError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class BatchItemResult:
    item_id: UUID
    result: str
    status: ReupQueueStatus | None = None
    reason_code: str | None = None
    message: str | None = None
    export_package_id: UUID | None = None
    publish_handoff_id: UUID | None = None


@dataclass(frozen=True)
class BatchOperationResult:
    requested_count: int
    succeeded_count: int
    skipped_count: int
    failed_count: int
    results: list[BatchItemResult]
    export_package_id: UUID | None = None
    publish_handoff_id: UUID | None = None


LIFECYCLE_BATCH_ACTIONS: dict[ReupQueueBatchAction, ReupQueueAction] = {
    ReupQueueBatchAction.START_PROCESSING: ReupQueueAction.START_PROCESSING,
    ReupQueueBatchAction.HOLD: ReupQueueAction.HOLD,
    ReupQueueBatchAction.RESUME: ReupQueueAction.RESUME,
    ReupQueueBatchAction.RETRY: ReupQueueAction.RETRY,
    ReupQueueBatchAction.CANCEL: ReupQueueAction.CANCEL,
    ReupQueueBatchAction.MARK_MEDIA_READY: ReupQueueAction.MARK_MEDIA_READY,
    ReupQueueBatchAction.DISMISS: ReupQueueAction.DISMISS,
}


class ExportHandoffService:
    def __init__(self, db: Session):
        self.db = db

    def list_export_packages(self, *, limit: int = 100, offset: int = 0) -> tuple[list[ExportPackage], int]:
        stmt: Select[tuple[ExportPackage]] = (
            select(ExportPackage)
            .options(selectinload(ExportPackage.items), selectinload(ExportPackage.publish_handoffs))
            .order_by(ExportPackage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.scalars(stmt).unique())
        total = len(list(self.db.scalars(select(ExportPackage))))
        return items, total

    def get_export_package(self, package_id: UUID) -> ExportPackage:
        package = self.db.scalar(
            select(ExportPackage)
            .options(selectinload(ExportPackage.items), selectinload(ExportPackage.publish_handoffs))
            .where(ExportPackage.id == package_id)
        )
        if package is None:
            raise ExportHandoffError("EXPORT_PACKAGE_NOT_FOUND", "Export Package was not found.")
        return package

    def list_publish_handoffs(self, *, limit: int = 100, offset: int = 0) -> tuple[list[PublishHandoff], int]:
        stmt: Select[tuple[PublishHandoff]] = (
            select(PublishHandoff)
            .options(selectinload(PublishHandoff.export_package).selectinload(ExportPackage.items))
            .order_by(PublishHandoff.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.scalars(stmt).unique())
        total = len(list(self.db.scalars(select(PublishHandoff))))
        return items, total

    def get_publish_handoff(self, handoff_id: UUID) -> PublishHandoff:
        handoff = self.db.scalar(
            select(PublishHandoff)
            .options(selectinload(PublishHandoff.export_package).selectinload(ExportPackage.items))
            .where(PublishHandoff.id == handoff_id)
        )
        if handoff is None:
            raise ExportHandoffError("PUBLISH_HANDOFF_NOT_FOUND", "Publish Handoff was not found.")
        return handoff

    def create_export_package(
        self,
        *,
        item_ids: list[UUID],
        label: str | None = None,
        operator_note: str | None = None,
    ) -> tuple[ExportPackage, BatchOperationResult]:
        if not item_ids:
            raise ExportHandoffError("NO_QUEUE_ITEMS", "At least one Reup Queue item is required.")

        now = datetime.now(UTC)
        queue_items = self._queue_items_by_id(item_ids)
        package = ExportPackage(
            workspace_id=self._workspace_id_for_items(queue_items.values()),
            status=ExportPackageStatus.DRAFT,
            label=label,
            operator_note=operator_note,
            item_count=0,
            manifest_json={"source": "reup_queue", "requested_item_ids": [str(item_id) for item_id in item_ids]},
            diagnostics_json={"created_by": "operator", "checks": []},
        )
        self.db.add(package)
        self.db.flush()
 
        results: list[BatchItemResult] = []
        included: list[ExportPackageItem] = []
        for item_id in item_ids:
            item = queue_items.get(item_id)
            if item is None:
                results.append(BatchItemResult(item_id=item_id, result="failed", reason_code="ITEM_NOT_FOUND", message="Queue item was not found."))
                continue
            eligibility_error = self._export_package_eligibility_error(item)
            if eligibility_error:
                code, message = eligibility_error
                results.append(BatchItemResult(item_id=item_id, result="skipped", status=item.status, reason_code=code, message=message))
                continue

            diagnostics = self._item_diagnostics(item)
            package_item = ExportPackageItem(
                workspace_id=item.workspace_id,
                export_package=package,
                reup_queue_item_id=item.id,
                source_video_id=item.source_video_id,
                video_candidate_id=item.video_candidate_id,
                render_output_id=item.render_output_id,
                publish_draft_id=item.publish_draft_id,
                item_status="INCLUDED",
                manifest_json=self._item_manifest(item),
                diagnostics_json=diagnostics,
            )
            self.db.add(package_item)
            included.append(package_item)
            item.status = ReupQueueStatus.EXPORT_PACKAGE_CREATED
            item.last_action_at = now
            item.last_action_note = operator_note or "Export Package created from Reup Queue."
            item.metadata_json = {**(item.metadata_json or {}), "export_package_id": str(package.id)}
            results.append(
                BatchItemResult(
                    item_id=item.id,
                    result="succeeded",
                    status=item.status,
                    message="Export Package item created.",
                    export_package_id=package.id,
                )
            )

        if not included:
            package.status = ExportPackageStatus.FAILED_NEEDS_ATTENTION
            package.failed_at = now
            package.diagnostics_json = {**(package.diagnostics_json or {}), "reason_code": "NO_ELIGIBLE_ITEMS"}
        else:
            package.status = ExportPackageStatus.READY_FOR_HANDOFF
            package.ready_at = now
            package.item_count = len(included)
            package.manifest_json = self._package_manifest(package, included)
            package.diagnostics_json = {**(package.diagnostics_json or {}), "item_count": len(included), "ready_for_handoff": True}

        self.db.commit()
        self.db.refresh(package)
        result = self._batch_result(results, export_package_id=package.id if included else None)
        return package, result

    def create_publish_handoff(
        self,
        *,
        export_package_id: UUID,
        target_platform: PublishTargetPlatform,
        operator_note: str | None = None,
    ) -> PublishHandoff:
        package = self.get_export_package(export_package_id)
        if package.status == ExportPackageStatus.CANCELLED:
            raise ExportHandoffError("PACKAGE_CANCELLED", "Cancelled packages cannot create Publish Handoffs.")
        if not package.items:
            raise ExportHandoffError("PACKAGE_EMPTY", "Export Package has no items to hand off.")

        now = datetime.now(UTC)
        diagnostics = self._handoff_diagnostics(package)
        handoff = PublishHandoff(
            workspace_id=package.workspace_id,
            export_package_id=package.id,
            target_platform=target_platform,
            status=PublishHandoffStatus.READY_FOR_OPERATOR,
            operator_note=operator_note,
            payload_json=self._handoff_payload(package, target_platform),
            diagnostics_json=diagnostics,
            ready_at=now,
        )
        self.db.add(handoff)
        self.db.flush()
        package.status = ExportPackageStatus.HANDOFF_CREATED
        for package_item in package.items:
            queue_item = package_item.reup_queue_item
            queue_item.status = ReupQueueStatus.PUBLISH_HANDOFF_CREATED
            queue_item.last_action_at = now
            queue_item.last_action_note = operator_note or "Publish Handoff created from Export Package."
            queue_item.metadata_json = {**(queue_item.metadata_json or {}), "publish_handoff_id": str(handoff.id)}
        self.db.commit()
        self.db.refresh(handoff)
        return handoff

    def run_batch_action(
        self,
        *,
        action: ReupQueueBatchAction,
        item_ids: list[UUID],
        note: str | None = None,
        target_platform: PublishTargetPlatform | None = None,
    ) -> BatchOperationResult:
        if action == ReupQueueBatchAction.CREATE_EXPORT_PACKAGE:
            _package, result = self.create_export_package(item_ids=item_ids, label="Batch Export Package", operator_note=note)
            return result
        if action == ReupQueueBatchAction.CREATE_PUBLISH_HANDOFF:
            package, package_result = self.create_export_package(item_ids=item_ids, label="Batch Publish Handoff Package", operator_note=note)
            if package_result.succeeded_count == 0:
                return package_result
            handoff = self.create_publish_handoff(
                export_package_id=package.id,
                target_platform=target_platform or PublishTargetPlatform.FACEBOOK_REELS,
                operator_note=note,
            )
            results = [
                BatchItemResult(
                    item_id=result.item_id,
                    result=result.result,
                    status=ReupQueueStatus.PUBLISH_HANDOFF_CREATED if result.result == "succeeded" else result.status,
                    reason_code=result.reason_code,
                    message="Publish Handoff created." if result.result == "succeeded" else result.message,
                    export_package_id=package.id if result.result == "succeeded" else None,
                    publish_handoff_id=handoff.id if result.result == "succeeded" else None,
                )
                for result in package_result.results
            ]
            return self._batch_result(results, export_package_id=package.id, publish_handoff_id=handoff.id)

        if action == ReupQueueBatchAction.PURGE:
            purge_result = ReupQueueService(self.db).purge_clearable_items(item_ids=item_ids)
            purged_ids = set(purge_result.purged_item_ids)
            skipped_ids = set(purge_result.skipped_item_ids)
            results = []
            for item_id in item_ids:
                if item_id in purged_ids:
                    results.append(BatchItemResult(item_id=item_id, result="succeeded", status="PURGED", message="Queue item permanently deleted."))
                elif item_id in skipped_ids:
                    results.append(
                        BatchItemResult(
                            item_id=item_id,
                            result="skipped",
                            reason_code="EXPORT_PACKAGE_LINKED",
                            message="Queue item is linked to an export package and was not deleted.",
                        )
                    )
                else:
                    results.append(
                        BatchItemResult(
                            item_id=item_id,
                            result="skipped",
                            reason_code="NOT_CLEARABLE",
                            message="Queue item is not in a clearable status.",
                        )
                    )
            return self._batch_result(results)

        queue_action = LIFECYCLE_BATCH_ACTIONS[action]
        accepted_ids = item_ids
        overflow_ids: list[UUID] = []
        batch_limit: int | None = None
        if action == ReupQueueBatchAction.START_PROCESSING:
            batch_limit = get_settings().reup_queue_start_processing_batch_limit
            accepted_ids, overflow_ids = apply_start_processing_batch_cap(item_ids, limit=batch_limit)

        service = ReupQueueService(self.db)
        results = []
        for item_id in accepted_ids:
            try:
                updated = service.apply_action(
                    item_id,
                    action=queue_action,
                    note=note,
                    blocked_reason=note if queue_action in {ReupQueueAction.HOLD, ReupQueueAction.CANCEL} else None,
                    media_prep_notes=note if queue_action == ReupQueueAction.MARK_MEDIA_READY else None,
                    media_prep_status=(
                        ReupQueueMediaPrepStatus.WAITING_FOR_METADATA if queue_action == ReupQueueAction.MARK_MEDIA_READY else None
                    ),
                )
            except ReupQueueError as exc:
                results.append(BatchItemResult(item_id=item_id, result="skipped", reason_code=exc.code, message=exc.message))
                continue
            results.append(BatchItemResult(item_id=item_id, result="succeeded", status=updated.status, message="Batch action applied."))
        if overflow_ids and batch_limit is not None:
            overflow_message = (
                f"Batch capped at {batch_limit} items for safe download processing. "
                "Start the remaining READY items in a later batch."
            )
            for item_id in overflow_ids:
                results.append(
                    BatchItemResult(
                        item_id=item_id,
                        result="skipped",
                        reason_code="START_PROCESSING_BATCH_LIMIT",
                        message=overflow_message,
                    )
                )
        return self._batch_result(results)

    def _queue_items_by_id(self, item_ids: list[UUID]) -> dict[UUID, ReupQueueItem]:
        if not item_ids:
            return {}
        items = self.db.scalars(select(ReupQueueItem).where(ReupQueueItem.id.in_(item_ids))).unique()
        return {item.id: item for item in items}

    def _workspace_id_for_items(self, items) -> UUID:
        item_list = list(items)
        if not item_list:
            raise ExportHandoffError("NO_QUEUE_ITEMS_FOUND", "No requested Reup Queue items were found.")
        workspace_ids = {item.workspace_id for item in item_list}
        if len(workspace_ids) != 1:
            raise ExportHandoffError("MIXED_WORKSPACES", "Export Package items must belong to one workspace.")
        return item_list[0].workspace_id

    def _export_package_eligibility_error(self, item: ReupQueueItem) -> tuple[str, str] | None:
        if item.status != ReupQueueStatus.READY_TO_EXPORT:
            return "INELIGIBLE_STATUS", f"Queue item is {item.status}, not READY_TO_EXPORT."
        if item.media_prep_status != ReupQueueMediaPrepStatus.READY_FOR_EXPORT:
            return "MEDIA_NOT_READY", "Queue item media prep is not READY_FOR_EXPORT."
        return None

    def _item_manifest(self, item: ReupQueueItem) -> dict:
        return {
            "reup_queue_item_id": str(item.id),
            "source_video_id": str(item.source_video_id),
            "video_candidate_id": str(item.video_candidate_id),
            "render_output_id": str(item.render_output_id) if item.render_output_id else None,
            "publish_draft_id": str(item.publish_draft_id) if item.publish_draft_id else None,
        }

    def _item_diagnostics(self, item: ReupQueueItem) -> dict:
        warnings = []
        if not item.render_output_id:
            warnings.append("MISSING_RENDER_OUTPUT")
        if not item.publish_draft_id:
            warnings.append("MISSING_PUBLISH_DRAFT")
        return {"warnings": warnings, "media_prep_status": item.media_prep_status}

    def _package_manifest(self, package: ExportPackage, items: list[ExportPackageItem]) -> dict:
        return {
            "export_package_id": str(package.id),
            "item_count": len(items),
            "items": [item.manifest_json for item in items],
        }

    def _handoff_payload(self, package: ExportPackage, target_platform: PublishTargetPlatform) -> dict:
        return {
            "export_package_id": str(package.id),
            "target_platform": str(target_platform),
            "item_count": len(package.items),
            "items": [item.manifest_json for item in package.items],
        }

    def _handoff_diagnostics(self, package: ExportPackage) -> dict:
        warnings = []
        for item in package.items:
            for warning in (item.diagnostics_json or {}).get("warnings", []):
                if warning not in warnings:
                    warnings.append(warning)
        return {"warnings": warnings, "external_publish_triggered": False}

    def _batch_result(
        self,
        results: list[BatchItemResult],
        *,
        export_package_id: UUID | None = None,
        publish_handoff_id: UUID | None = None,
    ) -> BatchOperationResult:
        succeeded = len([result for result in results if result.result == "succeeded"])
        skipped = len([result for result in results if result.result == "skipped"])
        failed = len([result for result in results if result.result == "failed"])
        return BatchOperationResult(
            requested_count=len(results),
            succeeded_count=succeeded,
            skipped_count=skipped,
            failed_count=failed,
            results=results,
            export_package_id=export_package_id,
            publish_handoff_id=publish_handoff_id,
        )
