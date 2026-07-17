# Phase 20A UI Component Inventory

## Keep In Main Run Flow
- Header title and operator subtitle in [`popup.html`](apps/extension-douyin-capture/public/popup.html)
- Status strip and header chips in [`#headerStatusChips`](apps/extension-douyin-capture/public/popup.html)
- `Run` tab as the default operator surface in [`#wholeProfileTabPanelRun`](apps/extension-douyin-capture/public/popup.html)
- Primary action card in [`#wholeProfileNextActionCard`](apps/extension-douyin-capture/public/popup.html)
- Compact workflow stepper in [`#wholeProfileStepper`](apps/extension-douyin-capture/public/popup.html)
- Compact summary cards in [`#wholeProfileSummaryCards`](apps/extension-douyin-capture/public/popup.html)
- Compact settings in [`#wholeProfileHarvestMode`](apps/extension-douyin-capture/public/popup.html), [`#wholeProfileHarvestBatch`](apps/extension-douyin-capture/public/popup.html), and [`#wholeProfileHarvestSpeed`](apps/extension-douyin-capture/public/popup.html)
- Progress-saved mode toggle in [`#wholeProfileHarvestUnattendedSafeMode`](apps/extension-douyin-capture/public/popup.html)
- Run alert container in [`#wholeProfileRunAlert`](apps/extension-douyin-capture/public/popup.html)
- Core operator actions in [`#verifyProfileButton`](apps/extension-douyin-capture/public/popup.html), [`#dryRunRandomButton`](apps/extension-douyin-capture/public/popup.html), [`#runHarvestButton`](apps/extension-douyin-capture/public/popup.html), [`#resumeHarvestButton`](apps/extension-douyin-capture/public/popup.html), [`#stopHarvestButton`](apps/extension-douyin-capture/public/popup.html), and [`#resetWholeProfileHarvestButton`](apps/extension-douyin-capture/public/popup.html)
- Shortcuts to secondary surfaces in [`#wholeProfileViewResultsButton`](apps/extension-douyin-capture/public/popup.html) and [`#wholeProfileOpenTechnicalButton`](apps/extension-douyin-capture/public/popup.html)
- Short workflow hint in [`#wholeProfileQuickStartHint`](apps/extension-douyin-capture/public/popup.html)

## Move To Results
- Results dashboard shell in [`#wholeProfileTabPanelResults`](apps/extension-douyin-capture/public/popup.html)
- Save flow section in [`#wholeProfileBackendFlowSection`](apps/extension-douyin-capture/public/popup.html)
- Capture Inbox CTA in [`#wholeProfileCaptureInboxCta`](apps/extension-douyin-capture/public/popup.html)
- Queue preview in [`#wholeProfileQueuePreviewPanel`](apps/extension-douyin-capture/public/popup.html)
- Extraction results in [`#wholeProfileExtractionResultsSection`](apps/extension-douyin-capture/public/popup.html)
- Save outcomes / backend results in [`#wholeProfileBackendResultsSection`](apps/extension-douyin-capture/public/popup.html)
- Save action explanation and progress rows in [`#wholeProfileBackendFlowRows`](apps/extension-douyin-capture/public/popup.html)

## Move To Advanced
- Advanced tab shell in [`#wholeProfileTabPanelAdvanced`](apps/extension-douyin-capture/public/popup.html)
- API base URL and reconnect controls in [`#apiBaseUrl`](apps/extension-douyin-capture/public/popup.html) and [`#reconnectDouyinButton`](apps/extension-douyin-capture/public/popup.html)
- Calibration section and actions in [`#startCalibrationButton`](apps/extension-douyin-capture/public/popup.html), [`#showCalibrationButton`](apps/extension-douyin-capture/public/popup.html), and [`#clearCalibrationButton`](apps/extension-douyin-capture/public/popup.html)
- Expanded progress details in [`#wholeProfileProgressDetails`](apps/extension-douyin-capture/public/popup.html)
- Troubleshooting guide in [`#wholeProfileTroubleshootingPanel`](apps/extension-douyin-capture/public/popup.html)
- Safety tips guide in [`#wholeProfileSafetyTipsPanel`](apps/extension-douyin-capture/public/popup.html)
- Debug / maintenance details in [`#advancedDiagnostics`](apps/extension-douyin-capture/public/popup.html)
- Raw state summary in [`#detailSummary`](apps/extension-douyin-capture/public/popup.html)
- Advanced test controls in [`#modalWholeProfileTestPanel`](apps/extension-douyin-capture/public/popup.html)

## Keep Hidden For Compatibility
- Quick-start details container in [`#wholeProfileQuickStartPanel`](apps/extension-douyin-capture/public/popup.html)
  - Preserved for local UI preference compatibility.
  - Forced hidden/closed by popup rendering.
- Existing shortcut id [`#wholeProfileOpenTechnicalButton`](apps/extension-douyin-capture/public/popup.html)
  - Preserved for handler compatibility.
  - Visible label changed to `Advanced`.

## Delete Or Stop Rendering In Main Flow
- Old top-level `Technical` tab label
- Old standalone `Controls` section in Run
- Raw connection rows from Run
- Queue preview from Run
- Extraction result list from Run
- Save outcome list from Run
- Debug details from Run
- Payload guard wording from Run
- Flush wording from Run primary surface
- Legacy first/last dry-run actions from Run
- Legacy probe-only main action from Run
- Legacy V2/staged progress panels from popup markup

## Non-Goals
- No harvest logic changes.
- No controller workflow changes.
- No backend contract changes.
- No new product capabilities beyond the Phase 20A UI foundation reset.
