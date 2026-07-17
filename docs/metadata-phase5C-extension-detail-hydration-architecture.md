# Metadata Phase 5C Extension Detail Hydration Architecture

## Goal

Collect `raw_detail_aweme` for discovered Douyin videos when feed/profile network evidence is absent.

## Execution flow

1. Grid discovery finds visible items with:
   - `aweme_id`
   - `source_url`
   - `share_url`
2. Existing feed/profile network evidence is still used first.
3. If capture is running in the content-script path, the extension runs detail hydration fallback:
   - fetch detail source URL
   - parse JSON or HTML-embedded JSON
   - recursively normalize aweme-like records
   - keep only exact-id matches
4. Exact matching detail items are passed into `extractor.ts`
5. Extractor builds final `VideoPayload` with:
   - `raw_network_aweme` if present
   - `raw_detail_aweme` if present
   - `raw_dom_snapshot`
   - `raw_evidence_summary`

## Detail source strategy

Priority:

1. `source_url`
2. `share_url`

Fetched with:

- credentials included
- redirect follow
- per-item timeout

## Detail parsing strategy

Supported:

- direct JSON response bodies
- HTML script tags with JSON
- balanced JSON literals inside script text

Each parsed root is sent through:

- `normalizeDouyinNetworkPayload(root, "detail_hydrate")`

That keeps:

- canonical duration/statistics extraction
- bounded raw evidence preservation
- secret-like key stripping

## Exact-id rule

Attach detail evidence only if:

- normalized `aweme_id` exactly equals the target discovered `aweme_id`

No matching by:

- title
- thumbnail
- index/order
- shared page text

## Timeout and concurrency

- default concurrency: `3`
- default timeout: `8000ms`
- failures are item-local
- capture continues even if some items fail hydration

## Diagnostics

Payload diagnostics now include:

- `detail_hydrate_attempted_count`
- `detail_hydrate_success_count`
- `detail_hydrate_failed_count`
- `detail_hydrate_timeout_count`
- `raw_detail_aweme_attached_count`

## Unchanged boundaries

This phase does not change:

- backend normalizer
- Capture Inbox UI
- filter policy
- backend hydration job

The backend remains the canonical place that turns raw detail evidence into final canonical metadata.
