# Douyin Factor 1C DOM Card Fix Log

## Scope

Narrow Stage D fix only: prevent extension request payload fan-out caused by DOM-card scoping. This task is limited to extension DOM-card extraction logic, direct execution mirror logic, focused tests, and these docs.

## Audit before patching

### `apps/extension-douyin-capture/src/extractor.ts`

Functions audited: `extractVideos()`, `nearestCard()`, `cardText()`, `titleFromCard()`, `thumbnailFromCard()`.

1. What DOM node is currently treated as the card for each link?
   - `extractVideos()` calls `nearestCard(link)` for each `/video/{aweme_id}` anchor.
   - `nearestCard()` walks up to 7 ancestors, scores every ancestor, sorts by highest score, and returns the highest-scoring ancestor.
   - Fallback is `link.closest("li, article, section, div[data-e2e], div")`.

2. Is that node item-local, or can it be a shared ancestor?
   - It can be a shared ancestor. The highest score can be earned by a larger grid/profile wrapper because it contains multiple video links, multiple images, background images, and enough text.

3. Can two different video links resolve to the same card container?
   - Yes. The current resolver does not reject ancestors containing multiple distinct `/video/` links, so multiple links inside the same grid/profile wrapper can resolve to the same container.

4. Do title/thumbnail selectors search too broadly inside that container?
   - Yes. `cardText()` reads `card.textContent` from whatever `nearestCard()` returns.
   - `titleFromCard()` then uses that text as title fallback.
   - `thumbnailFromCard()` scans all image/media/attribute/background candidates inside `card` and `link`, so a shared card/root can contribute sibling thumbnails.

5. Is there any first matching descendant selector causing cross-item contamination?
   - There is no single `querySelector(...)` first-match thumbnail call, but the broad `querySelectorAll(...)` scans inside the chosen root and then picks the first/highest-scored candidate after sorting. If the root is shared, this can still select another item's thumbnail.
   - `cardScore()` itself uses `element.querySelector(...)` to score ancestors. In a shared ancestor, those first-match checks can make a broad container look valid even when it is not item-local.

### `apps/extension-douyin-capture/src/popupTransport.ts`

The direct-page-execution fallback contains mirrored logic with the same issue:

1. `extractVideos()` calls mirrored `nearestCard(link)`.
2. Mirrored `nearestCard()` scores ancestors and can return a broad shared ancestor.
3. Two links can resolve to the same returned card.
4. Mirrored `cardText()`, `titleFromCard()`, and `thumbnailFromCard()` read inside that returned root.
5. Mirrored image candidate collection uses broad `querySelectorAll(...)` under the selected root and can choose sibling/shared media candidates if the selected root is too broad.

## Confirmed root cause in DOM-card scoping

The root cause is the card resolver's highest-score ancestor strategy. It rewards broad ancestors that contain images, links, and text but does not require a single-item/local-card boundary. In a profile grid, a broad shared wrapper can outscore a smaller tile and then contaminate text/title/thumbnail extraction across distinct `aweme_id` values.

## Implemented local-card rule

For each `/video/{aweme_id}` link:

1. Walk ancestors from nearest to farther.
2. Stop before `body`/`html`.
3. Only score a candidate through `isLocalCardForLink()` when the candidate contains exactly one distinct `/video/{id}` link and that id matches the current link.
4. Reject broad grid/profile wrappers because they contain multiple distinct video ids.
5. Prefer the highest-scoring safe local ancestor, with nearer ancestors winning score ties.
6. If no safe local ancestor exists, return the link itself only when the link is independently local and scoreable; otherwise return `null`.
7. Keep title/card-text extraction inside the returned local card; with `null`, use only link-local text/attributes.
8. Keep thumbnail extraction inside `card ?? link`, so a safe local card is used when available and the fallback is link-only. The extractor no longer scans both a card and a broader/alternate root.

## Files/functions changed

- `apps/extension-douyin-capture/src/extractor.ts`
  - `nearestCard()` now filters candidates through `isLocalCardForLink()` and no longer falls back to broad `closest(...)` ancestors.
  - `cardScore()` now returns `0` for non-local/shared candidates.
  - `isLocalCardForLink()` was added to enforce one distinct video id per accepted card root.
  - `videoLinksWithin()` was added to count the current link and descendant video links for locality checks.
  - `thumbnailFromCard()` now uses `[card ?? link]` to avoid broad-root plus link double scanning.
  - `cardText()` and `titleFromCard()` remain bounded by the stricter card returned by `nearestCard()` and do not climb to broader ancestors.
- `apps/extension-douyin-capture/src/popupTransport.ts`
  - Mirrored the same `nearestCard()`, `cardScore()`, `isLocalCardForLink()`, `videoLinksWithin()`, and `thumbnailFromCard()` behavior in the direct execute-script extraction copy.
- `apps/extension-douyin-capture/src/extractor.identity.test.ts`
  - Added a focused shared-grid fixture using the three Factor 1B ids.
- `apps/extension-douyin-capture/src/extractor.test.ts`
  - Added source-shape assertions that both extraction paths reject shared card ancestors and use the local-card/link-only thumbnail root.

## Tests added/updated

- Added `makeSharedGridTile()` and a shared-container fan-out regression test in `apps/extension-douyin-capture/src/extractor.identity.test.ts`.
- The regression fixture places three distinct video links under one shared wrapper with shared wrapper text/background/cover metadata.
- Assertions verify:
  1. Three payload items are produced.
  2. The three known `aweme_id` values stay distinct: `7508570147947334964`, `7632149506821311763`, `7629583407210614031`.
  3. Each item keeps its own local title.
  4. Each item keeps its own local thumbnail.
  5. No item inherits shared ancestor title text.
  6. No item inherits shared ancestor thumbnail candidates.
  7. `raw.visible_text` remains item-local.
- Updated `apps/extension-douyin-capture/src/extractor.test.ts` to assert the direct execution mirror in `apps/extension-douyin-capture/src/popupTransport.ts` contains the same shared-ancestor rejection and `card ?? link` thumbnail-root rule.

## Verification result

Targeted verification passed:

```text
npx --workspace apps/extension-douyin-capture tsx src/extractor.test.ts && npx --workspace apps/extension-douyin-capture tsx src/extractor.identity.test.ts && npx --workspace apps/extension-douyin-capture tsx src/popupTransport.test.ts && npm --workspace apps/extension-douyin-capture run typecheck
```

Output:

```text
extension extractor tests passed
extension identity / aweme_id mapping tests passed
extension direct execution transport tests passed

> typecheck
> tsc --noEmit -p tsconfig.json
```

For the three Factor 1B `aweme_id` values, the focused Stage D DOM fixture now proves the extension payload builder keeps title and thumbnail item-local and does not reuse shared ancestor metadata.
