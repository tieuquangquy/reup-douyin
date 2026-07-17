# Phase 21D-18 Scan Profile Navigation Resolver Log

## Summary

Phase 21D-18 fixes the Scan Profile entry path so the extension resolves a stable Douyin profile URL before starting the whole-profile scanner. The workflow now supports clean profile URLs, profile modal URLs, direct video pages with author profile links, and stored profile fallback URLs.

## Scope

Implemented only the Scan Profile navigation resolver and readiness behavior. This phase did not add crawler, video processing, scoring, database, queue, or publishing behavior.

## Files Changed

- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase21D-18-scan-profile-navigation-resolver-log.md`
- `docs/metadata-phase21D-18-scan-profile-navigation-resolver-resume.md`

## Active Scan Workflow Path

The active Scan Profile path remains:

1. Popup Scan Profile click.
2. `verifyWholeProfileFromPopup()`.
3. `runScanProfileWorkflow()`.
4. `verifyProfile()`.
5. Resolver/navigation/readiness gate.
6. `completeProfileVerify()`.
7. `scanWholeProfileTargets()`.
8. Classification and harvest queue preparation.

## Resolver Behavior

Added `normalizeDouyinProfileUrl()` to canonicalize Douyin profile URLs by preserving only the origin and `/user/<secUid>` path while removing query parameters and hashes.

Added `resolveTargetProfileUrlForScan()` with this return shape:

```ts
{
  ok: boolean,
  targetProfileUrl: string | null,
  source: "current_profile" | "modal_parent_profile" | "direct_video_author" | "stored_profile" | "none",
  needsNavigation: boolean,
  reason: string | null
}
```

Resolution priority:

1. Clean current profile URL: source `current_profile`, no navigation unless the visible URL has query/hash noise.
2. Current profile modal URL: source `modal_parent_profile`, navigation required.
3. Direct video URL with a discovered author link: source `direct_video_author`, navigation required.
4. Stored/queue/last successful profile URL fallback: source `stored_profile`, navigation required.
5. Otherwise unresolved: source `none`, reason `profile_url_unresolved`.

## Navigation Behavior

When the resolver requires navigation, Scan Profile now writes a running `navigating_to_profile` state, navigates to the resolved clean profile URL, waits for actual profile/grid readiness, and starts the scan only after readiness succeeds.

The scanner is not marked successful during navigation. While navigation/readiness is active, diagnostics keep the scanner action result as `running`.

## Timeout And Stale Behavior

Profile navigation/grid readiness now uses a 20 second maximum wait with 500ms polling. If navigation or grid readiness does not complete, the state fails with:

```txt
profile_navigation_or_grid_ready_timeout
```

The user-facing message is:

```txt
Could not open the profile page for scanning.
```

The pending-navigation resume path was also updated to use the same timeout code so stale modal/resume failures do not report the older `profile_navigation_timeout` code.

## Diagnostics Added

Scan Profile diagnostics now record:

- Scan start URL.
- Scan start page type.
- Resolved profile URL.
- Resolver source.
- Whether profile navigation was needed.
- Modal ID at scan start.
- Modal parent profile URL when applicable.
- Profile navigation status and errors.
- Profile readiness status and completion time.
- Scanner action/result/error state.

These diagnostics preserve the invariant that `phase = navigating_to_profile` cannot also imply scanner success.

## Tests Added Or Updated

Updated extension tests cover:

- Profile URL normalization from modal URLs with query/hash noise.
- Resolver output for clean profile URL.
- Resolver output for modal parent profile URL.
- Resolver output for direct video author profile link.
- Resolver stored profile fallback.
- Resolver unresolved direct video failure.
- Modal Scan Profile navigation/readiness/scan in the same workflow.
- Pending navigation resume timeout mapping to `profile_navigation_or_grid_ready_timeout`.
- Profile warmup timeout mapping to `profile_navigation_or_grid_ready_timeout`.

## Validation

Commands run successfully:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

The test command also runs the extension build and module resolution check as part of the workspace test script.
