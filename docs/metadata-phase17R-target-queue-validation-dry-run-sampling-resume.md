# Phase 17R Target Queue Validation And Dry-run Sampling Resume

## Current Phase

Phase 17R adds target queue validation and dry-run sampling options for the isolated Modal Whole Profile Test runtime.

## Files Changed

- `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `docs/metadata-phase17R-target-queue-validation-dry-run-sampling-log.md`
- `docs/metadata-phase17R-target-queue-validation-dry-run-sampling-resume.md`
- `docs/metadata-phase17R-target-validation-operator-guide.md`

## Behavior To Preserve

- `target_count` must count accepted video targets only.
- Rejected candidate diagnostics must remain visible in the Modal Whole Profile Test panel.
- Dry-run modes must sample accepted targets only.
- Specific IDs mode must ignore IDs not found in the accepted queue and fail with no dry-run targets if none match.
- Dry-run must continue writing only `douyinModalWholeProfileTestRun`.
- Dry-run must not call `/douyin-extension/full-modal-harvest`.

## Validation Rules

Candidates are accepted only when they are numeric 16-22 digit strings, not timestamp-like, and tied to video context from a video link, modal link, data attribute inside a recognized video card, or card-context regex. Body regex-only candidates and footer/legal/license/contact contexts are rejected.

## Retest Focus

1. Run Verify only on a profile from a modal URL.
2. Confirm `Total candidates`, `Accepted targets`, and `Rejected` display.
3. Confirm suspicious values such as `202605050200442800701` appear under rejected examples with `likely_timestamp` or are excluded from accepted targets.
4. Run each dry-run mode and confirm only accepted target IDs are opened.
