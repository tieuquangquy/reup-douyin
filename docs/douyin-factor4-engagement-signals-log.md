# Douyin Factor 4 — Engagement Signals Log

## Scope Lock
- Factor 4 only: normalize and preserve trustworthy engagement signals for `view_count`, `like_count`, `comment_count`, `share_count`, and derived `engagement_rate`.
- Keep source priority strict by `aweme_id`:
  1. exact network JSON
  2. exact detail hydrate
  3. item-local DOM fallback only when higher-priority sources are missing
- No broad duration/posted changes, no UI redesign, no unrelated refactors.

## Audit Notes (Current State)

### Extension: network normalization path
- File: `apps/extension-douyin-capture/src/networkCache.ts`
- `normalizeAwemeRecord(...)` already reads some metrics from `statistics` using `metricValue(...)`.
- Current extraction is strong for `view_count`, `like_count`, `comment_count` from network records.
- Gap: `share_count` consistency and canonical carry-through need hard confirmation and alignment in downstream payload merge.

### Extension: canonical merge path
- File: `apps/extension-douyin-capture/src/extractor.ts`
- `buildCanonicalVideoPayload(...)` performs source-priority merge using exact hydrate matching helpers.
- Local DOM metric parsing exists in `extractMetrics(...)` / `parseMetric(...)` / compact sequence parser.
- Gap: explicit Factor-4 trust/guard layering for all five signals (including computed `engagement_rate`) is not yet standardized.

### Extension popup direct execution parity
- File: `apps/extension-douyin-capture/src/popupTransport.ts`
- Contains in-page capture logic mirroring extractor metric parsing behavior.
- Gap: needs parity checks so engagement rules do not diverge between content-script and popup direct-execution path.

### API ingest and shaping
- File: `apps/api/src/services/capture_inbox_service.py`
- `_build_item(...)` currently persists canonical-like stats in metadata path focused on view/like/comment.
- Gap: `share_count` and trustworthy `engagement_rate` need minimal schema-safe preservation.

### API response schema
- File: `apps/api/src/schemas/capture_inbox.py`
- `CapturedItemResponse` hydration helpers read integer/float metadata.
- Gap: response model and hydration currently do not consistently expose canonical `share_count` + `engagement_rate`.

### Extension request schema
- File: `apps/api/src/schemas/douyin_extension.py`
- `DouyinExtensionVideoPayload` is the API boundary for extension payload.
- Gap: verify and minimally extend/align engagement fields as needed without widening unrelated contract surface.

### Frontend type surface
- File: `apps/web/src/types/capture-inbox.ts`
- Captured item type currently centered around existing metric fields and card metadata.
- Gap: minimal type/render alignment needed for canonical `share_count` and `engagement_rate` exposure only.

## Decisions for Implementation
1. Preserve exact-id precedence end-to-end; never cross-map metrics across different `aweme_id`.
2. Prefer trustworthy numeric values from network/detail sources over DOM compact text.
3. Use DOM compact parsing only as fallback with confidence guards; reject ambiguous fragments.
4. Derive `engagement_rate` only when denominator is trustworthy and `view_count > 0`.
5. Keep backend/frontend changes minimal and contract-safe.

## Work Progress
- [x] Step 1 (audit): completed at code-reading level across extension/api/web paths.
- [x] Step 2 (docs first): completed (`log` / `resume` / `architecture` files created before implementation edits).
- [x] Step 3 (exact-id network normalization): completed in [`normalizeAwemeRecord()`](apps/extension-douyin-capture/src/networkCache.ts:107) and mirrored in [`normalizeAwemeRecord()`](apps/extension-douyin-capture/src/pageNetworkHook.ts:70).
- [x] Step 4 (exact-id detail-hydrate fallback): completed in [`buildCanonicalVideoPayload()`](apps/extension-douyin-capture/src/extractor.ts:665) with guarded precedence `network -> detail -> DOM` by exact `aweme_id`.
- [x] Step 5 (compact parsing confidence guards): completed via stricter parsing in [`parseMetric()`](apps/extension-douyin-capture/src/extractor.ts:603) and [`parseMetric()`](apps/extension-douyin-capture/src/popupTransport.ts:835).
- [x] Step 6 (invalid-value guards + rejection safety): completed with [`validCount()`](apps/extension-douyin-capture/src/extractor.ts:920), [`countValue()`](apps/extension-douyin-capture/src/networkCache.ts:348), and [`deriveEngagementRate()`](apps/extension-douyin-capture/src/extractor.ts:925).
- [x] Step 7 (backend/API alignment): completed in [`DouyinExtensionVideoPayload`](apps/api/src/schemas/douyin_extension.py:123), [`_build_item()`](apps/api/src/services/capture_inbox_service.py:687), and [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:24).
- [x] Step 8 (minimal frontend alignment): completed in [`CapturedItem`](apps/web/src/types/capture-inbox.ts:44) and fixture compatibility update in [`baseItem`](apps/web/src/test/capture-inbox-canonical.test.ts:16).
- [x] Step 9 (focused tests updates): extension assertions updated in [`extractor.test.ts`](apps/extension-douyin-capture/src/extractor.test.ts:1); web fixture type regression fixed.
- [x] Step 10 (verification runs): extension tests passed; web typecheck passed; API pytest blocked by missing module in local environment.
- [x] Step 11 (docs finalization): this log updated with changed files + evidence.

## Verification Evidence
- Extension tests: passed after updating guarded precedence assertions in [`extractor.test.ts`](apps/extension-douyin-capture/src/extractor.test.ts:1).
- Web typecheck: passed with `npm --workspace @reup-douyin/web run typecheck` after adding `share_count` and `engagement_rate` to [`baseItem`](apps/web/src/test/capture-inbox-canonical.test.ts:16).
- API tests: `python -m pytest ...` could not run because `pytest` is not installed in the environment (`No module named pytest`).
