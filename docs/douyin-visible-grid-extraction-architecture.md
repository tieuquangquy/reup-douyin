# Douyin Visible Grid Extraction Architecture

## Goal

The extension should extract metadata from real visible Douyin profile-grid cards reliably, without treating the grid as a generic text scrape and without fabricating missing values.

## Real visible grid structure from audit

The current extension path sees profile-grid videos as visible anchors whose `href` contains `/video/{id}`. The poster and overlay metadata may live on the anchor itself, descendants, or nearby ancestor card containers. Because Douyin uses lazy-rendered media and nested anonymous `div` structures, the extractor must score ancestors rather than assume a single selector.

Visible image evidence can appear as:

- direct `img.src`
- raw `img.getAttribute("src")`
- lazy `img.getAttribute("data-src")`
- `img.srcset`
- `source[srcset]`
- image-related dataset values
- image-related attributes
- inline `background-image`
- computed `background-image`
- `video[poster]` where present

Visible metadata evidence can appear as:

- link text
- card text
- `aria-label`
- `title`
- overlay duration text
- compact numeric metric text
- date or relative posted text

## Network JSON source

Douyin profile/feed pages commonly load JSON responses containing aweme-like item data. The extension should observe same-page `fetch` and `XMLHttpRequest` JSON responses and normalize video-like payloads into an in-page cache keyed by `aweme_id`/video id.

Preferred network fields:

- `aweme_id`
- `desc` / `title`
- `share_url`
- `create_time`
- `statistics.play_count`
- `statistics.digg_count`
- `statistics.comment_count`
- `video.cover.url_list`
- `video.origin_cover.url_list`
- `video.dynamic_cover.url_list`
- `video.duration`

Network JSON is preferred because it can provide exact counts, stable ids, and canonical cover lists even when visible DOM text is compact or icon-only.

## Extraction priority

1. Network JSON cache for exact metadata and cover candidates.
2. DOM card fallback for visible poster, duration text, posted text, title, metrics, source/share URL, and id.
3. Later backend/detail hydrate if needed outside this part.

## Thumbnail strategy

For each card, the DOM fallback tries local card sources in deterministic order:

1. direct `img.src`
2. raw `img.getAttribute("src")`
3. `img.getAttribute("data-src")`
4. image-related dataset values
5. `srcset`
6. inline `background-image`
7. computed `background-image`

The helper sanitizes URLs, converts protocol-relative URLs to absolute URLs, ignores empty or non-image-like values, preserves the original poster URL, and records the winning source type for safe debug.

Network cover candidates are merged ahead of DOM candidates when an aweme-cache match exists, but DOM candidates remain as fallback evidence.

## Metadata strategy

- Parse `mm:ss` and `hh:mm:ss` duration text from DOM when network duration is missing.
- Prefer network duration for exact `duration_seconds` when available.
- Preserve raw `posted_text`; prefer network `create_time` for exact `posted_at`.
- Parse DOM metric text only when safe; prefer exact network statistics.
- Keep `source_video_url` and `share_url` from the visible anchor unless network provides a specific share URL.

## Lazy-load timing

The content script runs at `document_idle`, and popup capture runs on operator action. The implemented Part 1 path avoids arbitrary waits and instead improves the real capture source coverage: it injects a page-world network hook early, keeps a bounded aweme metadata cache, and reads DOM poster sources at operator capture time. A future narrow retry remains acceptable only when visible video links exist but thumbnail candidates are still missing.

## Safe debug logging

Debug logging should be scoped and safe. It may include:

- item id
- selected thumbnail source type
- selected thumbnail URL host/path summary or URL when already present in payload
- duration fields
- posted fields
- metric presence/count values
- network-cache match boolean
- aggregate counts

It must not log cookies, auth headers, local private paths, browser storage dumps, or full raw network payloads.

## Implemented Part 1 behavior

- `apps/extension-douyin-capture/src/pageNetworkHook.ts` is injected into the page world through the manifest web-accessible resource path so real Douyin fetch/XHR JSON can be observed.
- `apps/extension-douyin-capture/src/networkCache.ts` normalizes aweme-like records and exposes a bounded cache to content-script capture.
- `apps/extension-douyin-capture/src/contentScript.ts` merges bridged page-world cache items with the content-script cache before building a capture payload.
- `apps/extension-douyin-capture/src/extractor.ts` merges network and DOM data per video id, preferring network for canonical thumbnail, title/description, exact duration seconds, posted timestamp, and metric counts while retaining DOM raw visible text evidence.
- `apps/extension-douyin-capture/src/popupTransport.ts` prefers the content-script bridge before direct execute-script fallback so normal popup capture can benefit from the network cache.
- `apps/extension-douyin-capture/src/extractor.test.ts` validates the network normalizer and source-level merge/extraction invariants without requiring a browser DOM in Node.

## Verification

`npm run test --workspace apps/extension-douyin-capture` passed, including extractor tests, popup tests, build, static copy, and dist module resolution.
