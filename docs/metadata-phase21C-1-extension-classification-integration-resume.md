# Phase 21C-1 — Extension Classification Integration Resume

## Current status

Phase 21C-1 adds extension-side integration with `POST /douyin-extension/profile-video-classification` immediately after whole-profile scan candidate discovery.

## Key files

- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileClassification.ts`
  - Classification request/response types.
  - Request builder.
  - Classification application to scan targets.
  - Collect queue and preview builders.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
  - Durable classification state and normalization defaults.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
  - Calls the new profile classification runtime method after scan.
  - Stores classification state.
  - Builds harvest queue from backend `collect === true` targets.
- `apps/extension-douyin-capture/src/popup.ts`
  - Runtime API client method for `/douyin-extension/profile-video-classification`.
  - Scanner counter rendering includes `Need retry`.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
  - Collection gating requires classification success and non-empty queue.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
  - Scanner counts use classification totals/counts after classification success.

## Validation focus

Run these from the repository root:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Manual retest checklist

1. Open a Douyin profile with candidate videos.
2. Open the extension popup and confirm backend base URL is configured.
3. Click `Scan Profile`.
4. Confirm the backend receives `POST /douyin-extension/profile-video-classification` with schema `douyin_profile_video_classification.v1`, `collection_mode: new_incomplete_failed`, `include_unknown: false`, and `dry_run: true`.
5. Confirm popup counts map from the backend classification response.
6. Confirm `Start Collecting` is enabled only when classification succeeds and queue count is greater than zero.
7. Confirm a successful classification with zero collect targets shows `No new or incomplete videos to collect.`
