# Douyin Visible Grid Extraction Log

## Scope

Part 1 focuses only on the browser-extension extraction path for real visible Douyin profile-grid cards.

Allowed areas:

- `apps/extension-douyin-capture`
- extension extraction tests
- docs for this extraction path

Non-goals:

- No Capture Inbox redesign.
- No backend/API/frontend implementation in this part.
- No full crawler.
- No media download.
- No fabricated metadata.

## Audit completed before implementation

### Current profile-card detection

The current extension detects visible videos by selecting anchors matching `a[href*="/video/"]`, then validating the hostname and `/video/{id}` path. Page classification treats `/user/{id}` and `@handle` pages with video links as `profile_feed_page`.

Card root selection currently starts from each video link and scores up to seven ancestors. Scores increase when an ancestor has video links, media descendants, image-like attributes, background images, duration text, posted text, and a reasonable rendered rectangle. This is better than a shallow `closest("div")` lookup, but it is still DOM-only and has no network metadata merge.

### Current thumbnail extraction

Current extraction already inspects many visible DOM image sources inside the selected card/link roots:

- `img.currentSrc`
- `img.src`
- `img.getAttribute("src")`
- `img.getAttribute("data-src")`
- `img.srcset`
- `source[srcset]`
- `video[poster]`
- image-related dataset fields
- image-related attributes
- inline `background-image`
- computed `background-image`

Current gaps:

- URL normalization is weak: candidates are kept mostly as raw strings and are only later parsed by `new URL` in the image-like check.
- Protocol-relative URLs are not explicitly normalized in the emitted payload.
- The winning source type is not exposed as a single diagnostic field per item.
- The current deterministic score can still prefer `srcset` over `img.src`, while this part requires the explicit DOM fallback order to try direct `img.src` first.

### Current timing and lazy loading

The content script runs at `document_idle`. The popup direct-execute path runs when the operator clicks capture. There is currently no small read-after-render retry when visible cards exist but lazy poster fields are not populated yet. This can miss posters if Douyin populates image attributes shortly after initial DOM idle or after scroll-triggered lazy loading.

### Current metadata extraction

Current DOM metadata extraction attempts:

- video id from `/video/{id}` href
- source/share URL from link href
- title/caption from link ARIA/title or compact card text
- duration from `mm:ss` or `hh:mm:ss` text
- posted text from date/relative Chinese text patterns
- views/likes/comments from nearby labels or compact numeric sequences

Current gaps:

- No network JSON observation exists.
- DOM metrics are fragile for compact overlays or icon-only labels.
- Posted date parsing can produce misleading absolute timestamps for month/day text without enough context; raw `posted_text` should remain primary unless the source is stable network `create_time`.
- Exact counts are better sourced from Douyin JSON `statistics` when available.

### Network JSON audit

No current extension file hooks `fetch` or `XMLHttpRequest`. The extension has no page-side network cache, no bridge from page context to content script, and no normalized aweme cache keyed by `aweme_id`/video id.

Real Douyin profile pages commonly load aweme-like JSON payloads containing fields such as `aweme_id`, `desc`, `create_time`, `statistics.play_count`, `statistics.digg_count`, `statistics.comment_count`, `video.cover`, `video.origin_cover`, `video.dynamic_cover`, and `video.duration`. These responses are a stronger metadata source than DOM text when safely observed.

### Debug logging audit

Current diagnostics contain aggregate counts in the capture payload. There is no focused extension-side debug log for a representative item showing selected thumbnail source, extracted duration, posted value, metrics, and network-cache match status.

## Planned implementation order

1. Add page network hook and normalized cache.
2. Add content-script bridge to read the network cache safely.
3. Strengthen deterministic DOM thumbnail helper with explicit source priority and URL normalization.
4. Strengthen DOM metadata extraction while preserving raw text.
5. Merge network metadata over DOM fallback per item.
6. Add safe debug logging and diagnostics.
7. Add focused extension tests and run extension verification.

## Implementation completed

- Added typed network metadata support in `apps/extension-douyin-capture/src/types.ts` for aweme id, title/desc, share URL, cover URLs, duration, posted timestamp, metrics, raw metric text, and safe network source diagnostics.
- Added `apps/extension-douyin-capture/src/networkCache.ts` to observe extension-context fetch/XHR JSON responses, normalize aweme-like records, merge cache entries by `aweme_id`, and read the page cache from a hidden JSON script element.
- Added `apps/extension-douyin-capture/src/pageNetworkHook.ts` and exposed it through `apps/extension-douyin-capture/public/manifest.json` so the content script can inject a page-world hook that sees real Douyin page fetch/XHR traffic despite extension isolated-world limits.
- Updated `apps/extension-douyin-capture/src/contentScript.ts` to install the isolated hook, inject the page hook, receive bridged cache updates, merge cache entries, and pass network metadata into the capture payload builder.
- Updated `apps/extension-douyin-capture/src/extractor.ts` so visible `/video/` links are merged with matching network metadata by video id. Network JSON now wins for thumbnail/title/exact duration/exact posted timestamp/exact counts while DOM still preserves visible duration text, posted text, raw metric text, source link, and fallback thumbnails.
- Strengthened DOM thumbnail fallback in `apps/extension-douyin-capture/src/extractor.ts` with URL normalization, protocol-relative URL handling, deterministic scoring, and `thumbnail_source_type` diagnostics.
- Updated `apps/extension-douyin-capture/src/popupTransport.ts` so popup capture first attempts the content-script bridge and only falls back to direct execute-script capture when the bridge is unavailable.
- Added safe representative debug logging in `apps/extension-douyin-capture/src/extractor.ts` with aggregate counts, a sample aweme id, boolean metadata presence, selected source type, and network-source presence. It does not log cookies, tokens, headers, local private paths, or full raw payloads.

## Verification completed

- `npm run test --workspace apps/extension-douyin-capture` passed.
- The verification command ran extractor tests, popup action tests, popup transport tests, TypeScript build, static asset copy, and dist module resolution checks.
- Focused extractor tests now remain Node-safe by avoiding unavailable browser `DOMParser` APIs while still checking network normalizer behavior and source-level extraction/merge invariants.
