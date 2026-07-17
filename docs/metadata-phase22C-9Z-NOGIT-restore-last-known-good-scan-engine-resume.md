# Phase 22C-9Z-NOGIT Restore Last-Known-Good Scan Engine Resume

## Current state

Phase 22C-9Z-NOGIT recovered the local source scanner rather than using git history or compiled-only code. Phase 22C-9Z-1 wires that recovered scanner into the real production Scan Profile path after DOM Probe.

## Old scanner found

- Source exists at `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`.
- Last-known-good function: `collectProfileCardsUntilStable(...)`.
- Phase wrapper: `legacyVerifiedProfileScanner22C9ZNoGit(...)`.
- Content script owns the DOM scanner call because the scanner requires page DOM access.

## Production lock for 22C-9Z-1

Production diagnostics are now locked to:

```text
legacy_verified_profile_scroll_scanner_22C9Z1
legacy_verified_target_queue_adapter_22C9Z1
```

The controller still routes through the canonical whole-profile adapter and classification path. DOM Probe remains diagnostic/preflight and fallback-only; it is not the production queue builder.

## Phase 22C-9Z-1 production-path audit

- Post-DOM-probe branch: `runScanProfileWorkflow(...)` calls `runtime.runPostPingProfileDomProbe22C9I(...)`, then `completeProfileVerify(...)` in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`.
- Production runtime receiver: `createBackgroundScanProfileRuntime(...).scanProfile(...)` in `apps/extension-douyin-capture/src/background.ts`.
- Legacy source import is in `apps/extension-douyin-capture/src/contentScript.ts`, not in `background.ts`, because `collectProfileCardsUntilStable(...)` must run in the page/content-script DOM context.
- The old branch used `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE` and did not stamp hard `legacy_scanner_*` sentinels, so diagnostics could show `Legacy route invoked = none`, `scanRounds = 0`, and `scan_queue_builder_used = none` even after DOM Probe completed.
- Phase 22C-9Z-1 fixes the branch by sending `DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z1`, stamping invocation diagnostics before and after the content-script call, and preserving the canonical verified-target queue adapter path.

## Files changed

- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase22C-9Z-NOGIT-restore-last-known-good-scan-engine-log.md`
- `docs/metadata-phase22C-9Z-NOGIT-restore-last-known-good-scan-engine-resume.md`

## Validation completed

```powershell
npm --workspace @reup-douyin/extension-douyin-capture run test
```

The test command completed successfully and ran the extension build as part of the script.

## Remaining validation commands

Run explicit standalone commands before final handoff if not already run in this session:

```powershell
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```
