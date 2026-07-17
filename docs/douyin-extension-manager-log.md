# Douyin Extension Manager Implementation Log

## Goal

Implement a full backend/web-app Extension Manager for the Douyin browser extension so operators can install it, verify connection, detect the current page, capture the current page, and inspect extension status/history from one place.

## Required Route

Chosen route: `/ops/extensions/douyin`.

Reason: the manager is an operational control center and fits the existing Ops Console route namespace while remaining focused on the Douyin extension workflow.

## Initial Plan

1. Re-read `AGENTS.md` and audit current extension/backend/web implementation.
2. Create mandatory manager docs before code changes.
3. Add backend manager status/history support around existing setup/detect/capture endpoints.
4. Add web Extension Manager page and route.
5. Add focused tests and run verification.
6. Update docs and report final status.

## Audit Notes

- Existing setup page: `/setup/douyin-extension`.
- Existing setup page covers install guidance and status only.
- Existing backend setup endpoints:
  - `POST /douyin-extension/handshake`
  - `GET /douyin-extension/status`
  - `GET /douyin-extension/download`
- Existing backend capture endpoints:
  - `POST /douyin-extension/detect-page`
  - `POST /douyin-extension/capture-current-page`
- Existing extension popup can handshake, detect, and capture from the current active tab.
- Existing backend capture service uses canonical ingest/candidate pipeline and rejects secret-like payload keys.
- Missing backend history endpoint and unified manager page.

## Implementation Notes

- Added manager history schemas for safe, compact extension events.
- Extended the setup service with process-local Phase 1 manager history capped at 20 newest events.
- Added `GET /douyin-extension/history` with a `limit` query parameter.
- Recorded handshake, detect success/failure, and capture success/failure in manager history.
- Kept existing detect/capture processing on the canonical extension capture service and canonical downstream ingest/candidate pipeline.
- Added a dedicated web manager route at `/ops/extensions/douyin`.
- Added web API helpers and TypeScript contracts for status, history, detect, and capture manager operations.
- Added an Extension Manager page with install/setup, connection status, current-page tools, capture, troubleshooting, and history sections.
- Added Ops Console navigation, breadcrumbs, English/Vietnamese labels, and route-nav coverage for the manager route.

## Verification

Commands run successfully:

```text
npm --workspace @reup-douyin/web run typecheck
```

```text
npx tsx src/test/route-nav.test.ts
```

```text
py -m unittest tests.test_douyin_extension_setup_service tests.test_douyin_extension_capture_service
```

```text
npm --workspace @reup-douyin/web run test
```

## Final Status

Implemented and verified. The manager is available at `/ops/extensions/douyin`; extension installation remains manual in Chrome/Edge, while the backend/web app now owns setup guidance, connection/version visibility, detect/capture controls, recent history, and troubleshooting guidance around the existing extension workflow.
