from __future__ import annotations

from typing import TYPE_CHECKING

from src.enums import RiskFlagType, RiskSeverity
from src.risk.types import RiskFinding

if TYPE_CHECKING:
    from src.models.ingestion import SourceVideo
    from src.models.media import RenderOutput
    from src.models.publish import PublishDraft


def scan_source_video(source_video: SourceVideo) -> list[RiskFinding]:
    metadata = source_video.metadata_json or {}
    findings: list[RiskFinding] = []
    if metadata.get("has_heavy_watermark"):
        findings.append(_finding(RiskFlagType.WATERMARK_RISK, RiskSeverity.HIGH, "Heavy watermark signal", "Source metadata suggests a visible watermark. Review the final output before publish.", "metadata.has_heavy_watermark=true", "source_video_metadata"))
    if metadata.get("copyright_risk") in {"high", "HIGH", True}:
        findings.append(_finding(RiskFlagType.AUDIO_COPYRIGHT_RISK, RiskSeverity.HIGH, "Audio copyright heuristic", "The source metadata indicates possible copyrighted audio. This is a heuristic warning, not a legal judgment.", "metadata.copyright_risk=high", "source_video_metadata"))
    if metadata.get("text_density") == "high":
        findings.append(_finding(RiskFlagType.OCR_DENSITY_RISK, RiskSeverity.MEDIUM, "High text density", "The source appears to contain dense on-screen text. OCR or subtitle overlays may need manual review.", "metadata.text_density=high", "source_video_metadata"))
    if metadata.get("processing_complexity") == "high":
        findings.append(_finding(RiskFlagType.PROCESSING_COMPLEXITY_RISK, RiskSeverity.MEDIUM, "High processing complexity", "Prior pipeline metadata says this video may be hard to process cleanly.", "metadata.processing_complexity=high", "source_video_metadata"))
    return findings


def scan_render_output(render: RenderOutput) -> list[RiskFinding]:
    warnings = _warnings(render.warning_summary_json) + _warnings((render.metadata_json or {}).get("manifest") if render.metadata_json else None)
    findings: list[RiskFinding] = []
    for warning in warnings:
        severity = RiskSeverity.HIGH if "mismatch" in warning.lower() or "failed" in warning.lower() else RiskSeverity.MEDIUM
        findings.append(_finding(RiskFlagType.MANUAL_REVIEW_REQUIRED, severity, "Render warning needs review", "Render pipeline produced a warning that should be checked in final review.", warning, "render_output_warnings", {"warning": warning}))
    if render.subtitle_burned is False:
        findings.append(_finding(RiskFlagType.PLATFORM_POLICY_RISK, RiskSeverity.MEDIUM, "Subtitle not burned", "Final render metadata says subtitles were not hard-burned. Check whether this is intentional.", "render.subtitle_burned=false", "render_metadata"))
    return findings


def scan_publish_draft(draft: PublishDraft) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    caption = draft.caption or ""
    hashtags = draft.hashtags_json or []
    if not caption.strip():
        findings.append(_finding(RiskFlagType.PLATFORM_POLICY_RISK, RiskSeverity.HIGH, "Missing caption", "Publish draft has no caption. Add operator-approved post text before marking ready.", "caption is empty", "publish_draft_validation"))
    if not hashtags:
        findings.append(_finding(RiskFlagType.PLATFORM_POLICY_RISK, RiskSeverity.MEDIUM, "Missing hashtags", "Publish draft has no hashtags. Add at least one target-platform hashtag if appropriate.", "hashtags_json empty", "publish_draft_validation"))
    risky_terms = ["ban quyen", "copyright", "reup"]
    if any(term in caption.lower() for term in risky_terms):
        findings.append(_finding(RiskFlagType.PLATFORM_POLICY_RISK, RiskSeverity.MEDIUM, "Caption contains sensitive wording", "Caption includes wording that may need manual review before posting.", "caption keyword heuristic", "publish_draft_text"))
    return findings


def _finding(risk_type: RiskFlagType, severity: RiskSeverity, title: str, description: str, evidence_summary: str, scan_source: str, metadata: dict | None = None) -> RiskFinding:
    return RiskFinding(risk_type=risk_type, severity=severity, title=title, description=description, evidence_summary=evidence_summary, scan_source=scan_source, metadata=metadata or {})


def _warnings(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    warnings = value.get("warnings")
    if not isinstance(warnings, list):
        return []
    return [item for item in warnings if isinstance(item, str) and item]
