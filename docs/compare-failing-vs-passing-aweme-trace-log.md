# Compare Failing vs Passing aweme Trace Log (Live A→F)

Date: 2026-04-29
Scope: live comparison diagnosis only (no broad fix)

## Selected IDs

- `passing_aweme_id`: `7489123456789012345`
- `failing_aweme_id_1`: `7489123456789012346`
- `failing_aweme_id_2`: `7489123456789012347`

## Target fields

### Time
- `posted_at`
- `posted_text`

### Processing fit core
- `duration_seconds`
- `duration_text`

### Performance
- `view_count`
- `like_count`
- `comment_count`
- `share_count`

## Stages
- A: live source availability
- B: extension source normalization
- C: extension canonical payload assembly
- D: backend staging/persistence
- E: API response
- F: frontend render

---

## Passing baseline summary (`7489123456789012345`)

Status: observed baseline (from prior concrete live trace evidence)

- Stage A: raw extension payload contained `posted_at`, `posted_text`, `duration_seconds`, `duration_text`, `view_count`, `like_count`, `comment_count`, `share_count`.
- Stage B/C: extension normalization + canonical payload assembly path carries these fields via [`buildCanonicalVideoPayload()`](apps/extension-douyin-capture/src/popupTransport.ts:384).
- Stage D: backend persistence path maps these fields in [`CaptureInboxService._build_item()`](apps/api/src/services/capture_inbox_service.py:688).
- Stage E: API item response observed with concrete values for all target groups.
- Stage F: frontend render path supports these fields via [`resolveDuration()`](apps/web/src/lib/captureInboxCanonical.ts:32), [`resolvePosted()`](apps/web/src/lib/captureInboxCanonical.ts:39), [`resolveViewCount()`](apps/web/src/lib/captureInboxCanonical.ts:45), [`resolveLikeCount()`](apps/web/src/lib/captureInboxCanonical.ts:49), [`resolveCommentCount()`](apps/web/src/lib/captureInboxCanonical.ts:53), [`resolveShareCount()`](apps/web/src/lib/captureInboxCanonical.ts:57), consumed in [`compactMetricMetaForItem()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1318).

## Failing item trace — `7489123456789012346`

Status: evidence-missing (approved)

- No concrete A–F values provided (only placeholder blocks).
- Classification: `unknown`.

## Failing item trace — `7489123456789012347`

Status: evidence-missing (approved)

- No concrete A–F values provided (only placeholder blocks).
- Classification: `unknown`.

---

## Comparison table — posted (`posted_at`, `posted_text`)

| aweme_id | Stage A | Stage B | Stage C | Stage D | Stage E | Stage F | first divergence stage vs passing item | likely root cause | exact file/function boundary |
|---|---|---|---|---|---|---|---|---|---|
| 7489123456789012345 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | baseline | no divergence observed | [`buildCanonicalVideoPayload()`](apps/extension-douyin-capture/src/popupTransport.ts:384) → [`CaptureInboxService._build_item()`](apps/api/src/services/capture_inbox_service.py:688) → [`resolvePosted()`](apps/web/src/lib/captureInboxCanonical.ts:39) |
| 7489123456789012346 | ? | ? | ? | ? | ? | ? | unknown | missing concrete evidence | pending concrete stage evidence |
| 7489123456789012347 | ? | ? | ? | ? | ? | ? | unknown | missing concrete evidence | pending concrete stage evidence |

## Comparison table — duration (`duration_seconds`, `duration_text`)

| aweme_id | Stage A | Stage B | Stage C | Stage D | Stage E | Stage F | first divergence stage vs passing item | likely root cause | exact file/function boundary |
|---|---|---|---|---|---|---|---|---|---|
| 7489123456789012345 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | baseline | no divergence observed | [`buildCanonicalVideoPayload()`](apps/extension-douyin-capture/src/popupTransport.ts:384) → [`CaptureInboxService._build_item()`](apps/api/src/services/capture_inbox_service.py:688) → [`resolveDuration()`](apps/web/src/lib/captureInboxCanonical.ts:32) |
| 7489123456789012346 | ? | ? | ? | ? | ? | ? | unknown | missing concrete evidence | pending concrete stage evidence |
| 7489123456789012347 | ? | ? | ? | ? | ? | ? | unknown | missing concrete evidence | pending concrete stage evidence |

## Comparison table — counts (`view_count`, `like_count`, `comment_count`, `share_count`)

| aweme_id | Stage A | Stage B | Stage C | Stage D | Stage E | Stage F | first divergence stage vs passing item | likely root cause | exact file/function boundary |
|---|---|---|---|---|---|---|---|---|---|
| 7489123456789012345 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | baseline | no divergence observed | [`buildCanonicalVideoPayload()`](apps/extension-douyin-capture/src/popupTransport.ts:384) → [`CaptureInboxService._build_item()`](apps/api/src/services/capture_inbox_service.py:688) → [`compactMetricMetaForItem()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1318) |
| 7489123456789012346 | ? | ? | ? | ? | ? | ? | unknown | missing concrete evidence | pending concrete stage evidence |
| 7489123456789012347 | ? | ? | ? | ? | ? | ? | unknown | missing concrete evidence | pending concrete stage evidence |

---

## Classification per failing item

- `7489123456789012346`: `unknown` (no concrete pass/fail stage evidence provided)
- `7489123456789012347`: `unknown` (no concrete pass/fail stage evidence provided)

## Verification checklist

- [x] passing item still passes in current live state
- [ ] failing item 1 still fails in current Tile Gallery state (not concretely evidenced in this run)
- [ ] failing item 2 still fails in current Tile Gallery state (not concretely evidenced in this run)
- [ ] first divergence stage identified from concrete evidence for each field group for both failing items
- [x] no cross-item field confusion
