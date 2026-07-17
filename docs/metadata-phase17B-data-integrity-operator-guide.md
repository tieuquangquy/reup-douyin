# Phase 17B Data Integrity Operator Guide

## Purpose

Use this guide when retesting Douyin Smart Capture after Phase 17B. The goal is to confirm that modal metrics cannot be reused across different aweme ids and cannot update the wrong Capture Inbox row.

## Live Retest Steps

1. Start the API and extension in the normal local Windows workflow.
2. Open a Douyin creator profile with several visible videos.
3. Run Smart Capture so the extension creates a harvest plan rather than visible partial rows.
4. Start modal harvest from the planned target list.
5. Watch the recent items panel: OK rows must include the aweme id and must only appear after backend flush success.
6. If the modal changes to a different video during extraction, the target must fail with `data_integrity_mismatch`; no OK row should appear.
7. Confirm the Capture Inbox row for each updated item has `source_video_external_id` equal to the payload aweme id.
8. Run the audit script for the capture session:
   `python apps\\api\\scripts\\audit_douyin_duplicate_modal_metrics.py --session-id <capture-session-id>`
9. Review duplicate groups. Duplicates are warnings for investigation, not automatic deletes.

## Expected Failure Display

A failed identity check should be operator-visible as a failed recent item with the aweme id and reason. Backend failures should include `data_integrity_mismatch` and no unrelated item should be updated.

## Safety Notes

- Do not manually edit database rows to resolve duplicate metric warnings.
- Do not use title, thumbnail, card order, or target index as a replacement for aweme id identity.
- Rerun harvest only after confirming the modal and target aweme ids match.
