# Phase 22C-3B Secret/Debug Leakage Fix Resume

## Current status

Phase 22C-3B implementation is in progress in the extension only. Backend service code was audited but not changed.

## Implemented areas

- Clean Capture Inbox item DTO builder in `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`.
- Capture Inbox payload sanitizer and diagnostics in `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`.
- Local secret/debug leakage guard in `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`.
- One-item save path now builds and validates clean payload before backend save in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`.
- Safe batch mode treats secret/debug/schema failures as recoverable item failures and continues unless stop policy triggers.
- Recent per-item diagnostics are tracked during safe batch mode.
- Regression assertions were added to `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`.

## Follow-up checklist

- Run full extension test suite, typecheck, and build.
- Confirm final test assertions for safe batch recoverable behavior.
- Confirm backend acceptance of root `capture_session_id` with the existing backend secret marker list.
- If backend guard still rejects required session fields, align the backend guard allowlist in a separate backend-scoped fix.

## Manual retest

1. Load the rebuilt extension.
2. Open a verified Douyin profile with at least 10 pending targets.
3. Run Safe Batch Next 10 from the popup.
4. Confirm no item fails with backend secret/debug leakage.
5. Confirm failed recoverable items checkpoint as retry/failed recoverable without being marked saved.
6. Confirm Advanced diagnostics remain visible locally but are absent from backend payloads.
