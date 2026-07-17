# Phase 21D-0 Root Replace Control Panel Log

## Scope

Implemented Phase 21D-0 only: prove the actual extension popup root and replace the old visible main card-stack screen with a new ScannerControlPanel-style root.

## Popup root proof

- Confirmed `apps/extension-douyin-capture/public/manifest.json` declares `action.default_popup` as `popup.html`.
- Added a root confirmation comment in `apps/extension-douyin-capture/public/popup.html`.
- Added the required TypeScript source comment in `apps/extension-douyin-capture/src/popup.ts` immediately before `ScannerControlPanel`.

## Main UI replacement

- Replaced the old `scanner-*` main visible card-stack with `#scannerControlPanelRoot.scp-shell`.
- The main screen now uses only `scp-*` layout classes for the root/control-panel surface.
- Kept Results and Advanced as separate overlay panels.
- Preserved existing control IDs needed by popup handlers.

## View model

Added `ScannerControlPanelViewModel` and `getScannerControlPanelViewModel(state)` in `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`.

Action priority implemented:

1. calibration needed -> `calibrate`
2. profile not scanned -> `scan_profile`
3. profile scanned and queue exists while not running -> `start_collecting`
4. running -> `pause`
5. paused -> `resume`
6. fallback -> `open_capture_inbox`

## Tests

Updated static and view-model tests to assert:

- Manifest popup root is `popup.html`.
- Phase 21D-0 root confirmation comments exist.
- Main root is `#scannerControlPanelRoot.scp-shell`.
- Main layout uses `scp-*` classes.
- Old main card-stack/classes are not present on the main screen.
- Forbidden old texts are removed from the main screen.
- Existing handler wiring remains in `popup.ts`.
- New control-panel view model is exported, imported, and used by the popup renderer.

## Validation

Ran `npm --workspace @reup-douyin/extension-douyin-capture run test`; it passed and includes the extension build and dist module resolution checks in that workspace script.
