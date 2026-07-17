# Scan Profile Debug Report

## Actual Implemented Flow

The active `Scan Profile` feature appears to be the Chrome extension whole-profile harvest flow, not the older API-only source ingest form.

1. Operator opens a Douyin profile in Chrome and uses the extension popup.
2. Extension checks active tab and Douyin page readiness.
3. Extension `Scan Profile` action enters the whole-profile harvest controller.
4. Controller resolves/normalizes the target profile URL.
5. Controller ensures the content script/detector is ready.
6. `scanWholeProfileTargets()` calls runtime transport `scanProfile(tabId, profileUrl)`.
7. `scanProfile` returns a `ModalWholeProfileCardScanResult` with profile cards, diagnostics, stop reason, expected count, and discovered card count.
8. Scanner validates cards through `validateWholeProfileTargets()`.
9. Controller builds harvest queue / classification state.
10. Extension can create/verify backend capture session and later collect individual modal details.
11. Extension flushes canonical harvest payloads to API endpoint `/douyin-extension/full-modal-harvest`.
12. API persists capture sessions/items in capture inbox tables.
13. Web UI displays capture inbox data from `/capture-inbox/*` and `/douyin-extension/capture-sessions/{capture_session_id}/items`.
14. Operator promotes selected capture inbox items to Review Board, then later Reup Queue.

## Relevant Files

### Extension

- `apps/extension-douyin-capture/src/popup.ts`
  - Popup entry point; wires user actions to workflow.
- `apps/extension-douyin-capture/src/popupActions.ts`
  - Friendly popup error projection for backend, tab, login, challenge, and direct execution failures.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
  - Main whole-profile state machine and `Scan Profile` orchestration.
  - Important constants: `SCAN_PROFILE_ENSURE_CONTENT_SCRIPT_TIMEOUT_MS`, `SCAN_CONTROLLER_VERSION`, `SCANNER_RUNTIME_VERSION`.
  - Contains guards for calibration, backend session verification, target selection, and runner target allowlist.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
  - Thin scanner wrapper. Calls transport `scanProfile()`, validates target cards, maps scan failure reasons to domain error codes.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts`
  - Resolves/normalizes Douyin profile URL and modal/profile context.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/targetValidation.ts`
  - Validates discovered targets/cards.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`
  - Builds capture session requests, canonical harvest payloads, queue payloads, sec_uid extraction, and guards.
- `apps/extension-douyin-capture/src/extensionBackendClient.ts`
  - Posts extension payloads to backend, especially `/douyin-extension/full-modal-harvest`; classifies fetch/CORS/422/500 failures.
- `apps/extension-douyin-capture/src/contentScript.ts`
  - Content script visible in editor; likely provides in-page detection/extraction hooks used by background/runtime.

### API

- `apps/api/src/main.py`
  - Includes protected routers, including `douyin_extension_router`, `capture_inbox_router`, `source_ingest_router`.
- `apps/api/src/api/routes/douyin_extension.py`
  - Endpoints:
    - `POST /douyin-extension/handshake`
    - `GET /douyin-extension/status`
    - `GET /douyin-extension/history`
    - `GET /douyin-extension/download`
    - `POST /douyin-extension/detect-page`
    - `POST /douyin-extension/capture-current-page`
    - `POST /douyin-extension/capture-session`
    - `POST /douyin-extension/harvest-plan`
    - `POST /douyin-extension/full-modal-harvest`
    - `POST /douyin-extension/capture-inbox/classify-targets`
    - `POST /douyin-extension/profile-video-classification`
- `apps/api/src/api/routes/capture_inbox.py`
  - Endpoints used by web/extension follow-up:
    - `GET /capture-inbox/sessions`
    - `GET /capture-inbox/sessions/{capture_session_id}`
    - `GET /capture-inbox/items`
    - `POST /capture-inbox/items/query`
    - `GET /douyin-extension/capture-sessions/{capture_session_id}/items`
    - `POST /capture-inbox/sessions/{capture_session_id}/actions`
- `apps/api/src/services/douyin_extension_capture_service.py`
  - Capture session/item persistence and full-modal harvest ingest service.
- `apps/api/src/services/capture_inbox_service.py`
  - Capture inbox list/query/action/promote logic.

### API Source Ingest Path

- `apps/api/src/api/routes/source_ingest.py`
  - `POST /source-profiles/ingest` accepts `SourceProfileIngestRequest` and returns `IngestSummaryResponse`.
  - List endpoints for crawl sessions, profiles, and profile videos.
- `apps/api/src/services/source_ingest_service.py`
  - Creates a `CrawlSession`, runs Douyin adapter, upserts `SourceProfile`/`SourceVideo`, records metric snapshots, and marks completed/failed.
- `apps/api/src/adapters/douyin.py`
  - Validates Douyin URL, extracts `user/{id}`, `sec_uid`, or `@handle`, normalizes raw payloads, and maps aweme/video data.

### Web UI

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - Shows capture inbox sessions/items and a diagnostic empty state mentioning `/douyin-extension/capture-sessions/{id}/items`.
- `apps/web/src/lib/api.ts`
  - Web API client functions for intake, extension status/history, capture inbox sessions/items/actions, Douyin accounts, etc.
- `apps/web/src/app/intake/page.tsx`
  - Renders `IntakePage`; source-ingest/intake path exists separately from extension Scan Profile.

## Request/Response Shapes Identified

- Source ingest request fields from `SourceIngestService.ingest_profile`:
  - `workspace_id`, `profile_url`, `source_platform`, `crawl_mode`, `adapter_payload_json`
- Source ingest response summary:
  - `crawl_session_id`, `status`, `source_profile_id`, `source_platform`, `submitted_profile_url`, `normalized_profile_identifier`, counts, `error_code`, `error_message`
- Extension full modal harvest request top-level allowed keys from local guard:
  - `schema_version`, `capture_session_id`, `run_id`, `profile_url`, `target_aweme_id`, `source_video_external_id`, `started_at`, `page`, `capture_context`, `items`, `progress`, `commit_policy`
- Capture session item list response includes:
  - `session_id`, `items_count`, `items`, `counts`

## Likely Scan Profile Failure Points

1. Content script / in-page scanner unavailable.
   - Evidence: scanner maps failures such as `scan_content_script_unavailable`, `scan_dom_probe_handler_missing`, `scan_dom_probe_timeout`, `legacy_scanner_message_handler_missing`.
   - The controller has a 30 second content script readiness timeout.
2. Douyin profile grid not ready or page is blocked.
   - Evidence: failure codes include `profile_grid_not_ready_timeout`, `douyin_login_required`, `douyin_checkpoint_required`, `login_or_captcha_blocked`, `no_videos_found`.
3. Legacy/new scanner path mismatch.
   - Evidence: code contains `SCAN_POST_PROBE_HANDOFF_PATCH = "bypassed_direct_legacy_scan_22C9Z10"`, forbidden legacy runner targets, and many legacy scanner failure mappings.
4. Backend/API auth or URL mismatch from extension.
   - Evidence: API routers are protected when `API_AUTH_REQUIRED=true`; extension client reports `backend_unreachable`, `cors_or_permission_blocked`, and `http_4xx_client_error`.
5. Payload schema guard rejects flush after scan/collect.
   - Evidence: extension local guard rejects disallowed top-level or secret-like fields before posting `/douyin-extension/full-modal-harvest`; backend returns 422/503 for schema/migration/capture persist failures.
6. Capture session exists but items are not created or UI filter hides them.
   - Evidence: `CaptureInboxPage.tsx` empty state says likely reasons are no finalized harvest payload, backend item creation failure, or current filter hides items.

## Ranked Root Cause Hypotheses

1. High probability: extension content script/scanner readiness failure on the active Douyin tab.
   - Supported by many dedicated error codes and controller timeout logic.
   - Next debugging should inspect extension popup state/debug details and background/content-script console logs.
2. High probability: Douyin page state issue: login, challenge, stale modal/profile URL, or grid not loaded.
   - Supported by explicit safety/checkpoint/grid-not-ready failure mapping.
   - Next debugging should reproduce on a clean loaded profile page with the user logged in and challenge-free.
3. Medium probability: API auth/base URL/CORS mismatch between extension and local API.
   - Supported by `API_AUTH_REQUIRED=true` default in production-like contexts and extension auth token bridge code in web `api.ts`.
   - Next debugging should confirm extension backend base URL and whether Authorization token is present when required.
4. Medium probability: scan succeeds but collection/flush fails due to payload guard or backend schema/migration mismatch.
   - Supported by extension guard and backend `_capture_error_status()` mapping schema/migration issues to 503.
   - Next debugging should inspect `/douyin-extension/full-modal-harvest` response and capture session debug endpoint.
5. Medium-low probability: API-only source ingest is being used expecting live Douyin fetch, but live fetch is disabled.
   - Supported by `DouyinProfileAdapter.fetch_profile()` error when no fetch client is injected and `douyin_enable_live_fetch=false` default.
   - Applies if the reported Scan Profile bug is actually the web intake/source ingest button rather than the extension popup.

## Recommended Fix Strategy

1. Clarify which `Scan Profile` button is failing: extension popup vs web intake.
2. Add/collect a single diagnostic run artifact: active tab URL, extension state, exact error code, API response status/body code, capture session ID if any.
3. If extension popup: first fix content script readiness and profile grid detection, then backend flush.
4. If web/API source ingest: decide whether the MVP path should use extension capture inbox or `/source-profiles/ingest`; avoid maintaining two competing intake paths.
5. Add a deterministic local test fixture for the failing path before changing behavior.

## What Was Not Done

- No real Douyin crawl was performed.
- No `.env` secret values were printed.
- No source code was functionally changed.
- No dev server was started.
