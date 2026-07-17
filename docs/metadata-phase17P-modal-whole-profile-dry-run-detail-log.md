# Phase 17P Modal Whole Profile Dry-run Detail Log

## Scope

Phase 17P adds an isolated Dry-run first N target detail test after Modal Whole Profile Verify succeeds. The dry-run stays inside the extension beta test runtime and does not perform production harvest writes.

## Runtime Behavior

- Mode: `dry_run_first_n`.
- Default limit: `3` targets from the verified refresh-all target queue.
- Reuses an existing completed `douyinModalWholeProfileTestRun` when it has `targets.length > 0` and `resolved_profile_url`.
- If no verified targets exist, the normal verify scan and harvest-plan path runs first, then dry-run starts.

## Per-target Flow

1. Build direct target URL as `resolved_profile_url + ?modal_id=<aweme_id>`.
2. Navigate the active tab to that URL.
3. Wait for active tab `modal_id` to equal the target aweme id.
4. Settle and confirm the modal id remains stable.
5. Probe current modal metrics using the calibrated point detail extractor.
6. Validate target, before modal id, after modal id, and extracted aweme id integrity.
7. Store PASS or FAIL in `dry_run_results` and continue.

## No-backend-write Guarantee

Dry-run writes only `douyinModalWholeProfileTestRun`. It does not call `/douyin-extension/full-modal-harvest`, does not start Safe Runner, and does not write Smart Capture production state.

A local guard exposes `dry_run_backend_write_blocked` if a dry-run write path attempts a forbidden backend or production state destination.

## Summary Mapping Fix

The beta panel now treats `unknown` sentinel values as missing and falls back to diagnostics:

- Scan rounds: top-level value, else `diagnostics.rounds`, else `diagnostics.scan_rounds.length`.
- Last round new: top-level value, else last `diagnostics.scan_rounds[].new_count`.
- Scroll container: top-level status, else `diagnostics.scroll_container_found` or `diagnostics.selected_scroll_container`.
- Stop reason: diagnostics stop reason when no profile failure reason is active.
- Total found: top-level count, total cards, progress count, then diagnostics total.
