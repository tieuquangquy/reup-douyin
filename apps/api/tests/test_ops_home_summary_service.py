from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.schemas.analytics import PublishHealthDashboardResponse
from src.schemas.operations import OperationalMetricsResponse
from src.schemas.ops_home import OpsHomeDependencySignal
from src.schemas.publish_routing import PublishControlQueueResponse
from src.services.ops_home_summary_service import build_ops_home_summary


def _now() -> datetime:
    return datetime(2026, 7, 27, 4, 0, tzinfo=UTC)


def test_ops_home_summary_prioritizes_non_zero_actions_and_uses_no_activity() -> None:
    now = _now()
    metrics = OperationalMetricsResponse.model_validate(
        {
            "generated_at": now - timedelta(seconds=2),
            "job_counts_by_type_status": {
                "DOWNLOAD_VIDEO": {"COMPLETED": 10, "FAILED": 2},
                "ANALYZE_AUDIO": {"COMPLETED": 4},
            },
            "job_failure_rate_percent_by_type": {"DOWNLOAD_VIDEO": 16.67, "ANALYZE_AUDIO": 0},
            "queue_backlog": {"queued": 0, "running": 0, "retryable": 0},
            "retryable_jobs": 0,
            "step_duration_by_job_type": {
                "DOWNLOAD_VIDEO": {"sample_count": 10, "average_seconds": 20, "max_seconds": 45}
            },
            "render_counts_by_status": {"FAILED": 19, "READY_FOR_REVIEW": 19, "APPROVED": 2},
            "open_risk_counts_by_severity": {"MEDIUM": 34},
            "douyin_fetch_health": {
                "window_runs": 20,
                "blocked_runs": 3,
                "blocked_ratio_percent": 15,
                "top_blocked_reasons": [{"reason": "challenge", "count": 3}],
                "by_account": [
                    {
                        "douyin_account_connection_id": "acc-1",
                        "runs_total": 20,
                        "blocked_runs": 3,
                        "parse_warning_runs": 1,
                        "failed_runs": 0,
                    }
                ],
            },
        }
    )
    publish_health = PublishHealthDashboardResponse.model_validate(
        {
            "generated_at": now - timedelta(seconds=1),
            "window": "last_7_days",
            "window_start": now - timedelta(days=7),
            "window_end": now,
            "overview": {
                "total_attempts": 0,
                "succeeded_attempts": 0,
                "failed_attempts": 0,
                "needs_reconciliation_attempts": 0,
                "canonical_published_count": 0,
                "drafts_ready_not_published": 0,
                "drafts_blocked_by_risk": 0,
                "success_rate_percent": 0,
            },
            "by_day": [{"day": "2026-07-27", "attempts": 0, "succeeded": 0, "failed": 0, "needs_reconciliation": 0}],
            "account_health": [],
            "failure_categories": [],
            "action_queue": {"needs_reconciliation": [], "drafts_ready": [], "blocked_by_risk_count": 0, "recent_successes": []},
            "pipeline_feedback": {},
        }
    )
    queue = PublishControlQueueResponse.model_validate(
        {
            "generated_at": now,
            "accounts": [
                {
                    "platform_account_id": uuid4(),
                    "display_name": "Held page",
                    "platform": "FACEBOOK_REELS",
                    "account_status": "ACTIVE",
                    "health_status": "HELD",
                    "priority": 10,
                    "is_on_hold": True,
                    "cooldown_until": None,
                    "attempts_7d": 0,
                    "succeeded_7d": 0,
                    "failed_7d": 0,
                    "needs_reconciliation_count": 0,
                    "assigned_draft_count": 0,
                    "scheduled_draft_count": 0,
                    "recent_error_code": None,
                    "success_rate_percent": 0,
                    "reasons": ["manual hold"],
                }
            ],
            "unassigned_drafts": [],
            "assigned_drafts": [],
            "scheduled_drafts": [],
            "needs_attention": [],
        }
    )

    summary = build_ops_home_summary(metrics, publish_health, queue, generated_at=now)

    assert summary.overall.status == "blocked"
    assert summary.action_items[0].severity == "critical"
    assert all(item.count > 0 for item in summary.action_items)
    assert {item.id for item in summary.action_items} >= {
        "failed_jobs",
        "failed_renders",
        "risk_medium",
        "accounts_needing_care",
        "fetch_blocked",
    }
    publish_kpi = next(item for item in summary.kpis if item.key == "publish_success")
    assert publish_kpi.display_value == "No activity"
    assert publish_kpi.tone == "muted"
    output_kpi = next(item for item in summary.kpis if item.key == "output_health")
    assert output_kpi.display_value == "2/40"
    assert summary.job_health[0].job_type == "DOWNLOAD_VIDEO"
    assert summary.job_health[0].average_step_seconds == 20
    assert summary.account_health[0].is_on_hold is True
    assert summary.fetch_health.by_account[0].blocked_rate_percent == 15
    assert len(summary.publish_trend) == 7
    assert summary.publish_trend[-1].day == "2026-07-27"


def test_ops_home_summary_is_quiet_when_all_authorities_are_clear() -> None:
    now = _now()
    metrics = OperationalMetricsResponse(generated_at=now)
    publish_health = PublishHealthDashboardResponse.model_validate(
        {
            "generated_at": now,
            "window": "last_7_days",
            "window_start": now - timedelta(days=7),
            "window_end": now,
            "overview": {},
            "by_day": [],
            "account_health": [],
            "failure_categories": [],
            "action_queue": {},
            "pipeline_feedback": {},
        }
    )
    queue = PublishControlQueueResponse(generated_at=now, accounts=[], unassigned_drafts=[], assigned_drafts=[], scheduled_drafts=[], needs_attention=[])

    summary = build_ops_home_summary(metrics, publish_health, queue, generated_at=now)

    assert summary.overall.status == "quiet"
    assert summary.action_items == []
    assert summary.overall.critical_count == 0
    assert summary.overall.warning_count == 0


def test_ops_home_summary_uses_total_queue_counts_and_unique_signal_counts() -> None:
    now = _now()
    oldest_retryable = now - timedelta(hours=3)
    metrics = OperationalMetricsResponse.model_validate(
        {
            "generated_at": now,
            "job_counts_by_type_status": {"DOWNLOAD_VIDEO": {"FAILED": 9, "RETRYABLE": 4}},
            "queue_backlog": {"retryable": 4, "running_without_lock": 1},
            "retryable_jobs": 4,
            "oldest_job_at_by_status": {"RETRYABLE": oldest_retryable},
        }
    )
    publish_health = PublishHealthDashboardResponse.model_validate(
        {
            "generated_at": now,
            "window": "last_7_days",
            "window_start": now - timedelta(days=7),
            "window_end": now,
            "overview": {},
            "by_day": [],
            "account_health": [],
            "failure_categories": [],
            "action_queue": {},
            "pipeline_feedback": {},
        }
    )
    queue = PublishControlQueueResponse(
        generated_at=now,
        accounts=[],
        unassigned_drafts=[],
        assigned_drafts=[],
        scheduled_drafts=[],
        needs_attention=[],
        unassigned_total=240,
        needs_attention_total=17,
    )
    dependencies = [
        OpsHomeDependencySignal(
            key="worker",
            label="Workers",
            state="critical",
            signal="One running job has no worker lock",
            impact="Background execution",
            href="/ops/jobs",
        )
    ]

    summary = build_ops_home_summary(
        metrics,
        publish_health,
        queue,
        generated_at=now,
        dependencies=dependencies,
    )

    actions = {item.id: item for item in summary.action_items}
    assert actions["unassigned_drafts"].count == 240
    assert actions["routing_attention"].count == 17
    assert actions["retryable_jobs"].oldest_at == oldest_retryable
    assert summary.overall.critical_count == len([item for item in summary.action_items if item.severity == "critical"])
    assert summary.overall.critical_count < sum(item.count for item in summary.action_items if item.severity == "critical")
    assert summary.queue_health.running_without_lock == 1
    assert summary.dependencies[0].state == "critical"
