"""Automated quality verdict for a finished render.

Full auto ends with nobody watching the intermediate stages, so the last stage has to
decide on its own whether the output is worth an operator's time. The rules below stay
generic on purpose — duration, audio, subtitles, resolution and the risk gate hold for
cooking clips, UI-card clips and sparse-hardsub clips alike. Anything the pipeline cannot
measure is reported as skipped instead of being guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

# Render/source drift: encoders trim a frame or two, so allow a little slack before warning.
DURATION_WARN_RATIO = 0.05
DURATION_FAIL_RATIO = 0.20
# Anything below this is not a publishable vertical clip regardless of source.
MIN_RENDER_HEIGHT = 480
MIN_RENDER_WIDTH = 270


class RenderQaStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class RenderQaCheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RenderQaCheck:
    key: str
    status: RenderQaCheckStatus
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "status": str(self.status), "detail": self.detail}


@dataclass(frozen=True)
class RenderQaMetrics:
    source_duration_seconds: float | None
    render_duration_seconds: float | None
    render_width: int | None
    render_height: int | None
    audio_codec: str | None
    subtitle_burned: bool
    dub_expected: bool
    dub_audio_present: bool | None
    risk_can_continue: bool | None
    risk_highest_severity: str | None
    render_warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RenderQaVerdict:
    status: RenderQaStatus
    checks: list[RenderQaCheck]
    summary: str

    @property
    def failed_checks(self) -> list[str]:
        return [c.key for c in self.checks if c.status == RenderQaCheckStatus.FAIL]

    @property
    def warned_checks(self) -> list[str]:
        return [c.key for c in self.checks if c.status == RenderQaCheckStatus.WARN]

    @property
    def skipped_checks(self) -> list[str]:
        return [c.key for c in self.checks if c.status == RenderQaCheckStatus.SKIPPED]

    @property
    def can_auto_finish(self) -> bool:
        """A warn still reaches Final Review with a badge; a fail needs an operator first."""
        return self.status != RenderQaStatus.FAIL

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": str(self.status),
            "summary": self.summary,
            "failed": self.failed_checks,
            "warned": self.warned_checks,
            "checks": [check.to_dict() for check in self.checks],
        }


def _duration_check(metrics: RenderQaMetrics) -> RenderQaCheck:
    source = metrics.source_duration_seconds
    rendered = metrics.render_duration_seconds
    if not source or not rendered or source <= 0:
        return RenderQaCheck("duration_match", RenderQaCheckStatus.SKIPPED, "Duration unknown on one side.")
    drift = abs(rendered - source) / source
    detail = f"Render {rendered:.2f}s vs source {source:.2f}s ({drift * 100:.1f}% drift)."
    if drift > DURATION_FAIL_RATIO:
        return RenderQaCheck("duration_match", RenderQaCheckStatus.FAIL, detail)
    if drift > DURATION_WARN_RATIO:
        return RenderQaCheck("duration_match", RenderQaCheckStatus.WARN, detail)
    return RenderQaCheck("duration_match", RenderQaCheckStatus.PASS, detail)


def _dub_check(metrics: RenderQaMetrics) -> RenderQaCheck:
    if not metrics.dub_expected:
        return RenderQaCheck("dub_audio", RenderQaCheckStatus.PASS, "Clip has no dialogue; no dub expected.")
    if metrics.dub_audio_present is False:
        return RenderQaCheck("dub_audio", RenderQaCheckStatus.FAIL, "Dubbing expected but no joined narration exists.")
    if not metrics.audio_codec:
        return RenderQaCheck("dub_audio", RenderQaCheckStatus.FAIL, "Rendered file has no audio stream.")
    if metrics.dub_audio_present is None:
        return RenderQaCheck(
            "dub_audio",
            RenderQaCheckStatus.WARN,
            f"Audio stream present ({metrics.audio_codec}) but dub asset could not be confirmed.",
        )
    return RenderQaCheck("dub_audio", RenderQaCheckStatus.PASS, f"Audio stream present ({metrics.audio_codec}).")


def _subtitle_check(metrics: RenderQaMetrics) -> RenderQaCheck:
    if metrics.subtitle_burned:
        return RenderQaCheck("subtitle_burned", RenderQaCheckStatus.PASS, "Vietnamese subtitles are burned in.")
    return RenderQaCheck(
        "subtitle_burned",
        RenderQaCheckStatus.WARN,
        "Render reports no burned subtitles — check whether the clip needed them.",
    )


def _resolution_check(metrics: RenderQaMetrics) -> RenderQaCheck:
    width = metrics.render_width
    height = metrics.render_height
    if not width or not height:
        return RenderQaCheck("resolution", RenderQaCheckStatus.SKIPPED, "Output resolution unknown.")
    detail = f"Output {width}x{height}."
    if height < MIN_RENDER_HEIGHT or width < MIN_RENDER_WIDTH:
        return RenderQaCheck("resolution", RenderQaCheckStatus.FAIL, f"{detail} Too small to publish.")
    if height < width:
        return RenderQaCheck("resolution", RenderQaCheckStatus.WARN, f"{detail} Landscape output for a vertical feed.")
    return RenderQaCheck("resolution", RenderQaCheckStatus.PASS, detail)


def _risk_check(metrics: RenderQaMetrics) -> RenderQaCheck:
    if metrics.risk_can_continue is None:
        return RenderQaCheck("risk_gate", RenderQaCheckStatus.SKIPPED, "Risk scan did not run.")
    severity = str(metrics.risk_highest_severity or "none").lower()
    if not metrics.risk_can_continue:
        return RenderQaCheck("risk_gate", RenderQaCheckStatus.FAIL, f"Risk gate blocks publishing (severity {severity}).")
    if severity in {"high", "critical", "medium"}:
        return RenderQaCheck("risk_gate", RenderQaCheckStatus.WARN, f"Open risk flags at severity {severity}.")
    return RenderQaCheck("risk_gate", RenderQaCheckStatus.PASS, "No blocking risk flags.")


def _warnings_check(metrics: RenderQaMetrics) -> RenderQaCheck:
    warnings = [str(entry) for entry in (metrics.render_warnings or []) if str(entry).strip()]
    if not warnings:
        return RenderQaCheck("render_warnings", RenderQaCheckStatus.PASS, "Renderer reported no warnings.")
    joined = "; ".join(warnings[:3])
    return RenderQaCheck("render_warnings", RenderQaCheckStatus.WARN, f"Renderer warnings: {joined}")


def evaluate_render_qa(metrics: RenderQaMetrics) -> RenderQaVerdict:
    checks = [
        _duration_check(metrics),
        _dub_check(metrics),
        _subtitle_check(metrics),
        _resolution_check(metrics),
        _risk_check(metrics),
        _warnings_check(metrics),
    ]
    failed = [check for check in checks if check.status == RenderQaCheckStatus.FAIL]
    warned = [check for check in checks if check.status == RenderQaCheckStatus.WARN]

    if failed:
        status = RenderQaStatus.FAIL
        summary = "Render QA failed: " + " ".join(check.detail for check in failed)
    elif warned:
        status = RenderQaStatus.WARN
        summary = "Render QA passed with warnings: " + " ".join(check.detail for check in warned)
    else:
        status = RenderQaStatus.PASS
        summary = "Render QA passed all automated checks."
    return RenderQaVerdict(status=status, checks=checks, summary=summary[:800])


def collect_render_qa_metrics(db: Any, source_video_id: UUID | None, *, dub_expected: bool) -> RenderQaMetrics | None:
    """Read the render/source/risk facts for a finished item. None when there is no render."""
    if source_video_id is None:
        return None

    from src.enums import MediaAssetType, RiskTargetType
    from src.models.ingestion import SourceVideo
    from src.models.media import MediaAsset, RenderOutput
    from sqlalchemy import select

    render_output = db.scalar(
        select(RenderOutput)
        .where(RenderOutput.source_video_id == source_video_id)
        .order_by(RenderOutput.created_at.desc())
        .limit(1)
    )
    if render_output is None:
        return None

    source = db.get(SourceVideo, source_video_id)
    source_duration = getattr(source, "duration_seconds", None)

    dub_asset = db.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.source_video_id == source_video_id,
            MediaAsset.asset_type == MediaAssetType.TTS_AUDIO_JOINED,
            MediaAsset.is_current.is_(True),
        )
        .limit(1)
    )

    risk_can_continue: bool | None = None
    risk_severity: str | None = None
    try:
        from src.risk.services.risk_service import RiskService

        _, _, gate = RiskService(db).run_scan(RiskTargetType.RENDER_OUTPUT, render_output.id)
        risk_can_continue = bool(getattr(gate, "can_continue", True))
        highest = getattr(gate, "highest_severity", None)
        risk_severity = str(getattr(highest, "value", highest)) if highest is not None else None
    except Exception:  # noqa: BLE001 — QA must never block the pipeline on a scanner defect
        risk_can_continue = None

    warnings_payload = getattr(render_output, "warning_summary_json", None) or {}
    warnings = warnings_payload.get("warnings") if isinstance(warnings_payload, dict) else None

    return RenderQaMetrics(
        source_duration_seconds=float(source_duration) if source_duration else None,
        render_duration_seconds=(
            float(render_output.duration_seconds) if getattr(render_output, "duration_seconds", None) else None
        ),
        render_width=getattr(render_output, "width", None),
        render_height=getattr(render_output, "height", None),
        audio_codec=getattr(render_output, "audio_codec", None),
        subtitle_burned=bool(getattr(render_output, "subtitle_burned", False)),
        dub_expected=bool(dub_expected),
        dub_audio_present=bool(dub_asset) if dub_expected else None,
        risk_can_continue=risk_can_continue,
        risk_highest_severity=risk_severity,
        render_warnings=list(warnings) if isinstance(warnings, list) else [],
    )
