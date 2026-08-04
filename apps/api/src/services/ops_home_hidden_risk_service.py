from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.enums import JobStatus, PublishDraftStatus, RenderOutputStatus, SourcePlatformEnum
from src.models.ingestion import CrawlSession
from src.models.jobs import Job
from src.models.media import RenderOutput
from src.models.publish import PublishDraft
from src.schemas.ops_home import (
    OpsHomeAdmissionVerdict,
    OpsHomeDependencySignal,
    OpsHomeHiddenRisk,
    OpsHomeHiddenRiskSegment,
    OpsHomeStorageCapacity,
)
from src.services.job_runner import job_type_stale_seconds


@dataclass(frozen=True)
class OpsHomeHiddenRiskEvidence:
    running_jobs: int = 0
    observed_running_jobs: int = 0
    running_without_lock: int = 0
    stale_heartbeat_jobs: int = 0
    attempted_jobs: int = 0
    first_claims: int = 0
    retry_claims: int = 0
    recent_fetch_runs: int = 0
    unattributed_fetch_runs: int = 0
    render_outputs_without_asset: int = 0
    published_drafts_without_canonical_attempt: int = 0


def build_ops_home_hidden_risks(evidence: OpsHomeHiddenRiskEvidence) -> list[OpsHomeHiddenRisk]:
    if evidence.running_jobs:
        coverage = round((evidence.observed_running_jobs / evidence.running_jobs) * 100, 1)
        coverage_display = f"{coverage:.0f}%"
        coverage_detail = (
            f"{evidence.observed_running_jobs}/{evidence.running_jobs} running jobs have a current worker-lock heartbeat."
        )
        coverage_state = "clear" if evidence.observed_running_jobs == evidence.running_jobs else "critical"
    else:
        coverage = None
        coverage_display = "Idle"
        coverage_detail = "No running jobs currently require worker-lock coverage."
        coverage_state = "clear"

    potentially_stuck = evidence.running_without_lock + evidence.stale_heartbeat_jobs
    retry_amplification = (
        round((evidence.first_claims + evidence.retry_claims) / evidence.attempted_jobs, 2)
        if evidence.attempted_jobs
        else None
    )
    if retry_amplification is None:
        retry_state = "clear"
        retry_display = "No claims"
        retry_detail = "No retained job has been claimed by a worker yet."
    else:
        retry_state = "critical" if retry_amplification >= 2 else "watch" if retry_amplification >= 1.25 else "clear"
        retry_display = f"{retry_amplification:.2f}x"
        retry_detail = (
            f"{evidence.retry_claims} retry claims beyond {evidence.first_claims} first claims across retained jobs."
        )

    integrity_debt = (
        evidence.unattributed_fetch_runs
        + evidence.render_outputs_without_asset
        + evidence.published_drafts_without_canonical_attempt
    )
    integrity_state = "watch" if integrity_debt else "clear"

    return [
        OpsHomeHiddenRisk(
            key="observability_coverage",
            label="Observability coverage",
            state=coverage_state,
            value=coverage,
            display_value=coverage_display,
            detail=coverage_detail,
            href="/ops/jobs?status=RUNNING",
            segments=[
                OpsHomeHiddenRiskSegment(key="covered", label="Current heartbeat", value=evidence.observed_running_jobs),
                OpsHomeHiddenRiskSegment(key="uncovered", label="Coverage gap", value=potentially_stuck),
            ],
        ),
        OpsHomeHiddenRisk(
            key="potentially_stuck",
            label="Potentially stuck work",
            state="critical" if potentially_stuck else "clear",
            value=potentially_stuck,
            display_value=str(potentially_stuck),
            detail=(
                "Running work has missing or stale worker-lock evidence."
                if potentially_stuck
                else "Every running job has a current worker-lock heartbeat."
            ),
            href="/ops/jobs?status=RUNNING",
            segments=[
                OpsHomeHiddenRiskSegment(key="without_lock", label="No lock", value=evidence.running_without_lock),
                OpsHomeHiddenRiskSegment(key="stale_heartbeat", label="Stale heartbeat", value=evidence.stale_heartbeat_jobs),
            ],
        ),
        OpsHomeHiddenRisk(
            key="retry_amplification",
            label="Retry amplification",
            state=retry_state,
            value=retry_amplification,
            display_value=retry_display,
            detail=retry_detail,
            href="/ops/jobs",
            segments=[
                OpsHomeHiddenRiskSegment(key="first_claims", label="First claims", value=evidence.first_claims),
                OpsHomeHiddenRiskSegment(key="retry_claims", label="Retry claims", value=evidence.retry_claims),
            ],
        ),
        OpsHomeHiddenRisk(
            key="integrity_debt",
            label="Integrity debt",
            state=integrity_state,
            value=integrity_debt,
            display_value=str(integrity_debt),
            detail=(
                "Provable cross-record contract gaps that can make a healthy-looking flow unsafe."
                if integrity_debt
                else "No checked attribution, render-asset, or publish-canonical gap was found."
            ),
            href="/ops/health",
            segments=[
                OpsHomeHiddenRiskSegment(
                    key="fetch_attribution", label=f"Fetch attribution (latest {evidence.recent_fetch_runs})", value=evidence.unattributed_fetch_runs
                ),
                OpsHomeHiddenRiskSegment(key="render_asset", label="Render asset", value=evidence.render_outputs_without_asset),
                OpsHomeHiddenRiskSegment(
                    key="publish_canonical",
                    label="Publish canonical",
                    value=evidence.published_drafts_without_canonical_attempt,
                ),
            ],
        ),
    ]


def build_ops_home_admission_verdict(
    hidden_risks: list[OpsHomeHiddenRisk],
    dependencies: list[OpsHomeDependencySignal],
    storage_capacity: OpsHomeStorageCapacity,
) -> OpsHomeAdmissionVerdict:
    pause_reasons: list[str] = []
    caution_reasons: list[str] = []
    risk_by_key = {item.key: item for item in hidden_risks}

    stuck = risk_by_key.get("potentially_stuck")
    if stuck is not None and int(stuck.value or 0) > 0:
        pause_reasons.append(f"{int(stuck.value or 0)} running job(s) may be stuck")
    retry = risk_by_key.get("retry_amplification")
    if retry is not None and retry.state == "critical":
        pause_reasons.append(f"retry amplification is {retry.display_value}")
    elif retry is not None and retry.state == "watch":
        caution_reasons.append(f"retry amplification is {retry.display_value}")
    integrity = risk_by_key.get("integrity_debt")
    if integrity is not None and int(integrity.value or 0) > 0:
        caution_reasons.append(f"{int(integrity.value or 0)} integrity gap(s) remain")

    for dependency in dependencies:
        if dependency.state == "critical":
            pause_reasons.append(f"{dependency.label} is critical")
        elif dependency.state == "warning":
            caution_reasons.append(f"{dependency.label} needs attention")
        elif dependency.state == "not_observed":
            caution_reasons.append(f"{dependency.label} is not observed")
    if storage_capacity.state == "critical" and not any("Local storage" in reason for reason in pause_reasons):
        pause_reasons.append("storage headroom is critical")

    if pause_reasons:
        return OpsHomeAdmissionVerdict(
            status="pause",
            label="Pause new work",
            detail="Clear the blocking execution evidence before adding workload.",
            reasons=pause_reasons[:3],
        )
    if caution_reasons:
        return OpsHomeAdmissionVerdict(
            status="caution",
            label="Accept with guardrails",
            detail="New work can enter cautiously, but capacity or confidence is reduced.",
            reasons=caution_reasons[:3],
        )
    return OpsHomeAdmissionVerdict()


class OpsHomeHiddenRiskService:
    def __init__(self, db: Session, *, workspace_id: UUID) -> None:
        self.db = db
        self.workspace_id = workspace_id

    def get_hidden_risks(self, *, observed_at: datetime | None = None) -> list[OpsHomeHiddenRisk]:
        now = observed_at or datetime.now(UTC)
        settings = get_settings()
        running_rows = self.db.execute(
            select(Job.job_type, Job.locked_by, Job.locked_at).where(
                Job.workspace_id == self.workspace_id,
                Job.status == JobStatus.RUNNING,
            )
        ).all()
        running_without_lock = 0
        stale_heartbeat_jobs = 0
        observed_running_jobs = 0
        for job_type, locked_by, locked_at in running_rows:
            if not locked_by or locked_at is None:
                running_without_lock += 1
                continue
            if (now - locked_at).total_seconds() >= job_type_stale_seconds(job_type, settings=settings):
                stale_heartbeat_jobs += 1
                continue
            observed_running_jobs += 1

        attempts = [
            int(value or 0)
            for value in self.db.scalars(select(Job.attempts).where(Job.workspace_id == self.workspace_id)).all()
        ]
        first_claims = sum(1 for value in attempts if value > 0)
        retry_claims = sum(max(0, value - 1) for value in attempts)

        fetch_metadata = list(
            self.db.scalars(
                select(CrawlSession.metadata_json)
                .where(
                    CrawlSession.workspace_id == self.workspace_id,
                    CrawlSession.source_platform == SourcePlatformEnum.DOUYIN,
                )
                .order_by(CrawlSession.created_at.desc())
                .limit(200)
            ).all()
        )
        unattributed_fetch_runs = sum(
            1
            for raw in fetch_metadata
            if not isinstance(raw, dict) or not raw.get("resolved_douyin_account_connection_id")
        )
        render_outputs_without_asset = int(
            self.db.scalar(
                select(func.count(RenderOutput.id)).where(
                    RenderOutput.workspace_id == self.workspace_id,
                    RenderOutput.status.in_([RenderOutputStatus.READY_FOR_REVIEW, RenderOutputStatus.APPROVED]),
                    RenderOutput.media_asset_id.is_(None),
                )
            )
            or 0
        )
        published_drafts_without_canonical_attempt = int(
            self.db.scalar(
                select(func.count(PublishDraft.id)).where(
                    PublishDraft.workspace_id == self.workspace_id,
                    PublishDraft.status == PublishDraftStatus.PUBLISHED,
                    PublishDraft.canonical_publish_attempt_id.is_(None),
                )
            )
            or 0
        )
        return build_ops_home_hidden_risks(
            OpsHomeHiddenRiskEvidence(
                running_jobs=len(running_rows),
                observed_running_jobs=observed_running_jobs,
                running_without_lock=running_without_lock,
                stale_heartbeat_jobs=stale_heartbeat_jobs,
                attempted_jobs=first_claims,
                first_claims=first_claims,
                retry_claims=retry_claims,
                recent_fetch_runs=len(fetch_metadata),
                unattributed_fetch_runs=unattributed_fetch_runs,
                render_outputs_without_asset=render_outputs_without_asset,
                published_drafts_without_canonical_attempt=published_drafts_without_canonical_attempt,
            )
        )
