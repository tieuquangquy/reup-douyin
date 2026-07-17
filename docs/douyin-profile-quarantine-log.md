# Douyin Profile Quarantine Log

## Status

Started: 2026-04-26

This log records the implementation of Douyin browser-profile quarantine and clean-profile recommendation. The feature is scoped to operational account/profile state only. It does not delete profiles, create a second discovery architecture, or change the canonical downstream entities.

## Scope

Touched areas expected for this task:

- `apps/api`: persisted metadata policy, health projection, preflight readiness, account selection, current-page capture gating, tests.
- `apps/web`: account list UI, Intake selector/Ready Check UI, TypeScript response types, i18n strings.
- `docs`: quarantine architecture, resume notes, operator guide, and this implementation log.

Explicit non-goals:

- No crawler implementation.
- No alternate downstream discovery model.
- No deletion of risky browser profiles.
- No raw secrets, cookies, tokens, or private local paths in logs or UI.
- No automated publishing behavior.

## Audit Findings

### Existing challenge signals

Current repeated-challenge evidence is already stored on `DouyinAccountConnection.metadata_json` and projected through API responses.

Observed metadata keys:

- `douyin_challenge_state`
- `douyin_challenge_detected`
- `douyin_challenge_category`
- `douyin_challenge_validation_category`
- `douyin_challenge_count`
- `douyin_challenge_last_detected_at`
- `douyin_challenge_cooldown_until`
- `douyin_challenge_recommended_next_action`
- `douyin_challenge_recheck_resolved`
- `douyin_challenge_postcheck_result`
- `browser_context_blocked_count`
- `last_browser_validation_category`
- `last_browser_validation_final_category`
- `last_browser_validation_challenge_category`
- `last_browser_validation_recommended_next_action`
- `last_browser_validation_blocked_probe_reason`

Current challenge states:

- `challenge_waiting_for_manual_verification`
- `challenge_recently_solved_pending_recheck`
- `challenge_cooldown`
- `challenge_repeat_limit_reached`
- projected runtime state `challenge_cooldown_active`

Current thresholds:

- `DOUYIN_CHALLENGE_REPEAT_LIMIT = 3`
- `DOUYIN_CHALLENGE_COOLDOWN = 10 minutes`

### Existing blocking behavior

The backend already blocks unresolved challenges from live fetch through health and preflight paths:

- `health_summary` returns blocked health and `can_use_for_live_fetch=False` for unresolved challenge states.
- `preflight_fetch_readiness` returns `fetch_blocked_by_browser_challenge` for unresolved challenge states.
- Ready Check maps this to `CHALLENGE_BLOCKED`.
- Account recommendation uses `health.can_use_for_live_fetch` for selected/default/fallback account decisions.

### Gap

The current model treats repeated challenge state as a challenge recovery loop, not a durable operational quarantine decision. A profile that repeatedly enters challenge cooldown can remain in the primary operator loop and keep prompting solve/retry behavior. There is no explicit state that says: keep this profile available for reference, but stop preferring it for Intake/capture and recommend a cleaner managed profile.

## Implementation Plan

1. Add deterministic profile-risk/quarantine policy in `DouyinAccountService`.
2. Persist quarantine state in account metadata rather than adding a database schema in this step.
3. Project quarantine state through `DouyinBrowserHealthAlignmentSummary`, `DouyinAccountResponse`, and Ready Check.
4. Ensure health/preflight/account selection treat quarantined profiles as unavailable for primary live fetch.
5. Keep open/reopen/detect/reference inspection available.
6. Gate capture and Intake use with explicit quarantine messages.
7. Add UI warnings and clean-profile recommendations.
8. Add focused tests for detection, projection, account selection, Ready Check, and capture gating.
9. Run backend tests and frontend typecheck.

## Proposed Deterministic Policy

A browser-backed account/profile becomes a quarantine candidate when it has saved browser profile metadata and any of these conditions are true:

- `douyin_challenge_state == "challenge_repeat_limit_reached"`
- `douyin_challenge_count >= 3`
- `browser_context_blocked_count >= 3`
- post-challenge recheck reports repeated still-required/block outcomes while challenge count is already at or above the repeat limit.

Canonical projected states:

- `active_preferred`: usable account without risk indicators.
- `active_warning`: not quarantined, but has warning-level challenge evidence below threshold.
- `quarantine_candidate`: threshold crossed and should be moved out of the happy path.
- `quarantined`: blocked from primary live fetch/capture by quarantine state.
- `quarantined_recoverable`: quarantined, still openable/inspectable and may be manually validated later.
- `quarantined_replaced`: quarantined and a different account is now preferred.

For Phase 1 implementation, automatic threshold crossing persists `quarantined` immediately to avoid repeated poisoning of the normal flow. `quarantine_candidate`, `quarantined_recoverable`, and `quarantined_replaced` remain available projected states for future manual recovery/replacement workflows.

## Notes While Implementing

- Quarantine is operational state, not account deletion.
- Existing `DouyinAccountConnection` remains the account model.
- Existing `SourceProfile`, `SourceVideo`, `CrawlSession`, `VideoMetricSnapshot`, and `VideoCandidate` remain the downstream pipeline.
- A quarantined profile should remain openable and detectable for operator troubleshooting.
- Normal Intake, Ready Check, account recommendation, and capture should not prefer quarantined profiles.

## Final Implementation Notes

Implemented backend behavior:

- `DouyinAccountService` detects quarantine only for accounts with saved managed browser-profile metadata.
- Quarantine is triggered by repeat-limit challenge state, challenge count threshold, or blocked-browser-response count threshold.
- `health_summary` projects quarantined profiles as blocked and unavailable for live fetch, causing default/fallback recommendation to skip them.
- `preflight_fetch_readiness` returns `fetch_blocked_by_profile_quarantine` / `profile_quarantined` and recommends a clean managed browser-backed profile.
- `IntakeDiscoveryService.ready_check` maps this to `PROFILE_QUARANTINED` with `create_clean_managed_browser_profile` as the recommended action.
- Current-page detection remains allowed for reference inspection.
- Current-page capture is blocked before page snapshot/ingest when a profile is quarantined.

Implemented frontend behavior:

- Douyin account responses and Intake Ready Check types include quarantine projection fields.
- Douyin Accounts UI shows a quarantine badge, reason, state, clean-profile recommendation, and blocks Capture / Use in Intake for quarantined profiles.
- Open/Reopen and Detect current page remain available for reference inspection.
- Intake Ready Check UI displays `PROFILE_QUARANTINED`, quarantine reason/state, and the clean-profile recommendation.
- English and Vietnamese i18n strings were added.

Verification completed:

- `python -m unittest tests.test_douyin_account_preflight tests.test_intake_discovery_service tests.test_douyin_current_page_capture_service tests.test_douyin_account_service` from `apps/api`: 64 tests passed.
- `npm run typecheck` from `apps/web`: passed.
