# Phase 7C Combined Modal Text Primary Fallback Log

## Scope

Phase 7C was limited to `apps/extension-douyin-capture` and extension tests/docs. No backend, normalizer, crawler, captcha bypass, or visual right-rail selector changes were included.

## Root Cause

CDP could be attached and collecting JSON responses while still finding no exact aweme object. In that state, modal extraction went directly to profile-card-like or visible right-rail fallback. The combined modal text already contained the exact visible action counts after the `连播` marker, but the extension did not parse that segment as a structured source and could therefore keep wrong/partial values like a profile-card `75000` like count.

## Implementation

- Added `parseCombinedModalActionText(text)` to parse only the text segment after `连播` and before stop markers such as `听抖音`, `@`, author/post markers, or posted-date text.
- The parser accepts compact action count tokens such as `829`, `6.6万`, `1.2w`, and `3k`.
- The parser requires exactly four count tokens and maps them to like, comment, favorite, and share.
- Integrated `combined_modal_text_fallback` into modal metrics before profile-card-like and visible right-rail fallbacks when no exact CDP/runtime/page-cache aweme metrics are available.
- Added combined text diagnostics to metrics/probe payloads: `combined_text_segment`, `combined_count_tokens`, and `extraction_mode`.
- Updated Probe PASS behavior so `combined_modal_text_fallback` is PASS when duration and all four action counts are present.
- Full Modal Harvest continues using the same extractor as Probe through `waitForCurrentModalMetrics`, so successful combined text fallback is included in `raw_dom_detail_metrics` and `raw_evidence_summary.evidence_sources`.

## Updated Source Priority

1. `cdp_network_aweme`
2. `cdp_runtime_aweme`
3. `page_network_cache_aweme`
4. `combined_modal_text_fallback`
5. `video_element_duration` plus profile-card-like fallback
6. `visible_right_rail_fallback`

## Verification

Targeted modal harvest tests were run with:

```cmd
cd apps\\extension-douyin-capture && npx tsx src\\modalHarvest.test.ts
```

Result: passed.
