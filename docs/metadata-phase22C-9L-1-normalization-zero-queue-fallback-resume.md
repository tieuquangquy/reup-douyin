# Phase 22C-9L-1 Normalization Zero Queue Fallback Resume

## Current Status

Phase 22C-9L-1 repairs Scan Profile queue building when DOM Probe reports aweme/video counts but the full-scroll scanner produces zero normalized candidates.

## Files Changed

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`
- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `docs/metadata-phase22C-9L-1-normalization-zero-queue-fallback-log.md`
- `docs/metadata-phase22C-9L-1-normalization-zero-queue-fallback-resume.md`

## Key Behavior To Preserve

- Do not alter Start Collecting, Pause, Resume, Reset, backend flush, modal extraction, Capture Inbox, Review Board, calibration, or collection runners.
- DOM Probe candidate arrays are capped at 500.
- The fallback queue builder is stamped as `dom_probe_known_good_fallback_22C9K`.
- Fallback from normalization zero uses `scan_fallback_reason = "full_scroll_normalization_zero"`.
- Aweme-ID-only candidates synthesize `source_url = "https://www.douyin.com/video/" + aweme_id`.
- Queue fallback success clears scanner failure fields and sets profile scan readiness.

## Validation Checklist

Run these from the repository root:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

Manual retest should open a Douyin profile, run Scan Profile, and verify that DOM Probe counts greater than zero produce `profile_normalized_count > 0`, `profile_queue_total_count > 0`, pending count greater than zero, `scan_queue_builder_used = dom_probe_known_good_fallback_22C9K` if fallback is used, and no generic `profile_scan_failed` on fallback success.
