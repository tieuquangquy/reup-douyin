# Phase 22C-9Z-4C - Fix Runtime Post-Probe Dispatch

## Root cause

The 22C-9Z-4B runtime witness proved Chrome was running the new extension bundle, but it only proved route startup. It did not prove that the background-owned Scan Profile runtime:

1. read the persisted productive DOM Probe diagnostics,
2. evaluated the productive gate,
3. reached legacy scanner dispatch, or
4. preserved that handoff state through finalization.

That left a possible terminal state where the popup showed a completed productive probe, but final diagnostics still ended as `profile_scan_no_round_started` with `legacy_route_invoked = none` and no concrete `scan_no_round_reason`.

## Files changed

- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

## Runtime checkpoint fix

The background-owned Scan Profile path now records these checkpoints:

- `scan_post_probe_checkpoint_before_dom_probe`
- `scan_post_probe_checkpoint_after_dom_probe`
- `scan_post_probe_productive_gate_input`
- `scan_post_probe_productive_gate_result`
- `scan_post_probe_before_legacy_dispatch`
- `scan_post_probe_after_legacy_dispatch`
- `scan_post_probe_before_finalization`
- `scan_post_probe_after_finalization`

The productive gate input persists the raw DOM Probe values required for debugging:

- probe status
- grid readiness
- aweme count
- video-anchor count
- grid-card count
- scroll-container presence
- tab id
- scan run id

## Productive probe behavior

If the DOM Probe reports:

- `profile_dom_probe_status = completed`
- `profile_grid_ready = true`
- `aweme_id_count > 0`

then the background route marks:

- `scan_post_probe_productive_gate_result = productive`
- `legacy_route_invoked = yes`
- `legacy_scanner_route_invoked = yes`
- `legacy_scanner_message_type = DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3`

before sending the legacy scanner content-script message.

## Explicit failure classes

### Non-productive probe

The route returns `legacy_scanner_not_invoked_after_dom_probe` with one of:

- `dom_probe_not_completed_before_legacy_scanner`
- `dom_probe_grid_not_ready_before_legacy_scanner`
- `dom_probe_aweme_ids_missing_before_legacy_scanner`

### Productive probe without dispatch evidence

Finalization now surfaces:

- error: `productive_probe_legacy_dispatch_missing`
- `scan_no_round_reason = invariant_violation_productive_probe_without_legacy_dispatch`

This prevents an unexplained `profile_scan_no_round_started`.

### Legacy dispatch fails

The route keeps:

- `legacy_route_invoked = yes`
- `legacy_scanner_route_invoked = yes`

and records:

- `legacy_scanner_invocation_result = failed`
- `scan_no_round_reason = legacy_dispatch_failed:<reason>` or `legacy_scanner_failed:<reason>`

## Diagnostics display

Popup progress summary now surfaces:

- productive gate result
- timestamp before legacy dispatch
- timestamp after legacy dispatch

These sit beside the existing 22C-9Z-4B runtime witness fields.

## Tests

Regression coverage was updated to assert:

- productive-gate checkpoints exist,
- dispatch checkpoints exist,
- productive probe handoff sets legacy scanner fields,
- productive probe without dispatch becomes a concrete invariant failure,
- failed legacy scanner attempts preserve visible invocation diagnostics,
- watchdog stale-stage protection remains present.

Validation run:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Manual retest checklist

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Refresh the target Douyin profile tab.
3. Click `Scan Profile`.
4. Confirm the 22C-9Z-4B handoff witness is present.
5. Confirm `scan_post_probe_productive_gate_result`.
6. If productive, confirm legacy dispatch checkpoints and message type.
7. If dispatch is missing, confirm `scan_no_round_reason = invariant_violation_productive_probe_without_legacy_dispatch`.

## Remaining risk

This phase makes the runtime handoff deterministic and observable. If manual retest now reaches `legacy_route_invoked = yes` but still fails later, the next issue is inside the legacy scanner response or queue adapter output, not the post-probe dispatch bridge.
