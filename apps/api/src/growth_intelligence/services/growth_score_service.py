from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from src.analytics.services.publication_metrics_helpers import build_growth_summary
from src.enums import JobType
from src.models.affiliate import AffiliateProduct, AffiliateProductMatch
from src.models.analytics import PublicationGrowthAssessment, PublicationMetricSnapshot
from src.models.jobs import Job
from src.models.publish import PlatformAccount, PlatformPublication
from src.schemas.growth_intelligence import GrowthScoreRunRequest
from src.services.job_service import JobService


logger = logging.getLogger(__name__)

DEFAULT_GROWTH_SCORE_VERSION = "GROWTH_SCORE_V1"
STALE_MEASUREMENT_SECONDS = 24 * 60 * 60
HIGH_CONFIDENCE_MEASUREMENT_SECONDS = 6 * 60 * 60


class GrowthIntelligenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class GrowthScoreService:
    def __init__(self, db: Session):
        self.db = db

    def enqueue(
        self,
        publication_id: UUID,
        workspace_id: UUID,
        request: GrowthScoreRunRequest,
    ) -> tuple[PublicationGrowthAssessment | None, Job | None, bool]:
        publication = self._publication(publication_id, workspace_id)
        snapshots = self._snapshots(publication.id, workspace_id)
        fingerprint = self.input_fingerprint(snapshots)
        existing = self.db.scalar(
            select(PublicationGrowthAssessment).where(
                PublicationGrowthAssessment.workspace_id == workspace_id,
                PublicationGrowthAssessment.platform_publication_id == publication.id,
                PublicationGrowthAssessment.score_version == request.score_version,
                PublicationGrowthAssessment.input_fingerprint_sha256 == fingerprint,
            )
        )
        if existing is not None:
            self._make_current(existing)
            self.db.commit()
            return existing, None, True
        idempotency_key = f"growth-score:{publication.id}:{request.score_version}:{fingerprint[:20]}"
        existing_job = self.db.scalar(
            select(Job).where(Job.workspace_id == workspace_id, Job.idempotency_key == idempotency_key)
        )
        if existing_job is not None:
            return None, JobService(self.db).get_job(existing_job.id), True
        job = JobService(self.db).create_job(
            workspace_id=workspace_id,
            job_type=JobType.CALCULATE_GROWTH_SCORE,
            source_video_id=publication.source_video_id,
            reference_type="platform_publication_growth_score",
            reference_id=publication.id,
            idempotency_key=idempotency_key,
            max_attempts=2,
            payload_json={
                "platform_publication_id": str(publication.id),
                "score_version": request.score_version,
                "input_fingerprint_sha256": fingerprint,
                "snapshot_count": len(snapshots),
            },
        )
        logger.info(
            "growth_score_job_created",
            extra={"workspace_id": str(workspace_id), "publication_id": str(publication.id), "job_id": str(job.id)},
        )
        return None, job, False

    def execute_job(self, job_id: UUID) -> PublicationGrowthAssessment:
        job = JobService(self.db).get_job(job_id)
        if job.job_type != JobType.CALCULATE_GROWTH_SCORE:
            raise GrowthIntelligenceError("growth_score_job_type_invalid", "Job is not a Growth Score job")
        payload = job.payload_json or {}
        try:
            publication_id = UUID(str(payload["platform_publication_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise GrowthIntelligenceError("growth_score_input_missing", "Growth Score job input is incomplete") from exc
        publication = self._publication(publication_id, job.workspace_id)
        snapshots = self._snapshots(publication.id, job.workspace_id)
        fingerprint = self.input_fingerprint(snapshots)
        if fingerprint != str(payload.get("input_fingerprint_sha256") or ""):
            raise GrowthIntelligenceError(
                "growth_score_inputs_changed",
                "Metric evidence changed while scoring; run Growth Score again",
            )
        score_version = str(payload.get("score_version") or DEFAULT_GROWTH_SCORE_VERSION)
        existing = self.db.scalar(
            select(PublicationGrowthAssessment).where(
                PublicationGrowthAssessment.platform_publication_id == publication.id,
                PublicationGrowthAssessment.score_version == score_version,
                PublicationGrowthAssessment.input_fingerprint_sha256 == fingerprint,
            )
        )
        if existing is not None:
            self._make_current(existing)
            job.result_json = {"publication_growth_assessment_id": str(existing.id), "reused": True}
            self.db.commit()
            return existing

        calculated = self.calculate(publication, snapshots)
        self.db.execute(
            update(PublicationGrowthAssessment)
            .where(
                PublicationGrowthAssessment.platform_publication_id == publication.id,
                PublicationGrowthAssessment.is_current.is_(True),
            )
            .values(is_current=False)
        )
        assessment = PublicationGrowthAssessment(
            workspace_id=job.workspace_id,
            platform_publication_id=publication.id,
            score_version=score_version,
            input_fingerprint_sha256=fingerprint,
            latest_metric_snapshot_id=snapshots[-1].id if snapshots else None,
            created_by_job_id=job.id,
            status=calculated["status"],
            confidence=calculated["confidence"],
            growth_score=calculated["growth_score"],
            snapshot_count=len(snapshots),
            observation_hours=calculated["observation_hours"],
            measurement_age_seconds=calculated["measurement_age_seconds"],
            score_breakdown_json=calculated["score_breakdown"],
            evidence_json=calculated["evidence"],
            input_snapshot_ids_json=[str(snapshot.id) for snapshot in snapshots],
            is_current=True,
            metadata_json={
                "score_boundaries": calculated["score_boundaries"],
                "auto_placement": False,
                "combined_with_affiliate_fit": False,
            },
        )
        self.db.add(assessment)
        self.db.flush()
        job.result_json = {
            "publication_growth_assessment_id": str(assessment.id),
            "growth_score": assessment.growth_score,
            "status": assessment.status,
            "confidence": assessment.confidence,
        }
        self.db.commit()
        self.db.refresh(assessment)
        logger.info(
            "growth_score_completed",
            extra={
                "workspace_id": str(job.workspace_id),
                "publication_id": str(publication.id),
                "assessment_id": str(assessment.id),
                "status": assessment.status,
                "confidence": assessment.confidence,
            },
        )
        return assessment

    def get_current(self, publication_id: UUID, workspace_id: UUID) -> PublicationGrowthAssessment | None:
        self._publication(publication_id, workspace_id)
        return self.db.scalar(
            select(PublicationGrowthAssessment).where(
                PublicationGrowthAssessment.workspace_id == workspace_id,
                PublicationGrowthAssessment.platform_publication_id == publication_id,
                PublicationGrowthAssessment.is_current.is_(True),
            )
        )

    def opportunity_queue(
        self,
        workspace_id: UUID,
        *,
        recommendation: str | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        filters = [
            AffiliateProductMatch.workspace_id == workspace_id,
            AffiliateProductMatch.is_current.is_(True),
            AffiliateProductMatch.decision_status.in_(["APPROVED", "OVERRIDDEN"]),
            AffiliateProductMatch.selected_product_id.is_not(None),
        ]
        cleaned = (query or "").strip()
        if cleaned:
            pattern = f"%{cleaned}%"
            filters.append(
                or_(
                    PlatformPublication.external_reel_id.ilike(pattern),
                    PlatformAccount.display_name.ilike(pattern),
                    AffiliateProduct.name.ilike(pattern),
                )
            )
        rows = list(
            self.db.execute(
                select(
                    AffiliateProductMatch,
                    PlatformPublication,
                    PlatformAccount,
                    AffiliateProduct,
                    PublicationGrowthAssessment,
                )
                .join(PlatformPublication, PlatformPublication.id == AffiliateProductMatch.platform_publication_id)
                .join(PlatformAccount, PlatformAccount.id == PlatformPublication.platform_account_id)
                .join(AffiliateProduct, AffiliateProduct.id == AffiliateProductMatch.selected_product_id)
                .outerjoin(
                    PublicationGrowthAssessment,
                    (PublicationGrowthAssessment.platform_publication_id == PlatformPublication.id)
                    & PublicationGrowthAssessment.is_current.is_(True),
                )
                .where(*filters)
            ).all()
        )
        publication_ids = [row[1].id for row in rows]
        snapshots_by_publication: dict[UUID, list[PublicationMetricSnapshot]] = defaultdict(list)
        if publication_ids:
            for snapshot in self.db.scalars(
                select(PublicationMetricSnapshot)
                .where(
                    PublicationMetricSnapshot.workspace_id == workspace_id,
                    PublicationMetricSnapshot.platform_publication_id.in_(publication_ids),
                )
                .order_by(PublicationMetricSnapshot.observed_at.asc(), PublicationMetricSnapshot.id.asc())
            ):
                snapshots_by_publication[snapshot.platform_publication_id].append(snapshot)
        latest_jobs: dict[UUID, Job] = {}
        if publication_ids:
            for job in self.db.scalars(
                select(Job)
                .where(
                    Job.workspace_id == workspace_id,
                    Job.reference_type == "platform_publication_growth_score",
                    Job.reference_id.in_(publication_ids),
                )
                .order_by(Job.created_at.desc())
            ):
                if job.reference_id and job.reference_id not in latest_jobs:
                    latest_jobs[job.reference_id] = job

        now = datetime.now(UTC)
        items: list[dict[str, Any]] = []
        for product_match, publication, account, product, assessment in rows:
            snapshots = snapshots_by_publication.get(publication.id, [])
            fingerprint_changed = bool(
                assessment and assessment.input_fingerprint_sha256 != self.input_fingerprint(snapshots)
            )
            latest_age = (
                max(0, int((now - snapshots[-1].observed_at).total_seconds())) if snapshots else None
            )
            measurement_stale = latest_age is None or latest_age > STALE_MEASUREMENT_SECONDS
            growth_is_stale = bool(assessment and (fingerprint_changed or measurement_stale))
            recommendation_value, reason = self.recommendation(
                growth_score=assessment.growth_score if assessment else None,
                growth_status=assessment.status if assessment else None,
                confidence=assessment.confidence if assessment else None,
                affiliate_fit_score=product_match.selected_fit_score,
                growth_is_stale=growth_is_stale,
                product_active=product.is_active,
                product_availability=product.availability_status,
            )
            metadata = publication.metadata_json or {}
            items.append(
                {
                    "product_match": product_match,
                    "publication": publication,
                    "account": account,
                    "product": product,
                    "assessment": assessment,
                    "growth_is_stale": growth_is_stale,
                    "recommendation": recommendation_value,
                    "recommendation_reason": reason,
                    "latest_job": latest_jobs.get(publication.id),
                    "caption": metadata.get("external_caption") if isinstance(metadata.get("external_caption"), str) else None,
                    "thumbnail_url": metadata.get("thumbnail_url") if isinstance(metadata.get("thumbnail_url"), str) else None,
                }
            )
        kpis = {
            "eligible_count": len(items),
            "priority_count": sum(item["recommendation"] == "PRIORITY" for item in items),
            "monitor_count": sum(item["recommendation"] == "MONITOR" for item in items),
            "do_not_place_count": sum(item["recommendation"] == "DO_NOT_PLACE" for item in items),
            "insufficient_data_count": sum(item["recommendation"] == "INSUFFICIENT_DATA" for item in items),
            "stale_count": sum(bool(item["growth_is_stale"]) for item in items),
        }
        priority = {"PRIORITY": 0, "MONITOR": 1, "INSUFFICIENT_DATA": 2, "DO_NOT_PLACE": 3}
        items.sort(
            key=lambda item: (
                priority[item["recommendation"]],
                -(item["assessment"].growth_score if item["assessment"] and item["assessment"].growth_score is not None else -1),
                -(item["product_match"].selected_fit_score if item["product_match"].selected_fit_score is not None else -1),
            )
        )
        if recommendation:
            items = [item for item in items if item["recommendation"] == recommendation]
        total = len(items)
        return items[offset : offset + limit], total, kpis

    @staticmethod
    def input_fingerprint(snapshots: list[PublicationMetricSnapshot]) -> str:
        payload = [
            {
                "id": str(snapshot.id),
                "observed_at": snapshot.observed_at.isoformat(),
                "payload_hash": snapshot.payload_hash_sha256,
                "derivation_version": snapshot.derivation_version,
                "views_per_hour": snapshot.views_per_hour,
                "engagement_delta_rate_percent": snapshot.engagement_delta_rate_percent,
                "data_quality": snapshot.data_quality,
                "is_estimated": snapshot.is_estimated,
            }
            for snapshot in snapshots
        ]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def calculate(publication: PlatformPublication, snapshots: list[PublicationMetricSnapshot]) -> dict[str, Any]:
        now = datetime.now(UTC)
        summary = build_growth_summary(publication.id, snapshots, now=now)
        evidence: list[str] = []
        empty = {
            "growth_score": None,
            "confidence": "LOW",
            "observation_hours": summary.get("observation_hours"),
            "measurement_age_seconds": summary.get("measurement_age_seconds"),
            "score_breakdown": {},
            "evidence": evidence,
            "score_boundaries": GrowthScoreService.score_boundaries(),
        }
        if not snapshots or summary.get("velocity_status") in {"NO_DATA", "BASELINE_ONLY", "INSUFFICIENT_INTERVAL"}:
            evidence.append(f"velocity_status:{summary.get('velocity_status', 'NO_DATA')}")
            return {**empty, "status": "INSUFFICIENT_DATA"}
        if summary.get("velocity_status") == "COUNTER_REGRESSION":
            evidence.append("counter_regression_detected")
            return {**empty, "status": "COUNTER_REGRESSION"}

        velocity = float(summary.get("recent_views_per_hour") or 0.0)
        velocity_score = GrowthScoreService._velocity_score(velocity)
        stable_velocities = [
            float(snapshot.views_per_hour)
            for snapshot in snapshots
            if snapshot.views_per_hour is not None and not snapshot.counter_regression_detected
        ]
        acceleration_ratio = None
        if len(stable_velocities) >= 2 and stable_velocities[-2] > 0:
            acceleration_ratio = stable_velocities[-1] / stable_velocities[-2]
            acceleration_score = GrowthScoreService._acceleration_score(acceleration_ratio)
            evidence.append(f"acceleration_ratio:{round(acceleration_ratio, 4)}")
        else:
            acceleration_score = 10.0
            evidence.append("acceleration:neutral_insufficient_history")

        latest = snapshots[-1]
        engagement_rate = (
            latest.engagement_delta_rate_percent
            if latest.engagement_delta_rate_percent is not None
            else latest.engagement_rate_percent
        )
        engagement_score = GrowthScoreService._engagement_score(engagement_rate)
        freshness_score = GrowthScoreService._freshness_score(publication.published_at, now)
        quality_score = GrowthScoreService._quality_score(latest.data_quality, latest.is_estimated)
        breakdown = {
            "view_velocity": velocity_score,
            "view_acceleration": acceleration_score,
            "engagement_quality": engagement_score,
            "publication_freshness": freshness_score,
            "data_quality": quality_score,
        }
        growth_score = round(sum(breakdown.values()), 2)
        measurement_age = summary.get("measurement_age_seconds")
        status = "STALE" if measurement_age is None or measurement_age > STALE_MEASUREMENT_SECONDS else "READY"
        high_quality = latest.data_quality == "COMPLETE" and not latest.is_estimated
        if (
            len(snapshots) >= 3
            and len(stable_velocities) >= 2
            and high_quality
            and measurement_age is not None
            and measurement_age <= HIGH_CONFIDENCE_MEASUREMENT_SECONDS
        ):
            confidence = "HIGH"
        elif status == "READY" and len(snapshots) >= 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        evidence.extend(
            [
                f"recent_views_per_hour:{round(velocity, 4)}",
                f"engagement_rate_percent:{round(float(engagement_rate or 0), 4)}",
                f"latest_data_quality:{latest.data_quality}",
                f"snapshot_count:{len(snapshots)}",
            ]
        )
        return {
            "status": status,
            "growth_score": growth_score,
            "confidence": confidence,
            "observation_hours": summary.get("observation_hours"),
            "measurement_age_seconds": measurement_age,
            "score_breakdown": breakdown,
            "evidence": evidence,
            "score_boundaries": GrowthScoreService.score_boundaries(),
        }

    @staticmethod
    def recommendation(
        *,
        growth_score: float | None,
        growth_status: str | None,
        confidence: str | None,
        affiliate_fit_score: float | None,
        growth_is_stale: bool,
        product_active: bool,
        product_availability: str,
    ) -> tuple[str, str]:
        if not product_active or product_availability == "OUT_OF_STOCK":
            return "DO_NOT_PLACE", "selected_product_unavailable"
        if (
            growth_score is None
            or affiliate_fit_score is None
            or growth_status != "READY"
            or growth_is_stale
        ):
            return "INSUFFICIENT_DATA", "fresh_growth_and_affiliate_fit_required"
        if growth_score >= 70 and affiliate_fit_score >= 70 and confidence in {"MEDIUM", "HIGH"}:
            return "PRIORITY", "high_growth_and_high_affiliate_fit"
        if growth_score >= 70 and affiliate_fit_score < 70:
            return "DO_NOT_PLACE", "growth_is_high_but_affiliate_fit_is_not"
        if growth_score < 40 and affiliate_fit_score < 45:
            return "DO_NOT_PLACE", "growth_and_affiliate_fit_are_both_low"
        return "MONITOR", "one_signal_needs_more_evidence"

    @staticmethod
    def _velocity_score(value: float) -> float:
        if value >= 1000:
            return 35.0
        if value >= 200:
            return 28.0
        if value >= 50:
            return 20.0
        if value >= 10:
            return 12.0
        if value > 0:
            return 6.0
        return 0.0

    @staticmethod
    def _acceleration_score(ratio: float) -> float:
        if ratio >= 1.5:
            return 25.0
        if ratio >= 1.15:
            return 20.0
        if ratio >= 0.9:
            return 14.0
        if ratio >= 0.5:
            return 7.0
        return 0.0

    @staticmethod
    def _engagement_score(value: float | None) -> float:
        rate = float(value or 0.0)
        if rate >= 5:
            return 20.0
        if rate >= 3:
            return 16.0
        if rate >= 1.5:
            return 12.0
        if rate >= 0.5:
            return 7.0
        if rate > 0:
            return 3.0
        return 0.0

    @staticmethod
    def _freshness_score(published_at: datetime | None, now: datetime) -> float:
        if published_at is None:
            return 5.0
        age_hours = max(0.0, (now - published_at).total_seconds() / 3600)
        if age_hours <= 24:
            return 10.0
        if age_hours <= 72:
            return 8.0
        if age_hours <= 168:
            return 5.0
        if age_hours <= 336:
            return 2.0
        return 0.0

    @staticmethod
    def _quality_score(data_quality: str, is_estimated: bool) -> float:
        score = {"COMPLETE": 10.0, "PARTIAL": 6.0, "UNKNOWN": 2.0, "SUSPECT": 0.0}.get(data_quality, 2.0)
        return min(score, 3.0) if is_estimated else score

    @staticmethod
    def score_boundaries() -> dict[str, Any]:
        return {
            "view_velocity": {"max": 35, "thresholds_per_hour": [10, 50, 200, 1000]},
            "view_acceleration": {"max": 25, "ratio_thresholds": [0.5, 0.9, 1.15, 1.5]},
            "engagement_quality": {"max": 20, "percent_thresholds": [0.5, 1.5, 3, 5]},
            "publication_freshness": {"max": 10, "hour_thresholds": [24, 72, 168, 336]},
            "data_quality": {"max": 10},
        }

    def _snapshots(self, publication_id: UUID, workspace_id: UUID) -> list[PublicationMetricSnapshot]:
        return list(
            self.db.scalars(
                select(PublicationMetricSnapshot)
                .where(
                    PublicationMetricSnapshot.workspace_id == workspace_id,
                    PublicationMetricSnapshot.platform_publication_id == publication_id,
                )
                .order_by(PublicationMetricSnapshot.observed_at.asc(), PublicationMetricSnapshot.id.asc())
            )
        )

    def _publication(self, publication_id: UUID, workspace_id: UUID) -> PlatformPublication:
        publication = self.db.get(PlatformPublication, publication_id)
        if publication is None or publication.workspace_id != workspace_id:
            raise GrowthIntelligenceError("growth_publication_not_found", "Platform publication was not found")
        return publication

    def _make_current(self, assessment: PublicationGrowthAssessment) -> None:
        self.db.execute(
            update(PublicationGrowthAssessment)
            .where(
                PublicationGrowthAssessment.platform_publication_id == assessment.platform_publication_id,
                PublicationGrowthAssessment.id != assessment.id,
                PublicationGrowthAssessment.is_current.is_(True),
            )
            .values(is_current=False)
        )
        assessment.is_current = True
