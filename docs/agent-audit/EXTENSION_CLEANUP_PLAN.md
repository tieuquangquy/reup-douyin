# Extension Cleanup Plan

## Safety posture

This is a staged cleanup plan for the Douyin Chrome extension. The current phase is audit/planning only. No runtime behavior should be changed until a separate implementation task starts with a rollback snapshot.

## Cleanup principles

- Protect the currently working path first.
- Quarantine before deleting.
- Prefer flags, comments, and route maps before code removal.
- Do not mix marker/test drift cleanup with scanner behavior changes.
- Do not change backend or web app code during extension cleanup.
- Do not change calibration semantics.
- Treat [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts), [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts), and [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts) as high-risk.

## Phase 3K reconciliation diagnostics and modal-open hardening completed

Phase 3K hardens the Phase 3J reconciliation and safe-batch collection paths without changing the working Scan Profile scanner/autoscroll path.

Completed changes:

- Added profile reconciliation diagnostics for ignored `modal_id` query parameters, profile-source error codes, and explicitly labelled session fallback in [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts).
- Treated `modal_navigation_timeout` as a recoverable safe-batch item error, preserving queue, calibration, capture session, current index, active task, and action lock while avoiding backend writes before modal/payload extraction succeeds.
- Added modal-open diagnostics including attempt count, strategy, expected/actual URL, timeout, retry/fallback flags, result, and recoverable skip status in [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts).
- Added the authoritative popup reconciliation helpers [`deriveAuthoritativeRunnerLock()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts), [`deriveAuthoritativeProfileCounters()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts), and [`sanitizePopupViewState()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts) in [`apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts).
- Added `isCollectionRunnerActive(state)` and canonical primary-action locking in [`apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts), now delegated through the authoritative runner lock and final primary-action sanitizer.
- Suppressed duplicate popup `Start Collecting` clicks before dispatch in [`apps/extension-douyin-capture/src/popup.ts`](../../apps/extension-douyin-capture/src/popup.ts), recording `duplicate_start_suppressed: "yes"`, `primary_action_locked_reason: "collection_running"`, and `primary_action_lock_source` without showing normal duplicate-click `Action blocked` copy.
- Stabilized active safe-batch progress copy in [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts) as `Collecting batch: {processed}/{selected_count} processed, {success_count} saved.` and sanitizes final popup view state immediately before render/export diagnostics.
- Made profile counters use `verify_response.items` and `verify_response.counts.captured` as popup counter authority, preventing `Profile already collected count` from reverting to stale `0` when backend profile counts/items prove captured videos; batch-only saved fields are ignored as total already-collected authority.
- Added focused controller/readiness/popup/view-model tests in [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts), [`apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts), [`apps/extension-douyin-capture/src/popupWorkflow.test.ts`](../../apps/extension-douyin-capture/src/popupWorkflow.test.ts), and [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts).
- Added the detailed implementation note in [`docs/agent-audit/PHASE_3K_RECONCILIATION_MODAL_OPEN_HARDENING.md`](PHASE_3K_RECONCILIATION_MODAL_OPEN_HARDENING.md).

Operational notes:

- A single `modal_navigation_timeout` is recoverable in safe-batch mode and should report `modal_open_recoverable_skip: "yes"` with `collect_backend_write_attempted: false`.
- Active collection must remain locked as `Collecting videos...` while fresh workflow state or recent batch heartbeat diagnostics indicate an active runner.
- Terminal `batch_safe_mode_completed` with pending items remains `Continue Next 10`; true paused/interrupted states remain `Resume`.
- `Profile already collected count` is driven by matched backend verification IDs through the profile counter contract; backend captured-vs-matched differences are explained through unmatched diagnostics, and stale scan summary overwrites are corrected by the final sanitizer.

## Phase 3J profile-level reconciliation and collecting UI completed

Phase 3J fixed the Reset / Refresh Profile `Already collected` mismatch by adding a safe same-profile Capture Inbox reconciliation source and stabilizing the active safe-batch collection primary action.

Completed changes:

- Added safe profile-level Capture Inbox item reconciliation through [`apps/api/src/api/routes/capture_inbox.py`](../../apps/api/src/api/routes/capture_inbox.py), [`apps/api/src/services/capture_inbox_service.py`](../../apps/api/src/services/capture_inbox_service.py), and [`apps/api/src/schemas/capture_inbox.py`](../../apps/api/src/schemas/capture_inbox.py).
- Wired the extension runtime/client and controller to prefer `/douyin-extension/capture-inbox/profile-items` before session fallback in [`apps/extension-douyin-capture/src/popup.ts`](../../apps/extension-douyin-capture/src/popup.ts) and [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts).
- Stabilized active collecting primary action wording and non-reentrancy in [`apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts).
- Added focused route/readiness/reconciliation tests in [`apps/api/tests/test_douyin_extension_routes.py`](../../apps/api/tests/test_douyin_extension_routes.py), [`apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts), and [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts).
- Added the detailed implementation note in [`docs/agent-audit/PHASE_3J_PROFILE_LEVEL_RECONCILIATION_AND_COLLECTING_UI.md`](PHASE_3J_PROFILE_LEVEL_RECONCILIATION_AND_COLLECTING_UI.md).

Operational note:

- The preferred diagnostics are `backend_reconciliation_source: capture_inbox_profile_items`, `backend_reconciliation_current_session_only: "no"`, and `backend_reconciliation_used_capture_inbox_card_source: "yes"`.

## Phase 3B context invalidated fix completed

Phase 3B addressed live extension reload/runtime invalidation and XHR response body guard failures without changing backend/API/web code, payload schema, calibration semantics, queue finalization, or canonical route ownership.

Completed changes:

- Added guarded content-script Harvest Runtime V2 storage access for extension context invalidation in [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts).
- Added safe XHR `responseText` guards in [apps/extension-douyin-capture/src/pageNetworkHook.ts](../../apps/extension-douyin-capture/src/pageNetworkHook.ts) and [apps/extension-douyin-capture/src/networkCache.ts](../../apps/extension-douyin-capture/src/networkCache.ts).
- Made ownerless stale running collection recovery display as paused/interrupted in [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts), without clearing queue or calibration.
- Updated focused source-text coverage in [apps/extension-douyin-capture/src/networkProbe.test.ts](../../apps/extension-douyin-capture/src/networkProbe.test.ts) and [apps/extension-douyin-capture/src/popupWorkflow.test.ts](../../apps/extension-douyin-capture/src/popupWorkflow.test.ts).
- Added the detailed fix note in [docs/agent-audit/EXTENSION_CONTEXT_INVALIDATED_FIX.md](EXTENSION_CONTEXT_INVALIDATED_FIX.md).

Operational note:

- If the extension is reloaded while a Douyin tab remains open, the old content script may be unable to use Chrome extension APIs. The expected operator recovery is to reload the Douyin tab, then scan again.

## Phase 0: baseline snapshot and verification

Files likely touched:

- Docs only.
- Optional temporary backup artifacts outside source tree if owner approves.

Allowed changes:

- Save current extension source snapshot.
- Record current build/test/manual validation results.
- Add checklist docs.

Forbidden changes:

- No runtime source edits.
- No storage clearing.
- No route renaming.
- No marker updates.

Acceptance criteria:

- Six audit docs exist under [docs/agent-audit](../agent-audit).
- Current protected flow is documented.
- Known tests/marker drift are documented as risks.

## Phase 1: add non-runtime route inventory comments/tests

Files likely touched:

- [docs/agent-audit/EXTENSION_CODE_PATH_MAP.md](EXTENSION_CODE_PATH_MAP.md)
- Potential focused tests only if no behavior changes are needed.

Allowed changes:

- Add comments identifying canonical vs legacy route ownership.
- Add tests that assert current route names and reset preservation.
- Add diagnostics documentation.

Forbidden changes:

- No handler removal.
- No action name changes.
- No storage key changes.

Acceptance criteria:

- Tests describe current behavior without forcing 22C12F/22C13A marker migration.
- Manual Scan Profile and Calibration still pass.

## Phase 2: quarantine UI-invokable legacy controls

Files likely touched:

- [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts)
- [apps/extension-douyin-capture/src/legacy/legacyGuard.ts](../../apps/extension-douyin-capture/src/legacy/legacyGuard.ts)
- [apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts](../../apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts)

Allowed changes:

- Ensure legacy buttons remain hidden/guarded.
- Add explicit debug-only gates for legacy diagnostic actions if needed.
- Improve labels/comments that direct users to Whole Profile Harvest.

Forbidden changes:

- Do not change primary Scan Profile dispatch.
- Do not change Start Collecting dispatch.
- Do not clear calibration/queue on legacy guard.

Acceptance criteria:

- Legacy UI routes cannot mutate canonical harvest state except Clear Legacy State.
- Clear Legacy State does not clear calibration.
- Popup primary action remains unchanged.

## Phase 3: quarantine storage migration risks

Files likely touched:

- [apps/extension-douyin-capture/src/storageKeys.ts](../../apps/extension-douyin-capture/src/storageKeys.ts)
- [apps/extension-douyin-capture/src/extensionReset.ts](../../apps/extension-douyin-capture/src/extensionReset.ts)
- [apps/extension-douyin-capture/src/legacy/legacyStateKeys.ts](../../apps/extension-douyin-capture/src/legacy/legacyStateKeys.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)

Allowed changes:

- Add explicit comments and tests around current vs legacy storage keys.
- Add dry-run summary for legacy state presence if not already present.
- Strengthen tests for reset scopes.

Forbidden changes:

- Do not rename keys.
- Do not remove legacy key cleanup until migration has been proven on real operator data.
- Do not change calibration key groups.

Acceptance criteria:

- Reset Harvest preserves calibration.
- Reset Calibration clears calibration only.
- Factory Reset clears both only after confirmation.
- Legacy state cannot overwrite canonical state silently.

## Phase 4: isolate diagnostics generations

Files likely touched:

- [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts)
- [apps/extension-douyin-capture/src/pageNetworkHook.ts](../../apps/extension-douyin-capture/src/pageNetworkHook.ts)
- [apps/extension-douyin-capture/src/networkProbe.test.ts](../../apps/extension-douyin-capture/src/networkProbe.test.ts)
- [apps/extension-douyin-capture/src/background.test.ts](../../apps/extension-douyin-capture/src/background.test.ts)

Allowed changes:

- Put 22C12A/22C12C/22C12D/22C12E/22C13A diagnostics behind explicit debug routes or documented flags.
- Separate passive diagnostics from active scanner routing.
- Fix stale tests only after deciding whether current canonical marker is 22C11B or future 22C13A.

Forbidden changes:

- Do not switch scanner engine during diagnostics cleanup.
- Do not disable passive network merge unless validated on real profile.
- Do not remove diagnostic routes needed for auto-scroll investigation.

Acceptance criteria:

- Current Scan Profile behavior is unchanged.
- Diagnostic routes cannot compete with canonical scan route.
- Marker naming is documented and tests align with actual route ownership.

## Phase 5: scanner route consolidation

Files likely touched:

- [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts)
- [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)

Allowed changes:

- Choose one canonical scan route name and keep compatibility aliases.
- Add explicit deprecation diagnostics for aliases.
- Keep queue adapter stable.

Forbidden changes:

- Do not remove compatibility route aliases in the first consolidation pass.
- Do not change stop reason strings consumed by popup/tests without migration.
- Do not hard-code expected count such as 46.

Acceptance criteria:

- Exactly one canonical implementation handles Scan Profile.
- Aliases forward to canonical implementation without separate state mutation.
- Manual profile scan queue counts remain stable or improve.

## Phase 6: legacy code deletion candidates

Files likely touched:

- TBD after two successful cleanup releases.

Allowed changes:

- Delete legacy code only after it is unreachable, tests cover canonical path, and rollback exists.

Forbidden changes:

- No deletion of state migration code until old operator storage has been migrated or intentionally abandoned.
- No deletion of diagnostics still used for current auto-scroll debugging.

Acceptance criteria:

- Removal PR/task includes before/after file map.
- Manual checklist passes.
- Recovery plan is documented.

## Rollback strategy because there is no Git

Before any implementation phase:

1. Copy the entire [apps/extension-douyin-capture/src](../../apps/extension-douyin-capture/src) directory to a timestamped backup outside the source tree or to a clearly named backup folder excluded from build.
2. Copy [docs/agent-audit](../agent-audit) to preserve audit context.
3. Record the exact files modified in the task response.
4. Run build/test/manual checks before and after.
5. If regression occurs, restore touched files from backup instead of attempting broad manual reversal.

## Recommended first safe implementation task

The safest first code cleanup task is not deletion. It is to add a small route ownership registry/comment block and focused tests that assert:

- Popup Scan Profile dispatch still targets the background canonical route.
- Background route aliases forward to the same scan implementation.
- Content minimal handler is the only active scanner implementation invoked by background.
- Reset Harvest preserves calibration.
- Legacy UI routes remain blocked/hidden.

This provides safety rails before any quarantine/removal work.

## Phase 1A completed

Files changed:

- [apps/extension-douyin-capture/src/routeOwnership.test.ts](../../apps/extension-douyin-capture/src/routeOwnership.test.ts)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Checks run:

- `npx tsx src/routeOwnership.test.ts` passed.
- `npx tsx src/extensionReset.test.ts` passed.
- `npm run typecheck` failed on pre-existing `background.test.ts` drift around `__testDerivePostProbeProductiveGate22C9Z5` and older `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` expectations; no Phase 1A runtime source was changed to address this because marker drift cleanup is out of scope.
- `npm run build` passed using the extension build configuration.

Behavior intentionally unchanged:

- No runtime source files were edited.
- Popup Scan Profile dispatch remains owned by the existing popup-to-background route.
- Background Scan Profile compatibility aliases remain documented as protected.
- Content minimal scanner handling remains documented as protected.
- Queue adapter and stop reason compatibility strings remain documented as protected.
- Calibration, reset/storage keys, Start Collecting dispatch, content scanner logic, auto-scroll behavior, backend, web, and API behavior remain intentionally unchanged.
- Marker drift between 22C11B and later 22C12F/22C13A diagnostics remains unresolved by design in this phase.

Remaining risks:

- Existing broad extension tests still include older 22C12F/22C13A expectations in some files; Phase 1A does not reconcile those expectations.
- Source-text route ownership tests guard accidental string/route removal but do not replace manual validation on a live Douyin profile.
- Legacy diagnostic routes and historical storage cleanup paths remain present and should not be deleted until later quarantine phases prove they are unreachable or safely guarded.

Next recommended phase:

- Proceed to Phase 1B only after focused checks pass. Phase 1B should quarantine UI-invokable legacy controls without changing primary Scan Profile, Start Collecting, calibration, reset, scanner, auto-scroll, backend, web, or API behavior.

## Phase 1B completed

Files changed:

- [apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts](../../apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Checks run:

- `npx tsx src/phase18aPopupCleanup.test.ts` initially caught one stale assertion in the newly added test text; the assertion was corrected to match the existing canonical background dispatch path.
- `npx tsx src/routeOwnership.test.ts` passed.
- `npx tsx src/extensionReset.test.ts` passed.
- `npx tsx src/phase18aPopupCleanup.test.ts` passed.
- `npm run build` passed using the extension build configuration and module resolution check.

Behavior intentionally unchanged:

- Runtime source was not changed.
- Popup Scan Profile dispatch remains on `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` through the canonical background dispatch path.
- Start Collecting dispatch remains on the canonical product workflow and does not call legacy modal extraction runners.
- Legacy background/content handlers and diagnostic modal scan senders were not removed or renamed.
- Content scanner logic, auto-scroll behavior, calibration behavior, collection behavior, backend payload schema, storage keys, reset scopes, backend, web, and API behavior remain unchanged.
- `background.test.ts` marker drift remains unresolved by design and was not edited.

Phase 1B verification added:

- Legacy UI/product feature flags for capture-current-page, smart capture, full-modal harvest, safe runner, CDP, and probe-modal routes are asserted disabled.
- Deprecated legacy popup feature names are asserted to return the disabled `legacy_feature_disabled` result from the legacy guard.
- Popup legacy smart capture, capture current page, full-modal flush, and retry-failed harvest event listeners are asserted to route through the legacy guard if present.
- Popup primary action dispatch mapping and handler slices are asserted not to reference forbidden legacy modal, harvest, capture, or CDP runner strings.
- Clear Legacy State calibration preservation remains asserted by checking legacy cleanup keys do not include calibration aliases.
- Canonical Scan Profile route strings from Phase 1A remain asserted in popup source.

Remaining risks:

- Phase 1B is source-text and focused unit verification; it does not replace manual validation against a live Douyin profile.
- Legacy diagnostic handlers and beta modal whole-profile test code remain present by design. They are verified as outside the primary popup action path, not deleted.
- Existing broad typecheck remains blocked by known pre-existing `background.test.ts` marker drift until a dedicated marker alignment phase.

Runtime source changed:

- No.

Next recommended phase:

- Proceed to Phase 1C after the remaining focused Phase 1B checks and extension build pass. Phase 1C should continue with test/docs-first quarantine work and should still avoid scanner, calibration, collection, backend, web, API, storage-key, and reset-scope changes unless a specific unsafe path is proven.

## Phase 1C completed

Files changed:

- [apps/extension-douyin-capture/src/extensionReset.test.ts](../../apps/extension-douyin-capture/src/extensionReset.test.ts)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Checks run:

- `npx tsx src/extensionReset.test.ts` passed after adding Phase 1C storage/reset quarantine assertions.
- `npx tsx src/routeOwnership.test.ts` passed.
- `npx tsx src/extensionReset.test.ts` passed.
- `npx tsx src/phase18aPopupCleanup.test.ts` passed.
- `npm run build` passed using the extension build configuration and module resolution check.

Runtime source changed:

- No.

Behavior intentionally unchanged:

- No runtime source files were edited.
- Storage keys were not renamed, added, removed, migrated, or cleared.
- Reset scopes were not changed.
- Calibration behavior, scanner behavior, auto-scroll behavior, collection behavior, backend payload schema, backend, web, API, Docker, and legacy handler names remain unchanged.
- `background.test.ts` marker drift remains unresolved by design and was not edited.

Storage/reset guarantees verified:

- `DOUYIN_SCANNER_STORAGE_ROOT_KEY` and `DOUYIN_SCANNER_CALIBRATION_KEY` remain distinct canonical scanner storage keys.
- `HARVEST_STATE_STORAGE_KEYS` does not include canonical scanner calibration keys or right-rail calibration aliases.
- `CALIBRATION_STATE_STORAGE_KEYS` includes the canonical right-rail calibration key, legacy right-rail calibration alias, canonical scanner calibration key, scanner storage-root calibration bridge, and current probe result key by current design.
- `FACTORY_RESET_LOCAL_STORAGE_KEYS` includes both harvest and calibration key groups only through explicit Factory Reset scope.
- `FACTORY_RESET_SYNC_STORAGE_KEYS` remains limited to `lastCaptureSessionId` and `lastCaptureId`.
- `LEGACY_STATE_KEYS` and Clear Legacy State removal do not include canonical scanner calibration keys or right-rail calibration aliases.
- Clear Legacy State removal is asserted to remove only the legacy quarantine key list and preserve calibration keys.
- Explicit storage key groups are asserted not to include secret-like key names such as token, authorization, cookie, password, or secret.
- Existing Reset Harvest coverage still verifies calibration preservation for right-rail calibration, canonical scanner calibration, and scanner storage-root calibration bridge.

Remaining risks:

- Phase 1C is focused source/runtime-independent test verification and does not replace manual validation against live operator storage.
- Legacy diagnostic handlers, legacy key lists, and migration/quarantine code remain present by design until a later deletion or migration phase proves they are safe to remove.
- Existing broad typecheck remains blocked by known pre-existing `background.test.ts` marker drift until a dedicated marker alignment phase.

Next recommended phase:

- Proceed to the next cleanup phase only after the remaining focused Phase 1C route/popup checks and extension build pass. The next phase should continue to avoid runtime scanner, calibration, collection, backend, web, API, storage-key, and reset-scope changes unless a specific unsafe path is proven and approved before editing.

## Phase 1D completed

Files changed:

- [docs/agent-audit/BACKGROUND_TEST_DRIFT_INVENTORY.md](BACKGROUND_TEST_DRIFT_INVENTORY.md)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Checks run:

- `npm run typecheck` was run once and failed as expected on documented `background.test.ts` drift:
  - Missing `__testDerivePostProbeProductiveGate22C9Z5` export.
  - Five stale `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` route literals.
- `npx tsx src/routeOwnership.test.ts` passed.
- `npx tsx src/extensionReset.test.ts` passed.
- `npx tsx src/phase18aPopupCleanup.test.ts` passed.
- `npm run build` passed.

Runtime source changed:

- No.

Summary of drift inventory:

- The missing productive-gate helper is a removed export / outdated test helper reference with a current equivalent named `__testDerivePostProbeProductiveGate22C11B`.
- The stale `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` message literals are old action names and are no longer part of the typed extension message union.
- The affected scan fixtures still model old 22C12F / 22C12B network-first probe and handoff behavior instead of the current 22C11B minimal active-works scanner path.
- Several assertion blocks expect old diagnostic markers such as `live_network_stream_profile_collector_22C12F` and `network_stream_queue_adapter_22C12D`; current protected equivalents are `minimal_active_works_grid_scanner_22C11B` and `scan_queue_adapter_22C11B`.
- Some count-reconciliation assertions encode old strict under-count and over-count failure behavior. Current runtime accepts any non-empty canonical queue and records count diagnostics, so those blocks require a product/test decision in a dedicated drift-fix phase.
- No inventory item proves a runtime regression. The current runtime source still accepts protected Scan Profile routes and dispatches the protected canonical content scanner.

Recommended next phase:

- Proceed to a dedicated background test-drift fix phase. That phase should edit `apps/extension-douyin-capture/src/background.test.ts` only unless a separate approved product decision requires runtime behavior changes. It should update test helpers/routes to 22C11B, rewrite the scan fixture around current canonical messages, and explicitly decide whether historical strict count-reconciliation assertions should be rewritten, quarantined, or restored through a separate runtime task.

## Phase 2A completed

Files changed:

- [apps/extension-douyin-capture/src/background.test.ts](../../apps/extension-douyin-capture/src/background.test.ts)
- [docs/agent-audit/BACKGROUND_TEST_DRIFT_INVENTORY.md](BACKGROUND_TEST_DRIFT_INVENTORY.md)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Runtime source changed:

- No.

Checks run:

- `npx tsx src/background.test.ts` passed.
- `npm run typecheck` passed.
- `npx tsx src/routeOwnership.test.ts` passed.
- `npx tsx src/extensionReset.test.ts` passed.
- `npx tsx src/phase18aPopupCleanup.test.ts` passed.
- `npm run build` passed.

Typecheck result:

- Passed. The pre-existing `background.test.ts` typecheck drift from removed `__testDerivePostProbeProductiveGate22C9Z5` and stale `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` literals is resolved in tests only.

Summary:

- `background.test.ts` now imports `__testDerivePostProbeProductiveGate22C11B`.
- Active Scan Profile tests now use `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` and current 22C11B trace metadata.
- The scan fixture now models the current protected route path: `DOUYIN_SCANNER_PING`, `DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B`, `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING`, `DOUYIN_PROFILE_DOM_PROBE_22C11B`, and `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B`.
- Stale 22C12F / 22C12D diagnostic expectations were aligned to `minimal_active_works_grid_scanner_22C11B`, `active_works_grid_22C11B`, and `scan_queue_adapter_22C11B`.
- Under-count and over-count cases were rewritten to match the current product decision: non-empty canonical queues are accepted as ready/success, while count mismatch details remain asserted as diagnostics.
- Malformed/null scanner response coverage remains failure-oriented and still verifies `canonical_scanner_completed_without_result` plus no queue adapter invocation.

Remaining risks:

- Phase 2A is test/docs-only and does not validate live Douyin auto-scroll behavior.
- Count reconciliation now asserts current permissive finalizer behavior; if strict expected-count enforcement becomes a product requirement later, that should be a separate approved runtime task.
- Historical network-first scanner behavior is no longer represented by these active background tests except as passive diagnostic fields.

Next recommended phase:

- After the remaining focused safety checks and build pass, it is safe to proceed to the auto-scroll discovery fix or further cleanup. Any auto-scroll work should remain a focused runtime task with the existing route ownership and reset/calibration safety rails in place.

## Phase 3A backend schema rejected investigation completed

Files changed:

- [docs/agent-audit/BACKEND_SCHEMA_REJECTED_INVESTIGATION.md](BACKEND_SCHEMA_REJECTED_INVESTIGATION.md)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Runtime source changed:

- No.

Checks run:

- `npm run typecheck` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `npm run build` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `python -m pytest tests/test_douyin_extension_routes.py -q` was attempted in [apps/api](../../apps/api) but could not run because the active Python environment does not have `pytest` installed (`No module named pytest`). No packages were installed.

Scope:

- Investigation and documentation only.
- Scanner, auto-scroll, calibration, queue finalization, backend schema, migrations, payload guard, web UI, and persistence behavior were not changed.
- Auto-scroll discovery was treated as already fixed and was not re-investigated.

Findings:

- `backend_schema_rejected` is assigned in the extension controller when a backend flush result has HTTP 422 and is not one of the explicitly special-cased 422 response codes.
- One-item Start Collecting sends `POST /douyin-extension/full-modal-harvest` with a `douyin_full_modal_harvest.v1` request containing `items: [item]`; it does not send a legacy bare single-item body.
- Static source inspection did not find a definitive schema mismatch between the current one-item builder and backend `DouyinExtensionFullModalHarvestRequest`.
- Backend accepts the current static `raw_dom_detail_metrics.extraction_source: "calibrated_point_dom"`, `confidence: "high"`, `raw_evidence_summary.evidence_collection_version: "phase11a_production_stabilized_calibrated_harvest"`, and `profile_card_evidence.aweme_id` shape.
- Extension-only `progress` extras are unlikely to be the 422 cause under the current Pydantic v2 default extra-field behavior because the relevant backend models do not configure `extra="forbid"`.
- A semantic mismatch exists: the extension local guard accepts `duration_text` when `duration_seconds` is null, while backend `finalized_only` creation requires `duration_seconds > 0` for missing/new Capture Inbox items. The inspected service records this as `finalized_metadata_required` in response summaries rather than raising Pydantic 422 by itself.

Evidence still needed:

- The live failed POST response body or API logs are required to distinguish FastAPI/Pydantic validation from service-layer 422.
- If API logs lack `full_modal_harvest_received`, the failure is Pydantic validation before service entry.
- If API logs include `full_modal_harvest_error`, copy its `error_code`, `stage`, `diagnostics_id`, and `capture_session_id`.
- If FastAPI returns validation detail, copy `detail[*].loc`, `detail[*].msg`, and `detail[*].type`.

Recommended next phase:

- Proceed to a targeted fix phase only after copying the redacted popup Details/API evidence listed in [docs/agent-audit/BACKEND_SCHEMA_REJECTED_INVESTIGATION.md](BACKEND_SCHEMA_REJECTED_INVESTIGATION.md). Likely fix targets are invalid live UUID/session handoff, datetime normalization such as `profile_card_evidence.posted_at`, controller classification for unrecognized service 422 codes, or duration-seconds alignment for `finalized_only`.

## Phase 3C backend 422 diagnostic capture completed

Files changed:

- [apps/extension-douyin-capture/src/extensionBackendClient.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [apps/extension-douyin-capture/src/extensionBackendClient.test.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.test.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest.backendFlow.test.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest.backendFlow.test.ts)
- [docs/agent-audit/BACKEND_422_DIAGNOSTIC_CAPTURE.md](BACKEND_422_DIAGNOSTIC_CAPTURE.md)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Runtime source changed:

- Yes, extension diagnostics only.
- No backend, web, worker, database, persistence, queue, scanner, auto-scroll, calibration, validation, retry, or payload semantic changes were made.

Summary:

- One-item `POST /douyin-extension/full-modal-harvest` request summaries now store redacted request-shape diagnostics instead of headers.
- Failed one-item backend responses now store redacted response summaries on harvest state and debug state.
- The popup Backend Flow can now show `Last flush response: available in Details` for failed one-item schema rejections.
- HTTP 422 classification remains `backend_schema_rejected` unless an existing special-case code applies.
- The extension still does not hide failures or retry differently.

Redaction guarantees:

- Headers are not stored in the one-item flush request summary.
- Secret-like keys such as cookies, authorization, auth tokens, credentials, passwords, API keys, raw headers, raw HTML, and raw DOM keys are filtered from diagnostic key lists.
- Response diagnostics store validation paths and backend code/message/detail summaries, not the full raw response text.
- Request diagnostics store shape, presence, type, and parseability information rather than full raw payloads.

Checks run in this phase:

- `npm run typecheck` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `npx tsx src/extensionBackendClient.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `npx tsx src/wholeProfileHarvest.backendFlow.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture) after correcting one assertion to read Backend Flow `details_rows`.
- `npx tsx src/background.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `npx tsx src/routeOwnership.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `npx tsx src/extensionReset.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `npx tsx src/phase18aPopupCleanup.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `npx tsx src/networkProbe.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `npx tsx src/popupWorkflow.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `npx tsx src/wholeProfileHarvest.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture) after preserving the existing safe-batch recoverable failure `one_item_flush.status` behavior while still storing response diagnostics.
- `npm run build` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).
- `python -m pytest tests/test_douyin_extension_routes.py -q` was attempted in [apps/api](../../apps/api) but could not run because the active Python environment does not have `pytest` installed (`No module named pytest`). No packages were installed.

Next recommended phase:

- Use the redacted popup Details evidence from [docs/agent-audit/BACKEND_422_DIAGNOSTIC_CAPTURE.md](BACKEND_422_DIAGNOSTIC_CAPTURE.md) to identify the actual rejected field/code before making any targeted fix.

## Phase 3D backend error details popup exposure completed

Files changed:

- [apps/extension-douyin-capture/public/popup.html](../../apps/extension-douyin-capture/public/popup.html)
- [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts)
- [apps/extension-douyin-capture/src/popupWorkflow.test.ts](../../apps/extension-douyin-capture/src/popupWorkflow.test.ts)
- [docs/agent-audit/BACKEND_422_DIAGNOSTIC_CAPTURE.md](BACKEND_422_DIAGNOSTIC_CAPTURE.md)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Runtime source changed:

- Yes, popup diagnostic UI only.
- No backend, schema, persistence, payload semantic, scanner, auto-scroll, calibration, queue, retry, route marker, or validation behavior was changed.

Summary:

- The Advanced `Payload and save details` section now includes `Copy Backend Error Details` when a redacted backend request/response diagnostic summary exists.
- The copied JSON is limited to `last_flush_request_summary`, `last_flush_response_summary`, `last_backend_response`, `debug_last_response_summary`, `top_failure`, `current_aweme`, `current_index`, and valid UUID `capture_session_id`.
- A short copyable preview renders below the button so the operator can inspect the same redacted details without relying only on the clipboard.
- Popup Details rendering now targets the dedicated `wholeProfileBackendDetailsContent` container so the new copy controls are not cleared by definition-list rendering.

Redaction guarantees:

- The popup export applies an additional denylist for `token`, `authorization`, `cookie`, `secret`, `password`, `headers`, `raw_html`, `raw_dom`, and `raw_response_text` keys.
- The popup export does not add raw payloads, raw response text, raw DOM, raw HTML, headers, cookies, tokens, or credentials.

## Phase 3E profile-safe capture session reuse completed

Files changed:

- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [apps/extension-douyin-capture/src/extensionBackendClient.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.ts)
- [apps/extension-douyin-capture/src/types.ts](../../apps/extension-douyin-capture/src/types.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [apps/extension-douyin-capture/src/extensionBackendClient.test.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.test.ts)
- [apps/extension-douyin-capture/src/popupWorkflow.test.ts](../../apps/extension-douyin-capture/src/popupWorkflow.test.ts)
- [docs/agent-audit/BACKEND_422_DIAGNOSTIC_CAPTURE.md](BACKEND_422_DIAGNOSTIC_CAPTURE.md)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Runtime source changed:

- Yes, Start Collecting capture-session handoff now verifies local session reuse by backend profile proof instead of UUID existence alone.
- Yes, extension backend error classification now preserves semantic `capture_session_not_found` and `capture_session_profile_mismatch` 422 codes.
- No backend, schema, persistence, scanner, auto-scroll, calibration, queue clearing, or backend mismatch loosening was changed.

Summary:

- Local `capture_session_id` reuse now requires the backend session list to include the session and prove it matches the current normalized profile URL or profile identifier.
- Query/hash parameters such as `modal_id` are stripped for session profile comparison.
- A backend session with missing/unverifiable profile ownership fails closed and is not reused.
- A backend session for another profile is discarded for the current run and replaced with a fresh session before `full-modal-harvest` is flushed.
- Stale-session handling records redacted diagnostics including `stale_session_discarded`, `stale_session_discard_reason`, shortened stale session id, profile signal, `session_reuse_blocked_reason`, and create/reuse status.
- Existing queue and calibration state are preserved when only the stale local session is discarded.
- Nested backend `detail.code`, `detail.stage`, and `detail.message` are surfaced in redacted response diagnostics so popup details can distinguish semantic capture-session failures from Pydantic schema validation.

Focused tests added/updated:

- Existing local session reuse succeeds only when backend profile proof matches.
- Existing local session with a different backend profile creates and uses a fresh session in the `full-modal-harvest` payload.
- Existing local session with missing backend profile fields fails closed and creates a fresh session.
- `modal_id` query parameters do not cause false profile mismatches.
- Repeated Start Collecting/safe-batch reuse tests now include backend profile proof.
- Semantic `capture_session_not_found` response mapping preserves backend code/stage, while validation-array 422 remains `http_422_schema_error`.
- Popup workflow source coverage now requires backend response diagnostics to preserve `backend_stage` alongside code/detail.

Checks run so far in this phase:

- `npx tsx src/extensionBackendClient.test.ts && npx tsx src/wholeProfileHarvest.test.ts` was run in [apps/extension-douyin-capture](../../apps/extension-douyin-capture); backend client tests passed, then the whole-profile test exposed a stale ID-only reuse expectation that was corrected.
- `npx tsx src/wholeProfileHarvest.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture) after updating profile-proof fixtures.

## Phase 3G Batch Continuation UX clarity completed

Files changed:

- [apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
- [apps/extension-douyin-capture/src/popupWorkflow.test.ts](../../apps/extension-douyin-capture/src/popupWorkflow.test.ts)
- [docs/agent-audit/PHASE_3G_BATCH_CONTINUATION_UX.md](PHASE_3G_BATCH_CONTINUATION_UX.md)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Runtime source changed:

- Yes, view-model display copy only.
- No scanner, auto-scroll, profile discovery, backend validation, payload schema, harvest item semantics, queue clearing, calibration clearing, pending clearing, session clearing, current-index reset, or Phase 3E profile-safe session verification behavior was changed.

Summary:

- The exact successful safe-batch continuation state now shows `Continue Next 10` instead of `Start Collecting`.
- The continuation message is `Batch complete: {saved_count} saved, {pending_count} remaining. Click Continue Next 10 to process the next batch.` with live counts.
- The action key remains `start_collecting`, and popup source coverage confirms the dispatch remains the existing `runWholeProfileHarvestProductFromPopup()` path.
- Resume remains reserved for paused/interrupted collection states and is not used for safe-batch continuation.
- No persistent diagnostics were added because this phase is display-only and additional storage writes would expand mutation surface unnecessarily.

Focused tests added/updated:

- Safe continuation state shows continuation copy and `Continue Next 10`.
- Safe continuation state keeps `start_collecting` and does not route through Resume.
- Queue, calibration, capture session, and current index are preserved in the UI state.
- Completed zero-pending and failed-with-top-failure states do not show continuation copy.
- Source tests assert the existing Start Collecting dispatch path remains unchanged.

## Phase 3H Backend Reconciliation and Pause Recovery completed

Files changed:

- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts)
- [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [docs/agent-audit/PHASE_3H_BACKEND_RECONCILIATION_AND_PAUSE_RECOVERY.md](PHASE_3H_BACKEND_RECONCILIATION_AND_PAUSE_RECOVERY.md)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Runtime source changed:

- Yes, Scan Profile completion now performs non-blocking Capture Inbox reconciliation for current-profile backend items.
- Yes, Start/Continue Collecting diagnostics now report backend write attempt/status/success/failure counts.
- Yes, stale non-resumable paused state is recovered/guarded so Resume is shown only for real resumable paused runs.
- No scanner discovery, auto-scroll, backend validation, `/douyin-extension/full-modal-harvest` payload schema, harvest item semantics, calibration clearing, queue clearing, or Phase 3E profile-safe session verification behavior was changed.

Summary:

- Backend reconciliation uses capture sessions/items already exposed through the extension runtime and restricts matches to sessions that prove the current profile.
- Item matching prefers `aweme_id` and falls back to backend item fields `source_video_external_id`, `video_external_id`, and `external_id`.
- Matched backend items become local `already_collected`/complete queue entries, so Reset -> Refresh Profile no longer reports all backend-existing videos as new.
- Reconciliation failure is non-blocking and is surfaced through redacted `backend_reconciliation_*` diagnostics.
- Pause/Resume display and dispatch now require `resume_available === true` before routing to Resume, and stale paused/no-resume state is recovered without clearing queue, calibration, or session state.

Focused tests added/updated:

- Controller source coverage for backend reconciliation diagnostics and hooks.
- Controller source coverage for collect backend write diagnostics.
- Readiness behavior for stale non-resumable paused state selecting Start/Continue Collecting instead of disabled Resume.
- Readiness selector marker expectations aligned with the current `22C-11B` canonical primary action selector.

Checks run so far in this phase:

- `npm run typecheck && npx tsx src/wholeProfileHarvest.readiness.test.ts && npx tsx src/wholeProfileHarvest.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).

## Phase 3I Capture Inbox reconciliation and payload sanitizer completed

Files changed:

- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [docs/agent-audit/PHASE_3I_RECONCILIATION_AND_PAYLOAD_SANITIZER.md](PHASE_3I_RECONCILIATION_AND_PAYLOAD_SANITIZER.md)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Runtime source changed:

- Yes, Scan Profile reconciliation now inspects all listed Capture Inbox sessions for the current profile and can include item-level same-profile proof from otherwise unverifiable sessions.
- Yes, one-item full-modal collect now records redacted sanitizer diagnostics after building the clean backend payload and before local guard/network flush.
- Yes, the clean payload builder normalizes the legacy metric alias `duration` into schema-required `duration_seconds` while preserving backend-required finalized metric fields under `raw_dom_detail_metrics`.
- No scanner discovery, auto-scroll, profile discovery, backend validation, `/douyin-extension/full-modal-harvest` schema semantics, calibration clearing, queue clearing, pending clearing, current-index reset, or Phase 3E profile-safe capture-session verification behavior was changed.

Summary:

- The Phase 3H count mismatch was caused by reconciliation only trusting sessions with session-level profile proof, while manual Capture Inbox data can include same-profile items in listed sessions whose session-level profile fields are incomplete.
- Reconciliation still fails closed for explicit mismatching session profile proof, but for unverifiable sessions it fetches session items and only counts backend items that prove the same profile at item level.
- Item matching still uses `aweme_id` as the queue match key, with backend item fallback extraction from `source_video_external_id`, `video_external_id`, and `external_id`.
- New redacted diagnostics include reconciliation source/scope, listed/total session counts, inspected session count, backend item count, matched count, unmatched backend count, and unmatched queue count.
- The local payload guard rejection was caused by legacy/raw metric aliases reaching guard-visible paths while the backend schema still requires finalized metrics under `raw_dom_detail_metrics`.
- The sanitizer does not weaken `guardNoSecretDebugLeakage`, `guardCanonicalHarvestPayload`, `guardCaptureInboxPayload`, or the backend client guard. It builds a clean DTO first, normalizes safe aliases, strips unsupported/debug/raw fields through the existing sanitizer, then runs the existing guards.
- Pause/Resume behavior remains the Phase 3H model: valid paused state keeps `resume_available: true`, stale non-resumable paused state is recovered, and queue/session/calibration/current target state is not cleared by this phase.

Focused tests added/updated:

- Controller source coverage for Phase 3I reconciliation diagnostics and item-level same-profile fallback.
- Controller source coverage for payload sanitizer diagnostics in the one-item collect path.
- Clean payload builder coverage for preserving schema-required finalized metrics and mapping legacy `raw_dom_detail_metrics.duration` to `duration_seconds` without logging values.

Checks run so far in this phase:

- `npm run typecheck && npx tsx src/wholeProfileHarvest.test.ts` passed in [apps/extension-douyin-capture](../../apps/extension-douyin-capture).

## Phase 3F Pause/Resume audit completed

Files changed:

- [docs/agent-audit/PHASE_3F_PAUSE_RESUME_AUDIT.md](PHASE_3F_PAUSE_RESUME_AUDIT.md)
- [docs/agent-audit/EXTENSION_CLEANUP_PLAN.md](EXTENSION_CLEANUP_PLAN.md)

Runtime source changed:

- No.
- This was an audit-only pass. Scanner, calibration, queue, backend client, popup runtime behavior, auto-scroll behavior, backend validation, and legacy code were not changed.

Summary:

- Audited Pause/Resume controller state transitions, safe-batch checkpoints, popup routing, stale lifecycle recovery, session reuse/reverification, queue/index/calibration preservation, UI behavior, and existing tests.
- Confirmed that normal safe Next 10 completion with pending items is intentionally `batch_safe_mode_completed` / idle and should continue through Start Collecting, not Resume.
- Confirmed Resume is reserved for actual paused/interrupted collection states and dispatches to the canonical safe Next 10 runner.
- Confirmed Resume and repeated Start Collecting reach the Phase 3E profile-safe capture-session verification path through canonical one-item save.
- Identified no P0 blocker for continuing collection after a successful 10-item safe batch.
- Ranked follow-up risks around UI clarity, cooperative pause semantics, footer pause/resume visibility, and legacy runner guardrails.
