# Douyin Card Grid Metadata Fix User Guide

## What this fix is for

This fix improves Capture Inbox results when the operator captures a visible Douyin profile grid with the browser extension. Visible card metadata should flow into Capture Inbox instead of showing unnecessary missing or pending values.

## Expected Capture Inbox behavior

For visible Douyin profile-grid cards, Capture Inbox prefers real captured data:

- Thumbnail: shows the real card poster/cover when the extension can see it.
- Duration: shows parsed duration when safe, otherwise the raw visible duration text.
- Posted: shows parsed date/time when safe, otherwise the raw visible posted text.
- Views, likes, comments: show parsed numeric values when safe, otherwise raw visible text or pending instead of fabricated values.
- Preview: ready only when a real thumbnail or preview image exists.
- Media: shows `Source link captured` when the original Douyin link exists but no media asset is ready.

## Operator workflow

1. Open a supported Douyin profile page in the browser.
2. Wait until the visible profile grid has loaded thumbnails and overlay text.
3. Use the Douyin capture extension to capture the current page.
4. Open Capture Inbox.
5. Review the media tiles:
   - real thumbnails should display as images;
   - missing thumbnails should show the honest placeholder;
   - metadata chips should display captured duration/date/metric evidence when available;
   - preview/media chips should not overstate readiness.

## Troubleshooting

### Some cards still have no thumbnail

Possible causes:

- The card image was not loaded by Douyin at capture time.
- Douyin changed the DOM structure or moved poster data outside the visible card.
- The image URL is hidden behind a non-image script/state object not visible through safe DOM extraction.

Recommended action:

- Scroll the card into view and wait for the poster to render.
- Retry capture.
- If the issue persists across visible rendered cards, inspect extension diagnostics and backend logs for thumbnail candidate counts and source types.

### Duration or posted date still says Not captured

Possible causes:

- Douyin did not render that text on the visible profile-grid card.
- The text was present only after hover or in a detail page, not in the captured DOM.
- The format was ambiguous and was preserved only as raw text or rejected as unsafe to parse.

Recommended action:

- Capture after the visible card metadata is rendered.
- Use the item details panel to inspect raw safe payload fields if available.

### Views, likes, or comments show Pending

Pending means the extractor did not see a safe visible value for that metric or could not parse/preserve one without guessing. The system should not invent counts.

### Preview is Pending but the source URL exists

This is expected when no real thumbnail/preview image exists. A Douyin source URL is not a preview image.

### Media is not Ready but the source URL exists

This is expected for the current local-first capture step. A source URL means the original Douyin page reference was captured; it does not mean the media file has been downloaded or processed.

## Safe diagnostics

Diagnostics help identify extraction gaps without exposing secrets. They may include capture ids, video ids, booleans, counts, readiness statuses, and safe source labels. They must not include cookies, credentials, auth tokens, raw browser storage, or private local paths.

## Verification note

The extension and web Capture Inbox checks passed locally. Backend Python syntax compilation passed for the changed API files. The backend pytest command was attempted but could not run in this local Python environment because `pytest` is not installed.
