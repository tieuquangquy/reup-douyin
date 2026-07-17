# Phase 21D-0 Root Replace Control Panel Resume

## Completed

- Confirmed the actual extension popup root through `apps/extension-douyin-capture/public/manifest.json` -> `action.default_popup: "popup.html"`.
- Replaced the old visible popup main card-stack in `apps/extension-douyin-capture/public/popup.html`.
- Added the required `// 21D-0 POPUP ROOT CONFIRMED` source comment in `apps/extension-douyin-capture/src/popup.ts`.
- Added `ScannerControlPanel` in `apps/extension-douyin-capture/src/popup.ts`.
- Added `ScannerControlPanelViewModel` and `getScannerControlPanelViewModel(state)` in `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`.
- Replaced old main `scanner-*` layout CSS with `scp-*` control-panel CSS in `apps/extension-douyin-capture/public/popup.css`.
- Preserved existing scanner/backend/extraction/save logic and handler wiring.
- Kept Results and Advanced overlay panels separate from the main screen.
- Updated tests for root proof, `scp-*` layout, forbidden main text, existing controls, and view-model action priority.

## Validation already run

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
  - The workspace test script also ran its build step and dist module resolution test.

## Remaining if work resumes

- Run the explicit standalone commands requested by the phase if not already run after this note:
  - `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
  - `npm --workspace @reup-douyin/extension-douyin-capture run build`
- Prepare final report using exactly the requested eight sections.

## Manual retest focus

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Open the browser action popup on a Douyin profile.
3. Confirm the main screen shows the new compact `scp-*` control panel, not the old card-stack.
4. Confirm the primary action changes by state: calibrate, scan, start collecting, pause, resume, or open Capture Inbox.
5. Confirm Capture Inbox opens Results overlay and Advanced opens Advanced overlay.
6. Confirm Reset, Pause/Resume, and settings selects still operate through existing handlers.
