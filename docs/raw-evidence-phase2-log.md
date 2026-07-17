# Phase 2 Raw Evidence Collection Log

## Scope

This Phase 2 task implements raw evidence collection from the Douyin extension so the backend can later normalize Time, Performance, and Processing fit fields reliably.

Allowed touch points:

- `apps/extension-douyin-capture`
- minimal `apps/api` request schema and staging persistence
- Phase 2 docs/tests

## Explicit Non-Goals

- No UI redesign or Capture Inbox filter changes.
- No final canonical backend normalizer.
- No hydration job.
- No attempt to fix every existing canonical metadata gap.
- No invented metadata values.
- No index/title/thumbnail/order-based evidence matching.

## Phase 2 Evidence Contract

Each captured video item may carry these raw evidence fields:

- `raw_network_aweme`: a bounded raw aweme-like object intercepted from Douyin network JSON where `aweme_id` exactly matches the item.
- `raw_detail_aweme`: a bounded raw detail/hydrate/share-page aweme-like object where `aweme_id` exactly matches the item, if available.
- `raw_dom_snapshot`: item-local DOM evidence captured from the card/link associated with the exact discovered video link.
- `raw_evidence_summary`: compact diagnostics describing which evidence sources are present and which top-level raw keys were retained.

The extension remains an evidence collector, not the source of final business truth. Phase 3 backend normalization is responsible for choosing canonical `posted_at`, `duration_seconds`, counts, sources, and group statuses.

## Exact-ID Matching Rules

Evidence may attach only when one of these is true:

1. A network JSON object has `aweme_id === discovered.aweme_id`.
2. A detail/hydrate object has `aweme_id === discovered.aweme_id`.
3. A DOM snapshot is built from the local card containing the exact discovered link.

Evidence must not attach by:

- visible index
- title text
- thumbnail URL
- response/list order
- shared grid wrapper text
- page-wide DOM blob

## Bounded Raw Object Strategy

The extension stores only bounded evidence objects, not full responses:

- Keep the aweme-like object itself, not enclosing response payloads.
- Preserve useful original keys such as `aweme_id`, `create_time`, `statistics`, `video`, `desc`, `author`, and `share_info` when present.
- Truncate long strings.
- Cap arrays, including nested URL lists.
- Cap recursion depth and object key counts.
- Drop secret-like keys, headers, cookies, authorization tokens, and credentials.
- Prefer `null` when evidence is absent instead of inventing values.

The backend also persists only what the extension submits and does not interpret these raw fields as canonical truth in Phase 2.

## API Staging Strategy

`apps/api` accepts the new raw evidence fields on `DouyinExtensionVideoPayload`. `CaptureInboxService._build_item` persists raw evidence into staged item metadata/raw payload for later Phase 3 normalization. Old rows remain safe because fields are optional.

List/detail response behavior is not redesigned in this phase. Evidence is bounded before submission to avoid storing broad raw page/network blobs.

## Verification Plan

Focused tests should cover:

- network normalization preserves bounded raw aweme evidence by exact `aweme_id`
- detail evidence remains separate from network evidence
- DOM snapshot is item-local and includes visible text/link/image/data-attribute evidence
- mismatched network/detail IDs do not attach
- API schema accepts raw evidence fields
- staging persists raw evidence fields without normalizing final truth
