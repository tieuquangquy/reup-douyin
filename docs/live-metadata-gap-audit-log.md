# Live Metadata Gap Audit Log (Part A only)

## Scope

This audit is intentionally limited to the requested fields only:

- `posted_at`, `posted_text`
- `duration_seconds`, `duration_text`
- `view_count`, `like_count`, `comment_count`, `share_count`

Pipeline stages audited:

1. Extension extract/normalize
2. Backend stage/persist
3. API expose/hydrate
4. Frontend consume/render

Non-goals for Part A:

- No broad refactor
- No implementation fix for all stages
- No unrelated metadata fields

---

## Stage-by-stage evidence

### 1) Extension extract/normalize

Evidence from [`buildCanonicalVideoPayload()`](apps/extension-douyin-capture/src/extractor.ts:680):

- Duration fallback chain is explicit:
  - network -> detail hydrate -> DOM
  - Emits `duration_seconds`, `duration_text`, `duration_source`
- Posted fallback chain is explicit:
  - network -> detail hydrate -> DOM
  - Emits `posted_at`, `posted_text`, `posted_source`
- Metric fallback chain is explicit for each field:
  - network -> detail hydrate -> DOM
  - Emits `view_count`, `like_count`, `comment_count`, `share_count` + source fields

Supporting parsers:

- [`extractDuration()`](apps/extension-douyin-capture/src/extractor.ts:646)
- [`extractPosted()`](apps/extension-douyin-capture/src/extractor.ts:655)
- [`extractMetrics()`](apps/extension-douyin-capture/src/extractor.ts:590)

Type contract supports these fields in payload [`VideoPayload`](apps/extension-douyin-capture/src/types.ts:79).

### 2) Backend stage/persist

Evidence from [`_build_item()`](apps/api/src/services/capture_inbox_service.py:688):

- Persisted top-level model fields:
  - `duration_seconds`
  - `posted_at`
- Persisted inside `metadata_json`:
  - `duration_text`, `duration_seconds`
  - `posted_text`, `posted_at`
  - `view_count`, `view_count_text`
  - `like_count`, `like_count_text`
  - `comment_count`, `comment_count_text`
  - `share_count`
- Also normalizes from possible `statistics/stats` merge before persistence.

Result: backend persist path for target fields exists and is active.

### 3) API expose/hydrate

Evidence from [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:24) and [`hydrate_card_grid_metadata()`](apps/api/src/schemas/capture_inbox.py:100):

- Response includes direct fields for all target values:
  - `duration_seconds`, `duration_text`, `posted_at`, `posted_text`
  - `view_count`, `like_count`, `comment_count`, `share_count`
- Hydration function rehydrates from `metadata_json` / `raw_payload_json` / `statistics` fallback for counts.

Important schema mismatch found (source-enum only, not core value):

- Extension emits `dom_text` for duration/metric source enums (see [`DurationSource`](apps/extension-douyin-capture/src/types.ts:47), [`MetricSource`](apps/extension-douyin-capture/src/types.ts:48)).
- API response schema allows `dom_fallback` instead for those source fields (see [`CapturedItemResponse.duration_source`](apps/api/src/schemas/capture_inbox.py:57) and related source fields).
- Hydrator drops unrecognized values to `None` because whitelist excludes `dom_text` for duration/metric source.

This is a provenance/source-label gap, not the primary value field itself.

### 4) Frontend consume/render

Resolvers exist in [`captureInboxCanonical.ts`](apps/web/src/lib/captureInboxCanonical.ts):

- [`resolveDuration()`](apps/web/src/lib/captureInboxCanonical.ts:32)
- [`resolvePosted()`](apps/web/src/lib/captureInboxCanonical.ts:39)
- [`resolveViewCount()`](apps/web/src/lib/captureInboxCanonical.ts:45)
- [`resolveLikeCount()`](apps/web/src/lib/captureInboxCanonical.ts:49)
- [`resolveCommentCount()`](apps/web/src/lib/captureInboxCanonical.ts:53)

However compact tile metric row does **not** use metric resolvers:

- [`compactMetricMetaForItem()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1307)
- It renders direct numeric fields only via [`compactMetricValue()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1317)
- If numeric fields are null in response object, UI shows `—` even if `*_text` exists in metadata.

By contrast posted/duration compact quick meta uses resolvers via [`compactQuickMetaForItem()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1299).

---

## Per-field diagnosis (Part A)

### `duration_seconds`, `duration_text`

- extension_status: PASS (extracted/emitted)
- backend_status: PASS (persisted top-level + metadata)
- api_status: PASS for value fields
- frontend_status: PASS for displayed quick meta via resolver
- failing_stage: none confirmed for core value fields
- note: `duration_source` provenance may be dropped (`dom_text` vs `dom_fallback` enum mismatch)

### `posted_at`, `posted_text`

- extension_status: PASS (extracted/emitted)
- backend_status: PASS
- api_status: PASS
- frontend_status: PASS via resolver
- failing_stage: none confirmed

### `view_count`, `like_count`, `comment_count`, `share_count`

- extension_status: PASS (canonical fallback chain + payload emit)
- backend_status: PASS (canonical numeric merge + metadata persistence)
- api_status: PASS for core numeric fields with metadata/statistics fallback
- frontend_status: **PARTIAL FAIL in compact tile metric rendering path**
  - compact row uses direct numeric fields only, not text fallback resolvers
  - can show `—` when numbers are absent but `*_text` exists
- failing_stage: frontend render path (compact metric row), not necessarily upstream extraction/persistence

---

## Upstream missing vs pipeline missing

Based on code audit alone:

- No hard evidence that upstream (Douyin page/network) universally lacks these fields.
- Code paths already attempt extraction and persistence for all target fields.
- Most likely observed "missing" symptoms for metrics can be frontend render-path behavior when text-only fallback exists.
- Separate provenance enum mismatch (`dom_text`) affects source labels, not raw metric/posted/duration values.

---

## Part A conclusion

For requested target fields, the dominant actionable gap appears to be **frontend metric rendering fallback behavior**, with a secondary **API provenance enum compatibility issue** for duration/metrics source fields. Core extraction/persist/expose paths for target values are present across extension/backend/API.
