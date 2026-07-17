# Phase 17X V2 Failure Diagnostics Resume

## Scope

Phase 17X only: hard diagnostics and fail-point tracing for Whole Profile Staged Harvest V2.

## Changed area

- `apps/extension-douyin-capture/src/popup.ts`

## Implemented status

Implemented in popup V2 flow:

- Added V2 diagnostics state fields and trace model.
- Added capture-session lifecycle traces and request/response previews.
- Added hard capture-session preflight guard before target loop.
- Added payload preview and capture_session_id validation guard.
- Added flush start/success/failure traces and structured failure classification.
- Added V2 panel diagnostics rows including fail stage/reason, backend diagnostics, payload checks, and debug JSON snapshot.
- Updated popup failure banner to include `fail_stage` and `fail_reason`.

## Known verification notes

- Extension typecheck/tests/build pass.
- API `compileall` passes.
- API requested unittest command currently fails due to backend rejection of `payload.capture_session_source` as secret-like field in existing full-modal service tests.

## Next work (if continuing)

1. Decide whether backend should formally allow `capture_session_source` in full-modal payload preflight secret guard.
2. If backend is touched for Phase 17X echo fields, add route/service/schema updates and corresponding API tests.
3. Re-run required API unittest command after backend alignment.
