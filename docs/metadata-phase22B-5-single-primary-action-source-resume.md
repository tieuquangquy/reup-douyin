# Phase 22B-5 Resume — Single source of truth for primary action

## Completed
- Canonical calibration readiness helper finalized in [`apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts).
- Canonical primary-action selector consumed by:
  - [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
  - [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- Start Collecting preflight diagnostics updated in [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts).
- Regression coverage added in:
  - [`apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts)
  - [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
  - [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)

## Intent preserved
- Only one canonical selector should determine scanner primary action.
- The scanner UI and advanced diagnostics must report the same primary action.
- Canonical calibration readiness must win over conflicting legacy calibration flags.
- Start Collecting preflight or backend-session failures must not fall back to Calibrate.
- Dispatch must remain action-key based.

## Remaining work
- Run:
  - [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json)
  - [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json)
  - [`npm --workspace @reup-douyin/extension-douyin-capture run build`](apps/extension-douyin-capture/package.json)
- If any failures appear, fix only Phase 22B-5 regressions without broadening scope.

## Notes
- Popup import BOM removal was a user-side formatting change only.
- Controller diagnostics intentionally preserve the difference between calibration blocking and backend-session blocking.
