# metadata-phase18I-J6-operator-guide-in-ui-resume.md

## Current Step
- Phase 18I-J6 implementation is in the verification stage for the whole-profile popup operator guide and contextual help UI in [`apps/extension-douyin-capture`](apps/extension-douyin-capture).

## Done
- Re-read constraints in [`AGENTS.md`](AGENTS.md).
- Audited popup insertion points across [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html), [`apps/extension-douyin-capture/public/popup.css`](apps/extension-douyin-capture/public/popup.css), [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts), and [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts).
- Added Quick Start, troubleshooting, safety tips, disabled-reason helper, and Capture Inbox CTA surfaces in [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html).
- Added operator-guide and helper styling in [`apps/extension-douyin-capture/public/popup.css`](apps/extension-douyin-capture/public/popup.css).
- Added structured operator help and contextual action text generation in [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts).
- Added popup-local collapsed-panel preference handling and contextual help rendering in [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts).
- Updated tests in [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts) and [`apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts).
- Logged implementation details in [`docs/metadata-phase18I-J6-operator-guide-in-ui-log.md`](docs/metadata-phase18I-J6-operator-guide-in-ui-log.md).

## In Progress
- Final validation of the popup/operator-help changes.

## Next Exact Task
- Run extension verification commands from the workspace root:
  - `npm --workspace @reup-douyin/extension-douyin-capture run test`
  - `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
  - `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Key Files
- [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html)
- [`apps/extension-douyin-capture/public/popup.css`](apps/extension-douyin-capture/public/popup.css)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts)
- [`docs/metadata-phase18I-J6-operator-guide-in-ui-log.md`](docs/metadata-phase18I-J6-operator-guide-in-ui-log.md)
