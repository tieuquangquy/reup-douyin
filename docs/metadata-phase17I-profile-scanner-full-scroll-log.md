# Phase 17I profile scanner full-scroll log

## Why the scanner only found 8

After Phase 17H, the Modal Whole Profile Test resolved the modal URL and reached the profile page correctly, but the scanner used page/window scrolling. The live diagnostics showed `scroll_y: 0` across rounds while the visible profile grid exposed only the first 8 aweme IDs. This indicates Douyin keeps profile cards inside an internal scrollable container or virtualized grid rather than scrolling the browser window.

## Scroll container selection

Phase 17I adds `findDouyinProfileScrollContainer()` in the extension beta scanner. It scores candidates from `document.scrollingElement`, body/document, main/profile containers, scrollable overflow containers, and card/grid parents. The selected container favors elements that are scrollable, visible, contain video/card candidates, and have the strongest card/area score.

Diagnostics now include:

- `selected_scroll_container`
- `scroll_container_candidates`
- `scroll_container_found`

If no internal container is selected, the scanner falls back to window scrolling and can report `profile_scroll_container_not_found`/`scroll_failed` when scrolling cannot advance.

## Full collection loop

Phase 17I adds `collectProfileCardsUntilStable()` with defaults:

- `max_rounds = 20`
- `stable_rounds_to_stop = 3`
- `scroll_step = 0.75 * container.clientHeight`
- `round_wait_ms = 900`
- `max_total_time_ms = 45000`

Each round extracts cards, merges unique aweme IDs into a persistent map, scrolls the selected container, waits for lazy loading, and records per-round counts. It stops on stable no-new IDs, reached bottom, max rounds, max total time, or scroll failure.

## Virtualization handling

The scanner keeps a persistent `Map<aweme_id, card evidence>` across rounds. If Douyin replaces old DOM nodes during scrolling, earlier IDs remain in the result. Evidence merge rules prefer existing non-empty data while filling gaps from later observations.

## Diagnostics fields

Added scanner diagnostics include:

- `scan_rounds[]` with round, before/after scroll positions, scroll height, new count, total count, candidate count, visible link count
- `stop_reason`
- `selected_scroll_container`
- `scroll_container_candidates`
- `scroll_container_found`
- `warning: profile_scan_low_count` when discovered count is non-zero but suspiciously below 10

## Tests run

The required verification commands are:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live retest steps

1. Rebuild/reload the extension.
2. Open a Douyin modal URL shaped like `https://www.douyin.com/user/{profile_id}?modal_id={aweme_id}`.
3. Open Advanced/Beta in the extension popup.
4. Select Verify only.
5. Click Test Modal → Whole Profile Harvest.
6. Confirm the beta panel reports profile navigation success, scan rounds greater than one, a selected scroll container or fallback diagnostics, and total found close to the profile's actual video count.
