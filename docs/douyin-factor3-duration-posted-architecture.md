# Douyin Factor 3 — Duration + Posted Architecture

Date: 2026-04-28
Scope: ONLY duration/posted normalization and display quality

## 1) Objective

Ensure `duration_seconds` / `duration_text` and `posted_at` / `posted_text` are:
- exact-id bound to the correct `aweme_id`
- source-prioritized correctly
- guarded against malformed values
- rendered cleanly without leaking junk values to operators

## 2) Canonical source priority

For each captured tile (`aweme_id`):
1. network JSON metadata with exact id match
2. detail-hydrate metadata with exact id match
3. same-item DOM fallback

This precedence is already implemented in [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:661) and must be preserved.

## 3) Field-level rules

### Duration

Canonical numeric field: `duration_seconds`
- Accept finite, non-negative values only.
- Normalize ambiguous source units conservatively.
- Reject impossible/malformed values rather than displaying wrong values.

Canonical text field: `duration_text`
- Prefer trusted network/detail text when valid pattern.
- Else use DOM-extracted duration text for same tile.
- Else derive from canonical `duration_seconds`.

### Posted

Canonical timestamp field: `posted_at`
- Accept only valid date values.
- Reject suspicious defaults (including fake/default midnight patterns already filtered in extractor path).
- Never allow cross-item mapping.

Display text field: `posted_text`
- Keep for operator context only.
- Must be validated; obvious numeric-noise values (e.g. `13.0`) are invalid and should not be rendered.

## 4) Layer responsibilities

### Extension (`apps/extension-douyin-capture`)

Primary owner of normalization and provenance:
- [`normalizeAwemeRecord()`](../apps/extension-douyin-capture/src/networkCache.ts:107)
- [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:661)
- [`extractDuration()`](../apps/extension-douyin-capture/src/extractor.ts:627)
- [`extractPosted()`](../apps/extension-douyin-capture/src/extractor.ts:636)
- [`validNetworkPostedAt()`](../apps/extension-douyin-capture/src/extractor.ts:899)

### API (`apps/api`)

Pass-through and persistence integrity:
- [`_build_item()`](../apps/api/src/services/capture_inbox_service.py:687)
- [`CapturedItemResponse.hydrate_card_grid_metadata()`](../apps/api/src/schemas/capture_inbox.py:86)

No broad normalization rewrite planned in backend for this factor.

### Web (`apps/web`)

Safe rendering only:
- [`resolveDuration()`](../apps/web/src/lib/captureInboxCanonical.ts:32)
- [`resolvePosted()`](../apps/web/src/lib/captureInboxCanonical.ts:39)

Minimal guard additions permitted for malformed `posted_text` suppression.

## 5) Provenance and diagnostics requirements

Keep provenance narrow and explicit for posted source:
- `network_json`
- `detail_hydrate`
- `dom_text`
- `fallback_none`

Do not introduce unrelated provenance states in this factor.

## 6) Test strategy

### Extension tests
- Assert exact-id binding remains strict for duration/posted.
- Add cases for malformed duration / posted values.
- Assert rejection of invalid posted strings and suspicious defaults.

### Frontend tests
- Add resolver case: invalid `posted_text` is suppressed to `Not captured` unless canonical `posted_at` exists.

### Backend tests
- Not required for this factor because backend normalization surface was not changed.

## 7) Implemented architecture outcomes

- Exact-id precedence preserved for duration/posted in [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:661).
- Network normalization guards implemented in [`networkCache` helper set](../apps/extension-douyin-capture/src/networkCache.ts:350) and mirrored in [`pageNetworkHook` helper set](../apps/extension-douyin-capture/src/pageNetworkHook.ts:318).
- Frontend fallback suppression implemented in [`validPostedText()`](../apps/web/src/lib/captureInboxCanonical.ts:173).
- No backend contract changes required; canonical fields remain pass-through safe in [`capture_inbox_service._build_item()`](../apps/api/src/services/capture_inbox_service.py:687).

## 8) Risk controls

- Wrong value is worse than missing: prefer `null` / `Not captured` to dubious values.
- No cross-item leakage under any fallback path.
- Keep changes local to duration/posted code paths.
