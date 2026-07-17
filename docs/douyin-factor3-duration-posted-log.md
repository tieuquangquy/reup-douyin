# Douyin Capture Inbox — Factor 3 Duration + Posted Normalization Log

Date: 2026-04-28
Scope: ONLY Factor 3 (`duration_seconds`, `duration_text`, `posted_at`, `posted_text`)

## 1) Scope lock and non-goals

This log is restricted to Duration + Posted quality. The following are explicitly out of scope:
- views/likes/comments/shares logic changes
- thumbnail logic redesign
- capture workflow redesign
- queue/db schema changes not required by duration/posted

## 2) Audit summary (current state)

### Extension canonical merge is already exact-id first
Current canonical merge in [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:661):
- network metadata by exact `aweme_id`
- detail hydrate metadata by exact `aweme_id`
- DOM fallback from same discovered tile

Current priority implemented:
- `duration_seconds`: network -> detail -> dom
- `duration_text`: network -> detail -> dom -> derived from seconds
- `posted_at`: validated network -> validated detail -> dom parsed
- `posted_source`: `network_json` | `detail_hydrate` | `dom_text` | `fallback_none`

Reference lines:
- [`durationSeconds` merge](../apps/extension-douyin-capture/src/extractor.ts:682)
- [`durationText` merge](../apps/extension-douyin-capture/src/extractor.ts:683)
- [`postedAt` merge](../apps/extension-douyin-capture/src/extractor.ts:686)
- [`postedSource` selection](../apps/extension-douyin-capture/src/extractor.ts:687)

### Network normalization can still emit weak values
In [`normalizeAwemeRecord()`](../apps/extension-douyin-capture/src/networkCache.ts:107), current behavior:
- duration uses `video.duration` or `record.duration`, then rounds
- posted_at uses `create_time` directly to ISO

Risk points:
- ambiguous duration unit conversion (`ms` vs `s`) may allow suspicious values if input is malformed
- posted timestamps are transformed without guard at normalization stage; guard currently applies later in extractor canonical merge

Reference:
- [`duration_seconds` normalize path](../apps/extension-douyin-capture/src/networkCache.ts:131)
- [`posted_at` normalize path](../apps/extension-douyin-capture/src/networkCache.ts:132)

### Backend currently preserves canonical fields with minimal transformation
In [`_build_item()`](../apps/api/src/services/capture_inbox_service.py:687):
- duration persisted via `_float_or_none(raw_item.duration_seconds|duration)`
- posted persisted via `_datetime_or_none(raw_item.posted_at|create_time)`
- metadata stores `duration_text`, `posted_text`, `posted_at` snapshot

This is mostly pass-through and suitable for Factor 3 if upstream normalization is tightened.

### Frontend resolver behavior is canonical and simple
In [`resolveDuration()`](../apps/web/src/lib/captureInboxCanonical.ts:32):
- prefer `duration_text`, else format `duration_seconds`, else `Not captured`

In [`resolvePosted()`](../apps/web/src/lib/captureInboxCanonical.ts:39):
- prefer `posted_at` (formatted), else `posted_text`, else `Not captured`

Risk point:
- if malformed but non-empty `posted_text` arrives (e.g. `13.0`), UI currently displays it.

## 3) Observed root causes for reported symptoms

### Symptom A: Duration not captured
Likely causes:
1. weak network duration normalization from mixed source fields/units,
2. fallback path not deriving text when numeric value rejected/empty,
3. item-local DOM fallback unavailable for that tile.

### Symptom B: Posted shows `13.0`
Likely cause:
- non-date numeric-like string may flow into `posted_text` (or through metadata fallback), and current resolver displays any non-empty string.

### Symptom C: fake/default midnight timestamps
Current pipeline already rejects suspicious midnight via `validNetworkPostedAt` in extractor merge path, but this is not enforced at raw network normalization boundary.

## 4) Constraints validated against implementation

Required source priority from task:
1) exact network JSON by `aweme_id`
2) exact detail hydrate by `aweme_id`
3) item-local DOM fallback

Status: implemented in extractor merge; needs hardening for bad-value guards and consistency at normalization boundaries.

## 5) Planned narrow implementation (next step)

1. Tighten duration normalization in extension network parsing:
   - introduce stricter parser for `duration_seconds`
   - reject impossible/invalid values
   - keep fallback to `duration_text` only when trustworthy

2. Tighten posted normalization in extension network parsing:
   - apply network timestamp validity guard before exposure
   - avoid emitting low-quality `posted_text` from numeric noise

3. Keep exact-id merge order unchanged in extractor canonical merge, but add value-quality guards:
   - reject malformed duration text patterns
   - reject malformed posted text patterns (including `13.0`-like noise)

4. Backend minimal alignment only if needed to preserve canonical duration/posted without broad changes.

5. Frontend minimal display guard:
   - suppress known-invalid `posted_text` patterns instead of rendering them.

## 6) Existing tests relevant to Factor 3

- Extension identity tests already cover exact-id binding and no leakage:
  - [`apps/extension-douyin-capture/src/extractor.identity.test.ts`](../apps/extension-douyin-capture/src/extractor.identity.test.ts)
- Extension merge-contract tests include duration/posted precedence assertions:
  - [`apps/extension-douyin-capture/src/extractor.test.ts`](../apps/extension-douyin-capture/src/extractor.test.ts)
- Frontend canonical resolver tests include duration/posted behavior:
  - [`apps/web/src/test/capture-inbox-canonical.test.ts`](../apps/web/src/test/capture-inbox-canonical.test.ts)

## 7) Implemented changes (completed)

### Extension network normalization
Applied strict guards in [`normalizeAwemeRecord()`](../apps/extension-douyin-capture/src/networkCache.ts:107) and mirrored logic in [`pageNetworkHook` normalize path](../apps/extension-douyin-capture/src/pageNetworkHook.ts:70):
- duration seconds normalized with bounds checks
- duration text accepted only for `HH:MM[:SS]`
- posted timestamp accepted only from valid epoch and rejected on suspicious midnight defaults

### Extension canonical merge hardening
Updated [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:661):
- duration precedence remains exact-id `network -> detail -> dom` with value guards
- posted precedence remains exact-id `network -> detail -> dom` with timestamp validity guard
- provenance remains narrow: `network_json | detail_hydrate | dom_text | fallback_none`

### Frontend resolver hardening
Updated [`resolvePosted()`](../apps/web/src/lib/captureInboxCanonical.ts:39):
- invalid fallback posted text (for example numeric noise like `13.0`) is suppressed to `Not captured`
- valid relative/date strings (CN + EN forms such as `1 hour ago`) continue to render

### Tests updated
- Updated extractor source-contract assertions in [`extractor.test.ts`](../apps/extension-douyin-capture/src/extractor.test.ts:139)
- Added invalid posted-text resolver case in [`capture-inbox-canonical.test.ts`](../apps/web/src/test/capture-inbox-canonical.test.ts:266)

## 8) Verification results

Executed successfully:
- [`npm --workspace @reup-douyin/extension-douyin-capture run test`](../apps/extension-douyin-capture/package.json)
- [`npm --workspace @reup-douyin/web exec tsx src/test/capture-inbox-canonical.test.ts`](../apps/web/package.json)

Known unrelated workspace issue observed when running full web suite:
- [`npm --workspace @reup-douyin/web run test`](../apps/web/package.json) currently fails from pre-existing pathing in [`review-board.test.ts`](../apps/web/src/test/review-board.test.ts:37) (`apps/web/apps/web/...`).

## 9) Backend/API alignment decision

No backend code change required for Factor 3.
Current behavior in [`_build_item()`](../apps/api/src/services/capture_inbox_service.py:687) and [`CapturedItemResponse.hydrate_card_grid_metadata()`](../apps/api/src/schemas/capture_inbox.py:86) already preserves canonical duration/posted fields; upstream normalization hardening is sufficient for this scoped task.
