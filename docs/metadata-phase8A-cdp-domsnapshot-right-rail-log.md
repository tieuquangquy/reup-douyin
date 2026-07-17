# Phase 8A CDP DOMSnapshot Right-Rail Extractor Log

## Scope

Phase 8A replaces normal Douyin modal action metric extraction with a Chrome Debugger Protocol DOMSnapshot layout extractor in `apps/extension-douyin-capture`.

The change is intentionally narrow:

- keep `aweme_id` detection from `modal_id`, `/video/{aweme_id}`, and existing modal detectors;
- keep active video duration extraction from the modal video element;
- keep the existing backend flush endpoint and pending/flushed/updated progress model;
- keep resume and idempotent flush behavior;
- do not add crawler, video processing, scoring, queue, database, or publishing behavior.

## Why the old fallback path was abandoned for normal mode

The old modal metric path combined several brittle sources:

- visible right-rail DOM fallback;
- combined modal text fallback;
- text-node numeric clusters;
- icon-anchored selector extraction;
- profile-card fallback.

Those sources were useful for earlier diagnostics, but they were not reliable enough for normal Full Modal Harvest. Douyin modal text often contains captions, chapters, ratings, player controls, profile-grid numbers, and timeline strings near the same count labels. Selector and icon anchoring also changes with product/UI variants.

Phase 8A keeps legacy direct extractor behavior for focused unit diagnostics when the snapshot argument is omitted, but normal Probe and Full Modal Harvest no longer use those old fallback sources as readiness or persistence sources.

## DOMSnapshot layout strategy

The extension now requests the active Douyin tab through the Chrome Debugger Protocol:

1. attach to the active Douyin tab;
2. call `Page.getLayoutMetrics` to obtain viewport dimensions;
3. call `DOMSnapshot.captureSnapshot` with DOM rect collection enabled;
4. convert snapshot layout text and bounds into typed visible text entries;
5. pass those text entries into the modal right-rail extractor.

The normal extraction source is:

```text
cdp_dom_snapshot_right_rail
```

When the extractor succeeds, `raw_dom_detail_metrics.extraction_source`, `source_used`, and `source_priority_used` are all set to `cdp_dom_snapshot_right_rail`.

Evidence summaries include:

- `full_modal_auto_harvest`
- `cdp_dom_snapshot_right_rail`

and use collection version:

```text
phase8a_cdp_domsnapshot_right_rail
```

## Right-rail region rules

The extractor builds a right-rail region from the active modal video geometry when available. If video geometry is unavailable, it falls back to the viewport right band.

Candidates must be:

- visible within the viewport;
- inside the right-rail x/y region;
- compact count labels;
- not in the bottom player/timeline area;
- not in the left caption/profile area;
- not huge text blocks;
- not caption/chapter/profile/search/player text.

Rejected examples are preserved in diagnostics so operator/debug views can explain why labels were ignored.

## Count parsing

The DOMSnapshot extractor accepts compact count labels including:

- `7.5万`
- `441`
- `2.2万`
- `1.3万`
- `818`
- `15`
- `152`
- `35`

The selected four labels are assigned vertically as:

1. like count
2. comment count
3. favorite count
4. share count

## PASS/WARN/FAIL behavior

Normal Probe returns `PASS` only when all of the following are true:

- current `aweme_id` is detected;
- a CDP DOMSnapshot payload is available;
- active video duration is available;
- exactly one usable right-rail label group provides all four action metrics;
- source is `cdp_dom_snapshot_right_rail`.

Normal Probe returns `FAIL` when blocking prerequisites are missing, including:

- missing current `aweme_id`;
- missing CDP DOMSnapshot payload;
- missing duration.

Normal Probe returns `WARN` when snapshot data exists but the right-rail labels are insufficient or ambiguous.

Full Modal Harvest uses the same extractor and only persists items when the same snapshot-based PASS conditions are met. WARN, FAIL, and no-snapshot items are not flushed as harvested item payloads.

## Verification completed

Targeted verification completed successfully:

```text
npx tsx apps/extension-douyin-capture/src/modalHarvest.test.ts
npm run typecheck --workspace apps/extension-douyin-capture
```

The targeted modal harvest test now covers:

- snapshot PASS extraction for Chinese compact labels;
- snapshot PASS extraction for plain numeric labels;
- offscreen, caption/chapter/rating, timeline, and bottom-control rejection;
- fewer-than-four label WARN;
- ambiguous label WARN;
- normal Probe no-snapshot FAIL behavior for old fallback-only fixtures;
- Full Modal Harvest persistence through the same snapshot extractor;
- backend flush failure, 422, 200, resume, and navigation paths with snapshot-gated harvest items.

## Live retest steps

1. Load the rebuilt extension in Chrome.
2. Open an active Douyin modal video.
3. Attach CDP from the extension popup.
4. Run Probe.
5. Confirm Probe shows source `cdp_dom_snapshot_right_rail`, four selected snapshot labels, duration, and PASS.
6. Start Full Modal Harvest.
7. Confirm harvested items include `raw_dom_detail_metrics.extraction_source = "cdp_dom_snapshot_right_rail"`.
8. Confirm backend flush updates existing capture inbox items and pending/flushed progress remains stable.

## Known follow-up

Live validation should confirm the exact Chrome `DOMSnapshot.captureSnapshot` text payload shape across the operator's browser build. If a live browser omits `layout.text`, the snapshot converter may need a small compatibility adapter for additional DOMSnapshot string-table fields.
