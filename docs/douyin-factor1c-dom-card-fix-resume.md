# Douyin Factor 1C DOM Card Fix Resume

## Current task

Fix only the Stage D extension request-payload fan-out bug identified by Factor 1B. Do not touch backend, API schemas, frontend rendering, or broad metadata logic.

## Audit result

Current `nearestCard()` in both extraction paths can return broad shared ancestors because it scores ancestors by presence of video links/images/text without rejecting containers that include multiple distinct `/video/` links.

This allows:

- `cardText()` to read shared grid/profile text.
- `titleFromCard()` to use contaminated text as title fallback.
- `thumbnailFromCard()` to scan sibling/shared images and choose another item's thumbnail.

## Implemented fix

Applied the same local-card rule in both:

- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`

Rule now enforced:

- A candidate card must contain the current link.
- A candidate card must contain exactly one distinct `/video/{id}` link.
- That one distinct id must match the current link's `aweme_id`.
- Shared grid/profile wrappers with multiple distinct video ids are rejected before scoring.
- `nearestCard()` no longer falls back to a broad `closest(...)` ancestor.
- If no safe local card is found, extraction uses the link itself only when it is safely local; otherwise it returns `null` and relies only on link-local text/attributes.
- `thumbnailFromCard()` now scans only `card ?? link`, preventing sibling/shared media candidates from broad roots.

## Completed steps

1. Patched item-local card resolution in `apps/extension-douyin-capture/src/extractor.ts`.
2. Mirrored the patch in `apps/extension-douyin-capture/src/popupTransport.ts`.
3. Added focused shared-container fan-out coverage in `apps/extension-douyin-capture/src/extractor.identity.test.ts`.
4. Updated direct-execution mirror source-shape coverage in `apps/extension-douyin-capture/src/extractor.test.ts`.
5. Ran targeted extension tests/typecheck successfully.
6. Updated this doc and the log with verification results.

## Verification

Command:

```text
npx --workspace apps/extension-douyin-capture tsx src/extractor.test.ts && npx --workspace apps/extension-douyin-capture tsx src/extractor.identity.test.ts && npx --workspace apps/extension-douyin-capture tsx src/popupTransport.test.ts && npm --workspace apps/extension-douyin-capture run typecheck
```

Result:

```text
extension extractor tests passed
extension identity / aweme_id mapping tests passed
extension direct execution transport tests passed

> typecheck
> tsc --noEmit -p tsconfig.json
```

The shared-container fixture uses the Factor 1B ids `7508570147947334964`, `7632149506821311763`, and `7629583407210614031`; each now keeps its own item-local title and thumbnail in Stage D payload construction instead of inheriting shared-wrapper metadata.

## Scope guardrails

- No backend changes.
- No API schema changes.
- No frontend rendering changes.
- No broad thumbnail correctness redesign.
- No duration/views/posted changes except preventing contaminated card text.
