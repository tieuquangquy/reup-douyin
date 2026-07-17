# Phase 6J Runtime State Extraction Log

## Scope

Phase 6J replaces brittle primary visual DOM action-rail extraction for Douyin modal metadata with exact-aweme runtime state extraction in `apps/extension-douyin-capture`.

This change remains extension-only. It does not introduce a crawler, backend normalizer changes, captcha bypassing, fake metrics, database schema work, or publishing behavior.

## Root Cause

The visual right-rail/action-rail extractor was being used as the primary metadata source. On live Douyin modals the visual rail can be virtualized, hidden, reordered, compacted, or contaminated by nearby text nodes, causing missing or unreliable counts even when the exact aweme object is already present in runtime state, hydration state, or extension network caches.

## Implemented Sources

The extractor now prioritizes exact `aweme_id` runtime objects before weak visual fallbacks:

1. `exact_aweme_runtime_object`
2. `exact_aweme_script_hydration_object`
3. `exact_aweme_network_cache_object`
4. `combined_modal_text_fallback`
5. `visible_right_rail_fallback`
6. `missing`

Runtime scanning includes React fiber/props/internal-instance keys, Vue component state keys, selected window globals, script JSON/hydration literals, and known network caches.

## Safety Boundaries

The runtime walker is bounded with max depth, object count, array length, key count, `WeakSet` cycle protection, and a timeout. It skips functions and avoids walking the `Window` object directly except through selected runtime-like globals. Runtime evidence sanitization strips secret-like keys including cookies, auth tokens, headers, sessions, credentials, CSRF fields, and passwords.

## Field Mapping

Exact runtime aweme objects are mapped to canonical modal metrics:

- `statistics.digg_count` to `like_count`
- `statistics.comment_count` to `comment_count`
- `statistics.collect_count` to `favorite_count`
- `statistics.share_count` / `statistics.forward_count` to `share_count`
- `statistics.play_count` to `view_count`
- `video.duration`, `video.duration_millis`, `video.duration_ms`, `duration`, `duration_millis` to `duration_seconds`
- `desc` to `posted_text`
- `create_time` to `posted_at`

Higher-priority fields are not overwritten by lower-priority visual fallbacks. Visual right-rail values are retained only for fields missing from the exact runtime object.

## Probe And Harvest Behavior

Probe output now includes source priority, source used, runtime-found status, raw aweme keys, fallback status, rejection reason, and per-field confidence. Probe passes when `aweme_id`, `duration_seconds`, and `like_count` are present, especially from a runtime aweme object. Probe warns when only weak visual fallback is used and fails when the aweme id or duration is missing.

Full Modal Harvest uses the same extractor as Probe and attaches runtime aweme evidence as `raw_detail_aweme`, mapped canonical values as `raw_dom_detail_metrics`, and a Phase 6J evidence summary.

## Tests Added

`apps/extension-douyin-capture/src/modalHarvest.test.ts` now covers React fiber runtime objects, React props, Vue state, script hydration JSON, exact aweme id matching, stat mapping, duration mapping, bounded cyclic walking, secret stripping, runtime probe diagnostics, DOM-only fallback warnings, and Probe/Harvest extractor parity.

## Verification So Far

- `cd apps\\extension-douyin-capture && npx tsc -p tsconfig.json --noEmit` passed.
- `cd apps\\extension-douyin-capture && npx tsx src/modalHarvest.test.ts` passed.

Full extension test execution remains the final verification step.
