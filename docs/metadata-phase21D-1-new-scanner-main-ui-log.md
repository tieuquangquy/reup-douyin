# Phase 21D-1 — New scanner main UI log

## Goal

Replace the extension popup main Run screen with a visibly new scanner-first surface for the **Douyin Profile Scanner** while preserving the existing collection workflow logic, results surface, and advanced technical tools.

## Scope used in this phase

This phase only changes the popup main-screen presentation layer:

- new scanner-first popup shell
- new scanner summary cards
- new scanner footer actions
- new scanner view-model mapping
- existing Results and Advanced content kept behind overlay panels
- test coverage updates for the new surface

## Explicit non-goals

- no scanner logic rewrite
- no collect/extract pipeline rewrite
- no backend/API contract change
- no new review route
- no queue/data model change
- no removal of existing working handlers unless they were only old main-screen wiring

## Files touched

- [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html)
- [`apps/extension-douyin-capture/public/popup.css`](apps/extension-douyin-capture/public/popup.css)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)

## Main UI replacement outcome

The popup main screen now renders a scanner-specific shell instead of the older deck-style Run surface.

The new main screen contains:

- header
- connection status chips
- profile scan summary
- scan plan summary
- one primary action card
- progress strip
- footer actions

The main shell now uses scanner-specific class names and IDs such as:

- `scanner-shell`
- `scannerHeaderStatus`
- `scannerChipTab`
- `scannerProfileMetrics`
- `scannerPlanMetrics`
- `scannerPrimaryActionButton`
- `scannerProgressLabel`
- `scannerOpenCaptureInboxButton`
- `scannerOpenAdvancedButton`

## View-model change

Added [`getDouyinScannerMainViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:1127) to derive the scanner-first popup state from the existing whole-profile harvest state.

The view model now maps:

- health chips from current tab/API/calibration/safety state
- profile counts from verified/profile-scan data
- plan counts from queue/planned/extracted/saved data
- primary action from existing readiness/action state
- progress copy from current collecting/pause/save state
- footer actions for Capture Inbox, pause/resume, Advanced, and reset

## Runtime wiring change

The popup renderer now calls [`renderDouyinScannerMainScreen()`](apps/extension-douyin-capture/src/popup.ts:836) from the main whole-profile render flow.

Scanner footer actions reuse existing popup handlers rather than introducing new workflow logic.

Current main-screen behavior keeps:

- primary action on existing whole-profile action orchestration
- Results behind the existing relocated results overlay
- Advanced behind the existing advanced overlay
- reset on the existing whole-profile reset flow

## Styling change

The main-screen CSS was replaced from old deck-shell styling to scanner-prefixed styling.

Added scanner-specific styling for:

- shell
- header
- status chips
- summary cards
- primary action
- alert state
- progress strip
- footer action layout

Existing relocated results and advanced panel styles remain available through the retained `deck-panel` overlay styles.

## Acceptance direction

This phase moves the popup closer to the intended operator mental model:

1. Scan profile
2. Start collecting
3. Pause or resume if needed
4. Open Capture Inbox for review

The review destination remains the existing Capture Inbox route established in Phase 21A.
