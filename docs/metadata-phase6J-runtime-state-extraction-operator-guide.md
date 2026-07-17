# Phase 6J Runtime State Extraction Operator Guide

## Purpose

Phase 6J makes Douyin modal metadata extraction prefer exact aweme runtime state instead of brittle visual right-rail DOM text. This is intended to recover duration and engagement counts when the visible action rail is virtualized, hidden, compacted, reordered, or unreliable.

## How To Probe A Modal

1. Open Douyin in the browser profile used by the extension.
2. Open a video modal from a profile/grid page.
3. Use the extension action for Probe Current Modal Metrics.
4. Inspect the returned probe diagnostics.

## Successful Runtime Extraction

A healthy Phase 6J probe should show:

- `aweme_id` matching the current modal id or `/video/{aweme_id}` path.
- `source_priority_used` as one of:
  - `exact_aweme_runtime_object`
  - `exact_aweme_script_hydration_object`
  - `exact_aweme_network_cache_object`
- `source_used` as the concrete evidence location, for example `react_fiber_aweme_object`.
- `exact_aweme_runtime_found` as `true`.
- `raw_aweme_keys` containing safe top-level aweme keys.
- `duration_seconds` populated.
- `like_count` populated.
- `probe_status` as `PASS`.

## Fallback Behavior

If no exact aweme object is found, the extension may use fallback evidence:

- `combined_modal_text_fallback` for text/video-derived metadata.
- `visible_right_rail_fallback` for Phase 6I-H visible numeric-band/action-rail counts.

Fallback-only probes should be treated as weaker evidence. A probe that uses visual fallback can return `WARN` even if required fields exist.

## Failure Behavior

A probe should return `FAIL` when:

- The current aweme id cannot be detected.
- `duration_seconds` is missing.
- Required runtime statistics are missing and no reliable fallback can provide the minimum required fields.

## Full Modal Harvest Checks

After running Full Modal Harvest, inspect a harvested item payload. Phase 6J-compatible items should include:

- `raw_detail_aweme` containing sanitized exact runtime aweme evidence when found.
- `raw_dom_detail_metrics` containing mapped canonical fields such as `duration_seconds`, `like_count`, `comment_count`, `favorite_count`, and `share_count`.
- `raw_evidence_summary.has_runtime_aweme = true` when exact runtime/script/cache aweme evidence was found.
- `raw_evidence_summary.evidence_collection_version = phase6j_runtime_state_extraction`.

## Privacy And Safety Notes

Runtime evidence is sanitized before being attached to harvest payloads. Secret-like keys such as cookies, authorization headers, tokens, credentials, sessions, CSRF fields, and passwords are stripped. Runtime walking is bounded to avoid locking the page on large or cyclic application state.

## Live Retest Steps

1. Build or reload the extension after Phase 6J changes.
2. Open Douyin and navigate to the profile/grid containing the previously failing modal.
3. Open the target modal.
4. Run Probe Current Modal Metrics.
5. Confirm `aweme_id`, `duration_seconds`, and `like_count` are present.
6. Confirm `source_priority_used` is exact runtime/script/cache when available.
7. Run Full Modal Harvest for a small target count.
8. Confirm the harvested item includes `raw_detail_aweme`, mapped metrics, and Phase 6J evidence summary fields.
