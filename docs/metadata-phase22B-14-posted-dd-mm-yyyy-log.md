# Phase 22B-14 Posted dd/mm/yyyy Log

## Scope
- Implement Phase 22B-14 only.
- Normalize Douyin posted metadata into `dd/mm/yyyy` display format for Capture Inbox consumption.
- Preserve original Chinese relative/raw posted text such as `昨天`, `刚刚`, and `2天前` in a separate raw field.
- Propagate `posted_text_raw`, `posted_at`, `posted_display`, `posted_source`, and `posted_parse_confidence` through extension payloads, backend persistence, and Capture Inbox response hydration.
- Keep changes scoped to metadata flow; do not redesign Capture Inbox UI or unrelated workflows.

## Changes Applied
- [`extractDouyinPostedMetadataFromText()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:181) now returns raw text, parsed ISO time, display text, source, and parse confidence, while [`formatDateDdMmYyyy()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:304) formats dates as `dd/mm/yyyy` using Asia/Shanghai-aware date parts.
- [`WholeProfileHarvestMetrics`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:206), [`RawDomDetailMetrics`](apps/extension-douyin-capture/src/types.ts:142), [`VideoPayload`](apps/extension-douyin-capture/src/types.ts:559), and [`HarvestPlanProfileCardEvidence`](apps/extension-douyin-capture/src/types.ts:705) now carry `posted_text_raw` and `posted_display` in addition to parsed timestamp and provenance fields.
- [`buildRawEvidenceSummaryForCanonicalHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:484) now records `posted_text_raw` and `posted_display` in both metrics and profile-card snapshot output.
- [`buildCaptureInboxItemPayload()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:558) now preserves raw posted text, promotes parsed dates into display-ready `posted_text`, emits `posted_display`, and keeps raw-only text unchanged when no confident date parse exists.
- [`DouyinExtensionRawDomDetailMetrics`](apps/api/src/schemas/douyin_extension.py:138), [`DouyinExtensionVideoPayload`](apps/api/src/schemas/douyin_extension.py:205), and [`DouyinExtensionHarvestPlanProfileCardEvidence`](apps/api/src/schemas/douyin_extension.py:381) now accept the new posted raw/display fields from the extension.
- [`_profile_card_evidence_by_aweme_id()`](apps/api/src/services/douyin_extension_capture_service.py:1068) and [`_apply_modal_harvest_to_item()`](apps/api/src/services/douyin_extension_capture_service.py:1151) now persist `posted_text_raw`, `posted_display`, and `posted_parse_confidence`, while keeping `posted_text` display-friendly for downstream consumers.
- [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:28) now hydrates `posted_text_raw` and `posted_display`, and maps response [`posted_text`](apps/api/src/schemas/capture_inbox.py:49) to display text first so Capture Inbox receives `dd/mm/yyyy` without a frontend redesign.

## Regression Coverage Added
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) now asserts parsed dates become display-ready `posted_text`, raw posted text is preserved separately, and raw-only relative text still flows unchanged when no parsed date exists.
- [`apps/api/tests/test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py) now asserts finalized-only ingest persists `posted_text_raw`, `posted_display`, `posted_parse_confidence`, and exposes display-ready `posted_text` with raw text preserved in the Capture Inbox response model.

## Validation Notes
- Validation commands have not been run yet in this phase.
- Next validation should include focused extension tests, extension typecheck/build, and backend unit coverage for the updated schema/service flow.
