# Douyin Profile Quarantine Resume

## Current Goal

Implement browser-profile quarantine and clean-profile recommendation for Douyin managed browser accounts so repeatedly challenged/high-risk profiles do not keep poisoning the normal Ready Check, Intake, capture, and recommendation flow.

## User Requirements

- Detect too challenge-heavy browser-backed Douyin accounts/profiles.
- Quarantine risky profiles without deleting them.
- Surface clear operator guidance that quarantined profiles should no longer be preferred for capture/intake.
- Recommend creating or using a fresh cleaner browser-backed account/profile.
- Ensure Ready Check, Intake, and recommendation stop preferring quarantined profiles.
- Preserve canonical architecture:
  - `DouyinAccountConnection`
  - one account = one managed persistent browser profile
  - downstream pipeline remains `SourceProfile`, `SourceVideo`, `CrawlSession`, `VideoMetricSnapshot`, `VideoCandidate`
  - no second downstream discovery architecture.

## Mandatory Work Order

1. Audit high-risk/repeated-challenge signals.
2. Write quarantine docs first.
3. Implement quarantine and recommendation.
4. Verify each major layer:
   - detection
   - state projection
   - account recommendation
   - action gating
   - UI guidance.
5. Finish with final status.

## Audit Summary

Relevant backend files:

- `apps/api/src/services/douyin_account_service.py`
  - challenge constants and metadata policy
  - account health projection
  - fetch preflight readiness
  - browser validation outcome handling
  - API response projection
- `apps/api/src/services/intake_discovery_service.py`
  - Ready Check
  - account recommendation/selection
  - live-fetch preflight enforcement
- `apps/api/src/services/douyin_current_page_capture_service.py`
  - capture-current-page gating
- `apps/api/src/schemas/douyin_accounts.py`
  - account response and browser-health alignment schema
- `apps/api/src/schemas/intake.py`
  - Ready Check response schema

Relevant frontend files:

- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/types/intake.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`

Relevant existing tests:

- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/api/tests/test_douyin_current_page_capture_service.py`

## Design Direction

Persist quarantine state in `metadata_json` keys rather than introducing schema/migration in this step:

- `douyin_profile_quarantine_state`
- `douyin_profile_quarantine_reason`
- `douyin_profile_quarantine_detected_at`
- `douyin_profile_quarantine_recommended_next_action`
- `douyin_profile_quarantine_challenge_count`
- `douyin_profile_quarantine_blocked_count`
- `douyin_profile_quarantine_replaced_by_account_id` when available.

Projected response fields should make UI/backend behavior explicit:

- `profile_quarantine_state`
- `profile_quarantine_reason`
- `profile_quarantine_detected`
- `profile_quarantine_recommended_next_action`
- `profile_quarantine_blocks_primary_flow`
- `profile_quarantine_replaced_by_account_id`
- `profile_quarantine_clean_profile_recommendation`

## Expected Gating

- Health summary returns blocked/unusable for quarantined profiles.
- Preflight returns a dedicated blocked category/code such as `fetch_blocked_by_profile_quarantine` / `profile_quarantined`.
- Ready Check returns a dedicated status such as `PROFILE_QUARANTINED` and recommends creating/using a clean browser-backed profile.
- Account selection skips quarantined accounts for default/fallback selection.
- If the operator explicitly selects a quarantined account and no clean account exists, Ready Check should clearly report quarantine instead of silently falling through to generic not-ready.
- Current-page detection remains allowed as reference inspection.
- Current-page capture is blocked by default for quarantined profiles.
- Opening/reopening the browser profile remains allowed.

## Verification Checklist

- [x] Backend unit tests for quarantine threshold detection.
- [x] Backend unit tests for response projection.
- [x] Backend unit tests for Ready Check and account recommendation skipping quarantined accounts.
- [x] Backend unit tests for capture gating.
- [x] Frontend typecheck.
- [x] Docs updated with final implementation status.

## Final Status

Implemented and verified. Quarantined Douyin managed browser-backed profiles are now projected as blocked from the primary flow, excluded from account recommendation through health selection, blocked by Ready Check and Capture, and surfaced in the UI with clean-profile guidance. Reference inspection remains available through Open/Reopen and Detect current page.

Verification commands completed:

- `python -m unittest tests.test_douyin_account_preflight tests.test_intake_discovery_service tests.test_douyin_current_page_capture_service tests.test_douyin_account_service` from `apps/api`: passed, 64 tests.
- `npm run typecheck` from `apps/web`: passed.
