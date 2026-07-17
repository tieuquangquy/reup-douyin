# Phase 5F Captcha-Aware Hydration Log

## Status
- completed

## Why Phase 5F is needed
- Phase 5D backend browser-assisted hydration can open Douyin detail pages with the saved browser profile.
- In real runs, Douyin may return a captcha/challenge page instead of detail content.
- Treating that page as normal detail HTML would produce false negatives or misleading parse failures.

## What the system will and will not do

### Will do
- detect captcha/challenge/block pages conservatively
- stop hydration safely when captcha is detected
- persist item/session hydration status and reason
- tell the operator exactly which browser-profile command to run
- allow hydration to be rerun after manual login/captcha completion

### Will not do
- solve captcha automatically
- rotate proxies/accounts
- fake metadata values
- scrape arbitrary DOM numbers as duration/performance

## Audit findings
- The best insertion point is the backend hydration service:
  - `CaptureInboxMetadataHydrationService._hydrate_item(...)`
  - it already receives `fetch_detail_page(...)` results including:
    - `title`
    - `page_url`
    - `html`
    - `response_documents`
- Browser runtime reuse/open already exists via:
  - `DouyinAccountService.preflight_fetch_readiness(...)`
  - `douyin_browser_context_registry.fetch_detail_page(...)`
  - `python scripts/douyin_account_readiness.py --account-id <id> --open-profile`

## Planned implementation
1. Add deterministic captcha/block detector over title/url/html/response markers.
2. Mark items with:
   - `metadata_hydration_status`
   - `metadata_hydration_error_code`
   - `metadata_hydration_error_message`
   - `captcha_required_at`
   - `captcha_required_url`
3. Stop the session hydration batch on first captcha/block detection.
4. Return operator-friendly command output from hydration script.
5. Reuse existing open-profile command for manual resolution.

## Files touched
- `apps/api/src/services/capture_inbox_metadata_hydration_service.py`
- `apps/api/scripts/hydrate_capture_session_metadata.py`
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/tests/test_capture_inbox_metadata_hydration_service.py`
- `apps/api/tests/test_hydrate_capture_session_metadata_script.py`
- `docs/metadata-phase5F-captcha-aware-hydration-log.md`
- `docs/metadata-phase5F-captcha-aware-hydration-resume.md`
- `docs/metadata-phase5F-captcha-aware-hydration-operator-guide.md`

## Captcha detection logic
- Detector runs in backend hydration service before detail-aweme parsing.
- Inputs checked:
  - final page URL
  - page title
  - first HTML/body slice
  - first few response documents
- Structured outcomes:
  - `captcha_required` for captcha/challenge/manual verification signals
  - `detail_page_blocked` for generic blocked/access-denied style signals

## Item/session behavior
- Item-level:
  - do not attach `raw_detail_aweme`
  - persist:
    - `metadata_hydration_status`
    - `metadata_hydration_error_code`
    - `metadata_hydration_error_message`
    - `metadata_hydration_attempted_at`
    - `last_metadata_hydrated_at`
    - `captcha_required_at`
    - `captcha_required_url`
    - `performance_missing_reason`
    - `processing_fit_missing_reason`
- Session-level:
  - stop hydration on first captcha/block detection
  - persist run summary with:
    - `captcha_required_count`
    - `detail_page_blocked_count`
    - `stop_reason_code`
    - `stop_reason_message`
    - `next_operator_action`

## Tests run
- `python -m unittest tests.test_capture_inbox_metadata_hydration_service tests.test_hydrate_capture_session_metadata_script tests.test_douyin_account_readiness_script`
- `python -m compileall src scripts`

## Verification
- Passed focused backend tests.
- Hydration script now returns operator-facing `--open-profile` guidance when captcha/manual verification is required.
