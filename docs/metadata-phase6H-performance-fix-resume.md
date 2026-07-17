# Phase 6H Performance Fix Resume

## Current target

Make Full Modal Harvest reliably populate `like_count` and, when structurally visible, `comment_count`, before running the full 49-video sweep.

## Root cause summary

- Modal extraction alone is not robust enough across all Douyin modal layouts for performance counts.
- The profile grid already contains a per-video like count keyed by exact `aweme_id`, but the harvester was not using it as a fallback.

## Intended post-fix behavior

- modal like count wins when confidently extracted
- exact profile-card fallback fills `like_count` when modal like is missing
- comment/share stay null when the action block is ambiguous
- duration behavior stays unchanged

## Operator-visible diagnostics to add

- `like_count_source`
- `comment_count_source`
- `share_count_source`
- `profile_card_like_text`
- `modal_action_blocks_found`
- `assigned_metric_node_ids`
- `rejected_metric_reasons`
- compact last harvested item summary in popup progress

## Verification plan

- extension typecheck
- extension tests with new profile-card fallback coverage
- backend focused normalizer test for source-label/performance capture if needed

## Implemented outcome

- modal like count still wins when confidently extracted
- exact profile-card fallback now fills `like_count` when modal like is missing
- `comment_count` and `share_count` remain null when the modal block is ambiguous
- `like_count_source` can now be `dom_detail_modal` or `dom_profile_card_fallback`
- duration conflict handling remains unchanged from the previous accuracy fix

## Exact live retest steps

1. `cd apps/extension-douyin-capture`
2. `npm run build`
3. Reload the unpacked extension.
4. Open the Douyin profile page and click the first video modal.
5. Start Full Modal Harvest.
6. After the first harvested item, click `Show Harvest Progress`.
7. Verify `Last harvested item` shows:
   - correct `aweme_id`
   - `duration_seconds`
   - `like_count`
   - `like_count_source`
   - `comment_count`
   - `share_count`
   - `extraction_warning`
8. Flush harvested metadata.
9. `cd ../api`
10. `python tests/metadata_phase5a_real_live_audit.py`
