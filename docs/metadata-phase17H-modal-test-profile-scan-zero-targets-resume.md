# Phase 17H Modal Whole Profile Test zero-target scanner resume

## Completed

- Added Phase 17H diagnostic types and scanner helpers in `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`.
- Fixed harvest-plan payload construction to import `HarvestPlanRequestPayload` from `requestPayloads.ts` and use the existing `RawDomSnapshot` shape.
- Wired the popup beta path to:
  - navigate from modal URL to resolved profile URL,
  - wait until `modal_id` is absent,
  - scan profile cards before harvest-plan,
  - fail zero-card scans before backend submission,
  - submit refresh-all harvest-plan payloads only after cards exist,
  - keep production Smart Capture and Safe Harvest state untouched.
- Added source-level extension tests for Phase 17H scanner/navigation/coverage/isolation requirements.

## Verification commands

Run from the repository root on Windows:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Expected manual behavior

Given a modal URL shaped like `https://www.douyin.com/user/{profile_id}?modal_id={aweme_id}`, the beta test should resolve and navigate to `https://www.douyin.com/user/{profile_id}` before profile scanning. If the profile has visible videos, the test should report `total_cards_found > 0` and then call the harvest-plan endpoint with schema `douyin_extension_harvest_plan.v1` and `refresh_all` coverage. If no cards are discovered, the test should fail with a diagnostic reason rather than reporting profile scan success with zero targets.

## Non-goals preserved

- No backend-wide changes.
- No Tile Gallery changes.
- No calibrated metric extraction changes.
- No CDP/debug workflow changes.
- No visible Capture Inbox item creation from verify-only zero-card scans.
- No full modal harvest start or flush in verify-only mode.
