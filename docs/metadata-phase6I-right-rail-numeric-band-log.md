# Phase 6I-H Right-Rail Numeric Band Log

## Scope

Phase 6I-H replaces brittle Douyin modal action rail extraction that depended on icon semantics and text-node range geometry with visible right-rail numeric band extraction in `apps/extension-douyin-capture`.

## Root Cause

Douyin modal action rail markup can be obfuscated, nested, and portal-rendered. Icon nodes and text nodes may lack stable selectors, semantic labels, or reliable `Range` geometry. In live modal probes this caused text-node rects such as `0x0`, so comment, favorite, and share counts were missed even when visible in the UI.

## Implementation

- Added right-rail diagnostic types to `apps/extension-douyin-capture/src/types.ts`.
- Reworked `detectActionBlockCandidates()` in `apps/extension-douyin-capture/src/modalHarvest.ts` to use a right-side rail region instead of icon anchoring.
- Added visible element numeric label collection using element `getBoundingClientRect()` and exact compact numeric text.
- Added `document.elementsFromPoint()` sampling fallback across the rail band.
- Added y-order assignment for like, comment, favorite, and share.
- Preserved profile-card fallback only for `like_count`; profile grid numbers remain rejected for comment, favorite, and share.
- Added diagnostics for rail region, found labels, selected labels, assigned metrics, rejected examples, and extraction mode.

## Diagnostics

Probe and Full Modal Harvest now expose the same extractor diagnostics:

- `rail_region`
- `numeric_labels_found`
- `selected_rail_labels`
- `selected_rail_labels_with_rect`
- `assigned_metrics`
- `rejected_examples`
- `extraction_mode`

Extraction mode is `right_rail_numeric_band` when element geometry supplies labels, and `right_rail_element_from_point_fallback` when point sampling recovers the selected labels.

## Validation

Focused modal harvest tests pass with Phase 6I-H scenarios, including:

- visible labels `818`, `15`, `152`, `35` mapping to like/comment/favorite/share
- `elementsFromPoint()` recovery when queried element rects are zero
- bottom player time rejection
- caption/chapter number rejection
- profile grid numbers not used for comment/favorite/share
- only-like returning `WARN`
- four-label rail returning `PASS`
- Probe and Full Modal Harvest sharing the same extractor fields
