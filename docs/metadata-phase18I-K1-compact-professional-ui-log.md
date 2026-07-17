# Phase 18I-K1 Log

## UI problems found from screenshots

- Calibration showed `calibrated`, but Next step still said `Calibrate 4 Points`.
- Test buttons were disabled by a stale calibration requirement.
- `Extract Next 10` looked too prominent before Test was complete.
- Save controls were too large before any extracted result existed.
- Connection and Quick Start repeated workflow text.
- Queue Preview was useful but took too much space in the main flow.
- Main popup still felt like a long technical console instead of a compact operator dashboard.

## Readiness inconsistencies fixed

- Added canonical `calibration_ready` to whole-profile readiness.
- `calibration_ready = true` when:
  - `state.calibration.status === "calibrated"`, or
  - `state.calibration.point_count >= 4`
- Dry-run enablement now uses `profile_scan_ready && calibration_ready`.
- Next action no longer recommends calibration when calibration is already valid.
- Extraction button remains locked until dry-run is ready in the default safe flow.

## Compact header/status bar

- Replaced long Connection summary rows in the main view with compact chips:
  - `Tab`
  - `API`
  - `Calibration`
  - `Profile`
  - `Safety`
- Kept API URL input and Reconnect button in a compact row.
- Moved raw connection rows to Debug Details.

## Stepper behavior

- Stepper is now a compact 4-step strip:
  - `Scan`
  - `Test`
  - `Extract`
  - `Save`
- Added operator-facing statuses:
  - `Done`
  - `Next`
  - `Locked`
  - `Running`
  - `Needs review`
  - `Failed`
- Screenshot-state behavior is now:
  - `Scan = Done`
  - `Test = Next`
  - `Extract = Locked`
  - `Save = Locked`

## One-primary-action rule

- Added one primary action button driven by `next_recommended_action`.
- Secondary buttons remain available, but the recommended duplicate action is hidden from the secondary row.
- Primary action routes to the existing handler for:
  - scan
  - calibrate
  - test
  - extract
  - create session
  - check save data
  - save one
  - save batch
  - resume

## Save flow collapsed rule

- If there are no extracted results:
  - Save section stays visible but locked
  - guided save rows stay hidden
  - main message: `Locked until extraction has results.`
- After extracted results exist:
  - save guidance and compact backend rows appear

## Queue preview collapsed rule

- Queue Preview now renders as a collapsed details block by default.
- It auto-opens only while extraction is running.
- Main progress no longer gives queue preview the same visual weight as stepper/cards.

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Remaining UI ideas

- Merge `Controls` into the workflow card when the popup has enough width.
- Add a compact session badge with a short session id in the Save card header.
- Add a tiny current-target badge in Queue Preview while extraction is running.
