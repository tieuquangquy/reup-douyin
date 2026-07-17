# Extension Legacy Quarantine Plan

## Goal

Prevent old scanner, harvest, probe, and state paths from competing with the canonical whole-profile flow while preserving compatibility and rollback safety.

Canonical protected flow:

`Popup Scan Profile -> background canonical scan -> content minimal active works scan -> queue adapter -> Calibration 4 Points -> Start Collecting -> canonical payload -> backend full-modal-harvest -> Capture Inbox`

## Legacy paths to quarantine

### Legacy harvest UI paths

Files:

- [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts)
- [apps/extension-douyin-capture/src/legacy/legacyGuard.ts](../../apps/extension-douyin-capture/src/legacy/legacyGuard.ts)

Plan:

- Keep legacy buttons hidden or blocked.
- Route any accidental click to the legacy guard.
- Do not let legacy UI controls start CDP, smart capture, old full-modal harvest, or old queue mutation.

Do not delete yet:

- Guard code.
- Tests proving legacy routes are disabled.

### Legacy scanner/handoff errors

Files:

- [apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)

Legacy error reasons still mapped include legacy_scanner_not_invoked_after_dom_probe, legacy_dispatch_failed, productive_probe_legacy_dispatch_missing, legacy_scanner_message_handler_missing, legacy_scanner_timeout, legacy_scanner_threw, legacy_scanner_zero_verified_targets, and legacy_queue_adapter_zero_output.

Plan:

- Keep mappings for diagnostic compatibility.
- Mark them as compatibility-only in docs/tests.
- Do not use them as active fallback route triggers.

Do not delete yet:

- Error mapping until no stored state/test/log consumer depends on it.

### Deprecated real modal extraction runner

Files:

- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)

Current safeguards:

- Allowed runner targets are explicit.
- Forbidden runner targets include runRealModalExtractionHarvest and legacy names.
- Migration sanitizes forbidden runner target diagnostics and can clear stale collect locks.

Plan:

- Keep blocked state migration.
- Ensure popup cannot dispatch forbidden runners.
- Add tests before removal.

Do not delete yet:

- Migration/recovery logic, because it protects stored operator state.

### CDP and old harvest runtime paths

Files:

- [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts)
- [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts)
- [apps/extension-douyin-capture/src/harvestRuntimeV2.ts](../../apps/extension-douyin-capture/src/harvestRuntimeV2.ts)
- [apps/extension-douyin-capture/src/flushQueue.ts](../../apps/extension-douyin-capture/src/flushQueue.ts)

Plan:

- Treat CDP/status helpers as legacy/debug unless proven used by current flow.
- Gate debug-only routes behind explicit debug flag or popup-hidden dev action.
- Keep reset cleanup for their storage keys.

Do not delete yet:

- Reset key cleanup.
- Any runtime code that current tests still assert.

### Passive network probe and pagination diagnostics

Files:

- [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts)
- [apps/extension-douyin-capture/src/pageNetworkHook.ts](../../apps/extension-douyin-capture/src/pageNetworkHook.ts)
- [apps/extension-douyin-capture/src/networkProbe22C12A.ts](../../apps/extension-douyin-capture/src/networkProbe22C12A.ts)

Generations observed:

- 22C12A passive network probe.
- 22C12C pagination reverse engineering.
- 22C12D live network stream runtime.
- 22C12E activation truth probe.
- 22C13A manual pagination verifier.

Plan:

- Separate diagnostic-only routes from active Scan Profile route in docs and tests.
- Do not allow diagnostic routes to mutate canonical harvest state.
- Keep passive network merge only if current scanner uses it as supplemental target source.

Do not delete yet:

- Auto-scroll diagnostics needed to debug remaining unscrolled-profile completeness issue.

## How to prevent legacy routes competing with canonical routes

1. Define one active route owner for Scan Profile in docs/tests.
2. Keep background aliases as forwarders only.
3. Ensure content diagnostic handlers never write whole profile harvest state directly.
4. Keep all state mutation for scan acceptance/finalization in background/controller-owned paths.
5. Ensure popup primary action cannot dispatch legacy route names.
6. Add diagnostic field route_owner with values canonical, compatibility_alias, or debug_only in a later implementation.

## Feature flags and debug-only gates

Potential future flags:

- REUP_EXTENSION_DEBUG_LEGACY_ROUTES=false by default.
- REUP_EXTENSION_DEBUG_PAGINATION_PROBES=false by default.
- REUP_EXTENSION_DEBUG_CDP=false by default.

Rules:

- Flags must default to safe/off for legacy routes.
- Flags must not be stored in a way that can be confused with calibration or harvest state.
- Debug routes must be read-only unless explicitly named as reset/clear with confirmation.

## Storage migration/quarantine strategy

Current key groups are in [apps/extension-douyin-capture/src/storageKeys.ts](../../apps/extension-douyin-capture/src/storageKeys.ts).

Plan:

- Keep legacy keys in reset cleanup lists.
- Add read-only legacy state summary before deletion.
- Do not migrate unknown legacy state into canonical queue unless validation passes.
- Keep controller migration that removes forbidden runner target diagnostics.
- Preserve calibration keys during harvest reset.

Current vs legacy distinction:

- Current: whole profile harvest state, scanner calibration keys, backend session state, safe harvest runtime used by protected flow.
- Legacy: old CDP status/debug, old target queues, old pending/retry/failed queues, smart capture state, old rightRailCalibration alias.

## What not to delete yet

- Legacy guards.
- Legacy state key lists.
- Reset cleanup for legacy storage keys.
- Forbidden runner migration/recovery.
- Scanner failure code compatibility mappings.
- Passive network probe merge until real-profile scan behavior is verified without it.
- Pagination diagnostics while auto-scroll completeness remains a known issue.

## Quarantine acceptance criteria

- Canonical Scan Profile remains the only route that can build the active queue.
- Legacy/debug routes either do nothing, return diagnostics, or are guarded.
- Legacy storage cannot overwrite canonical state without explicit migration logic.
- Reset Harvest preserves calibration.
- Manual stable baseline checklist passes.
