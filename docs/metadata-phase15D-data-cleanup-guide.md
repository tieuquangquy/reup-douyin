# Metadata Phase 15D — Data Cleanup Guide

## Purpose
Use this guide when legacy or noisy modal harvest metadata causes ambiguous analytics or duplicate-like metric traces.

## Signals To Review
- `data_integrity_status == "mismatch"`
- `data_integrity_reason` populated
- repeated `metric_signature` values within the same capture session
- non-null `duplicate_signature_warning`

## Recommended Workflow
1. Identify affected sessions from ingest logs.
2. Run duplicate signature audit:
   - `python apps/api/scripts/audit_duplicate_modal_metric_signatures.py --session-id <uuid>`
3. Inspect grouped items and confirm whether duplicates are true data duplicates or expected repeats.
4. For mismatch rows, prioritize re-harvest from extension instead of manual metadata edits.
5. Only apply direct DB cleanup if replay/re-harvest is impossible.

## Safe Cleanup Principles
- Preserve original evidence fields where possible.
- Do not fabricate engagement values.
- Keep an audit trail of changed item IDs and reasons.
- Re-run ingest/verification after cleanup.

## Minimal Validation After Cleanup
- Successful exact-match ingest for at least one affected aweme.
- No new mismatch failures for corrected items.
- Audit script shows expected duplicate group count trend.
