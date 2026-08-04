from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.enums import JobType
from src.schemas.ops_home import OpsHomeDependencySignal, OpsHomeStorageCapacity
from src.services.ops_home_hidden_risk_service import (
    OpsHomeHiddenRiskEvidence,
    OpsHomeHiddenRiskService,
    build_ops_home_admission_verdict,
    build_ops_home_hidden_risks,
)


class _Rows:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class _RiskDb:
    def __init__(self, *, now: datetime) -> None:
        self.now = now
        self.scalar_results = [1, 1]
        self.scalars_results = [
            [1, 3, 0],
            [{"resolved_douyin_account_connection_id": "account-1"}, {}, None],
        ]

    def execute(self, _stmt: object) -> _Rows:
        return _Rows(
            [
                (JobType.DOWNLOAD_VIDEO, "worker-a", self.now - timedelta(seconds=60)),
                (JobType.DOWNLOAD_VIDEO, "worker-b", self.now - timedelta(seconds=121)),
                (JobType.DOWNLOAD_VIDEO, None, None),
            ]
        )

    def scalars(self, _stmt: object) -> _Rows:
        return _Rows(self.scalars_results.pop(0))

    def scalar(self, _stmt: object) -> int:
        return self.scalar_results.pop(0)


def _ready_dependencies() -> list[OpsHomeDependencySignal]:
    return [
        OpsHomeDependencySignal(
            key="database",
            label="PostgreSQL",
            state="ready",
            signal="Query completed",
            impact="Durable state",
        )
    ]


def test_hidden_risks_use_lock_heartbeat_retry_claims_and_provable_integrity_gaps() -> None:
    risks = build_ops_home_hidden_risks(
        OpsHomeHiddenRiskEvidence(
            running_jobs=4,
            observed_running_jobs=2,
            running_without_lock=1,
            stale_heartbeat_jobs=1,
            attempted_jobs=4,
            first_claims=4,
            retry_claims=4,
            recent_fetch_runs=20,
            unattributed_fetch_runs=1,
            render_outputs_without_asset=1,
            published_drafts_without_canonical_attempt=1,
        )
    )

    by_key = {item.key: item for item in risks}
    assert by_key["observability_coverage"].display_value == "50%"
    assert by_key["observability_coverage"].state == "critical"
    assert by_key["potentially_stuck"].value == 2
    assert by_key["retry_amplification"].display_value == "2.00x"
    assert by_key["retry_amplification"].state == "critical"
    assert by_key["integrity_debt"].value == 3
    assert {item.key: item.value for item in by_key["integrity_debt"].segments} == {
        "fetch_attribution": 1,
        "render_asset": 1,
        "publish_canonical": 1,
    }

    verdict = build_ops_home_admission_verdict(risks, _ready_dependencies(), OpsHomeStorageCapacity(state="ready"))
    assert verdict.status == "pause"
    assert verdict.label == "Pause new work"
    assert any("stuck" in reason for reason in verdict.reasons)


def test_idle_clear_evidence_is_safe_only_when_dependencies_are_observed() -> None:
    risks = build_ops_home_hidden_risks(
        OpsHomeHiddenRiskEvidence(
            attempted_jobs=10,
            first_claims=10,
            retry_claims=1,
            recent_fetch_runs=10,
        )
    )
    by_key = {item.key: item for item in risks}
    assert by_key["observability_coverage"].display_value == "Idle"
    assert by_key["potentially_stuck"].value == 0
    assert by_key["retry_amplification"].display_value == "1.10x"
    assert by_key["retry_amplification"].state == "clear"
    assert by_key["integrity_debt"].state == "clear"

    safe = build_ops_home_admission_verdict(risks, _ready_dependencies(), OpsHomeStorageCapacity(state="ready"))
    assert safe.status == "safe"

    not_observed = [
        OpsHomeDependencySignal(
            key="redis",
            label="Redis broker",
            state="not_observed",
            signal="No probe",
            impact="Queue wake-up",
        )
    ]
    cautious = build_ops_home_admission_verdict(risks, not_observed, OpsHomeStorageCapacity(state="ready"))
    assert cautious.status == "caution"
    assert cautious.label == "Accept with guardrails"


def test_hidden_risk_service_uses_type_specific_stale_heartbeat_and_retained_claims(monkeypatch) -> None:
    now = datetime(2026, 7, 28, 4, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "src.services.ops_home_hidden_risk_service.job_type_stale_seconds",
        lambda _job_type, settings: 120,
    )
    service = OpsHomeHiddenRiskService(_RiskDb(now=now), workspace_id=uuid4())  # type: ignore[arg-type]

    risks = {item.key: item for item in service.get_hidden_risks(observed_at=now)}

    assert risks["observability_coverage"].display_value == "33%"
    assert risks["potentially_stuck"].value == 2
    assert risks["retry_amplification"].display_value == "2.00x"
    assert risks["integrity_debt"].value == 4
