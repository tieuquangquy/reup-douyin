# Douyin Factor 0B Grid Scope Log

## Task

Fix only Factor 0B: active grid discovery scoping and count integrity for real Douyin profile capture. Discovery must include only real visible video tiles from the active profile works grid.

## Audit: how discovery worked before

### `apps/extension-douyin-capture/src/extractor.ts`

- [`discoverGridVideos()`](apps/extension-douyin-capture/src/extractor.ts:129) called [`collectVideoLinks()`](apps/extension-douyin-capture/src/extractor.ts:163).
- [`collectVideoLinks()`](apps/extension-douyin-capture/src/extractor.ts:163) used broad document scan:
  - `document.querySelectorAll('a[href*="/video/"]')`
- Filtering only validated Douyin host and `/video/{id}` path, then dedupe by `aweme_id` in [`discoverGridVideos()`](apps/extension-douyin-capture/src/extractor.ts:131).
- No active works-grid root selection.
- No explicit rejection for hidden/detached/modal/non-active-tab links.
- Result: any stray `/video/` anchor in document scope could inflate count.

### `apps/extension-douyin-capture/src/popupTransport.ts` (direct execution mirror)

- Mirror implementation in [`discoverGridVideos()`](apps/extension-douyin-capture/src/popupTransport.ts:307) had same broad behavior.
- Mirror [`collectVideoLinks()`](apps/extension-douyin-capture/src/popupTransport.ts:410) also used document-wide `querySelectorAll('a[href*="/video/"]')`.
- This made fallback path vulnerable to the same overcount as primary extractor path.

## Exact overreach points

1. Document-wide anchor collection in [`collectVideoLinks()`](apps/extension-douyin-capture/src/extractor.ts:163).
2. No active works-grid root selection before link collection in [`discoverGridVideos()`](apps/extension-douyin-capture/src/extractor.ts:129).
3. No tile eligibility gate before acceptance into discovery set in [`discoverGridVideos()`](apps/extension-douyin-capture/src/extractor.ts:129).
4. Same overreach duplicated in direct fallback mirror in [`popupTransport.ts`](apps/extension-douyin-capture/src/popupTransport.ts:307).

## New rules to implement

1. **Active-grid scoping rule**
   - Discovery must first identify one active visible profile works-grid root.
   - Candidate links are collected only from that root.
   - No primary discovery from entire document.

2. **Tile eligibility rule**
   - Candidate requires valid `aweme_id` + local card/tile root.
   - Must be attached, visible, non-zero-size, and not hidden/inert.
   - Reject if inside modal/overlay/template/preload/non-active containers.
   - Reject if outside active works-grid root.

3. **Count integrity rule**
   - Track diagnostics for:
     - `discovered_count`
     - `eligible_tile_count`
     - `deduped_aweme_count`
     - `rejected_link_count`
     - reject-reason summary
   - Deduplicate only by exact `aweme_id` after eligibility checks.

## Implemented changes

- Added active-grid scoped discovery and diagnostics in [`discoverGridVideos()`](apps/extension-douyin-capture/src/extractor.ts:156).
- Added strict reject-reason gating in [`discoveryRejectReason()`](apps/extension-douyin-capture/src/extractor.ts:243):
  - `outside_active_grid`, `detached_node`, `hidden_node`, `invalid_visibility`, `non_active_profile_tab`, `modal_link`, `no_tile_media_frame`, plus duplicate rejection.
- Added active-grid candidate scoring in [`findActiveWorksGridRoot()`](apps/extension-douyin-capture/src/extractor.ts:229).
- Scoped link collection root in [`collectVideoLinks(root)`](apps/extension-douyin-capture/src/extractor.ts:206).
- Exposed count-integrity diagnostics in extractor payload from [`buildCapturePayload()`](apps/extension-douyin-capture/src/extractor.ts:27).
- Mirrored the same scoped behavior and diagnostics in direct fallback path [`runDouyinActionInPage()`](apps/extension-douyin-capture/src/popupTransport.ts:167), including [`discoverGridVideos(diagnostics)`](apps/extension-douyin-capture/src/popupTransport.ts:322) and [`collectVideoLinks(root)`](apps/extension-douyin-capture/src/popupTransport.ts:442).

## Focused tests updated

- Updated source-shape expectation for direct fallback discovery signature in [`extractor.test.ts`](apps/extension-douyin-capture/src/extractor.test.ts:68).
- Added duplicate-count integrity test with diagnostics assertions in [`extractor.identity.test.ts`](apps/extension-douyin-capture/src/extractor.identity.test.ts:217):
  - candidate count reflects raw scoped anchors,
  - deduped count reflects unique `aweme_id`,
  - `duplicate_aweme_in_grid` rejection reason is counted.

## Verification result

- Ran extension suite: `npm run test --workspace apps/extension-douyin-capture`.
- Result: pass for [`extractor.test.ts`](apps/extension-douyin-capture/src/extractor.test.ts), [`extractor.identity.test.ts`](apps/extension-douyin-capture/src/extractor.identity.test.ts), [`popupActions.test.ts`](apps/extension-douyin-capture/src/popupActions.test.ts), [`popupTransport.test.ts`](apps/extension-douyin-capture/src/popupTransport.test.ts), build, and dist module resolution.

## Outcome against Factor 0B target

- Discovery no longer relies on document-wide acceptance as primary behavior.
- Discovery is scoped to active works-grid root when available, with strict rejections for out-of-scope/non-eligible links.
- Count integrity now tracks candidate/eligible/deduped/rejected dimensions and duplicate reason counts, preventing duplicate-anchor inflation.
