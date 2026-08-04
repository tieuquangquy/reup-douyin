from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.analytics.collectors import MetricCollectorError, MetricCollectorRegistry
from src.analytics.services.publication_metrics_helpers import canonical_payload_hash
from src.analytics.services.publication_metrics_service import PublicationMetricsError, PublicationMetricsService
from src.core.settings import get_settings
from src.enums import ExternalPublicationStatus, JobType, PlatformAccountStatus, PublishTargetPlatform
from src.models.analytics import PublicationMetricSnapshot
from src.models.jobs import Job
from src.models.publish import PlatformAccount, PlatformPublication
from src.publish.services.platform_account_service import PlatformAccountError, PlatformAccountService
from src.schemas.analytics import (
    PublicationMetricCollectionEnqueueRequest,
    PublicationMetricSnapshotCreateRequest,
)
from src.services.job_factory import build_job

logger = logging.getLogger(__name__)

METRICS_COOLDOWN_METADATA_KEY = "metrics_collection_cooldown_until"


class PublicationMetricCollectionError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class PublicationMetricCollectionService:
    def __init__(
        self,
        db: Session,
        registry: MetricCollectorRegistry | None = None,
        *,
        enforce_facebook_live_preflight: bool = True,
    ):
        self.db = db
        self.registry = registry or MetricCollectorRegistry()
        self.metrics = PublicationMetricsService(db)
        self.enforce_facebook_live_preflight = enforce_facebook_live_preflight

    def enqueue(
        self,
        platform_publication_id: UUID,
        request: PublicationMetricCollectionEnqueueRequest,
    ) -> Job:
        publication = self._get_publication(platform_publication_id)
        account = self._get_account(publication.platform_account_id)
        self._validate_publication(publication)
        self._validate_account_static(account)
        self._validate_collector_allowed(
            request.collector,
            external_network_authorized=request.external_network_authorized,
            account=account,
        )
        self._assert_facebook_live_preflight(request.collector, publication, account)

        request_payload = request.model_dump(mode="json")
        request_hash = canonical_payload_hash(request_payload)
        job_idempotency_key = (
            f"metric-collect:{publication.id}:{request.collector}:{request.collection_key}"
        )
        existing = self._find_job_by_idempotency(publication.workspace_id, job_idempotency_key)
        if existing is not None:
            self._assert_same_job_payload(existing, request_hash)
            return existing

        effective_cooldown = self._effective_cooldown_until(account)
        scheduled_at = request.scheduled_at
        if effective_cooldown is not None and (
            scheduled_at is None or scheduled_at < effective_cooldown
        ):
            scheduled_at = effective_cooldown

        job = build_job(
            workspace_id=publication.workspace_id,
            job_type=JobType.COLLECT_PUBLICATION_METRICS,
            payload_json={
                "platform_publication_id": str(publication.id),
                "platform_account_id": str(account.id),
                "collector": request.collector,
                "collection_key": request.collection_key,
                "request_hash_sha256": request_hash,
                "external_network_authorized": request.external_network_authorized,
                "mock_metrics": (
                    request.mock_metrics.model_dump(mode="json")
                    if request.mock_metrics is not None
                    else None
                ),
            },
            reference_type="platform_publication",
            reference_id=publication.id,
            idempotency_key=job_idempotency_key,
            max_attempts=request.max_attempts,
            context_json={
                "authority": "PUBLICATION_METRICS_V1",
                "external_network_authorized": request.external_network_authorized,
            },
        )
        job.scheduled_at = scheduled_at
        self.db.add(job)
        try:
            self.db.commit()
            self.db.refresh(job)
        except IntegrityError as exc:
            self.db.rollback()
            concurrent = self._find_job_by_idempotency(
                publication.workspace_id,
                job_idempotency_key,
            )
            if concurrent is None:
                raise
            self._assert_same_job_payload(concurrent, request_hash)
            return concurrent

        logger.info(
            "publication_metric_collection_job_queued",
            extra={
                "job_id": str(job.id),
                "platform_publication_id": str(publication.id),
                "platform_account_id": str(account.id),
                "collector": request.collector,
            },
        )
        return job

    def execute_job(self, job_id: UUID) -> PublicationMetricSnapshot:
        job = self.db.get(Job, job_id)
        if job is None:
            raise PublicationMetricCollectionError("metrics_job_not_found", "Metric collection job not found")
        if job.job_type != JobType.COLLECT_PUBLICATION_METRICS:
            raise PublicationMetricCollectionError(
                "metrics_job_type_invalid",
                "Job is not a publication metric collection job",
            )
        payload = job.payload_json or {}
        try:
            publication_id = UUID(str(payload["platform_publication_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise PublicationMetricCollectionError(
                "metrics_job_payload_invalid",
                "Metric collection job is missing platform_publication_id",
            ) from exc

        publication = self._get_publication(publication_id)
        account = self._get_account(publication.platform_account_id)

        snapshot_idempotency_key = f"metric-collection-job:{job.id}"
        existing_snapshot = self.db.scalar(
            select(PublicationMetricSnapshot)
            .where(
                PublicationMetricSnapshot.platform_publication_id == publication.id,
                PublicationMetricSnapshot.idempotency_key == snapshot_idempotency_key,
            )
            .limit(1)
        )
        if existing_snapshot is not None:
            self._record_job_result(job, existing_snapshot, resumed=True)
            self._sync_cadence(job, existing_snapshot)
            return existing_snapshot

        # A worker may crash after the snapshot commit but before finalizing the job.
        # Eligibility and cooldown changes must not block replaying that persisted result;
        # apply every provider-facing guard only after the resume lookup above.
        self._validate_publication(publication)
        self._validate_account_static(account)
        self._assert_not_in_cooldown(account)

        collector_name = str(payload.get("collector") or "")
        external_network_authorized = bool(payload.get("external_network_authorized", False))
        self._validate_collector_allowed(
            collector_name,
            external_network_authorized=external_network_authorized,
            account=account,
        )
        self._assert_facebook_live_preflight(collector_name, publication, account)
        account_config = None
        if collector_name == "FACEBOOK_GRAPH":
            try:
                account_config = PlatformAccountService(self.db).resolve_config(account.id)
            except (PlatformAccountError, ValueError) as exc:
                raise PublicationMetricCollectionError(
                    "metrics_account_credentials_missing",
                    str(exc),
                    retryable=False,
                ) from exc
            except Exception as exc:
                self._raise_unexpected_boundary_error(
                    exc,
                    stage="resolve_account_credentials",
                    job=job,
                    publication=publication,
                )
        try:
            result = self.registry.get(collector_name).collect(
                platform_publication_id=publication.id,
                platform_account_id=account.id,
                external_publish_id=publication.external_publish_id,
                payload=payload,
                external_media_id=getattr(publication, "external_media_id", None),
                external_reel_id=getattr(publication, "external_reel_id", None),
                account_config=account_config,
                collector_config=dict(account.metadata_json or {}),
            )
        except MetricCollectorError as exc:
            self._handle_collector_error(account, exc)
            raise PublicationMetricCollectionError(
                exc.code,
                str(exc),
                retryable=exc.retryable,
                retry_after_seconds=exc.retry_after_seconds,
            ) from exc
        except Exception as exc:
            self._raise_unexpected_boundary_error(
                exc,
                stage="provider_collect",
                job=job,
                publication=publication,
            )

        try:
            snapshot_request = PublicationMetricSnapshotCreateRequest(
                observed_at=result.observed_at,
                collection_source=result.collection_source,
                provider_schema_version=result.provider_schema_version,
                idempotency_key=snapshot_idempotency_key,
                view_count=result.view_count,
                like_count=result.like_count,
                comment_count=result.comment_count,
                share_count=result.share_count,
                save_count=result.save_count,
                impression_count=result.impression_count,
                reach_count=result.reach_count,
                follower_gain_count=result.follower_gain_count,
                total_watch_time_seconds=result.total_watch_time_seconds,
                average_watch_time_seconds=result.average_watch_time_seconds,
                completion_rate_percent=result.completion_rate_percent,
                is_estimated=result.is_estimated,
                data_quality=result.data_quality,
                unavailable_metrics=result.unavailable_metrics,
                provider_summary_json=result.provider_summary,
                metadata_json={
                    "collection_job_id": str(job.id),
                    "collector": collector_name,
                    "collection_key": payload.get("collection_key"),
                },
            )
            snapshot = self.metrics.record_snapshot(publication.id, snapshot_request)
        except (PublicationMetricsError, ValidationError) as exc:
            code = getattr(exc, "code", "metrics_provider_payload_invalid")
            raise PublicationMetricCollectionError(code, str(exc), retryable=False) from exc

        self._record_job_result(job, snapshot, resumed=False)
        self._sync_cadence(job, snapshot)
        account.metadata_json = {
            **(account.metadata_json or {}),
            "last_metric_collection_at": datetime.now(UTC).isoformat(),
            "last_metric_collection_job_id": str(job.id),
        }
        self.db.commit()
        logger.info(
            "publication_metric_collection_completed",
            extra={
                "job_id": str(job.id),
                "metric_snapshot_id": str(snapshot.id),
                "platform_publication_id": str(publication.id),
            },
        )
        return snapshot

    def _raise_unexpected_boundary_error(
        self,
        exc: Exception,
        *,
        stage: str,
        job: Job,
        publication: PlatformPublication,
    ) -> None:
        """Turn unexpected provider/credential errors into a durable job failure.

        The operator-facing error deliberately excludes exception text because provider
        and credential exceptions may contain sensitive request context.
        """
        logger.error(
            "publication_metric_collection_unhandled_error",
            extra={
                "job_id": str(job.id),
                "platform_publication_id": str(publication.id),
                "stage": stage,
                "exception_type": type(exc).__name__,
            },
            exc_info=True,
        )
        try:
            self.db.rollback()
        except Exception:
            logger.error(
                "publication_metric_collection_rollback_failed",
                extra={"job_id": str(job.id), "stage": stage},
                exc_info=True,
            )
        raise PublicationMetricCollectionError(
            "metrics_unhandled_error",
            "Insights collection failed unexpectedly inside the worker; no credential data was exposed",
            retryable=True,
        ) from exc

    def _sync_cadence(self, job: Job, snapshot: PublicationMetricSnapshot) -> None:
        from src.analytics.services.publication_metric_cadence_service import (
            PublicationMetricCadenceService,
        )

        PublicationMetricCadenceService(self.db).sync_after_collection(job, snapshot)

    def _get_publication(self, publication_id: UUID) -> PlatformPublication:
        publication = self.db.get(PlatformPublication, publication_id)
        if publication is None:
            raise PublicationMetricCollectionError(
                "publication_not_found",
                "Platform publication not found",
            )
        return publication

    def _get_account(self, account_id: UUID) -> PlatformAccount:
        account = self.db.get(PlatformAccount, account_id)
        if account is None:
            raise PublicationMetricCollectionError(
                "metrics_account_not_found",
                "Platform account not found",
            )
        return account

    @staticmethod
    def _validate_publication(publication: PlatformPublication) -> None:
        if publication.status != ExternalPublicationStatus.PUBLISHED:
            raise PublicationMetricCollectionError(
                "metrics_publication_not_published",
                "Metrics can only be collected for a confirmed PUBLISHED publication",
            )

    @staticmethod
    def _validate_account_static(account: PlatformAccount) -> None:
        if account.status != PlatformAccountStatus.ACTIVE:
            raise PublicationMetricCollectionError(
                "metrics_account_inactive",
                "Platform account must be ACTIVE for metric collection",
            )
        if account.is_on_hold:
            raise PublicationMetricCollectionError(
                "metrics_account_on_hold",
                "Platform account is on manual hold",
            )

    def _assert_not_in_cooldown(self, account: PlatformAccount) -> None:
        cooldown_until = self._effective_cooldown_until(account)
        now = datetime.now(UTC)
        if cooldown_until is not None and cooldown_until > now:
            retry_after = max(1, int((cooldown_until - now).total_seconds()))
            raise PublicationMetricCollectionError(
                "metrics_account_cooldown",
                "Metric collection is deferred until the account cooldown expires",
                retryable=True,
                retry_after_seconds=retry_after,
            )

    @staticmethod
    def _effective_cooldown_until(account: PlatformAccount) -> datetime | None:
        candidates = [account.cooldown_until]
        raw = (account.metadata_json or {}).get(METRICS_COOLDOWN_METADATA_KEY)
        if raw:
            try:
                parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                    candidates.append(parsed)
            except ValueError:
                pass
        active = [item for item in candidates if item is not None and item > datetime.now(UTC)]
        return max(active) if active else None

    def _handle_collector_error(self, account: PlatformAccount, exc: MetricCollectorError) -> None:
        if not exc.retryable:
            return
        retry_after = exc.retry_after_seconds
        if retry_after is None and exc.code == "metrics_rate_limited":
            retry_after = int(getattr(get_settings(), "metrics_collection_rate_limit_cooldown_seconds", 900))
        if retry_after is None:
            return
        cooldown_until = datetime.now(UTC) + timedelta(seconds=max(1, int(retry_after)))
        account.metadata_json = {
            **(account.metadata_json or {}),
            METRICS_COOLDOWN_METADATA_KEY: cooldown_until.isoformat(),
            "last_metrics_collection_error_code": exc.code,
            "last_metrics_collection_error_at": datetime.now(UTC).isoformat(),
        }
        self.db.commit()

    @staticmethod
    def _validate_collector_allowed(
        collector_name: str,
        *,
        external_network_authorized: bool = False,
        account: PlatformAccount | None = None,
    ) -> None:
        settings = get_settings()
        normalized = str(collector_name).upper()
        if normalized == "LOCAL_MOCK" and settings.app_env in {
            "production",
            "prod",
        }:
            raise PublicationMetricCollectionError(
                "metrics_mock_disabled_in_production",
                "LOCAL_MOCK metric collection is disabled in production",
            )
        if normalized == "FACEBOOK_GRAPH":
            if not external_network_authorized:
                raise PublicationMetricCollectionError(
                    "metrics_external_network_authorization_required",
                    "FACEBOOK_GRAPH requires explicit external network authorization",
                )
            if account is None or account.platform != PublishTargetPlatform.FACEBOOK_REELS:
                raise PublicationMetricCollectionError(
                    "metrics_account_platform_invalid",
                    "FACEBOOK_GRAPH requires a FACEBOOK_REELS platform account",
                )
            if not str(getattr(account, "external_account_id", "") or "").strip():
                raise PublicationMetricCollectionError(
                    "metrics_account_identity_missing",
                    "FACEBOOK_GRAPH requires an explicit Facebook Page/account id",
                )
            if not str(getattr(account, "token_reference", "") or "").strip():
                raise PublicationMetricCollectionError(
                    "metrics_account_credentials_reference_missing",
                    "FACEBOOK_GRAPH requires an explicit server-side token reference",
                )
            if not bool((account.metadata_json or {}).get("metrics_insights_enabled")):
                raise PublicationMetricCollectionError(
                    "metrics_insights_capability_not_enabled",
                    "Enable metrics_insights_enabled on the exact Facebook account first",
                )

    def _record_job_result(
        self,
        job: Job,
        snapshot: PublicationMetricSnapshot,
        *,
        resumed: bool,
    ) -> None:
        job.result_json = {
            "metric_snapshot_id": str(snapshot.id),
            "platform_publication_id": str(snapshot.platform_publication_id),
            "observed_at": snapshot.observed_at.isoformat(),
            "resumed_from_existing_snapshot": resumed,
        }
        job.metadata_json = {
            **(job.metadata_json or {}),
            "metric_snapshot_id": str(snapshot.id),
            "metrics_collection_resume_safe": True,
        }
        self.db.commit()

    def _assert_facebook_live_preflight(
        self,
        collector_name: str,
        publication: PlatformPublication,
        account: PlatformAccount,
    ) -> None:
        if str(collector_name).upper() != "FACEBOOK_GRAPH":
            return
        if not self.enforce_facebook_live_preflight:
            logger.warning(
                "facebook_insights_live_preflight_bypassed_for_injected_fixture",
                extra={
                    "platform_publication_id": str(publication.id),
                    "platform_account_id": str(account.id),
                },
            )
            return

        from src.analytics.services.facebook_insights_live_pilot_service import (
            FacebookInsightsLivePilotService,
            _resolve_publication_media_reference,
        )
        from src.schemas.analytics import FacebookInsightsLivePilotPreflightRequest

        _source, media_id = _resolve_publication_media_reference(
            publication,
            account.metadata_json or {},
        )
        if not media_id:
            raise PublicationMetricCollectionError(
                "metrics_live_preflight_required",
                "Facebook live preflight failed: exact media reference is missing",
            )
        preflight = FacebookInsightsLivePilotService(self.db).preflight(
            publication.id,
            FacebookInsightsLivePilotPreflightRequest(
                operator_confirmation="FACEBOOK_INSIGHTS_LIVE_PILOT_APPROVED",
                expected_platform_account_id=account.id,
                expected_external_account_id=account.external_account_id,
                expected_media_id=media_id,
            ),
        )
        if not preflight.ready_for_live_job:
            blockers = ",".join(preflight.blocker_codes)
            raise PublicationMetricCollectionError(
                "metrics_live_preflight_required",
                f"Facebook live preflight is blocked: {blockers}",
            )

    def _find_job_by_idempotency(self, workspace_id: UUID, idempotency_key: str) -> Job | None:
        return self.db.scalar(
            select(Job)
            .where(
                Job.workspace_id == workspace_id,
                Job.idempotency_key == idempotency_key,
            )
            .limit(1)
        )

    @staticmethod
    def _assert_same_job_payload(job: Job, request_hash: str) -> None:
        existing_hash = (job.payload_json or {}).get("request_hash_sha256")
        if existing_hash != request_hash:
            raise PublicationMetricCollectionError(
                "metrics_collection_idempotency_conflict",
                "Collection key was already used with a different request payload",
            )
