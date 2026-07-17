# Risk Scan Overview

Risk scan is an operator-assist layer. It is not a legal compliance engine and must not be described as one.

## Purpose

Phase 1 risk scan helps the operator notice common warning signals before final approval or publish draft handoff:

- possible watermark issues
- heuristic audio copyright risk
- dense OCR/text complexity
- speech or processing quality issues
- render warnings
- publish metadata problems
- platform policy placeholders

The output is a warning summary plus traceable operator decisions.

## Data Model

`RiskFlag` is the canonical warning record. It can attach to:

- `SOURCE_VIDEO`
- `RENDER_OUTPUT`
- `PUBLISH_DRAFT`

Each flag includes target reference, risk type, severity, status, title, description, evidence summary, scan source, detected/resolved timestamps, and metadata.

`OperatorRiskDecision` records the operator choice for a target:

- `CONTINUE`
- `NEEDS_FIX`
- `REJECT`
- `ACCEPT_WITH_WARNING`

## Scan Flow

1. API receives `target_type` and `target_id`.
2. Service resolves the target and source video.
3. Rule-based scanners read existing pipeline signals.
4. Current open flags for that target are marked resolved as superseded.
5. New flags are created with one `scan_run_id`.
6. Gate summary is returned to the UI.

## Phase 1 Scanners

Scanners are heuristic and rule-based:

- source video metadata scanner
- render warning scanner
- publish draft metadata scanner

If a signal does not exist, the scanner skips it. The scanner must not pretend to detect things it cannot actually inspect.

## API

- `POST /risk-scans`
- `GET /risk-flags`
- `GET /risk-flags/{risk_flag_id}`
- `POST /risk-flags/{risk_flag_id}/acknowledge`
- `POST /risk-flags/{risk_flag_id}/resolve`
- `POST /risk-flags/{risk_flag_id}/waive`
- `POST /risk-decisions`
- `GET /targets/{target_type}/{target_id}/risk-summary`

## UI Integration

Risk summary appears in:

- final review for `RENDER_OUTPUT`
- publish draft page for `PUBLISH_DRAFT`

The UI is intentionally not a risk management console.
