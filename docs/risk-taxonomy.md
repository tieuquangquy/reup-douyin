# Risk Taxonomy

Risk taxonomy is designed for clear operator warnings, not legal conclusions.

## Risk Types

Phase 1 supports:

- `AUDIO_COPYRIGHT_RISK`: heuristic signal for possibly risky audio.
- `WATERMARK_RISK`: visible or metadata-indicated watermark concern.
- `BRAND_LOGO_RISK`: placeholder for brand/logo concern.
- `CELEBRITY_PERSONA_RISK`: placeholder for persona or likeness concern.
- `OCR_DENSITY_RISK`: dense on-screen text or OCR complexity.
- `SPEECH_QUALITY_RISK`: low confidence speech or hard-to-review audio.
- `PROCESSING_COMPLEXITY_RISK`: source or pipeline suggests hard processing.
- `PLATFORM_POLICY_RISK`: platform rule placeholder or metadata issue.
- `MANUAL_REVIEW_REQUIRED`: generic checkpoint warning.

Legacy types such as `COPYRIGHT`, `WATERMARK`, `LOW_QUALITY`, `DUPLICATE`, `POLICY`, and `MANUAL_REVIEW` remain for compatibility.

## Severity

- `LOW`: informational.
- `MEDIUM`: review when convenient.
- `HIGH`: operator decision required before high-confidence handoff.
- `CRITICAL`: blocks handoff unless explicitly accepted with warning.
- `BLOCKING`: compatibility alias for critical-level blocking behavior.

## Status

- `OPEN`: active warning.
- `ACKNOWLEDGED`: operator saw it, but it is still active.
- `RESOLVED`: fixed or superseded.
- `WAIVED`: intentionally ignored for this target.
- `REJECTED`: target should not continue because of this warning.

## Evidence

Evidence is a short summary and optional JSON metadata. Evidence should say what signal was observed, not overstate certainty.

Good:

- `metadata.has_heavy_watermark=true`
- `subtitle timing mismatch`

Bad:

- `copyright violation confirmed`
- `illegal content`
