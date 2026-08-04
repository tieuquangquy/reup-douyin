from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from src.analytics.services.publication_metric_cadence_policy import (
    CADENCE_POLICY_VERSION,
    decide_next_collection,
)
from src.analytics.services.publication_metric_collection_service import (
    PublicationMetricCollectionError,
    PublicationMetricCollectionService,
)
from src.analytics.services.publication_metrics_service import PublicationMetricsService
from src.analytics.services.publication_metrics_helpers import build_growth_summary
from src.enums import ExternalPublicationStatus
from src.models.analytics import PublicationMetricSchedule, PublicationMetricSnapshot
from src.models.jobs import Job
from src.models.publish import PlatformAccount, PlatformPublication
from src.schemas.analytics import (
    PublicationMetricCollectionEnqueueRequest,
    PublicationMetricMockPayload,
    PublicationMetricScheduleUpsertRequest,
)

logger = logging.getLogger(__name__)


class PublicationMetricCadenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PublicationMetricCadenceService:
    def __init__(self, db: Session):
        self.db = db
        self.metrics = PublicationMetricsService(db)

    def upsert_schedule(
        self,
        platform_publication_id: UUID,
        request: PublicationMetricScheduleUpsertRequest,
    ) -> PublicationMetricSchedule:
        publication = self._get_publication(platform_publication_id)
        self._validate_publication(publication)
        try:
            account = PublicationMetricCollectionService(self.db)._get_account(
                publication.platform_account_id
            )
            PublicationMetricCollectionService._validate_collector_allowed(
                request.collector,
                external_network_authorized=request.external_network_authorized,
                account=account,
            )
            PublicationMetricCollectionService(self.db)._assert_facebook_live_preflight(
                request.collector,
                publication,
                account,
            )
        except PublicationMetricCollectionError as exc:
            raise PublicationMetricCadenceError(exc.code, str(exc)) from exc

        schedule = self.db.scalar(
            select(PublicationMetricSchedule)
            .where(PublicationMetricSchedule.platform_publication_id == publication.id)
            .limit(1)
        )
        now = datetime.now(UTC)
        start_at = request.start_at or self._default_start_at(publication, now=now)
        tracking_started_at = start_at
        tracking_ends_at = tracking_started_at + timedelta(hours=request.max_age_hours)
        config = {
            "external_network_authorized": request.external_network_authorized,
            "operator_confirmation": request.operator_confirmation,
            "mock_growth_per_hour": (
                request.mock_growth_per_hour.model_dump(mode="json")
                if request.mock_growth_per_hour is not None
                else None
            ),
            "mock_baseline_metrics": (
                request.mock_baseline_metrics.model_dump(mode="json")
                if request.mock_baseline_metrics is not None
                else None
            ),
        }
        if schedule is None:
            schedule = PublicationMetricSchedule(
                workspace_id=publication.workspace_id,
                platform_publication_id=publication.id,
                collector_name=request.collector,
                status="ACTIVE",
                policy_version=CADENCE_POLICY_VERSION,
                collection_count=0,
                consecutive_flat_count=0,
            )
            self.db.add(schedule)
        schedule.collector_name = request.collector
        schedule.status = "ACTIVE"
        schedule.policy_version = CADENCE_POLICY_VERSION
        schedule.max_age_hours = request.max_age_hours
        schedule.collector_config_json = config
        schedule.next_collection_at = start_at
        schedule.metadata_json = {
            **(schedule.metadata_json or {}),
            "tracking_started_at": tracking_started_at.isoformat(),
            "tracking_ends_at": tracking_ends_at.isoformat(),
            "tracking_authorized_at": now.isoformat(),
            "tracking_authorization": "FACEBOOK_INSIGHTS_AUTO_TRACKING_APPROVED",
        }
        self._record_decision(schedule, {
            "status": "ACTIVE",
            "next_collection_at": start_at.isoformat(),
            "reason": "operator_schedule_upsert",
            "policy_version": CADENCE_POLICY_VERSION,
            "tracking_started_at": tracking_started_at.isoformat(),
            "tracking_ends_at": tracking_ends_at.isoformat(),
        })
        self.db.commit()
        self.db.refresh(schedule)
        logger.info(
            "publication_metric_schedule_upserted",
            extra={
                "metric_schedule_id": str(schedule.id),
                "platform_publication_id": str(publication.id),
                "collector": schedule.collector_name,
            },
        )
        return schedule

    def get_schedule(self, schedule_id: UUID) -> PublicationMetricSchedule:
        schedule = self.db.get(PublicationMetricSchedule, schedule_id)
        if schedule is None:
            raise PublicationMetricCadenceError("metric_schedule_not_found", "Metric schedule not found")
        return schedule

    def get_for_publication(self, platform_publication_id: UUID) -> PublicationMetricSchedule:
        schedule = self.db.scalar(
            select(PublicationMetricSchedule)
            .where(PublicationMetricSchedule.platform_publication_id == platform_publication_id)
            .limit(1)
        )
        if schedule is None:
            raise PublicationMetricCadenceError("metric_schedule_not_found", "Metric schedule not found")
        return schedule

    def list_schedules(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[PublicationMetricSchedule], int]:
        filters = []
        if status:
            filters.append(PublicationMetricSchedule.status == status.upper())
        total = int(
            self.db.scalar(
                select(func.count()).select_from(PublicationMetricSchedule).where(*filters)
            )
            or 0
        )
        rows = list(
            self.db.scalars(
                select(PublicationMetricSchedule)
                .where(*filters)
                .order_by(
                    PublicationMetricSchedule.next_collection_at.asc().nullslast(),
                    PublicationMetricSchedule.created_at.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total

    def tracking_monitor(
        self,
        *,
        status: str | None = None,
        health: str | None = None,
        platform_account_id: UUID | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
        now: datetime | None = None,
    ) -> dict:
        """Aggregate operator-facing schedule health without exposing provider secrets."""
        observed_at = now or datetime.now(UTC)
        stmt = (
            select(PublicationMetricSchedule, PlatformPublication, PlatformAccount, Job)
            .join(
                PlatformPublication,
                PlatformPublication.id == PublicationMetricSchedule.platform_publication_id,
            )
            .join(PlatformAccount, PlatformAccount.id == PlatformPublication.platform_account_id)
            .outerjoin(Job, Job.id == PublicationMetricSchedule.last_collection_job_id)
        )
        if platform_account_id is not None:
            stmt = stmt.where(PlatformPublication.platform_account_id == platform_account_id)
        cleaned_query = str(query or "").strip()
        if cleaned_query:
            pattern = f"%{cleaned_query}%"
            stmt = stmt.where(
                or_(
                    PlatformAccount.display_name.ilike(pattern),
                    PlatformPublication.external_reel_id.ilike(pattern),
                    PlatformPublication.external_publish_id.ilike(pattern),
                    cast(PlatformPublication.metadata_json, String).ilike(pattern),
                )
            )
        stmt = stmt.order_by(
            PublicationMetricSchedule.next_collection_at.asc().nullslast(),
            PublicationMetricSchedule.updated_at.desc(),
        )
        rows = list(self.db.execute(stmt).all())
        publication_ids = [publication.id for _schedule, publication, _account, _job in rows]
        snapshots_by_publication: dict[UUID, list[PublicationMetricSnapshot]] = {
            publication_id: [] for publication_id in publication_ids
        }
        if publication_ids:
            snapshots = list(
                self.db.scalars(
                    select(PublicationMetricSnapshot)
                    .where(PublicationMetricSnapshot.platform_publication_id.in_(publication_ids))
                    .order_by(
                        PublicationMetricSnapshot.observed_at.asc(),
                        PublicationMetricSnapshot.id.asc(),
                    )
                )
            )
            for snapshot in snapshots:
                snapshots_by_publication.setdefault(snapshot.platform_publication_id, []).append(snapshot)

        all_items = []
        for schedule, publication, account, job in rows:
            health_status, health_reason = self._classify_tracking_health(
                schedule,
                account,
                job,
                now=observed_at,
            )
            growth = build_growth_summary(
                publication.id,
                snapshots_by_publication.get(publication.id, []),
                now=observed_at,
            )
            metadata = publication.metadata_json or {}
            all_items.append(
                {
                    "schedule": schedule,
                    "platform_account_id": publication.platform_account_id,
                    "page_display_name": account.display_name,
                    "external_reel_id": publication.external_reel_id,
                    "external_permalink": publication.external_permalink,
                    "caption": metadata.get("external_caption"),
                    "thumbnail_url": metadata.get("thumbnail_url"),
                    "published_at": publication.published_at,
                    "health_status": health_status,
                    "health_reason": health_reason,
                    "growth": growth,
                    "last_job": (
                        {
                            "id": job.id,
                            "status": str(getattr(job.status, "value", job.status)),
                            "progress_percent": job.progress_percent,
                            "attempts": job.attempts,
                            "max_attempts": job.max_attempts,
                            "error_code": job.error_code,
                            "error_message": job.error_message,
                            "created_at": job.created_at,
                            "started_at": job.started_at,
                            "finished_at": job.finished_at,
                        }
                        if job is not None
                        else None
                    ),
                }
            )

        scoped_items = [
            item
            for item in all_items
            if (not status or str(item["schedule"].status).upper() == status.upper())
            and (not health or item["health_status"] == health.upper())
        ]
        due_soon_at = observed_at + timedelta(minutes=30)
        today_start = observed_at.replace(hour=0, minute=0, second=0, microsecond=0)
        snapshots_today_count = sum(
            1
            for snapshots in snapshots_by_publication.values()
            for snapshot in snapshots
            if snapshot.observed_at >= today_start
        )
        kpis = {
            "active_count": sum(1 for item in all_items if item["schedule"].status == "ACTIVE"),
            "due_soon_count": sum(
                1
                for item in all_items
                if item["schedule"].status == "ACTIVE"
                and item["schedule"].next_collection_at is not None
                and item["schedule"].next_collection_at <= due_soon_at
            ),
            "needs_attention_count": sum(
                1
                for item in all_items
                if item["health_status"] in {"BLOCKED", "DELAYED", "COOLDOWN"}
            ),
            "paused_count": sum(1 for item in all_items if item["schedule"].status == "PAUSED"),
            "completed_count": sum(1 for item in all_items if item["schedule"].status == "COMPLETED"),
            "snapshots_today_count": snapshots_today_count,
        }
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        return {
            "items": scoped_items[bounded_offset : bounded_offset + bounded_limit],
            "total": len(scoped_items),
            "limit": bounded_limit,
            "offset": bounded_offset,
            "kpis": kpis,
        }

    @staticmethod
    def _classify_tracking_health(
        schedule: PublicationMetricSchedule,
        account: PlatformAccount,
        job: Job | None,
        *,
        now: datetime,
    ) -> tuple[str, str]:
        if schedule.status == "BLOCKED":
            return "BLOCKED", "schedule_blocked"
        if schedule.status == "PAUSED":
            return "PAUSED", "schedule_paused"
        if schedule.status == "COMPLETED":
            return "COMPLETED", "tracking_window_completed"

        cooldown_candidates = [account.cooldown_until]
        raw_cooldown = (account.metadata_json or {}).get("metrics_collection_cooldown_until")
        if raw_cooldown:
            try:
                parsed = datetime.fromisoformat(str(raw_cooldown).replace("Z", "+00:00"))
                if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                    cooldown_candidates.append(parsed)
            except ValueError:
                pass
        if any(candidate is not None and candidate > now for candidate in cooldown_candidates):
            return "COOLDOWN", "account_metrics_cooldown"

        if job is not None:
            job_status = str(getattr(job.status, "value", job.status))
            if job_status in {"FAILED", "CANCELLED"}:
                return "BLOCKED", f"last_job_{job_status.lower()}"
            if job_status == "QUEUED" and (now - job.created_at).total_seconds() > 120:
                return "DELAYED", "last_job_queued_too_long"
            if job_status == "RUNNING" and job.locked_at is not None and (now - job.locked_at).total_seconds() > 300:
                return "DELAYED", "last_job_running_too_long"

        if schedule.next_collection_at is not None and schedule.next_collection_at < now - timedelta(minutes=5):
            return "DELAYED", "collection_overdue"
        if schedule.last_completed_at is None:
            return "WAITING", "awaiting_first_collection"
        return "HEALTHY", "tracking_healthy"

    def pause(self, schedule_id: UUID) -> PublicationMetricSchedule:
        schedule = self.get_schedule(schedule_id)
        schedule.status = "PAUSED"
        schedule.next_collection_at = None
        self._record_decision(schedule, {
            "status": "PAUSED",
            "reason": "operator_paused",
            "policy_version": schedule.policy_version,
        })
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def resume(
        self,
        schedule_id: UUID,
        *,
        resume_at: datetime | None = None,
    ) -> PublicationMetricSchedule:
        schedule = self.get_schedule(schedule_id)
        if schedule.status == "COMPLETED":
            raise PublicationMetricCadenceError(
                "metric_schedule_completed",
                "Completed schedule must be updated before it can resume",
            )
        publication = self._get_publication(schedule.platform_publication_id)
        schedule.status = "ACTIVE"
        schedule.next_collection_at = resume_at or self._default_start_at(
            publication,
            now=datetime.now(UTC),
        )
        self._record_decision(schedule, {
            "status": "ACTIVE",
            "next_collection_at": schedule.next_collection_at.isoformat(),
            "reason": "operator_resumed",
            "policy_version": schedule.policy_version,
        })
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def dispatch_due(self, *, now: datetime | None = None, limit: int = 20) -> dict:
        dispatch_at = now or datetime.now(UTC)
        schedules = list(
            self.db.scalars(
                select(PublicationMetricSchedule)
                .where(
                    PublicationMetricSchedule.status == "ACTIVE",
                    PublicationMetricSchedule.next_collection_at.is_not(None),
                    PublicationMetricSchedule.next_collection_at <= dispatch_at,
                )
                .order_by(PublicationMetricSchedule.next_collection_at.asc())
                .limit(max(1, int(limit)))
                .with_for_update(skip_locked=True)
            )
        )
        summary = {
            "evaluated_count": len(schedules),
            "enqueued_count": 0,
            "blocked_count": 0,
            "completed_count": 0,
            "job_ids": [],
        }
        for schedule in schedules:
            publication = self.db.get(PlatformPublication, schedule.platform_publication_id)
            if publication is None or publication.status != ExternalPublicationStatus.PUBLISHED:
                schedule.status = "BLOCKED"
                schedule.next_collection_at = None
                self._record_decision(schedule, {
                    "status": "BLOCKED",
                    "reason": "publication_missing_or_not_published",
                    "policy_version": schedule.policy_version,
                })
                summary["blocked_count"] += 1
                continue

            tracking_reference_at = self._tracking_reference_at(schedule, publication)
            decision = decide_next_collection(
                reference_at=dispatch_at,
                published_at=tracking_reference_at,
                trend_label=self.metrics.growth_summary(publication.id)["trend_label"],
                consecutive_flat_count=schedule.consecutive_flat_count,
                max_age_hours=schedule.max_age_hours,
            )
            if decision.status == "COMPLETED":
                schedule.status = "COMPLETED"
                schedule.next_collection_at = None
                self._record_decision(schedule, decision.as_dict())
                summary["completed_count"] += 1
                continue

            slot_at = schedule.next_collection_at or dispatch_at
            try:
                mock_metrics = (
                    self._build_local_mock_metrics(
                        schedule,
                        publication,
                        observed_at=dispatch_at,
                    )
                    if schedule.collector_name == "LOCAL_MOCK"
                    else None
                )
                collector_config = schedule.collector_config_json or {}
                request = PublicationMetricCollectionEnqueueRequest(
                    collection_key=f"cadence:{schedule.id}:{int(slot_at.timestamp())}",
                    collector=schedule.collector_name,
                    external_network_authorized=bool(
                        collector_config.get("external_network_authorized", False)
                    ),
                    max_attempts=5,
                    mock_metrics=mock_metrics,
                )
                job = PublicationMetricCollectionService(self.db).enqueue(publication.id, request)
            except (PublicationMetricCollectionError, PublicationMetricCadenceError) as exc:
                schedule.status = "BLOCKED"
                schedule.next_collection_at = None
                self._record_decision(schedule, {
                    "status": "BLOCKED",
                    "reason": getattr(exc, "code", "metric_schedule_dispatch_failed"),
                    "message": str(exc),
                    "policy_version": schedule.policy_version,
                })
                summary["blocked_count"] += 1
                continue

            if str(getattr(job.status, "value", job.status)) in {"FAILED", "CANCELLED"}:
                schedule.status = "BLOCKED"
                schedule.next_collection_at = None
                self._record_decision(schedule, {
                    "status": "BLOCKED",
                    "reason": "previous_collection_job_terminal",
                    "job_id": str(job.id),
                    "policy_version": schedule.policy_version,
                })
                summary["blocked_count"] += 1
                self.db.commit()
                continue

            job.payload_json = {
                **(job.payload_json or {}),
                "metric_schedule_id": str(schedule.id),
            }
            schedule.last_collection_job_id = job.id
            schedule.last_enqueued_at = dispatch_at
            schedule.next_collection_at = decision.next_collection_at
            self._record_decision(schedule, {
                **decision.as_dict(),
                "reason": "provisional_after_enqueue:" + decision.reason,
                "collection_slot_at": slot_at.isoformat(),
            })
            summary["enqueued_count"] += 1
            summary["job_ids"].append(job.id)
            self.db.commit()

        self.db.commit()
        logger.info("publication_metric_schedules_dispatched", extra={**summary})
        return summary

    def sync_after_collection(self, job: Job, snapshot: PublicationMetricSnapshot) -> None:
        schedule_id = (job.payload_json or {}).get("metric_schedule_id")
        if not schedule_id:
            return
        try:
            schedule_uuid = UUID(str(schedule_id))
        except ValueError:
            return
        schedule = self.db.get(PublicationMetricSchedule, schedule_uuid)
        if schedule is None:
            return
        publication = self.db.get(PlatformPublication, schedule.platform_publication_id)
        if publication is None:
            schedule.status = "BLOCKED"
            schedule.next_collection_at = None
            self.db.commit()
            return

        is_new_snapshot = schedule.last_metric_snapshot_id != snapshot.id
        if is_new_snapshot:
            schedule.collection_count = int(schedule.collection_count or 0) + 1
        schedule.last_metric_snapshot_id = snapshot.id
        schedule.last_collection_job_id = job.id
        schedule.last_completed_at = datetime.now(UTC)
        if not is_new_snapshot:
            self.db.commit()
            return
        if snapshot.delta_view_count == 0:
            schedule.consecutive_flat_count = int(schedule.consecutive_flat_count or 0) + 1
        elif snapshot.delta_view_count is not None and snapshot.delta_view_count > 0:
            schedule.consecutive_flat_count = 0

        if schedule.status != "ACTIVE":
            self.db.commit()
            return
        summary = self.metrics.growth_summary(publication.id)
        decision = decide_next_collection(
            reference_at=snapshot.observed_at,
            published_at=self._tracking_reference_at(schedule, publication),
            trend_label=summary["trend_label"],
            consecutive_flat_count=schedule.consecutive_flat_count,
            max_age_hours=schedule.max_age_hours,
        )
        schedule.status = decision.status
        schedule.next_collection_at = decision.next_collection_at
        self._record_decision(schedule, decision.as_dict())
        self.db.commit()

    @staticmethod
    def _record_decision(schedule: PublicationMetricSchedule, decision: dict) -> None:
        metadata = dict(schedule.metadata_json or {})
        history = list(metadata.get("decision_history") or [])
        if schedule.last_decision_json:
            history.append(
                {
                    **schedule.last_decision_json,
                    "superseded_at": datetime.now(UTC).isoformat(),
                }
            )
        metadata["decision_history"] = history[-20:]
        schedule.metadata_json = metadata
        schedule.last_decision_json = decision

    def _default_start_at(
        self,
        publication: PlatformPublication,
        *,
        now: datetime,
    ) -> datetime:
        """Avoid an extra noisy read when a recent manual baseline already exists."""
        summary = self.metrics.growth_summary(publication.id)
        next_stable = summary.get("next_stable_measurement_at")
        if isinstance(next_stable, datetime) and next_stable > now:
            return next_stable
        return now

    @staticmethod
    def _tracking_reference_at(
        schedule: PublicationMetricSchedule,
        publication: PlatformPublication,
    ) -> datetime:
        raw = (schedule.metadata_json or {}).get("tracking_started_at")
        if raw:
            try:
                parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                    return parsed
            except ValueError:
                pass
        return publication.published_at or publication.created_at

    def _build_local_mock_metrics(
        self,
        schedule: PublicationMetricSchedule,
        publication: PlatformPublication,
        *,
        observed_at: datetime,
    ) -> PublicationMetricMockPayload:
        if schedule.collector_name != "LOCAL_MOCK":
            raise PublicationMetricCadenceError(
                "metric_schedule_collector_not_supported",
                f"Schedule collector is not supported: {schedule.collector_name}",
            )
        config = schedule.collector_config_json or {}
        growth = config.get("mock_growth_per_hour") or {}
        baseline = config.get("mock_baseline_metrics") or {}
        latest = self.db.scalar(
            select(PublicationMetricSnapshot)
            .where(PublicationMetricSnapshot.platform_publication_id == publication.id)
            .order_by(PublicationMetricSnapshot.observed_at.desc(), PublicationMetricSnapshot.id.desc())
            .limit(1)
        )
        reference_at = latest.observed_at if latest is not None else publication.published_at or publication.created_at
        elapsed_hours = max(0.0, (observed_at - reference_at).total_seconds() / 3600)
        values = {}
        for field in [
            "view_count",
            "like_count",
            "comment_count",
            "share_count",
            "save_count",
            "impression_count",
            "reach_count",
        ]:
            current = getattr(latest, field, None) if latest is not None else baseline.get(field)
            rate = growth.get(f"{field}_per_hour")
            if current is None and rate is None:
                values[field] = None
            else:
                values[field] = max(0, int(current or 0) + round(float(rate or 0) * elapsed_hours))
        for field in [
            "follower_gain_count",
            "total_watch_time_seconds",
            "average_watch_time_seconds",
            "completion_rate_percent",
        ]:
            values[field] = getattr(latest, field, None) if latest is not None else baseline.get(field)
        return PublicationMetricMockPayload(
            observed_at=observed_at,
            **values,
            is_estimated=True,
            data_quality="SUSPECT",
        )

    def _get_publication(self, publication_id: UUID) -> PlatformPublication:
        publication = self.db.get(PlatformPublication, publication_id)
        if publication is None:
            raise PublicationMetricCadenceError("publication_not_found", "Platform publication not found")
        return publication

    @staticmethod
    def _validate_publication(publication: PlatformPublication) -> None:
        if publication.status != ExternalPublicationStatus.PUBLISHED:
            raise PublicationMetricCadenceError(
                "metrics_publication_not_published",
                "Metric cadence requires a confirmed PUBLISHED publication",
            )
