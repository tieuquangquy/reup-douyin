# Capture Current Page 422 Resume

Date: 2026-04-29
Status: Completed

## Scope lock

- One narrow task: fix backend 422 for extension current-tab capture request only.
- In-scope files: [`apps/extension-douyin-capture`](apps/extension-douyin-capture), [`apps/api`](apps/api), focused docs/tests.
- Out-of-scope: popup UX redesign, broad pipeline refactor, unrelated backend systems.

## Root-cause summary (confirmed)

- 422 occurs at request schema validation for [`DouyinExtensionCaptureRequest`](apps/api/src/schemas/douyin_extension.py:197), not at later domain staging.
- Extension sends literals from [`VideoPayload`](apps/extension-douyin-capture/src/types.ts:79) and direct path builder [`buildCanonicalVideoPayload()`](apps/extension-douyin-capture/src/popupTransport.ts:384):
  - `duration_source`/metric sources use `"dom_text"`
  - `engagement_rate_source` uses `"derived_from_canonical_counts"`
- Backend schema currently expects different enum literals in [`DouyinMetricSource`](apps/api/src/schemas/douyin_extension.py:50), [`DouyinDurationSource`](apps/api/src/schemas/douyin_extension.py:51), [`DouyinEngagementRateSource`](apps/api/src/schemas/douyin_extension.py:52).

## Implementation summary

1. Updated schema literals in [`apps/api/src/schemas/douyin_extension.py`](apps/api/src/schemas/douyin_extension.py:50) through [`DouyinEngagementRateSource`](apps/api/src/schemas/douyin_extension.py:52):
   - added `"dom_text"` for metric and duration sources,
   - added `"derived_from_canonical_counts"` for engagement-rate source.
2. Added focused test [`test_video_payload_accepts_extension_dom_text_and_canonical_engagement_literals()`](apps/api/tests/test_douyin_extension_capture_service.py:138).
3. Executed targeted unittest checks for both new acceptance coverage and existing staging metadata behavior.
4. Updated diagnosis log with changed files and verification evidence.
