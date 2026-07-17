# Douyin Capture Runtime Schema Fix Log

## Scope

Fix the remaining true-system-failure path for `POST /douyin-extension/capture-current-page` after malformed item payload hardening.

## Current Findings

- Extension handshake and active-tab detection can succeed while capture still fails at the backend persistence boundary.
- Capture Inbox migration `0021_douyin_capture_inbox` defines `capture_sessions` and `captured_items`.
- SQLAlchemy models expect those tables and columns at runtime.
- The current route maps `DouyinExtensionCaptureError` and validation `ValueError` into structured HTTP details, but raw database/runtime failures can still escape as opaque HTTP 500.
- `CaptureInboxService.stage_extension_capture` currently persists `CaptureSession` before item processing, which is correct for partial payload resilience, but session persistence itself is not yet translated into a stage-specific operator error.

## Implementation Plan

1. Add first-use Capture Inbox schema readiness validation near the Capture Inbox service boundary.
2. Classify missing table and missing column/migration drift separately.
3. Wrap Capture Session creation failures as `capture_session_persist_failed` unless schema validation identifies `schema_missing` or `migration_mismatch` first.
4. Wrap Captured Item persistence failures as structured item-stage failures when the session can still be preserved.
5. Translate runtime schema/persistence failures into `DouyinExtensionCaptureError` with stage, code, message, and diagnostics id.
6. Ensure popup and manager display backend-provided structured details.
7. Add tests for schema missing, migration mismatch, session persistence failure, item persistence failure, and UI error projection.

## Non-Goals

- No crawler implementation.
- No video processing implementation.
- No queue/database redesign.
- No auto-publish integration.
- No direct browser automation changes.

## Verification Log

Pending implementation and test execution.
