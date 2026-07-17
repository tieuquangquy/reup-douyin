# All-Failing Aweme Checkpoint Trace Log

## Scope

Trace only these three real failing aweme IDs:

- `7628281732369796388`
- `7631223404342857006`
- `7628596519502892307`

This is not a pass-vs-fail comparison. There is no confirmed passing baseline for this task.

## Goal

Identify the first missing checkpoint for each field group:

- Posted: `posted_at`, `posted_text`
- Duration: `duration_seconds`, `duration_text`
- Counts: `view_count`, `like_count`, `comment_count`, `share_count`

## Checkpoints

1. Extension pre-canonical source bundle before `buildCanonicalVideoPayload()`.
2. Extension canonical payload after `buildCanonicalVideoPayload()`.
3. Backend staged item in `CaptureInboxService._build_item()`.
4. Capture Inbox API response exposure.
5. Frontend Tile Gallery / inspector render.

## Non-goals

- Do not implement the permanent metadata fix.
- Do not broad-refactor extension, API, or web code.
- Do not redesign UI.
- Do not add unrelated diagnostics.
- Do not assume a passing baseline.

## Implementation Plan

1. Select the exact three target IDs above.
2. Keep trace instrumentation ID-gated to those IDs.
3. Reuse existing checkpoint 1-3 one-shot summary where possible.
4. Add only narrow checkpoint 4 and checkpoint 5 exposure if current code cannot prove those stages.
5. Run syntax/build checks for touched files only.
6. Collect live evidence from the next real capture.
7. Fill the evidence tables below.
8. Report the cross-item first missing checkpoint and the narrowest next fix boundary.

## Evidence Status

Current status: instrumentation ready; pending live evidence.

Checkpoint 1-3 instrumentation has been retargeted from the older debug IDs to the three failing IDs above. Checkpoint 4 API response logging and checkpoint 5 frontend render logging were added as narrow ID-gated diagnostics. No real capture evidence has been collected yet in this task, so all field-level checkpoint values below remain evidence-missing until the next live capture.

## Per-Aweme Evidence Tables

### Aweme `7628281732369796388`

| Checkpoint | Posted | Duration | Counts | Evidence source | Status |
|---|---|---|---|---|---|
| 1. Extension pre-canonical | Pending | Pending | Pending | Extension console / injected raw metadata | Pending evidence |
| 2. Extension canonical | Pending | Pending | Pending | Extension console / injected raw metadata | Pending evidence |
| 3. Backend staged item | Pending | Pending | Pending | Backend one-shot summary | Pending evidence |
| 4. API response | Pending | Pending | Pending | Capture Inbox response log | Pending evidence |
| 5. Frontend render | Pending | Pending | Pending | Browser console render trace | Pending evidence |

### Aweme `7631223404342857006`

| Checkpoint | Posted | Duration | Counts | Evidence source | Status |
|---|---|---|---|---|---|
| 1. Extension pre-canonical | Pending | Pending | Pending | Extension console / injected raw metadata | Pending evidence |
| 2. Extension canonical | Pending | Pending | Pending | Extension console / injected raw metadata | Pending evidence |
| 3. Backend staged item | Pending | Pending | Pending | Backend one-shot summary | Pending evidence |
| 4. API response | Pending | Pending | Pending | Capture Inbox response log | Pending evidence |
| 5. Frontend render | Pending | Pending | Pending | Browser console render trace | Pending evidence |

### Aweme `7628596519502892307`

| Checkpoint | Posted | Duration | Counts | Evidence source | Status |
|---|---|---|---|---|---|
| 1. Extension pre-canonical | Pending | Pending | Pending | Extension console / injected raw metadata | Pending evidence |
| 2. Extension canonical | Pending | Pending | Pending | Extension console / injected raw metadata | Pending evidence |
| 3. Backend staged item | Pending | Pending | Pending | Backend one-shot summary | Pending evidence |
| 4. API response | Pending | Pending | Pending | Capture Inbox response log | Pending evidence |
| 5. Frontend render | Pending | Pending | Pending | Browser console render trace | Pending evidence |

## Cross-Item Summary

| Field group | Do all 3 fail at same checkpoint? | First missing checkpoint | Evidence status |
|---|---|---|---|
| Posted | Unknown | Unknown | Pending evidence |
| Duration | Unknown | Unknown | Pending evidence |
| Counts | Unknown | Unknown | Pending evidence |

## Instrumentation Added

- Checkpoint 1 and 2 target IDs retargeted in `apps/extension-douyin-capture/src/popupTransport.ts`.
- Checkpoint 3 target IDs retargeted in `apps/api/src/services/capture_inbox_service.py`.
- Checkpoint 4 API response log added in `apps/api/src/api/routes/capture_inbox.py` with marker `targeted_aweme_checkpoint4_api_response`.
- Checkpoint 5 frontend render log added in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` with marker `[targeted-aweme-checkpoint5-frontend-render]`.
- Extension dist output regenerated so the unpacked extension artifact contains the three real failing IDs.

## Verification

- `python -m compileall apps/api/src/services/capture_inbox_service.py apps/api/src/api/routes/capture_inbox.py` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed.
- Search confirmed `apps/extension-douyin-capture/dist/popupTransport.js` contains `7628281732369796388`, `7631223404342857006`, and `7628596519502892307`.

## Narrowest Next Fix Boundary

Evidence-missing. The current narrow boundary is live evidence collection only: run one real capture with the rebuilt extension and inspect the checkpoint markers. No metadata fix boundary should be chosen until the first missing checkpoint is proven for all three target aweme IDs.
