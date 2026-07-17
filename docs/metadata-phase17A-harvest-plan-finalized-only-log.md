# Metadata Phase 17A — Harvest Plan / Finalized-Only Capture Log

## Scope
- Stop normal Smart Capture from creating partial visible Capture Inbox / Tile Gallery items during profile scans.
- Add a backend Harvest Plan / Staged Scan endpoint that classifies profile-card videos without creating visible rows.
- Require finalized modal metadata before creating any new visible `CapturedItem` row in Smart Capture modal harvest.
- Keep the advanced/manual current-page capture path available for explicit operator use.

## Changes Implemented
1. Added `POST /douyin-extension/harvest-plan` schemas and route.
2. Added backend Harvest Plan classification for Douyin `aweme_id` values:
   - `new`
   - `incomplete`
   - `complete`
   - `skipped`
3. Harvest Plan returns `target_aweme_ids` based on mode:
   - `new_and_incomplete`
   - `new_only`
   - `refresh_all`
4. Harvest Plan returns `created_visible_item_count = 0` and does not persist `CapturedItem` rows.
5. Extended full-modal harvest request with `commit_policy`.
6. Added `finalized_only` behavior for unmatched modal payloads:
   - full metadata + integrity ok creates a visible item;
   - incomplete metadata creates no item and reports `finalized_metadata_required`.
7. Preserved existing-row modal updates when full modal metadata matches an existing `aweme_id`.
8. Carried profile-card evidence from Harvest Plan through Smart Capture state, runtime options, and full-modal harvest payloads.
9. Updated normal Smart Capture to call `/douyin-extension/harvest-plan`; the advanced/manual current-page capture action still calls `/douyin-extension/capture-current-page`.

## Finalized Metadata Gate
A new visible item requires:
- `aweme_id`;
- source/page URL;
- title/caption/description from profile-card evidence;
- thumbnail when profile-card evidence provides it;
- `duration_seconds > 0`;
- non-negative `like_count`, `comment_count`, `favorite_count`, and `share_count`;
- integrity status not marked `mismatch`.

`view_count` is intentionally not required in this phase.

## Verification Completed During Implementation
- API focused test module passed.
- Extension test chain passed, including TypeScript build and dist module resolution.

## Non-Goals Preserved
- No runner rewrite.
- No calibrated-points metric extraction changes.
- No broad Tile Gallery UI changes.
- No CDP/debug workflow reintroduction.
- No fake metrics.
- No visible item creation with missing mandatory finalized metadata.
