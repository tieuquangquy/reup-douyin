# Phase 22C-9L Restore Full Profile Scroll Scan Resume

## Current behavior
Scan Profile now treats DOM Probe as a preflight signal and runs the existing full-profile scroll scanner before finalizing the canonical profile queue.

## Key files
- `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`: old full scroll scan engine and diagnostics.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`: 22C-9L scan contract and fallback routing.
- `apps/extension-douyin-capture/src/background.ts`: background-owned Scan Profile route/versioning.
- `apps/extension-douyin-capture/src/contentScript.ts`: DOM Probe trace version support.
- `apps/extension-douyin-capture/src/popup.ts`: popup diagnostics/version stamps only.

## Retest focus
1. Open a Douyin profile with more than the visible first grid.
2. Click Scan Profile.
3. Confirm diagnostics show multiple scan rounds and a stop reason from the full scanner, not `dom_probe_queue_built` unless fallback is explicitly used.
4. Confirm queue total reflects full scanner discovery and Next 10/Safe only affects Start Collecting pending selection.
