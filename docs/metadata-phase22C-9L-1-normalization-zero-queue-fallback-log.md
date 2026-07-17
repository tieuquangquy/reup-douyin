# Phase 22C-9L-1 Normalization Zero Queue Fallback Log

## Scope

Phase 22C-9L-1 is a surgical Scan Profile repair. It only touches post-probe normalization, DOM-probe/full-scroll candidate adapters, the DOM-probe queue fallback, diagnostics, tests, and phase notes.

## Audit Result

The normalized-count zero failure came from a split count contract:

- `profile_discovered_count` used count diagnostics such as `aweme_id_count`, `video_anchor_count`, and `video_link_count`.
- `profile_normalized_count` used `normalization.candidates.length`.
- The prior normalizer only consumed sample arrays and could be called with a full-scroll wrapper instead of the nested DOM Probe object.
- ID-only DOM Probe candidates were not guaranteed to synthesize a video `source_url`.

This allowed diagnostics to report 28 discovered aweme IDs while producing zero normalized queue candidates.

## Implementation

- Added DOM Probe full arrays capped to 500 in content and background fallback probe paths.
- Made DOM Probe normalization read full arrays and legacy sample arrays.
- Made normalization unwrap nested full-scroll diagnostics via `full_scroll_scan_22C9L.scrollDiagnostics.dom_probe_preflight`.
- Added ID-only candidate support with synthesized `https://www.douyin.com/video/<aweme_id>` source URLs.
- Restored the known-good DOM Probe queue fallback identity as `dom_probe_known_good_fallback_22C9K`.
- Added fallback-before-failure behavior when full-scroll returns zero candidates or zero targets.
- Added specific failure diagnostics for candidate-normalization and queue-persist failures.

## Diagnostics Added

- `scan_queue_builder_used`
- `scan_fallback_used`
- `scan_fallback_reason`
- `normalization_input_has_aweme_ids`
- `normalization_input_has_video_anchors`
- `normalization_input_has_modal_links`
- `normalization_candidate_array_count`
- `normalization_rejected_count`
- `normalization_reject_reasons`
- `normalization_rejected_samples`
- `probe_candidate_array_count`
- `probe_aweme_ids_array_count`
- `probe_video_anchors_array_count`
- `probe_modal_links_array_count`
- `queue_entry_sample`
- `queue_persist_result`
- `queue_persist_count`

## Expected Runtime Behavior

If full-scroll normalization returns zero while DOM Probe has usable aweme/video/modal candidates, Scan Profile should build the queue from the DOM Probe fallback, report `scanRounds = 1`, set `scan_stop` / stop reason to `queue_built_from_probe_fallback`, mark profile scan ready, and avoid generic `profile_scan_failed`.
