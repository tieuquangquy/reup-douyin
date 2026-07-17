# Metadata Phase 17A — Harvest Plan / Finalized-Only Resume

## Current Phase State
Phase 17A introduces a staged Harvest Plan before Smart Capture modal harvest. Normal Smart Capture should no longer stage partial visible Capture Inbox items from profile-card scans. Visible items are created only after full modal metadata passes the finalized-only gate.

## Backend State
- `POST /douyin-extension/harvest-plan` classifies profile videos and returns target aweme ids without creating visible rows.
- `POST /douyin-extension/full-modal-harvest` accepts `commit_policy`.
- With `commit_policy = "finalized_only"`, unmatched incomplete payloads are rejected at item level with `finalized_metadata_required` and do not create visible rows.
- Existing matched rows can still be updated by full modal harvest.

## Extension State
- Normal Smart Capture calls the Harvest Plan endpoint before modal harvest.
- Manual/advanced current-page capture still calls the legacy partial-visible capture endpoint.
- Harvest Plan target aweme ids and profile-card evidence are persisted in smart capture state.
- Runtime start options carry `profile_card_evidence_by_aweme_id`.
- Smart Capture modal flush uses `commit_policy: "finalized_only"`.
- No-target Harvest Plan responses complete as a no-op without starting modal harvest.

## Test Coverage Added
- API tests cover new/incomplete/complete classification, idempotent plan creation, harvest modes, finalized-only item creation, finalized-only rejection, existing-row update, and unrelated-row protection.
- Extension tests cover Harvest Plan usage in Smart Capture, absence of the old partial path in normal Smart Capture, manual current-page capture compatibility, no-target no-op, profile-card evidence propagation, and finalized-only modal flush policy.

## Verification Commands
Use these from repository root on Windows:

```cmd
cd apps/api && python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_metadata_normalizer tests.test_capture_inbox_metadata_status
```

```cmd
cd apps/api && python -m compileall src scripts
```

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
```

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
```

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Watch Points
- Keep Harvest Plan read/classification-only; do not add visible item persistence there.
- Keep finalized-only visible-item creation tied to full modal metadata completeness and integrity.
- Do not require `view_count` until a later phase explicitly adds it.
- Do not move crawling, scoring, or media processing into this phase.
