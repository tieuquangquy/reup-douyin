# Extension Risk Register

| Risk | Impact | Probability | Detection method | Mitigation |
|---|---:|---:|---|---|
| Scan Profile route alias changed or removed accidentally | High | Medium | Popup Scan Profile no longer starts, accepted state missing | Keep DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B and DOUYIN_SCANNER_START_SCAN_PROFILE aliases until tests/manual validation prove migration |
| Content minimal scanner disabled while no replacement is active | High | Medium | Background scan times out or returns no targets | Protect DOUYIN_SCAN_PROFILE_MINIMAL_22C11B in [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts) |
| Queue finalization caps scan queue to next 10 | High | Medium | Known profile produces 10 pending instead of 46 | Preserve all-profile queue finalization diagnostics in [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts) |
| Calibration cleared by harvest reset | High | Medium | After Reset Harvest, calibration ready becomes no | Preserve key separation in [apps/extension-douyin-capture/src/storageKeys.ts](../../apps/extension-douyin-capture/src/storageKeys.ts) and tests in [apps/extension-douyin-capture/src/extensionReset.test.ts](../../apps/extension-douyin-capture/src/extensionReset.test.ts) |
| Legacy state overwrites canonical state | High | Medium | Old runner target appears in active_runner_target or action lock stays collect_videos | Keep migration sanitization in [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts) |
| Marker/test drift causes false confidence or false failures | Medium | High | Tests expect 22C12F/22C13A while runtime reports 22C11B | Separate marker alignment task from cleanup; document actual active route before updating tests |
| Debug/pagination probe mutates state unexpectedly | Medium | Medium | Scan diagnostics change after running probe-only route | Gate diagnostic routes and assert they are read-only |
| Passive network probe removal reduces target discovery | Medium | Medium | Unscrolled scan finds fewer targets; network target count drops to zero | Do not remove network probe merge until real-profile A/B validation |
| Backend guard loosened during cleanup | High | Low | Payload includes debug/secrets or backend rejects with guard error | Protect [apps/extension-douyin-capture/src/extensionBackendClient.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.ts) and [apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts) |
| Popup primary action selector conflicts with controller state | High | Medium | Popup shows wrong primary action or Start Collecting blocked unexpectedly | Add tests around primary action and state readiness before cleanup |
| Action lock not released after failed scan/collect | Medium | Medium | Popup remains busy or action disabled | Verify workflow.active_task and workflow.action_lock clear on terminal states |
| Removing legacy error codes breaks stored diagnostics/tests | Low | Medium | Tests fail or old stored state displays unknown errors | Keep compatibility mappings until after migration window |
| Reset controls become too easy to trigger | High | Low | Operator loses queue/calibration/session | Keep confirmation prompts and separated reset scopes |
| Source file size/complexity hides duplicate handlers | Medium | High | Search shows multiple route strings or duplicate message listeners | Maintain code path map; use targeted tests before edits |
| Auto-scroll completeness regresses | High | Medium | Known unscrolled/manual-scrolled delta worsens | Preserve current scroll constants and diagnostics; use manual checklist |
| Storage quota compaction drops useful queue evidence | Medium | Medium | Queue remains but thumbnails/captions disappear from preview | Keep compaction minimal; monitor storage_budget diagnostics |
| Backend session readiness confused with collection completion | Medium | Low | UI reports success before item saved | Preserve distinct session_verified and backend save diagnostics |
| Forbidden runner accidentally re-enabled | High | Low | active_runner_target shows runRealModalExtractionHarvest or legacy runner | Keep assertAllowedScannerRunnerTarget and forbidden target set |
| Cleanup deletes reset cleanup for legacy keys | Medium | Medium | Legacy keys persist and later interfere | Keep legacy key lists until final deletion phase |
| No Git rollback available | High | High | Regression hard to reverse | Create timestamped backup before implementation; modify small file sets only |

## Highest-priority mitigations

1. Add tests/route registry before deleting or renaming routes.
2. Keep compatibility aliases for Scan Profile.
3. Keep Reset Harvest calibration preservation tests green.
4. Do not mix marker alignment with scanner behavior cleanup.
5. Manually validate the known 46-item profile after every cleanup phase.

## Current top conflicts found

- Active runtime diagnostics report 22C11B minimal active works scanner, while some tests/search hits expect 22C12F/22C13A network-first authority.
- Multiple generations of diagnostics/probes coexist in [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts).
- Background owns active scan state mutation while controller also has scan workflow abstractions; ownership must remain clear.
- Reset logic spans popup, extension reset module, storage key groups, and controller reset helpers.
- Legacy runner code still exists but is guarded/migrated; deleting it too early could break stored-state recovery.
