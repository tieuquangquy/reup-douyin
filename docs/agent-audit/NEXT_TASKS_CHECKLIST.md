# Next Tasks Checklist

## P0: Must Fix Before Core Flow Works

- [ ] Title: Confirm canonical import path
  - Why it matters: The codebase has both extension capture inbox and API source ingest; MVP needs one reliable path.
  - Files likely involved: `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`, `apps/api/src/api/routes/source_ingest.py`, `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`, `apps/web/src/components/intake/IntakePage.tsx`
  - Acceptance criteria: Owner and code agree whether Scan Profile means extension whole-profile harvest or web/API source ingest; non-canonical path is labelled fallback/dev.
  - Risk level: High

- [ ] Title: Reproduce Scan Profile with diagnostics
  - Why it matters: Current bug cannot be safely fixed without exact error code/stage.
  - Files likely involved: `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`, `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`, browser extension console, API logs
  - Acceptance criteria: One failing run captured with active URL, extension state, error code, backend status/body, capture session ID if created.
  - Risk level: High

- [ ] Title: Fix content script/profile scanner readiness path
  - Why it matters: Highest-probability blocker is scanner/content-script/grid readiness.
  - Files likely involved: `apps/extension-douyin-capture/src/contentScript.ts`, `apps/extension-douyin-capture/src/background.ts`, `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`, `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
  - Acceptance criteria: On a loaded Douyin profile, Scan Profile returns validated targets or a precise user-action error for login/challenge/no videos.
  - Risk level: High

- [ ] Title: Verify backend auth/base URL from extension
  - Why it matters: Extension requests can fail independently of scanning due to API auth/CORS/base URL.
  - Files likely involved: `apps/extension-douyin-capture/src/extensionBackendClient.ts`, `apps/web/src/lib/api.ts`, `apps/api/src/core/settings.py`, `apps/api/src/main.py`
  - Acceptance criteria: Extension health check succeeds against local API; protected routes include Authorization when required; errors are visible in popup.
  - Risk level: Medium

- [ ] Title: Validate capture session item creation after scan/collect
  - Why it matters: Scan may succeed but UI remains empty if payload flush or item creation fails.
  - Files likely involved: `apps/api/src/api/routes/douyin_extension.py`, `apps/api/src/services/douyin_extension_capture_service.py`, `apps/api/src/api/routes/capture_inbox.py`, `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - Acceptance criteria: After a successful scan/collect, `/douyin-extension/capture-sessions/{id}/items` returns persisted items visible in Capture Inbox.
  - Risk level: High

## P1: Important For MVP

- [ ] Title: Add deterministic Scan Profile regression fixture
  - Why it matters: Prevents repeated breakage while avoiding live Douyin in tests.
  - Files likely involved: `apps/extension-douyin-capture/src/wholeProfileHarvest.*.test.ts`, `apps/api/tests/fixtures/douyin_profile_payload.json`, `apps/api/tests/test_douyin_extension_routes.py`
  - Acceptance criteria: A failing scenario is reproduced in tests and passes after the fix.
  - Risk level: Medium

- [ ] Title: Make empty-state diagnostics actionable in Capture Inbox
  - Why it matters: Operator needs to know if scan, collect, flush, item creation, or filters failed.
  - Files likely involved: `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`, `apps/api/src/api/routes/capture_inbox.py`
  - Acceptance criteria: Empty state shows last session status, item counts, failure code, and direct next action.
  - Risk level: Low

- [ ] Title: Move long-running live ingest toward job model
  - Why it matters: Architecture says crawls should not run inside HTTP request handlers.
  - Files likely involved: `apps/api/src/services/source_ingest_service.py`, `apps/api/src/api/routes/source_ingest.py`, `apps/worker/src/runtime.py`, `apps/api/src/models/jobs.py`
  - Acceptance criteria: New crawl request creates a durable job/session and UI can poll status.
  - Risk level: Medium

- [ ] Title: Normalize profile URL/sec_uid handling across extension and API
  - Why it matters: Mismatched profile identity causes duplicates, failed classification, or wrong session lookup.
  - Files likely involved: `apps/api/src/adapters/douyin.py`, `apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts`, `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`
  - Acceptance criteria: Same Douyin profile URL variants resolve to one canonical identifier in both systems.
  - Risk level: Medium

## P2: Quality/Improvement

- [ ] Title: Consolidate Douyin docs into one current operator guide
  - Why it matters: Existing docs are extensive and phase-heavy; operators need the current happy path.
  - Files likely involved: `docs/browser-connect-local-setup.md`, `docs/releases/*`, `docs/agent-audit/*`
  - Acceptance criteria: One guide explains setup, extension install, scan, collect, capture inbox, promote, and troubleshooting.
  - Risk level: Low

- [ ] Title: Add startup health page or doctor output for Scan Profile dependencies
  - Why it matters: Missing Playwright/browser/auth/API state should be visible before scanning.
  - Files likely involved: `scripts/dev-doctor.ps1`, `apps/api/src/api/routes/operations.py`, `apps/web/src/app/ops/health/page.tsx`
  - Acceptance criteria: Doctor checks API, DB, auth mode, extension package, Playwright install, and relevant Douyin env flags.
  - Risk level: Low

- [ ] Title: Reduce legacy scanner paths
  - Why it matters: Legacy/new scanner naming increases bug probability.
  - Files likely involved: `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`, `apps/extension-douyin-capture/src/legacy/*`
  - Acceptance criteria: One allowed scanner runner path remains for product use; legacy paths are test-only or removed after approval.
  - Risk level: Medium

## P3: Later/Optional

- [ ] Title: Productionize distributed worker/queue
  - Why it matters: Needed for SaaS scale, not first local MVP.
  - Files likely involved: `apps/worker/src/runtime.py`, `docker-compose.yml`, `apps/api/src/models/jobs.py`
  - Acceptance criteria: Redis-backed durable queue, retries, idempotency, cancellation, progress events.
  - Risk level: High

- [ ] Title: Complete real media processing pipeline
  - Why it matters: Core product ultimately needs rewrite/TTS/subtitle/text-cover/render export.
  - Files likely involved: `apps/api/src/audio_analysis`, `apps/api/src/tts_pipeline`, render modules, worker handlers
  - Acceptance criteria: Selected video can move through processing checkpoints to an export artifact.
  - Risk level: High

- [ ] Title: SaaS hardening
  - Why it matters: Needed before multi-user/hosted deployment.
  - Files likely involved: auth, tenancy models, Docker/deploy config, storage abstraction, compliance docs
  - Acceptance criteria: Tenant isolation, secure secret handling, billing/auth plan, compliance posture.
  - Risk level: High
