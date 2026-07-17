# Phase 5D Backend Browser Hydration Architecture

## Problem
- Capture Inbox live sessions already persist `aweme_id`, `source_url`, `share_url`, and `raw_dom_snapshot`.
- Extension evidence is still failing to provide structured `raw_network_aweme` / `raw_detail_aweme`.
- As a result, duration and performance fields remain unhydrated.

## Canonical runtime reused
- `DouyinAccountConnection` remains the account model.
- Managed browser runtime remains the authenticated fetch path.
- Reuse:
  - `DouyinAccountService` for account selection, preflight, and auto-reopen.
  - `douyin_browser_context_registry` for managed browser page fetch.
  - `CaptureMetadataNormalizer` for canonical metadata derivation.

## Hydration algorithm
1. Select a target capture session (latest or explicit session id).
2. Resolve a browser-backed Douyin account and ensure the saved browser profile is available.
3. Select only incomplete captured items:
   - missing performance
   - missing processing-fit
   - or missing canonical duration/count fields
4. For each item:
   - use `source_url` if present, else `https://www.douyin.com/video/{aweme_id}`
   - fetch the detail page with the managed browser runtime
   - parse HTML / browser response documents for exact matching `aweme_id`
   - sanitize and bound the resulting aweme-like object
   - store it as `raw_detail_aweme`
   - update `raw_evidence_summary`
   - rerun `CaptureMetadataNormalizer`
   - persist refreshed canonical metadata/status fields
5. Continue per-item on failure; do not fail the whole session because one item fails.

## Parsing strategy
- Recursive search over embedded JSON and browser response documents.
- Exact match only:
  - `String(candidate.aweme_id).trim() === String(target_aweme_id).trim()`
- Preserve useful keys only:
  - `aweme_id`
  - `create_time`
  - `video`
  - `statistics`
  - `desc`
  - `author`
  - `share_info`
  - `text_extra`
  - `music`
- Remove secret-like keys and bound depth/array/string sizes.

## Persistence strategy
- Update `captured_items` canonical columns where derived:
  - `posted_at`
  - `duration_seconds`
- Update `metadata_json` with:
  - `raw_detail_aweme`
  - `raw_evidence_summary`
  - `posted_text`
  - `duration_text`
  - `view_count`
  - `like_count`
  - `comment_count`
  - `share_count`
  - `engagement_rate`
  - `*_source`
  - `metadata_status`
  - `time_status`
  - `performance_status`
  - `processing_fit_status`
  - missing-reason fields
  - `metadata_source_summary`
  - `last_metadata_hydrated_at`
  - hydration attempt/result metadata

## Operator path
- Narrow operator script, latest-session or explicit-session scoped.
- No frontend dependency for Phase 5D.
- Script:
  - `python scripts/hydrate_capture_session_metadata.py`
  - `python scripts/hydrate_capture_session_metadata.py --session-id <id>`
  - optional `--account-id`, `--limit`, `--timeout-seconds`, `--force`

## Safety controls
- Managed browser path is primary.
- Requested concurrency limit defaults to `2`.
- Effective runtime fetch concurrency is intentionally `1` for now because the managed browser runtime is a single shared local Playwright owner; Phase 5D keeps hydration deterministic and safe instead of issuing overlapping page mutations into the same profile runtime.
- Per-item timeout enforced.
- Per-item failure isolation.
- No cookie/token/header persistence.
- No index/title/thumbnail matching.

## What remains unchanged
- Extension remains unchanged.
- Capture Inbox UI remains unchanged.
- `CaptureMetadataNormalizer` remains the canonical metadata derivation path.
