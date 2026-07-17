from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.adapters.douyin import DouyinProfileAdapter
from src.adapters.errors import SourceAdapterError, SourceAdapterErrorCode
from src.core.settings import get_settings
from src.enums import CrawlSessionStatus, SourcePlatformEnum
from src.models.ingestion import CrawlSession, SourceProfile, SourceVideo
from src.models.source_accounts import DouyinAccountConnection
from src.services.candidate_service import CandidateEvaluationService
from src.services.candidate_types import FilterConfig
from src.services.douyin_account_service import DouyinAccountError, DouyinAccountHealthSummary, DouyinAccountService
from src.services.source_ingest_service import SourceIngestError, SourceIngestService

logger = logging.getLogger(__name__)


class IntakeDiscoveryError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        stage: str = "unknown",
        diagnostics_id: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.diagnostics_id = diagnostics_id or str(uuid4())
        self.details = details or {}


@dataclass(frozen=True)
class IntakeDiscoverySummary:
    diagnostics_id: str
    source_profile_id: UUID
    crawl_session_id: UUID | None
    submitted_profile_url: str
    normalized_profile_identifier: str | None
    videos_discovered_count: int
    videos_created_count: int
    videos_updated_count: int
    candidates_total_count: int
    candidates_matched_count: int
    candidates_rejected_count: int
    candidate_results_count: int
    filters_applied_summary: dict
    unsupported_filters_ignored: list[str]
    fetch_mode: str
    used_existing_profile: bool
    douyin_account_connection_id: UUID | None
    warning: str | None
    discovered_at: datetime
    fetch_stage: str | None = None
    fetch_stage_code: str | None = None
    fetch_stage_message: str | None = None
    parser_strategy: str | None = None
    fetch_execution_path: str | None = None
    fallback_from_execution_path: str | None = None
    strategy_policy: str | None = None
    primary_execution_path: str | None = None
    http_fallback_attempted: bool | None = None
    http_fallback_reason: str | None = None
    preflight_ran: bool = False
    preflight_result: str | None = None
    fetch_readiness_category: str | None = None
    selected_fetch_path: str | None = None
    browser_reopen_attempted: bool | None = None
    browser_reopen_result: str | None = None
    preflight_failure_code: str | None = None
    preflight_cached: bool | None = None
    watchdog_result: str | None = None
    watchdog_status: str | None = None
    watchdog_reason: str | None = None
    runtime_reconciled: bool | None = None
    videos_normalized_count: int = 0
    videos_persisted_count: int = 0
    selected_douyin_account_connection_id: UUID | None = None
    resolved_douyin_account_connection_id: UUID | None = None
    douyin_account_selection_mode: str | None = None
    douyin_account_selection_reason: str | None = None
    douyin_account_fallback_notice: str | None = None


@dataclass(frozen=True)
class ExistingProfileUsability:
    usable: bool
    video_count: int
    latest_crawl_session_id: UUID | None
    latest_crawl_status: CrawlSessionStatus | None
    reason: str | None = None


@dataclass(frozen=True)
class LiveFetchAccountSelection:
    selected_account_id: UUID | None
    resolved_account_id: UUID
    selection_mode: str
    selection_reason: str
    fallback_notice: str | None = None


@dataclass(frozen=True)
class FetchStageSummary:
    stage: str
    code: str
    message: str
    parser_strategy: str | None = None
    fetch_execution_path: str | None = None
    fallback_from_execution_path: str | None = None
    strategy_policy: str | None = None
    primary_execution_path: str | None = None
    http_fallback_attempted: bool | None = None
    http_fallback_reason: str | None = None
    videos_normalized_count: int = 0
    videos_persisted_count: int = 0


@dataclass(frozen=True)
class IntakeReadyCheckSummary:
    diagnostics_id: str
    readiness_status: str
    safe_to_run_intake_now: bool
    selected_account_id: UUID | None
    selected_account_label: str | None
    resolved_account_id: UUID | None
    resolved_account_label: str | None
    account_selection_mode: str | None
    account_selection_reason: str | None
    account_fallback_notice: str | None
    account_health: str | None
    browser_profile_status: str | None
    browser_profile_available: bool
    browser_reopen_needed: bool
    browser_reopen_attempted: bool
    browser_reopen_result: str | None
    intended_fetch_path: str | None
    fallback_allowed: bool
    recommended_action: str
    recommended_action_label: str
    summary_message: str
    preflight_cached: bool = False
    watchdog_result: str | None = None
    watchdog_status: str | None = None
    watchdog_reason: str | None = None
    preflight_result: str | None = None
    fetch_readiness_category: str | None = None
    preflight_failure_code: str | None = None
    preflight_failure_message: str | None = None
    challenge_state: str | None = None
    challenge_category: str | None = None
    challenge_count: int | None = None
    challenge_cooldown_until: datetime | None = None
    challenge_recommended_next_action: str | None = None
    profile_quarantine_state: str = "active_preferred"
    profile_quarantine_reason: str | None = None
    profile_quarantine_detected: bool = False
    profile_quarantine_recommended_next_action: str | None = None
    profile_quarantine_blocks_primary_flow: bool = False
    profile_quarantine_replaced_by_account_id: UUID | None = None
    profile_quarantine_clean_profile_recommendation: str | None = None
    profile_url: str | None = None


class IntakeDiscoveryService:
    def __init__(self, db: Session):
        self.db = db

    def ready_check(
        self,
        *,
        workspace_id: UUID | None,
        requested_account_id: UUID | None,
        profile_url: str | None = None,
    ) -> IntakeReadyCheckSummary:
        diagnostics_id = str(uuid4())
        settings = get_settings()
        fallback_allowed = bool(getattr(settings, "douyin_enable_legacy_http_fallback", False))
        account_service = DouyinAccountService(self.db)
        try:
            selected_account = account_service.get_account(requested_account_id) if requested_account_id is not None else None
        except DouyinAccountError:
            selected_account = None
        selected_label = getattr(selected_account, "display_name", None)

        try:
            selection = self._resolve_live_fetch_account_selection(
                workspace_id=workspace_id,
                requested_account_id=requested_account_id,
            )
        except IntakeDiscoveryError as exc:
            return IntakeReadyCheckSummary(
                diagnostics_id=diagnostics_id,
                readiness_status="NOT_READY",
                safe_to_run_intake_now=False,
                selected_account_id=requested_account_id,
                selected_account_label=selected_label,
                resolved_account_id=None,
                resolved_account_label=None,
                account_selection_mode="unresolved",
                account_selection_reason=exc.code,
                account_fallback_notice=None,
                account_health=None,
                browser_profile_status=None,
                browser_profile_available=False,
                browser_reopen_needed=False,
                browser_reopen_attempted=False,
                browser_reopen_result=None,
                intended_fetch_path=None,
                fallback_allowed=fallback_allowed,
                recommended_action="go_to_accounts",
                recommended_action_label="Go to accounts",
                summary_message=exc.message,
                preflight_result="failed",
                fetch_readiness_category="fetch_not_ready",
                preflight_failure_code=exc.code,
                preflight_failure_message=exc.message,
                profile_url=profile_url,
            )

        resolved_account = account_service.get_account(selection.resolved_account_id)
        health = account_service.health_summary(resolved_account)
        preflight = account_service.preflight_fetch_readiness(selection.resolved_account_id)
        readiness_status = self._ready_check_status(preflight=preflight)
        browser_reopen_needed = preflight.fetch_readiness_category == "fetch_ready_after_browser_reopen"
        browser_profile_status = (
            preflight.browser_context_status
            or preflight.watchdog_status
            or ("saved" if preflight.browser_profile_available else "none")
        )
        recommended_action, recommended_action_label = self._ready_check_recommended_action(
            readiness_status=readiness_status,
            preflight=preflight,
        )
        summary_message = self._ready_check_summary_message(
            readiness_status=readiness_status,
            account_label=resolved_account.display_name,
            preflight=preflight,
        )
        return IntakeReadyCheckSummary(
            diagnostics_id=diagnostics_id,
            readiness_status=readiness_status,
            safe_to_run_intake_now=readiness_status in {"READY", "READY_AFTER_REOPEN"} or (fallback_allowed and readiness_status == "FALLBACK_READY"),
            selected_account_id=selection.selected_account_id,
            selected_account_label=selected_label,
            resolved_account_id=resolved_account.id,
            resolved_account_label=resolved_account.display_name,
            account_selection_mode=selection.selection_mode,
            account_selection_reason=selection.selection_reason,
            account_fallback_notice=selection.fallback_notice,
            account_health=health.health_status.value if hasattr(health.health_status, "value") else str(health.health_status),
            browser_profile_status=browser_profile_status,
            browser_profile_available=preflight.browser_profile_available,
            browser_reopen_needed=browser_reopen_needed,
            browser_reopen_attempted=preflight.browser_reopen_attempted,
            browser_reopen_result=preflight.browser_reopen_result,
            intended_fetch_path=preflight.selected_fetch_path,
            fallback_allowed=fallback_allowed,
            recommended_action=recommended_action,
            recommended_action_label=recommended_action_label,
            summary_message=summary_message,
            preflight_cached=preflight.preflight_cached,
            watchdog_result=preflight.watchdog_result,
            watchdog_status=preflight.watchdog_status,
            watchdog_reason=preflight.watchdog_reason,
            preflight_result=preflight.preflight_result,
            fetch_readiness_category=preflight.fetch_readiness_category,
            preflight_failure_code=preflight.preflight_failure_code,
            preflight_failure_message=preflight.preflight_failure_message,
            challenge_state=preflight.challenge_state,
            challenge_category=preflight.challenge_category,
            challenge_count=preflight.challenge_count,
            challenge_cooldown_until=preflight.challenge_cooldown_until,
            challenge_recommended_next_action=preflight.challenge_recommended_next_action,
            profile_quarantine_state=preflight.profile_quarantine_state,
            profile_quarantine_reason=preflight.profile_quarantine_reason,
            profile_quarantine_detected=preflight.profile_quarantine_detected,
            profile_quarantine_recommended_next_action=preflight.profile_quarantine_recommended_next_action,
            profile_quarantine_blocks_primary_flow=preflight.profile_quarantine_blocks_primary_flow,
            profile_quarantine_replaced_by_account_id=preflight.profile_quarantine_replaced_by_account_id,
            profile_quarantine_clean_profile_recommendation=preflight.profile_quarantine_clean_profile_recommendation,
            profile_url=profile_url,
        )

    def discover(
        self,
        *,
        profile_url: str,
        workspace_id: UUID | None,
        source_platform: SourcePlatformEnum,
        preset_name: str | None,
        filter_config: FilterConfig | None,
        persist: bool,
        force_live_refresh: bool = False,
        douyin_account_connection_id: UUID | None = None,
    ) -> IntakeDiscoverySummary:
        diagnostics_id = str(uuid4())
        stage = "normalize_profile_input"
        if source_platform != SourcePlatformEnum.DOUYIN:
            raise IntakeDiscoveryError(
                "unsupported_platform",
                "Only Douyin intake is supported",
                stage=stage,
                diagnostics_id=diagnostics_id,
            )

        adapter = DouyinProfileAdapter()
        try:
            identity = adapter.normalize_profile_identity(profile_url)
        except SourceAdapterError as exc:
            raise IntakeDiscoveryError(str(exc.code), exc.message, stage=stage, diagnostics_id=diagnostics_id) from exc

        source_profile = self._find_existing_profile(
            workspace_id=workspace_id,
            source_platform=source_platform,
            external_id=identity.source_profile_external_id,
            profile_url=profile_url,
            canonical_url=identity.canonical_url,
        )

        crawl_session_id: UUID | None = None
        videos_discovered_count = 0
        videos_created_count = 0
        videos_updated_count = 0
        warning: str | None = None
        used_existing_profile = False
        account_selection: LiveFetchAccountSelection | None = None
        preflight = None
        fetch_stage_summary = FetchStageSummary(
            stage="candidate_filter",
            code="success",
            message="Candidate discovery completed.",
        )
        logger.info(
            "intake_discovery_started",
            extra={
                "diagnostics_id": diagnostics_id,
                "profile_url": profile_url,
                "source_platform": str(source_platform),
                "requested_account_id": None if douyin_account_connection_id is None else str(douyin_account_connection_id),
                "force_live_refresh": force_live_refresh,
            },
        )

        try:
            if source_profile is not None and not force_live_refresh:
                usability = self._existing_profile_usability(source_profile.id)
                if usability.usable:
                    used_existing_profile = True
                    crawl_session_id = usability.latest_crawl_session_id
                    videos_discovered_count = usability.video_count
                    warning = "Used existing source profile with usable source videos; no new crawl was run."
                    fetch_stage_summary = FetchStageSummary(
                        stage="existing_data",
                        code="success",
                        message="Used existing source profile data.",
                        videos_normalized_count=usability.video_count,
                        videos_persisted_count=usability.video_count,
                    )
                else:
                    warning = (
                        "Existing source profile was not reusable"
                        f" ({usability.reason or 'unusable data'}); ran live fetch instead."
                    )

            if source_profile is not None and force_live_refresh:
                warning = "Force live refresh requested; existing source profile data was ignored."

            if source_profile is None or not used_existing_profile:
                stage = "resolve_account"
                try:
                    account_selection = self._resolve_live_fetch_account_selection(
                        workspace_id=workspace_id,
                        requested_account_id=douyin_account_connection_id,
                    )
                except IntakeDiscoveryError as exc:
                    raise IntakeDiscoveryError(
                        exc.code,
                        exc.message,
                        stage=exc.stage or stage,
                        diagnostics_id=diagnostics_id,
                    ) from exc
                logger.info(
                    "intake_discovery_account_resolved",
                    extra={
                        "diagnostics_id": diagnostics_id,
                        "selection_mode": account_selection.selection_mode,
                        "selection_reason": account_selection.selection_reason,
                        "selected_account_id": None if account_selection.selected_account_id is None else str(account_selection.selected_account_id),
                        "resolved_account_id": str(account_selection.resolved_account_id),
                    },
                )
                stage = "preflight_fetch"
                try:
                    account_service = DouyinAccountService(self.db)
                    preflight = account_service.preflight_fetch_readiness(account_selection.resolved_account_id)
                    logger.info(
                        "intake_discovery_fetch_preflight_completed",
                        extra={
                            "diagnostics_id": diagnostics_id,
                            "resolved_account_id": str(account_selection.resolved_account_id),
                            "preflight_result": preflight.preflight_result,
                            "fetch_readiness_category": preflight.fetch_readiness_category,
                            "selected_fetch_path": preflight.selected_fetch_path,
                            "browser_reopen_attempted": preflight.browser_reopen_attempted,
                            "browser_reopen_result": preflight.browser_reopen_result,
                            "preflight_cached": preflight.preflight_cached,
                            "watchdog_result": preflight.watchdog_result,
                            "runtime_reconciled": preflight.runtime_reconciled,
                        },
                    )
                    if preflight.preflight_result != "passed":
                        raise IntakeDiscoveryError(
                            preflight.preflight_failure_code or "fetch_preflight_failed",
                            preflight.preflight_failure_message or "Selected Douyin account is not fetch-ready.",
                            stage=stage,
                            diagnostics_id=diagnostics_id,
                            details={"preflight": preflight.to_dict()},
                        )
                except IntakeDiscoveryError:
                    raise
                except DouyinAccountError as exc:
                    code, message = self._classify_account_error(exc)
                    raise IntakeDiscoveryError(code, message, stage=stage, diagnostics_id=diagnostics_id) from exc

                stage = "build_fetch_client"
                try:
                    adapter = account_service.build_douyin_adapter(account_selection.resolved_account_id)
                except DouyinAccountError as exc:
                    code, message = self._classify_account_error(exc)
                    raise IntakeDiscoveryError(code, message, stage=stage, diagnostics_id=diagnostics_id) from exc

                stage = "dispatch_live_fetch"
                try:
                    ingest_summary = SourceIngestService(
                        self.db,
                        adapters={SourcePlatformEnum.DOUYIN: adapter},
                    ).ingest_profile(
                        workspace_id=workspace_id,
                        profile_url=profile_url,
                        source_platform=source_platform,
                        crawl_mode="operator_intake",
                    )
                except SourceIngestError as exc:
                    code, message, stage = self._classify_ingest_error(exc)
                    raise IntakeDiscoveryError(code, message, stage=stage, diagnostics_id=diagnostics_id) from exc

                if ingest_summary.status != CrawlSessionStatus.COMPLETED or ingest_summary.source_profile_id is None:
                    raise IntakeDiscoveryError(
                        ingest_summary.error_code or "ingest_incomplete",
                        ingest_summary.error_message or "Source profile ingest did not complete",
                        stage="persist_entities",
                        diagnostics_id=diagnostics_id,
                    )
                source_profile = self.db.get(SourceProfile, UUID(str(ingest_summary.source_profile_id)))
                if source_profile is None:
                    raise IntakeDiscoveryError(
                        "source_profile_missing",
                        "Ingest completed but source profile was not found",
                        stage="persist_entities",
                        diagnostics_id=diagnostics_id,
                    )
                crawl_session_id = UUID(str(ingest_summary.crawl_session_id))
                videos_discovered_count = ingest_summary.videos_discovered_count
                videos_created_count = ingest_summary.videos_created_count
                videos_updated_count = ingest_summary.videos_updated_count
                fetch_stage_summary = self._fetch_stage_summary_from_crawl(
                    self.db.get(CrawlSession, crawl_session_id),
                    videos_discovered_count=videos_discovered_count,
                )

            stage = "candidate_filtering"
            result = CandidateEvaluationService(self.db).apply(
                preset_name=preset_name,
                filter_config=filter_config,
                source_profile_id=source_profile.id,
                persist=persist,
            )
        except IntakeDiscoveryError:
            raise
        except Exception as exc:
            logger.exception(
                "intake_discovery_failed",
                extra={"diagnostics_id": diagnostics_id, "stage": stage},
            )
            raise IntakeDiscoveryError(
                "unknown_server_error",
                "Unexpected intake discovery error.",
                stage=stage,
                diagnostics_id=diagnostics_id,
            ) from exc

        if not used_existing_profile and fetch_stage_summary.code not in {"success", "filter_zero_candidates"}:
            warning = self._append_warning(warning, fetch_stage_summary.message)
        elif videos_discovered_count == 0 and not used_existing_profile:
            warning = self._append_warning(warning, "Profile fetch returned zero videos.")
        if result.matched_count == 0 and fetch_stage_summary.code == "success":
            warning = self._append_warning(
                warning,
                "No candidates matched the current filters." if videos_discovered_count > 0 else "No candidates were produced from this discovery run.",
            )
            fetch_stage_summary = FetchStageSummary(
                stage="candidate_filter",
                code="filter_zero_candidates",
                message="Videos were fetched, but no candidates matched the current filters.",
                parser_strategy=fetch_stage_summary.parser_strategy,
                fetch_execution_path=fetch_stage_summary.fetch_execution_path,
                fallback_from_execution_path=fetch_stage_summary.fallback_from_execution_path,
                strategy_policy=fetch_stage_summary.strategy_policy,
                primary_execution_path=fetch_stage_summary.primary_execution_path,
                http_fallback_attempted=fetch_stage_summary.http_fallback_attempted,
                http_fallback_reason=fetch_stage_summary.http_fallback_reason,
                videos_normalized_count=fetch_stage_summary.videos_normalized_count or videos_discovered_count,
                videos_persisted_count=fetch_stage_summary.videos_persisted_count or (videos_created_count + videos_updated_count),
            )

        fetch_mode = (
            "existing_data"
            if used_existing_profile
            else "forced_live_fetch_using_account"
            if force_live_refresh
            else "live_fetch_using_account"
        )

        if crawl_session_id is not None:
            crawl_session = self.db.get(CrawlSession, crawl_session_id)
            if crawl_session is not None and hasattr(crawl_session, "metadata_json"):
                existing_metadata = crawl_session.metadata_json
                metadata = dict(existing_metadata) if isinstance(existing_metadata, dict) else {}
                metadata.update(
                    {
                        "diagnostics_id": diagnostics_id,
                        "fetch_mode": fetch_mode,
                        "candidates_total_count": result.total_count,
                        "candidates_matched_count": result.matched_count,
                        "candidates_rejected_count": result.rejected_count,
                        "candidate_results_count": len(result.evaluations),
                        "douyin_account_selection_mode": account_selection.selection_mode if account_selection else None,
                        "douyin_account_selection_reason": account_selection.selection_reason if account_selection else None,
                        "douyin_account_fallback_notice": account_selection.fallback_notice if account_selection else None,
                        "preflight": preflight.to_dict() if preflight is not None else None,
                    }
                )
                crawl_session.metadata_json = metadata
                self.db.commit()

        return IntakeDiscoverySummary(
            diagnostics_id=diagnostics_id,
            source_profile_id=source_profile.id,
            crawl_session_id=crawl_session_id,
            submitted_profile_url=profile_url,
            normalized_profile_identifier=source_profile.source_profile_external_id,
            videos_discovered_count=videos_discovered_count,
            videos_created_count=videos_created_count,
            videos_updated_count=videos_updated_count,
            candidates_total_count=result.total_count,
            candidates_matched_count=result.matched_count,
            candidates_rejected_count=result.rejected_count,
            candidate_results_count=len(result.evaluations),
            filters_applied_summary=filter_config.to_dict() if filter_config is not None else {},
            unsupported_filters_ignored=[],
            fetch_mode=fetch_mode,
            used_existing_profile=used_existing_profile,
            douyin_account_connection_id=account_selection.resolved_account_id if account_selection else None,
            warning=warning,
            discovered_at=datetime.now(UTC),
            fetch_stage=fetch_stage_summary.stage,
            fetch_stage_code=fetch_stage_summary.code,
            fetch_stage_message=fetch_stage_summary.message,
            parser_strategy=fetch_stage_summary.parser_strategy,
            fetch_execution_path=fetch_stage_summary.fetch_execution_path,
            fallback_from_execution_path=fetch_stage_summary.fallback_from_execution_path,
            strategy_policy=fetch_stage_summary.strategy_policy,
            primary_execution_path=fetch_stage_summary.primary_execution_path,
            http_fallback_attempted=fetch_stage_summary.http_fallback_attempted,
            http_fallback_reason=fetch_stage_summary.http_fallback_reason,
            preflight_ran=bool(preflight.preflight_ran) if preflight is not None else False,
            preflight_result=preflight.preflight_result if preflight is not None else None,
            fetch_readiness_category=preflight.fetch_readiness_category if preflight is not None else None,
            selected_fetch_path=preflight.selected_fetch_path if preflight is not None else None,
            browser_reopen_attempted=preflight.browser_reopen_attempted if preflight is not None else None,
            browser_reopen_result=preflight.browser_reopen_result if preflight is not None else None,
            preflight_failure_code=preflight.preflight_failure_code if preflight is not None else None,
            preflight_cached=preflight.preflight_cached if preflight is not None else None,
            watchdog_result=preflight.watchdog_result if preflight is not None else None,
            watchdog_status=preflight.watchdog_status if preflight is not None else None,
            watchdog_reason=preflight.watchdog_reason if preflight is not None else None,
            runtime_reconciled=preflight.runtime_reconciled if preflight is not None else None,
            videos_normalized_count=fetch_stage_summary.videos_normalized_count,
            videos_persisted_count=fetch_stage_summary.videos_persisted_count,
            selected_douyin_account_connection_id=account_selection.selected_account_id if account_selection else None,
            resolved_douyin_account_connection_id=account_selection.resolved_account_id if account_selection else None,
            douyin_account_selection_mode=account_selection.selection_mode if account_selection else None,
            douyin_account_selection_reason=account_selection.selection_reason if account_selection else None,
            douyin_account_fallback_notice=account_selection.fallback_notice if account_selection else None,
        )

    def _fetch_stage_summary_from_crawl(
        self,
        crawl_session: CrawlSession | None,
        *,
        videos_discovered_count: int,
    ) -> FetchStageSummary:
        if crawl_session is None or not hasattr(crawl_session, "status"):
            return FetchStageSummary(
                stage="dispatch_live_fetch",
                code="unknown_fetch_stage",
                message="Fetch completed without crawl session diagnostics.",
            )
        metadata_json = getattr(crawl_session, "metadata_json", None)
        raw_summary_json = getattr(crawl_session, "raw_summary_json", None)
        result_summary_json = getattr(crawl_session, "result_summary_json", None)
        metadata = metadata_json if isinstance(metadata_json, dict) else {}
        observability = metadata.get("fetch_observability") if isinstance(metadata.get("fetch_observability"), dict) else {}
        stages = observability.get("stages") if isinstance(observability.get("stages"), dict) else {}
        response_stage = stages.get("response_classification") if isinstance(stages.get("response_classification"), dict) else {}
        raw_summary = raw_summary_json if isinstance(raw_summary_json, dict) else {}
        result_summary = result_summary_json if isinstance(result_summary_json, dict) else {}
        code = response_stage.get("code") if isinstance(response_stage.get("code"), str) else None
        message = response_stage.get("message") if isinstance(response_stage.get("message"), str) else None
        parser_strategy = raw_summary.get("parse_strategy") if isinstance(raw_summary.get("parse_strategy"), str) else None
        normalized_count = raw_summary.get("normalized_video_count") if isinstance(raw_summary.get("normalized_video_count"), int) else videos_discovered_count
        persisted_count = result_summary.get("persisted_video_count") if isinstance(result_summary.get("persisted_video_count"), int) else (getattr(crawl_session, "videos_created_count", 0) + getattr(crawl_session, "videos_updated_count", 0))
        fetch_execution_path = raw_summary.get("fetch_execution_path")
        if not isinstance(fetch_execution_path, str):
            fetch_execution_path = observability.get("fetch_execution_path") if isinstance(observability.get("fetch_execution_path"), str) else None
        fallback_from_execution_path = raw_summary.get("fallback_from_execution_path")
        if not isinstance(fallback_from_execution_path, str):
            fallback_from_execution_path = (
                observability.get("fallback_from_execution_path")
                if isinstance(observability.get("fallback_from_execution_path"), str)
                else None
            )
        strategy_policy = raw_summary.get("strategy_policy")
        if not isinstance(strategy_policy, str):
            strategy_policy = observability.get("strategy_policy") if isinstance(observability.get("strategy_policy"), str) else None
        primary_execution_path = raw_summary.get("primary_execution_path")
        if not isinstance(primary_execution_path, str):
            primary_execution_path = (
                observability.get("primary_execution_path")
                if isinstance(observability.get("primary_execution_path"), str)
                else None
            )
        http_fallback_attempted = raw_summary.get("http_fallback_attempted")
        if not isinstance(http_fallback_attempted, bool):
            http_fallback_attempted = (
                observability.get("http_fallback_attempted")
                if isinstance(observability.get("http_fallback_attempted"), bool)
                else None
            )
        http_fallback_reason = raw_summary.get("http_fallback_reason")
        if not isinstance(http_fallback_reason, str):
            http_fallback_reason = (
                observability.get("http_fallback_reason")
                if isinstance(observability.get("http_fallback_reason"), str)
                else None
            )

        if crawl_session.status == CrawlSessionStatus.FAILED:
            return FetchStageSummary(
                stage="classify_response",
                code=self._canonical_fetch_stage_code(code),
                message=message or crawl_session.error_message or "Douyin profile fetch failed before videos could be ingested.",
                parser_strategy=parser_strategy,
                fetch_execution_path=fetch_execution_path,
                fallback_from_execution_path=fallback_from_execution_path,
                strategy_policy=strategy_policy,
                primary_execution_path=primary_execution_path,
                http_fallback_attempted=http_fallback_attempted,
                http_fallback_reason=http_fallback_reason,
                videos_normalized_count=normalized_count,
                videos_persisted_count=persisted_count,
            )

        if videos_discovered_count == 0:
            return FetchStageSummary(
                stage="classify_response",
                code=self._canonical_fetch_stage_code(code or raw_summary.get("response_classification_code")),
                message=message or raw_summary.get("response_classification_message") or "Profile fetch returned zero videos.",
                parser_strategy=parser_strategy,
                fetch_execution_path=fetch_execution_path,
                fallback_from_execution_path=fallback_from_execution_path,
                strategy_policy=strategy_policy,
                primary_execution_path=primary_execution_path,
                http_fallback_attempted=http_fallback_attempted,
                http_fallback_reason=http_fallback_reason,
                videos_normalized_count=normalized_count,
                videos_persisted_count=persisted_count,
            )

        return FetchStageSummary(
            stage="candidate_filter",
            code="success",
            message="Profile fetch returned videos and candidate discovery completed.",
            parser_strategy=parser_strategy,
            fetch_execution_path=fetch_execution_path,
            fallback_from_execution_path=fallback_from_execution_path,
            strategy_policy=strategy_policy,
            primary_execution_path=primary_execution_path,
            http_fallback_attempted=http_fallback_attempted,
            http_fallback_reason=http_fallback_reason,
            videos_normalized_count=normalized_count,
            videos_persisted_count=persisted_count,
        )

    def _canonical_fetch_stage_code(self, code: str | None) -> str:
        normalized = (code or "").lower().strip()
        if normalized in {"blocked_response", "login_required", "parse_failed", "parse_zero_videos", "true_zero_videos"}:
            return normalized
        if "challenge" in normalized or "blocked" in normalized:
            return "blocked_response"
        if "login" in normalized:
            return "login_required"
        if "parse_zero" in normalized:
            return "parse_zero_videos"
        if "true_zero" in normalized:
            return "true_zero_videos"
        if "parse" in normalized or "unsupported_shape" in normalized:
            return "parse_failed"
        return "parse_zero_videos"

    def _find_existing_profile(
        self,
        *,
        workspace_id: UUID | None,
        source_platform: SourcePlatformEnum,
        external_id: str,
        profile_url: str,
        canonical_url: str,
    ) -> SourceProfile | None:
        stmt = select(SourceProfile).where(
            SourceProfile.source_platform == source_platform,
            or_(
                SourceProfile.source_profile_external_id == external_id,
                SourceProfile.profile_url == profile_url,
                SourceProfile.profile_url == canonical_url,
            ),
        )
        if workspace_id is not None:
            stmt = stmt.where(SourceProfile.workspace_id == workspace_id)
        return self.db.scalar(stmt.order_by(SourceProfile.updated_at.desc()).limit(1))

    def _existing_profile_usability(self, source_profile_id: UUID) -> ExistingProfileUsability:
        video_count = self.db.scalar(
            select(func.count(SourceVideo.id)).where(SourceVideo.source_profile_id == source_profile_id)
        ) or 0
        latest_crawl = self.db.scalar(
            select(CrawlSession)
            .where(CrawlSession.source_profile_id == source_profile_id)
            .order_by(CrawlSession.created_at.desc())
            .limit(1)
        )

        if video_count <= 0:
            return ExistingProfileUsability(
                usable=False,
                video_count=video_count,
                latest_crawl_session_id=latest_crawl.id if latest_crawl else None,
                latest_crawl_status=latest_crawl.status if latest_crawl else None,
                reason="no source videos",
            )
        if latest_crawl is not None and latest_crawl.status == CrawlSessionStatus.FAILED:
            return ExistingProfileUsability(
                usable=False,
                video_count=video_count,
                latest_crawl_session_id=latest_crawl.id,
                latest_crawl_status=latest_crawl.status,
                reason="latest crawl failed",
            )
        return ExistingProfileUsability(
            usable=True,
            video_count=video_count,
            latest_crawl_session_id=latest_crawl.id if latest_crawl else None,
            latest_crawl_status=latest_crawl.status if latest_crawl else None,
        )

    def _append_warning(self, current: str | None, next_warning: str) -> str:
        if not current:
            return next_warning
        return f"{current} {next_warning}"

    def _resolve_live_fetch_account_selection(
        self,
        *,
        workspace_id: UUID | None,
        requested_account_id: UUID | None,
    ) -> LiveFetchAccountSelection:
        account_service = DouyinAccountService(self.db)
        accounts = account_service.list_accounts(workspace_id=workspace_id)
        accounts_by_id = {account.id: account for account in accounts}

        if requested_account_id is not None and requested_account_id not in accounts_by_id:
            raise IntakeDiscoveryError(
                "account_resolution_failed",
                "Selected Douyin account connection was not found in this workspace.",
                stage="resolve_account",
            )

        evaluations = [
            (account, account_service.health_summary(account))
            for account in accounts
        ]
        usable = [item for item in evaluations if item[1].can_use_for_live_fetch]

        selected_account = accounts_by_id.get(requested_account_id) if requested_account_id else None
        if selected_account is not None:
            selected_health = account_service.health_summary(selected_account)
            if selected_health.can_use_for_live_fetch:
                return LiveFetchAccountSelection(
                    selected_account_id=selected_account.id,
                    resolved_account_id=selected_account.id,
                    selection_mode="selected",
                    selection_reason="selected_account_usable",
                )
            fallback = self._pick_best_usable_account(usable)
            if fallback is not None:
                fallback_account, fallback_health = fallback
                return LiveFetchAccountSelection(
                    selected_account_id=selected_account.id,
                    resolved_account_id=fallback_account.id,
                    selection_mode="fallback",
                    selection_reason="selected_account_unusable",
                    fallback_notice=(
                        "Selected Douyin account was not usable for live fetch "
                        f"({selected_health.health_status}); used {fallback_account.display_name} "
                        f"({fallback_health.health_status}) instead."
                    ),
                )
            code, message = self._classify_unusable_selected_account(selected_account, selected_health)
            raise IntakeDiscoveryError(code, message, stage="resolve_account")

        default_account = account_service.default_account(workspace_id=workspace_id)
        if default_account is not None:
            default_health = account_service.health_summary(default_account)
            if default_health.can_use_for_live_fetch:
                return LiveFetchAccountSelection(
                    selected_account_id=None,
                    resolved_account_id=default_account.id,
                    selection_mode="default",
                    selection_reason="default_account_usable",
                )
            fallback = self._pick_best_usable_account(usable)
            if fallback is not None:
                fallback_account, fallback_health = fallback
                return LiveFetchAccountSelection(
                    selected_account_id=None,
                    resolved_account_id=fallback_account.id,
                    selection_mode="fallback",
                    selection_reason="default_account_unusable",
                    fallback_notice=(
                        "Default Douyin account was not usable for live fetch "
                        f"({default_health.health_status}); used {fallback_account.display_name} "
                        f"({fallback_health.health_status}) instead."
                    ),
                )
            raise IntakeDiscoveryError(
                "account_resolution_failed",
                "No usable Douyin account is available for live fetch. Connect or validate one at /accounts/douyin.",
                stage="resolve_account",
            )

        fallback = self._pick_best_usable_account(usable)
        if fallback is not None:
            fallback_account, _ = fallback
            return LiveFetchAccountSelection(
                selected_account_id=None,
                resolved_account_id=fallback_account.id,
                selection_mode="fallback",
                selection_reason="default_missing_used_best_available",
                fallback_notice="No default Douyin account was configured; used the healthiest available account.",
            )

        raise IntakeDiscoveryError(
            "account_resolution_failed",
            "Live Douyin fetch requires a validated Douyin account connection. Connect one at /accounts/douyin.",
            stage="resolve_account",
        )

    def _ready_check_status(self, *, preflight) -> str:
        if preflight.fetch_readiness_category == "fetch_blocked_by_profile_quarantine":
            return "PROFILE_QUARANTINED"
        if preflight.fetch_readiness_category == "fetch_blocked_by_browser_challenge":
            return "CHALLENGE_BLOCKED"
        if preflight.preflight_result != "passed":
            return "NOT_READY"
        if preflight.fetch_readiness_category == "fetch_ready_after_browser_reopen":
            return "READY_AFTER_REOPEN"
        if preflight.fetch_readiness_category == "fetch_ready_http_fallback":
            return "FALLBACK_READY"
        return "READY"

    def _ready_check_recommended_action(self, *, readiness_status: str, preflight) -> tuple[str, str]:
        if readiness_status == "READY":
            return "run_intake_now", "Run Intake now"
        if readiness_status == "READY_AFTER_REOPEN":
            return "run_intake_now", "Run Intake now"
        if readiness_status == "FALLBACK_READY":
            if bool(getattr(get_settings(), "douyin_enable_legacy_http_fallback", False)):
                return "run_intake_now", "Run Intake with legacy HTTP fallback"
            return "go_to_accounts", "Reconnect browser profile"
        if readiness_status == "PROFILE_QUARANTINED":
            return "create_clean_managed_browser_profile", "Create clean browser profile"
        if readiness_status == "CHALLENGE_BLOCKED":
            if preflight.challenge_state == "challenge_recently_solved_pending_recheck":
                return "recheck_challenge", "Run post-challenge validation"
            if preflight.challenge_state == "challenge_cooldown_active":
                return "mark_challenge_solved", "Wait for cooldown or mark challenge solved"
            return "solve_douyin_challenge", "Solve Douyin challenge"
        if preflight.preflight_failure_code == "account_not_fetch_ready":
            return "revalidate_account", "Validate account"
        return "go_to_accounts", "Go to accounts"

    def _ready_check_summary_message(self, *, readiness_status: str, account_label: str, preflight) -> str:
        if readiness_status == "PROFILE_QUARANTINED":
            return (
                f"Profile quarantined: {account_label} is blocked from normal Capture and Intake because it repeatedly hit Douyin challenges or blocked browser responses. "
                "Create and validate a fresh managed browser-backed profile, then use that clean profile for Intake."
            )
        if readiness_status == "CHALLENGE_BLOCKED":
            if preflight.challenge_state == "challenge_recently_solved_pending_recheck":
                return f"Challenge pending recheck: {account_label} must pass browser-backed validation after the manual solve before Intake can run."
            if preflight.challenge_state == "challenge_cooldown_active":
                return (
                    f"Challenge cooldown active: {account_label} cannot run normal Validate or Intake until cooldown clears. "
                    "Complete the challenge in the saved browser profile, then use Mark challenge solved for the browser-backed recheck."
                )
            return f"Challenge blocked: {account_label} has an unresolved Douyin browser challenge. Complete it in the saved browser profile before Intake."
        if readiness_status == "READY":
            return f"Ready: {account_label} can run Intake now using the connected browser profile."
        if readiness_status == "READY_AFTER_REOPEN":
            return (
                f"Ready after reopen: {account_label} needed its saved browser profile reopened. "
                "Intake can run now using that profile."
            )
        if readiness_status == "FALLBACK_READY":
            if bool(getattr(get_settings(), "douyin_enable_legacy_http_fallback", False)):
                return (
                    f"Legacy fallback ready: {account_label} can run Intake now through detached HTTP because "
                    "legacy HTTP fallback was explicitly enabled."
                )
            return f"Not ready: {account_label} must reconnect or reopen its browser profile before Intake."
        return preflight.preflight_failure_message or f"Not ready: {account_label} cannot run Intake yet."

    def _classify_account_error(self, exc: DouyinAccountError) -> tuple[str, str]:
        code = getattr(exc, "code", None) or str(exc)
        if code == "imported_session_missing_cookie":
            return "imported_session_missing_cookie", "Selected imported session is missing a valid Cookie header."
        if code == "imported_session_cookie_parse_failed":
            return "imported_session_cookie_parse_failed", "Selected imported session could not be parsed into a valid cookie export."
        if code == "imported_session_cookie_too_thin":
            return "imported_session_cookie_too_thin", "Selected imported session did not include strong authenticated Douyin cookies."
        if code == "imported_session_invalid":
            return "imported_session_invalid", "Selected imported session could not be normalized into a usable Cookie header."
        if code in {"missing_user_agent", "imported_session_missing_user_agent"}:
            return "missing_user_agent", "Selected account is missing a usable browser user agent."
        if code == "validation_transport_error":
            return "validation_transport_error", "Selected account could not complete validation because Douyin was not reachable reliably."
        if code == "parse_failed":
            return "parse_failed", "Selected account did not pass fetch preflight cleanly."
        if code == "login_required":
            return "login_required", "Selected account session is invalid or expired."
        if code == "blocked_response":
            return "blocked_response", "Douyin rejected the selected account session with a blocked response."
        if code == "account_resolution_failed":
            return "account_resolution_failed", str(exc)
        return "fetch_client_construction_failed", str(exc)

    def _classify_ingest_error(self, exc: SourceIngestError) -> tuple[str, str, str]:
        code = str(exc.code)
        message = exc.message
        lowered = message.lower()
        raw_payload = exc.raw_payload if isinstance(exc.raw_payload, dict) else {}
        raw_metadata = raw_payload.get("metadata") if isinstance(raw_payload.get("metadata"), dict) else {}
        response_classification = raw_metadata.get("response_classification") if isinstance(raw_metadata.get("response_classification"), dict) else {}
        response_code = response_classification.get("code") if isinstance(response_classification.get("code"), str) else None
        if code == str(SourceAdapterErrorCode.NORMALIZATION_FAILED):
            return "normalize_failed", "Douyin response could not be normalized into canonical profile/video data.", "normalize_payload"
        if code == str(SourceAdapterErrorCode.PERSISTENCE_FAILED):
            return "persistence_failed", "Fetched Douyin data could not be persisted.", "persist_entities"
        if code == str(SourceAdapterErrorCode.RATE_LIMITED):
            return "blocked_response", "Douyin rate limited the selected account or network path.", "classify_response"
        if response_code == "blocked_response":
            return "blocked_response", response_classification.get("message") or "Douyin returned a blocked or challenge response.", "classify_response"
        if response_code == "login_required":
            return "login_required", response_classification.get("message") or "Selected account session is invalid or expired.", "classify_response"
        if response_code == "parse_failed":
            return "parse_failed", response_classification.get("message") or "Douyin rendered the profile but the parser did not expose video payloads.", "classify_response"
        if response_code == "parse_zero_videos":
            return "parse_zero_videos", response_classification.get("message") or "Douyin returned an HTML shell without parseable profile videos.", "classify_response"
        if "login" in lowered or "passport" in lowered or "expired" in lowered:
            return "login_required", "Selected account session is invalid or expired.", "classify_response"
        if "blocked" in lowered or "captcha" in lowered or "security" in lowered or "challenge" in lowered:
            return "blocked_response", "Douyin returned a blocked or challenge response.", "classify_response"
        if "profile/video metadata" in lowered or "did not expose" in lowered:
            return "parse_failed", "Douyin response did not expose parseable profile/video data.", "classify_response"
        return "unknown_server_error", message, "dispatch_live_fetch"

    def _pick_best_usable_account(
        self,
        candidates: list[tuple[DouyinAccountConnection, DouyinAccountHealthSummary]],
    ) -> tuple[DouyinAccountConnection, DouyinAccountHealthSummary] | None:
        if not candidates:
            return None

        def health_rank(health: DouyinAccountHealthSummary) -> int:
            if str(health.health_status) == "HEALTHY":
                return 0
            if str(health.health_status) == "STALE":
                return 1
            if str(health.health_status) == "EXPIRING_SOON":
                return 2
            return 99

        def ts(value: datetime | None) -> float:
            if value is None:
                return 0.0
            return value.timestamp()

        return sorted(
            candidates,
            key=lambda item: (
                health_rank(item[1]),
                -ts(item[0].last_successful_validation_at),
                -ts(item[0].updated_at),
            ),
        )[0]

    def _classify_unusable_selected_account(
        self,
        account: DouyinAccountConnection,
        health: DouyinAccountHealthSummary,
    ) -> tuple[str, str]:
        raw_warning_summary = getattr(health, "warning_summary", None)
        warning_summary = raw_warning_summary if isinstance(raw_warning_summary, dict) else {}
        if warning_summary.get("profile_quarantine_state") in {"quarantined", "quarantined_recoverable", "quarantined_replaced"}:
            return (
                "profile_quarantined",
                "Selected Douyin browser profile is quarantined from normal Intake. Create and validate a fresh managed browser-backed profile, then use that clean profile.",
            )
        error_code = getattr(account, "last_error_code", None)
        if error_code == "imported_session_missing_user_agent":
            return "missing_user_agent", "Selected imported account is missing a usable User-Agent."
        if error_code == "imported_session_missing_cookie":
            return "imported_session_missing_cookie", "Selected imported account is missing a valid Cookie header."
        if error_code == "imported_session_cookie_parse_failed":
            return "imported_session_cookie_parse_failed", "Selected imported account could not parse its saved cookie export."
        if error_code == "imported_session_cookie_too_thin":
            return "imported_session_cookie_too_thin", "Selected imported account does not include strong authenticated Douyin cookies."
        if error_code == "imported_session_invalid":
            return "imported_session_invalid", "Selected imported account could not be normalized into a usable runtime session."
        if error_code == "blocked_response" or str(health.health_status) == "BLOCKED":
            return "blocked_response", "Douyin rejected the selected account session with a blocked response."
        if error_code in {"expired_session", "login_required"} or str(health.health_status) == "EXPIRED":
            return "login_required", "Selected account session is expired or redirected to login."
        if error_code == "validation_transport_error":
            return "validation_transport_error", "Selected account could not reach Douyin reliably during validation."
        if error_code == "parse_failed":
            return "parse_failed", "Selected account did not pass fetch preflight cleanly."
        return "account_resolution_failed", "Selected Douyin account is not usable for live fetch. Revalidate or repair it in /accounts/douyin."
