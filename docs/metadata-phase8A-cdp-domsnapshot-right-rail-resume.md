# Phase 8A CDP DOMSnapshot Right-Rail Extractor Resume

## Resume point

Phase 8A implementation is complete enough for targeted modal harvest tests and extension typecheck to pass.

The active source of truth is the extension package:

- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`

## What changed

### CDP transport

`background.ts` handles `REUP_DOUYIN_CDP_DOM_SNAPSHOT`, calls `Page.getLayoutMetrics`, calls `DOMSnapshot.captureSnapshot`, and returns a typed viewport/text-entry payload to the content script.

### Normal Probe

Normal Probe now treats missing snapshot as a blocking failure. It does not pass from old fallback action metrics.

Expected no-snapshot behavior:

- `probe_status = "FAIL"`
- `blocking_reason = "cdp_snapshot_unavailable"`
- action counts are `null`
- source is not a legacy fallback

Expected snapshot success behavior:

- `probe_status = "PASS"`
- `ready_for_full_harvest = true`
- source is `cdp_dom_snapshot_right_rail`
- all four action metrics and video duration are present

### Full Modal Harvest

`FullModalHarvestController.bootstrapCurrentItem()` and the normal harvest loop now pass `getCdpDomSnapshot` into `waitForCurrentModalMetrics()`.

`waitForCurrentModalMetrics()` only returns an item payload when the snapshot extractor source is `cdp_dom_snapshot_right_rail` and duration plus all four action metrics are present.

### Tests

`modalHarvest.test.ts` was updated so controller tests provide CDP DOMSnapshot callbacks where they expect a harvested item or backend flush path. Old normal Probe fallback expectations were changed to no-snapshot FAIL while direct legacy extractor tests remain available for diagnostic coverage.

## Verification already run

Both commands completed with exit code 0:

```text
npx tsx apps/extension-douyin-capture/src/modalHarvest.test.ts
npm run typecheck --workspace apps/extension-douyin-capture
```

## Recommended next verification

Run the full extension test script before final release if time permits:

```text
npm test --workspace apps/extension-douyin-capture
```

This script also builds the extension and runs distribution module resolution checks.

## Live validation checklist

1. Build or load the updated extension.
2. Open Douyin and navigate to a modal video.
3. Use the popup to attach CDP.
4. Run Probe.
5. Confirm `PASS` and source `cdp_dom_snapshot_right_rail`.
6. Confirm popup diagnostics show snapshot text count, compact label count, right-rail region, and selected snapshot labels.
7. Start Full Modal Harvest.
8. Confirm only PASS items are harvested and flushed.
9. Confirm backend progress still reports pending/flushed/updated counts correctly.
10. Confirm repeated flush remains idempotent.

## Important implementation note

Direct calls to `extractCurrentModalMetricsForAweme(document, awemeId)` without the snapshot parameter still exercise legacy extraction paths for focused tests and debug diagnostics. Normal Probe and Full Modal Harvest explicitly pass a snapshot value (`null` when unavailable), which disables those legacy sources in normal Phase 8A operation.

## Potential live compatibility watch item

Chrome `DOMSnapshot.captureSnapshot` output shape should be validated on the operator machine. Current conversion reads layout text entries and falls back to node values. If live snapshots expose text through a different string-table field, add a compatibility branch in `background.ts` without changing the extractor contract.
