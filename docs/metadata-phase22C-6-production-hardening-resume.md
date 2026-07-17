# Phase 22C-6 Production Hardening Resume

## Current phase

`22C-6 — Production hardening, final QA, operator-friendly diagnostics, and release readiness`

## Key files

- `apps/extension-douyin-capture/src/wholeProfileHarvest/hardening.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.hardening.test.ts`
- `apps/extension-douyin-capture/package.json`
- `docs/douyin-extension-release-readiness-checklist.md`

## Implemented behavior

- `normalizeScannerViewState(state)` repairs impossible display states and emits normalization diagnostics.
- `getOperatorStatusMessage(state)` returns Vietnamese operator-friendly message, level, next step, and diagnostics.
- `buildRunSummary(state)` derives the required run summary shape from canonical state and batch response diagnostics.
- `buildRecentItemResults(state)` returns at most 10 safe item summaries with no raw payloads.
- `classifyScannerError(error)` maps scanner/backend/safety failures into the requested categories.
- `buildExportRunReport(state)` returns a sanitized report that excludes tokens, cookies, headers, raw DOM/script, raw payloads, and secret-like fields.
- `evaluateCounterInvariant(state)` computes queue/new/incomplete/retry/already-collected counters from canonical queue state.
- Reset current run preserves calibration, settings, backend session, queue, results, and backend data.

## Resume checklist

1. Run full extension validation if not already complete:
   - `npm --workspace @reup-douyin/extension-douyin-capture run test`
   - `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
   - `npm --workspace @reup-douyin/extension-douyin-capture run build`
2. Manually verify Advanced diagnostics copy includes `hardening_diagnostics` and `export_report`.
3. Manually verify reset preserves queue/session and clears active run locks.
4. Manually retest captcha/checkpoint pause and resume messaging on a safe test profile.
