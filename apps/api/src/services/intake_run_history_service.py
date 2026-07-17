from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.db.bootstrap import ensure_default_workspace
from src.enums import CrawlSessionStatus
from src.models.ingestion import CrawlSession


@dataclass(frozen=True)
class TroubleshootingSummary:
    category: str
    severity: str
    why: str
    recommended_actions: list[str]


class IntakeRunHistoryError(ValueError):
    pass


class IntakeRunHistoryService:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_workspace_id(self, workspace_id: UUID | None) -> UUID:
        if workspace_id is not None:
            return workspace_id
        return ensure_default_workspace(self.db).id

    def list_runs(self, *, workspace_id: UUID | None, limit: int = 12) -> list[CrawlSession]:
        resolved_workspace_id = self._resolve_workspace_id(workspace_id)
        safe_limit = min(max(limit, 1), 50)
        return list(
            self.db.scalars(
                select(CrawlSession)
                .where(CrawlSession.workspace_id == resolved_workspace_id)
                .order_by(CrawlSession.created_at.desc())
                .limit(safe_limit)
            )
        )

    def get_run(self, crawl_session_id: UUID) -> CrawlSession:
        run = self.db.scalar(
            select(CrawlSession)
            .where(CrawlSession.id == crawl_session_id)
            .options(selectinload(CrawlSession.source_profile))
        )
        if run is None:
            raise IntakeRunHistoryError("Intake run not found")
        return run

    def compare_runs(self, *, left_run_id: UUID, right_run_id: UUID) -> tuple[CrawlSession, CrawlSession, dict]:
        left = self.get_run(left_run_id)
        right = self.get_run(right_run_id)

        left_duration = self._duration_seconds(left)
        right_duration = self._duration_seconds(right)

        delta = {
            "status_changed": str(left.status) != str(right.status),
            "duration_seconds_delta": self._diff_number(left_duration, right_duration),
            "videos_discovered_delta": right.videos_discovered_count - left.videos_discovered_count,
            "videos_created_delta": right.videos_created_count - left.videos_created_count,
            "videos_updated_delta": right.videos_updated_count - left.videos_updated_count,
            "error_code_changed": (left.error_code or "") != (right.error_code or ""),
            "left_error_code": left.error_code,
            "right_error_code": right.error_code,
            "left_candidates_total": self._candidate_total(left),
            "right_candidates_total": self._candidate_total(right),
            "candidates_total_delta": self._candidate_total(right) - self._candidate_total(left),
            "left_candidates_matched": self._candidate_matched(left),
            "right_candidates_matched": self._candidate_matched(right),
            "candidates_matched_delta": self._candidate_matched(right) - self._candidate_matched(left),
        }
        return left, right, delta

    def troubleshooting_for(self, run: CrawlSession) -> TroubleshootingSummary:
        code = (run.error_code or "").lower().strip()
        message = (run.error_message or "").lower().strip()
        status = str(run.status)
        metadata = run.metadata_json if isinstance(run.metadata_json, dict) else {}
        observability = metadata.get("fetch_observability") if isinstance(metadata.get("fetch_observability"), dict) else {}
        blocked_reason = observability.get("blocked_reason") if isinstance(observability.get("blocked_reason"), str) else None
        stages = observability.get("stages") if isinstance(observability.get("stages"), dict) else {}
        response_stage = stages.get("response_classification") if isinstance(stages.get("response_classification"), dict) else {}
        parse_stage = stages.get("normalize_payload") if isinstance(stages.get("normalize_payload"), dict) else {}

        if status != str(CrawlSessionStatus.FAILED):
            videos_discovered_count = getattr(run, "videos_discovered_count", None)
            if videos_discovered_count == 0:
                response_code = response_stage.get("code") if isinstance(response_stage.get("code"), str) else None
                response_message = response_stage.get("message") if isinstance(response_stage.get("message"), str) else None
                if response_code == "true_zero_videos":
                    return TroubleshootingSummary(
                        category="TRUE_ZERO_VIDEOS",
                        severity="info",
                        why="Profile fetch completed with an explicit zero-video result.",
                        recommended_actions=["Confirm the target profile truly has no public videos before retrying."],
                    )
                return TroubleshootingSummary(
                    category="FETCH_ZERO_VIDEOS",
                    severity="medium",
                    why=response_message or "Profile fetch completed without usable videos.",
                    recommended_actions=[
                        "Inspect fetch-stage diagnostics before changing candidate filters.",
                        "Retry with a healthier account or repaired fetch path if this profile should contain public videos.",
                    ],
                )
            if blocked_reason:
                return TroubleshootingSummary(
                    category="FETCH_BLOCKED_RECOVERED",
                    severity="warning",
                    why=f"Run completed but fetch had blocked signal: {blocked_reason}.",
                    recommended_actions=["Monitor account health and rerun if candidate quality degrades."],
                )
            return TroubleshootingSummary(
                category="NO_FAILURE",
                severity="info",
                why="Run is not in FAILED status.",
                recommended_actions=["Review run counts and proceed with current intake form if results look correct."],
            )

        if blocked_reason in {"login_required", "challenge_required"}:
            return TroubleshootingSummary(
                category="FETCH_BLOCKED_AUTH",
                severity="high",
                why=f"Douyin fetch was blocked ({blocked_reason}).",
                recommended_actions=[
                    "Reconnect the account using browser connect and validate in /accounts/douyin.",
                    "Retry intake with explicit healthy account selection.",
                ],
            )

        if blocked_reason in {"throttled_or_empty", "network_forbidden"}:
            return TroubleshootingSummary(
                category="FETCH_BLOCKED_NETWORK",
                severity="medium",
                why=f"Douyin fetch likely throttled/blocked by network controls ({blocked_reason}).",
                recommended_actions=[
                    "Wait and retry in a non-peak window.",
                    "Use a validated account and reduce rapid retries on the same profile.",
                ],
            )

        if blocked_reason == "unsupported_shape":
            return TroubleshootingSummary(
                category="FETCH_PARSE_SHAPE_CHANGED",
                severity="high",
                why="Douyin payload shape looks unsupported for current parser.",
                recommended_actions=[
                    "Capture this run id and escalate parser update.",
                    "Use already-ingested profile fallback if available.",
                ],
            )

        if parse_stage.get("result") in {"warning", "failed"}:
            return TroubleshootingSummary(
                category="PARSE_OR_NORMALIZE_FAILED",
                severity="high",
                why="Fetch completed but payload parse/normalize stage failed.",
                recommended_actions=[
                    "Inspect run raw summary parse counts/drop reasons.",
                    "Retry with healthy account and compare run deltas.",
                ],
            )

        if "douyin_account" in code or "account" in message or "selected_account_unusable" in message:
            return TroubleshootingSummary(
                category="ACCOUNT_UNUSABLE",
                severity="high",
                why="The selected/default Douyin account was not usable for live fetch.",
                recommended_actions=[
                    "Validate or revalidate Douyin account health in /accounts/douyin.",
                    "Select a healthy account in intake form and rerun with force live refresh.",
                ],
            )

        if "expired" in code or "invalid" in code or "cookie" in message or "session" in message:
            return TroubleshootingSummary(
                category="AUTH_EXPIRED",
                severity="high",
                why="Session/authentication context appears invalid or expired.",
                recommended_actions=[
                    "Reconnect the account using browser connect and validate.",
                    "Retry intake using refreshed account credentials.",
                ],
            )

        if "unsupported_profile" in code or "invalid_url" in code or "not found" in message or "private" in message:
            return TroubleshootingSummary(
                category="PROFILE_NOT_FOUND_OR_PRIVATE",
                severity="medium",
                why="Profile URL/visibility may be invalid, inaccessible, or private.",
                recommended_actions=[
                    "Check and normalize profile URL format before retry.",
                    "Confirm profile visibility and account access rights.",
                ],
            )

        if "rate_limited" in code or "rate limit" in message or "challenge" in message or "captcha" in message:
            return TroubleshootingSummary(
                category="RATE_LIMIT_OR_ANTIBOT",
                severity="medium",
                why="Fetch likely hit anti-bot or rate-limit constraints.",
                recommended_actions=[
                    "Wait and retry with a healthy account.",
                    "Avoid repeated immediate retries for same profile.",
                ],
            )

        if "timeout" in message or "network" in message:
            return TroubleshootingSummary(
                category="NETWORK_OR_TIMEOUT",
                severity="medium",
                why="Network instability or timeout interrupted run.",
                recommended_actions=[
                    "Retry intake after network stabilizes.",
                    "Prefer non-peak retry window if failures are repeated.",
                ],
            )

        return TroubleshootingSummary(
            category="UNKNOWN_FAILURE",
            severity="medium",
            why="Failure does not match a known deterministic category.",
            recommended_actions=[
                "Review error code/message and run metadata.",
                "Retry with force live refresh and explicit healthy account selection.",
            ],
        )

    def _duration_seconds(self, run: CrawlSession) -> int | None:
        if run.started_at is None or run.finished_at is None:
            return None
        delta = run.finished_at - run.started_at
        return max(int(delta.total_seconds()), 0)

    def _candidate_total(self, run: CrawlSession) -> int:
        payload = run.metadata_json if isinstance(run.metadata_json, dict) else {}
        value = payload.get("candidates_total_count")
        return value if isinstance(value, int) else 0

    def _candidate_matched(self, run: CrawlSession) -> int:
        payload = run.metadata_json if isinstance(run.metadata_json, dict) else {}
        value = payload.get("candidates_matched_count")
        return value if isinstance(value, int) else 0

    def _diff_number(self, left: int | None, right: int | None) -> int | None:
        if left is None or right is None:
            return None
        return right - left


def iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()
