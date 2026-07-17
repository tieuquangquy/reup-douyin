# Douyin Identity Fan-out Fix Architecture

## Problem

The Capture Inbox pipeline must not allow one network payload to fan out into multiple distinct captured videos. The observed failure pattern was several different video IDs showing the same thumbnail, title, posted timestamp, stats, or metadata. This is an identity-boundary problem, not a visual rendering problem.

## Authoritative Identity Model

`aweme_id` is the only authoritative per-video identity for extension item-level joins.

### DOM Input

The DOM stage extracts visible cards into lightweight records:

- `aweme_id` derived from the visible `/video/<id>` URL.
- `source_video_url` from the anchor href.
- DOM fallback title/text.
- DOM fallback thumbnail candidates.
- DOM fallback duration, posted text, and metric text.
- Visible order for diagnostics only.

DOM records with missing or invalid `aweme_id` do not receive guessed network metadata.

### Network Input

The network stage normalizes aweme-like JSON records into network metadata only when a non-empty `aweme_id` exists. Records without `aweme_id` are not canonical items and cannot be merged into visible DOM cards by index, batch position, profile URL, share URL alone, title, or thumbnail URL.

### Canonical Extension Storage

The extension uses an ID-keyed canonical model:

```ts
Map<aweme_id, CanonicalItem>
```

Each canonical item owns exactly one identity. Network and DOM fields merge into that item only when they share the same `aweme_id`.

## Merge Rules

Allowed merge:

- `dom.aweme_id === network.aweme_id`
- both IDs are non-empty strings

Rejected merge:

- one side is missing an ID
- IDs differ
- identity would be inferred from profile URL, share URL, source URL alone, index, list position, loop order, title, thumbnail URL, or object position

When a merge is rejected, the DOM record can still be emitted with DOM fallback fields, but network-backed fields must not be copied onto it.

## Field Provenance

Captured payloads carry safe provenance fields:

- `thumbnail_source = network_json | dom_fallback | detail_hydrate`
- `posted_source = network_json | dom_text | fallback_none`

Existing fields such as `thumbnail_source_type` and `thumbnail_source_types` remain for compatibility and card candidate diagnostics.

## Anti-fan-out Safeguards

### Merge Guard

The merge helper validates identity internally. The call site also uses an ID-keyed map, but correctness no longer depends only on call-site discipline.

### Reference Safety

Network metadata is cloned before merge, and `url_list` arrays are cloned when merging cache entries. One canonical item should not reuse another item's mutable array/object reference.

### Suspicious Duplicate Metadata

When different `aweme_id` values produce the same network-backed metadata signature, the pipeline emits a safe warning code:

```text
suspicious_duplicate_payload_mapping
```

This diagnostic uses safe counts/signatures only and does not log cookies, auth tokens, credentials, private paths, or excessive raw payloads.

### Posted-at Guard

Network `posted_at` values are accepted only when they parse as real timestamps and are not default midnight placeholders. DOM visible posted text can remain as text provenance even when a parsed timestamp is rejected.

## Backend Boundary

The backend preserves one staged item per payload identity and avoids cross-item overwrite during normalization. It now:

- prefers explicit `aweme_id` for `source_video_external_id`;
- preserves per-item raw payload and metadata objects;
- persists `thumbnail_source`, `posted_source`, and `network_source` into metadata;
- exposes provenance fields through captured item response schemas;
- adds a batch-level warning when distinct external IDs share suspicious network-backed metadata signatures.

## Frontend Boundary

The frontend renders each backend item by stable backend item `id`, with item-local metadata resolution. It does not key cards by array index, thumbnail URL, or `aweme_id`. Details, deletes, updates, selection, and focus operate by backend item `id` and resolve the selected item record each render.

Safe thumbnail debug logs include:

- backend item ID;
- source video external ID;
- `aweme_id`;
- thumbnail provenance;
- posted provenance;
- network source indicator;
- thumbnail availability booleans.

## Verification Coverage

The implemented architecture is covered by:

- extension source/compile tests for canonical map, merge guard, provenance, diagnostics, and build output;
- backend tests for provenance schema persistence and suspicious duplicate fan-out warning codes;
- frontend tests for stable tile keying, safe debug identity/provenance fields, and item-local resolver behavior across two distinct items;
- web typecheck.

## Non-goals

- No UI redesign.
- No crawler, downloader, video processor, scoring, queue, or worker implementation.
- No production database schema changes.
- No auto-publish integration.
