from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from src.analytics.services.publish_health_service import PublishHealthService
from src.core.settings import get_settings
from src.enums import PublishTargetPlatform
from src.publish_routing.services.control_queue_service import ControlQueueService
from src.schemas.analytics import PublishHealthDashboardResponse
from src.schemas.operations import OperationalMetricsResponse
from src.schemas.ops_home import (
    OpsHomeAccountHealthRow,
    OpsHomeAdmissionVerdict,
    OpsHomeActionItem,
    OpsHomeDependencySignal,
    OpsHomeFailureSignature,
    OpsHomeFetchAccountRow,
    OpsHomeFetchHealth,
    OpsHomeFetchReason,
    OpsHomeFreshness,
    OpsHomeHiddenRisk,
    OpsHomeJobHealthRow,
    OpsHomeKpi,
    OpsHomeOperationalStatus,
    OpsHomeOverall,
    OpsHomeQueueHealth,
    OpsHomeStorageCapacity,
    OpsHomeSummaryResponse,
    OpsHomeTrendDay,
)
from src.schemas.publish_routing import PublishControlQueueResponse
from src.services.operational_metrics import OperationalMetricsService
from src.services.operational_dependency_probe import probe_operational_dependencies
from src.services.ops_home_hidden_risk_service import (
    OpsHomeHiddenRiskService,
    build_ops_home_admission_verdict,
)


_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _count_status(metrics: OperationalMetricsResponse, status: str) -> int:
    return sum(int(counts.get(status, 0) or 0) for counts in metrics.job_counts_by_type_status.values())


def _render_count(metrics: OperationalMetricsResponse, *statuses: str) -> int:
    return sum(int(metrics.render_counts_by_status.get(status, 0) or 0) for status in statuses)


def _account_needs_care(account: object) -> bool:
    return _enum_value(getattr(account, "health_status", "")) != "HEALTHY" or bool(getattr(account, "is_on_hold", False))


def _job_tone(*, failed: int, retryable: int, running: int, queued: int, failure_rate: float) -> str:
    if failed > 0:
        return "danger"
    if retryable > 0 or failure_rate >= 10:
        return "warn"
    if running > 0 or queued > 0:
        return "active"
    return "good"


def _seven_day_publish_trend(
    publish_health: PublishHealthDashboardResponse,
    *,
    now: datetime,
) -> list[OpsHomeTrendDay]:
    by_day = {item.day: item for item in publish_health.by_day}
    days: list[OpsHomeTrendDay] = []
    for offset in range(6, -1, -1):
        day = (now.date() - timedelta(days=offset)).isoformat()
        item = by_day.get(day)
        days.append(
            OpsHomeTrendDay(
                day=day,
                attempts=item.attempts if item else 0,
                succeeded=item.succeeded if item else 0,
                failed=item.failed if item else 0,
                needs_reconciliation=item.needs_reconciliation if item else 0,
            )
        )
    return days


def build_ops_home_summary(
    metrics: OperationalMetricsResponse,
    publish_health: PublishHealthDashboardResponse,
    queue: PublishControlQueueResponse,
    *,
    generated_at: datetime | None = None,
    dependencies: list[OpsHomeDependencySignal] | None = None,
    storage_capacity: OpsHomeStorageCapacity | None = None,
    hidden_risks: list[OpsHomeHiddenRisk] | None = None,
    admission_verdict: OpsHomeAdmissionVerdict | None = None,
) -> OpsHomeSummaryResponse:
    now = generated_at or datetime.now(UTC)
    failed_jobs = _count_status(metrics, "FAILED")
    retryable_jobs = int(metrics.retryable_jobs or metrics.queue_backlog.retryable)
    active_jobs = int(metrics.queue_backlog.queued + metrics.queue_backlog.running + metrics.queue_backlog.retryable)
    failed_renders = _render_count(metrics, "FAILED")
    review_renders = _render_count(metrics, "READY_FOR_REVIEW", "WARNING")
    approved_renders = _render_count(metrics, "APPROVED", "PASSED")
    total_renders = sum(int(value or 0) for value in metrics.render_counts_by_status.values())
    open_risks = sum(int(value or 0) for value in metrics.open_risk_counts_by_severity.values())
    reconciliation = int(publish_health.overview.needs_reconciliation_attempts)
    blocked_by_risk = int(publish_health.overview.drafts_blocked_by_risk)
    care_accounts = [account for account in queue.accounts if _account_needs_care(account)]
    healthy_accounts = len(queue.accounts) - len(care_accounts)

    actions: list[OpsHomeActionItem] = []

    def add_action(
        *,
        action_id: str,
        severity: str,
        area: str,
        title: str,
        detail: str,
        count: int,
        href: str,
        recommended_action: str,
        oldest_at: datetime | None = None,
    ) -> None:
        if count <= 0:
            return
        actions.append(
            OpsHomeActionItem(
                id=action_id,
                severity=severity,
                area=area,
                title=title,
                detail=detail,
                count=count,
                href=href,
                recommended_action=recommended_action,
                oldest_at=oldest_at,
            )
        )

    add_action(
        action_id="failed_jobs",
        severity="critical",
        area="Jobs",
        title="Failed durable jobs",
        detail="Jobs ended in a terminal failure and require diagnosis.",
        count=failed_jobs,
        href="/ops/jobs?status=FAILED",
        recommended_action="Inspect the failure code before retrying or deleting work.",
        oldest_at=metrics.oldest_job_at_by_status.get("FAILED"),
    )
    add_action(
        action_id="retryable_jobs",
        severity="warning",
        area="Jobs",
        title="Retryable jobs",
        detail="Jobs are waiting for an operator-safe retry.",
        count=retryable_jobs,
        href="/ops/jobs?status=RETRYABLE",
        recommended_action="Review the latest error and retry eligible jobs.",
        oldest_at=metrics.oldest_job_at_by_status.get("RETRYABLE"),
    )
    add_action(
        action_id="failed_renders",
        severity="critical",
        area="Output",
        title="Failed renders",
        detail="Final outputs failed before they could reach review.",
        count=failed_renders,
        href="/production/output-review",
        recommended_action="Inspect render diagnostics and rerun only safe failures.",
    )
    add_action(
        action_id="review_renders",
        severity="info",
        area="Output",
        title="Outputs awaiting review",
        detail="Rendered media is ready for an operator QA decision.",
        count=review_renders,
        href="/production/output-review",
        recommended_action="Open Output Review and record the QA verdict.",
    )
    for severity, count in metrics.open_risk_counts_by_severity.items():
        key = str(severity).upper()
        action_severity = "critical" if key in {"CRITICAL", "HIGH", "BLOCKING"} else "warning" if key in {"MEDIUM", "WARNING", "WARN", "MODERATE"} else "info"
        add_action(
            action_id=f"risk_{key.lower()}",
            severity=action_severity,
            area="Risk",
            title=f"Open {key.lower()} risk flags",
            detail="Unresolved risk decisions can block downstream publishing.",
            count=int(count),
            href="/ops/risk",
            recommended_action="Review, resolve, or explicitly accept the risk decision.",
        )
    add_action(
        action_id="publish_reconciliation",
        severity="warning",
        area="Publish",
        title="Publish attempts need reconciliation",
        detail="External publication state differs from the canonical local record.",
        count=reconciliation,
        href="/ops/reconciliation",
        recommended_action="Reconcile external evidence with the canonical attempt.",
    )
    add_action(
        action_id="publish_blocked_by_risk",
        severity="critical",
        area="Publish",
        title="Drafts blocked by risk",
        detail="Publish-ready drafts cannot continue while blocking risk remains open.",
        count=blocked_by_risk,
        href="/ops/risk",
        recommended_action="Resolve the blocking risk before assigning or scheduling.",
    )
    add_action(
        action_id="unassigned_drafts",
        severity="warning",
        area="Routing",
        title="Unassigned publish drafts",
        detail="Ready drafts do not have a target platform account.",
        count=queue.unassigned_total or len(queue.unassigned_drafts),
        href="/ops/publish-control",
        recommended_action="Review routing recommendations and assign an eligible account.",
    )
    add_action(
        action_id="routing_attention",
        severity="warning",
        area="Routing",
        title="Drafts need routing attention",
        detail="Assignment or publishing state requires an operator decision.",
        count=queue.needs_attention_total or len(queue.needs_attention),
        href="/ops/publish-control",
        recommended_action="Inspect warnings and correct account routing.",
    )
    add_action(
        action_id="accounts_needing_care",
        severity="warning",
        area="Accounts",
        title="Accounts degraded or held",
        detail=", ".join(account.display_name for account in care_accounts[:3]) or "Platform account health requires attention.",
        count=len(care_accounts),
        href="/publishing/accounts",
        recommended_action="Review hold, cooldown, recent errors, and eligibility reasons.",
    )
    add_action(
        action_id="fetch_failed",
        severity="critical",
        area="Douyin fetch",
        title="Failed fetch runs",
        detail="Recent Douyin crawl sessions ended in failure.",
        count=int(metrics.douyin_fetch_health.failed_runs),
        href="/ops/health",
        recommended_action="Inspect the affected account and latest blocked reason.",
    )
    add_action(
        action_id="fetch_blocked",
        severity="warning",
        area="Douyin fetch",
        title="Blocked fetch runs",
        detail=f"{metrics.douyin_fetch_health.blocked_ratio_percent:.0f}% of the recent fetch window was blocked.",
        count=int(metrics.douyin_fetch_health.blocked_runs),
        href="/ops/health",
        recommended_action="Review blocked reasons and account-level fetch health.",
    )

    for dependency in dependencies or []:
        if dependency.state not in {"critical", "warning"}:
            continue
        add_action(
            action_id=f"dependency_{dependency.key}",
            severity="critical" if dependency.state == "critical" else "warning",
            area="Dependency",
            title=f"{dependency.label} needs attention",
            detail=dependency.signal,
            count=1,
            href=dependency.href or "/ops/health",
            recommended_action="Open system health and verify the dependency before starting more work.",
        )

    hidden_risk_by_key = {item.key: item for item in hidden_risks or []}
    stuck_risk = hidden_risk_by_key.get("potentially_stuck")
    stale_heartbeat_count = next(
        (segment.value for segment in stuck_risk.segments if segment.key == "stale_heartbeat"),
        0,
    ) if stuck_risk else 0
    add_action(
        action_id="stale_job_heartbeats",
        severity="critical",
        area="Execution",
        title="Stale running-job heartbeats",
        detail="Running jobs exceeded their type-specific worker heartbeat threshold.",
        count=stale_heartbeat_count,
        href="/ops/jobs?status=RUNNING",
        recommended_action="Inspect the worker and allow stale-lock recovery before accepting more work.",
    )
    retry_risk = hidden_risk_by_key.get("retry_amplification")
    retry_claims = next(
        (segment.value for segment in retry_risk.segments if segment.key == "retry_claims"),
        0,
    ) if retry_risk else 0
    if retry_risk is not None and retry_risk.state in {"watch", "critical"}:
        add_action(
            action_id="retry_amplification",
            severity="critical" if retry_risk.state == "critical" else "warning",
            area="Reliability",
            title="Retry amplification is consuming capacity",
            detail=retry_risk.detail,
            count=max(1, retry_claims),
            href=retry_risk.href,
            recommended_action="Inspect recurring failure signatures before increasing throughput.",
        )
    integrity_risk = hidden_risk_by_key.get("integrity_debt")
    if integrity_risk is not None:
        add_action(
            action_id="integrity_debt",
            severity="warning",
            area="Data integrity",
            title="Cross-record integrity gaps",
            detail=integrity_risk.detail,
            count=int(integrity_risk.value or 0),
            href=integrity_risk.href,
            recommended_action="Resolve missing attribution and canonical record links before downstream automation.",
        )

    actions.sort(key=lambda item: (_SEVERITY_ORDER[item.severity], -item.count, item.title))
    critical_count = len([item for item in actions if item.severity == "critical"])
    warning_count = len([item for item in actions if item.severity == "warning"])
    actionable = [item for item in actions if item.severity != "info"]
    if critical_count:
        overall_status = "blocked"
        headline = f"{critical_count} critical signal{'s' if critical_count != 1 else ''} require attention."
    elif warning_count:
        overall_status = "needs_attention"
        headline = f"{warning_count} warning signal{'s' if warning_count != 1 else ''} need review."
    elif active_jobs:
        overall_status = "healthy"
        headline = "Operations are active with no blocking condition."
    else:
        overall_status = "quiet"
        headline = "The operations workspace is quiet."
    overall_detail = " · ".join(f"{item.count} {item.title.lower()}" for item in actionable[:3]) or "No action queue items are open."

    publish_attempts = int(publish_health.overview.total_attempts)
    publish_display = "No activity" if publish_attempts == 0 else f"{publish_health.overview.success_rate_percent:.0f}%"
    publish_tone = "muted" if publish_attempts == 0 else "warn" if publish_health.overview.failed_attempts or reconciliation else "good"
    output_display = f"{approved_renders}/{total_renders}" if total_renders else "No outputs"
    kpis = [
        OpsHomeKpi(key="attention", label="Needs attention", value=critical_count + warning_count, display_value=str(critical_count + warning_count), detail=f"{critical_count} critical · {warning_count} warning", tone="danger" if critical_count else "warn" if warning_count else "good", href="/ops/jobs"),
        OpsHomeKpi(key="active_jobs", label="Active jobs", value=active_jobs, display_value=str(active_jobs), detail=f"{metrics.queue_backlog.queued} queued · {metrics.queue_backlog.running} running · {retryable_jobs} retryable", tone="warn" if retryable_jobs else "active" if active_jobs else "muted", href="/ops/jobs"),
        OpsHomeKpi(key="output_health", label="Output health", value=approved_renders, display_value=output_display, detail=f"{failed_renders} failed · {review_renders} awaiting review", tone="danger" if failed_renders else "warn" if review_renders else "good", href="/production/output-review"),
        OpsHomeKpi(key="publish_success", label="Publish success", value=None if publish_attempts == 0 else publish_health.overview.success_rate_percent, display_value=publish_display, detail=f"{publish_health.overview.succeeded_attempts}/{publish_attempts} attempts · {reconciliation} reconciliation", tone=publish_tone, href="/ops/publish-health"),
        OpsHomeKpi(key="account_health", label="Account health", value=healthy_accounts, display_value=f"{healthy_accounts}/{len(queue.accounts)}", detail=f"{len(care_accounts)} degraded or held", tone="warn" if care_accounts else "good", href="/publishing/accounts"),
        OpsHomeKpi(key="open_risk", label="Open risk", value=open_risks, display_value=str(open_risks), detail="Open risk flags across all severities", tone="warn" if open_risks else "good", href="/ops/risk"),
    ]

    job_rows: list[OpsHomeJobHealthRow] = []
    for job_type, statuses in metrics.job_counts_by_type_status.items():
        total = sum(int(value or 0) for value in statuses.values())
        if total <= 0:
            continue
        queued = int(statuses.get("QUEUED", 0) or 0)
        running = int(statuses.get("RUNNING", 0) or 0)
        retryable = int(statuses.get("RETRYABLE", 0) or 0)
        failed = int(statuses.get("FAILED", 0) or 0)
        duration = metrics.step_duration_by_job_type.get(job_type, {})
        failure_rate = float(metrics.job_failure_rate_percent_by_type.get(job_type, 0.0) or 0.0)
        job_rows.append(
            OpsHomeJobHealthRow(
                job_type=job_type,
                queued=queued,
                running=running,
                retryable=retryable,
                failed=failed,
                waiting_review=int(statuses.get("WAITING_FOR_REVIEW", 0) or 0),
                completed=int(statuses.get("COMPLETED", 0) or 0),
                total=total,
                failure_rate_percent=failure_rate,
                average_step_seconds=float(duration.get("average_seconds", 0.0) or 0.0),
                max_step_seconds=float(duration.get("max_seconds", 0.0) or 0.0),
                tone=_job_tone(failed=failed, retryable=retryable, running=running, queued=queued, failure_rate=failure_rate),
            )
        )
    job_rows.sort(key=lambda row: ({"danger": 0, "warn": 1, "active": 2, "good": 3, "muted": 4}[row.tone], -(row.failed + row.retryable + row.running), row.job_type))

    account_rows = [
        OpsHomeAccountHealthRow(
            platform_account_id=str(account.platform_account_id),
            display_name=account.display_name,
            platform=_enum_value(account.platform),
            account_status=_enum_value(account.account_status),
            health_status=_enum_value(account.health_status),
            priority=account.priority,
            is_on_hold=account.is_on_hold,
            cooldown_until=account.cooldown_until,
            attempts_7d=account.attempts_7d,
            succeeded_7d=account.succeeded_7d,
            failed_7d=account.failed_7d,
            success_rate_percent=account.success_rate_percent,
            needs_reconciliation_count=account.needs_reconciliation_count,
            assigned_draft_count=account.assigned_draft_count,
            scheduled_draft_count=account.scheduled_draft_count,
            recent_error_code=account.recent_error_code,
            reasons=list(account.reasons),
        )
        for account in queue.accounts
    ]
    account_rows.sort(key=lambda row: (0 if row.is_on_hold or row.health_status != "HEALTHY" else 1, -row.failed_7d, row.display_name))

    failure_signatures = [
        OpsHomeFailureSignature(source="Jobs", error_code=item.error_code, label=item.error_code.replace("_", " ").title(), count=item.count, href="/ops/jobs?status=FAILED")
        for item in metrics.common_failure_categories
    ]
    failure_signatures.extend(
        OpsHomeFailureSignature(source="Publish", error_code=item.error_code, label=item.label, count=item.count, href="/ops/publish-health")
        for item in publish_health.failure_categories
    )
    failure_signatures.sort(key=lambda item: (-item.count, item.source, item.error_code))

    fetch_accounts = [
        OpsHomeFetchAccountRow(
            account_id=item.douyin_account_connection_id,
            runs_total=item.runs_total,
            blocked_runs=item.blocked_runs,
            parse_warning_runs=item.parse_warning_runs,
            failed_runs=item.failed_runs,
            blocked_rate_percent=round((item.blocked_runs / item.runs_total) * 100, 2) if item.runs_total else 0.0,
        )
        for item in metrics.douyin_fetch_health.by_account
    ]
    fetch_accounts.sort(key=lambda item: (-item.failed_runs, -item.blocked_runs, -item.runs_total))
    fetch_health = OpsHomeFetchHealth(
        window_runs=metrics.douyin_fetch_health.window_runs,
        blocked_runs=metrics.douyin_fetch_health.blocked_runs,
        parse_warning_runs=metrics.douyin_fetch_health.parse_warning_runs,
        failed_runs=metrics.douyin_fetch_health.failed_runs,
        blocked_ratio_percent=metrics.douyin_fetch_health.blocked_ratio_percent,
        top_blocked_reasons=[OpsHomeFetchReason(reason=item.reason, count=item.count) for item in metrics.douyin_fetch_health.top_blocked_reasons],
        by_account=fetch_accounts,
    )

    operational_status = [
        OpsHomeOperationalStatus(key="jobs", label="Durable jobs", status="critical" if failed_jobs else "warning" if retryable_jobs else "active" if active_jobs else "ready", detail=f"{failed_jobs} failed · {retryable_jobs} retryable · {metrics.queue_backlog.running} running", href="/ops/jobs"),
        OpsHomeOperationalStatus(key="outputs", label="Render outputs", status="critical" if failed_renders else "warning" if review_renders else "ready", detail=f"{failed_renders} failed · {review_renders} review · {approved_renders} approved", href="/production/output-review"),
        OpsHomeOperationalStatus(key="publishing", label="Publishing", status="warning" if reconciliation or publish_health.overview.failed_attempts else "quiet" if publish_attempts == 0 else "ready", detail="No publish activity in 7 days" if publish_attempts == 0 else f"{publish_health.overview.success_rate_percent:.0f}% success · {reconciliation} reconciliation", href="/ops/publish-health"),
        OpsHomeOperationalStatus(key="accounts", label="Platform accounts", status="warning" if care_accounts else "ready", detail=f"{healthy_accounts}/{len(queue.accounts)} healthy", href="/publishing/accounts"),
        OpsHomeOperationalStatus(key="fetch", label="Douyin fetch", status="critical" if metrics.douyin_fetch_health.failed_runs else "warning" if metrics.douyin_fetch_health.blocked_runs else "ready", detail=f"{metrics.douyin_fetch_health.blocked_ratio_percent:.0f}% blocked · {metrics.douyin_fetch_health.failed_runs} failed", href="/ops/health"),
    ]

    waiting_review = _count_status(metrics, "WAITING_FOR_REVIEW")
    queue_health = OpsHomeQueueHealth(
        queued=metrics.queue_backlog.queued,
        running=metrics.queue_backlog.running,
        retryable=metrics.queue_backlog.retryable,
        waiting_review=waiting_review,
        failed=failed_jobs,
        oldest_queued_at=metrics.queue_backlog.oldest_queued_at,
        running_with_lock=metrics.queue_backlog.running_with_lock,
        running_without_lock=metrics.queue_backlog.running_without_lock,
        busy_worker_count=metrics.queue_backlog.active_worker_count,
        total_retry_attempts=metrics.total_retry_attempts,
    )

    return OpsHomeSummaryResponse(
        overall=OpsHomeOverall(status=overall_status, headline=headline, detail=overall_detail, critical_count=critical_count, warning_count=warning_count),
        freshness=OpsHomeFreshness(generated_at=now, metrics_generated_at=metrics.generated_at, publish_health_generated_at=publish_health.generated_at, control_queue_generated_at=queue.generated_at),
        kpis=kpis,
        action_items=actions,
        job_health=job_rows,
        account_health=account_rows,
        publish_trend=_seven_day_publish_trend(publish_health, now=now),
        failure_signatures=failure_signatures[:10],
        fetch_health=fetch_health,
        operational_status=operational_status,
        queue_health=queue_health,
        dependencies=list(dependencies or []),
        storage_capacity=storage_capacity or OpsHomeStorageCapacity(),
        hidden_risks=list(hidden_risks or []),
        admission_verdict=admission_verdict or OpsHomeAdmissionVerdict(),
    )


class OpsHomeSummaryService:
    def __init__(self, db: Session, *, workspace_id: UUID) -> None:
        self.db = db
        self.workspace_id = workspace_id

    def get_summary(self) -> OpsHomeSummaryResponse:
        metrics = OperationalMetricsService(self.db, workspace_id=self.workspace_id).get_metrics()
        publish_health = PublishHealthService(self.db, workspace_id=self.workspace_id).dashboard_snapshot(window="last_7_days")
        queue = ControlQueueService(self.db, workspace_id=self.workspace_id).queue(platform=PublishTargetPlatform.FACEBOOK_REELS, limit=100)
        dependencies, storage_capacity = probe_operational_dependencies(metrics, settings=get_settings())
        hidden_risks = OpsHomeHiddenRiskService(self.db, workspace_id=self.workspace_id).get_hidden_risks()
        admission_verdict = build_ops_home_admission_verdict(hidden_risks, dependencies, storage_capacity)
        return build_ops_home_summary(
            metrics,
            publish_health,
            queue,
            dependencies=dependencies,
            storage_capacity=storage_capacity,
            hidden_risks=hidden_risks,
            admission_verdict=admission_verdict,
        )
