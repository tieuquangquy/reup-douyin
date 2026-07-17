# Metadata Status Phase 1 Log

## Scope

Phase 1 introduces a computed metadata status and evidence model for Capture Inbox item responses and compact web rendering. The model makes Time, Performance, and Processing fit diagnosable without changing extraction, metadata sourcing, or adding a hydration job.

## Touched Areas

- `apps/api`: response schema-level computed statuses and focused tests.
- `apps/web`: Capture Inbox item types and compact status rendering.
- `docs`: this implementation log and resume note.

## Explicit Non-Goals

- No extension extraction changes.
- No `pageNetworkHook` changes.
- No metadata sourcing changes.
- No Capture Inbox UI redesign.
- No metadata hydration worker/job implementation.
- No database migration for persisted status columns in Phase 1.

## Status Model

Item-level `metadata_status` values:

- `pending_hydration`: item has no captured metadata groups, no hard metadata failure, and hydration has not been attempted.
- `complete`: Time, Performance, and Processing fit are captured.
- `partial`: at least one metadata group is captured and at least one group is missing or pending.
- `missing`: no metadata group is captured after metadata has been attempted or canonical payload evidence exists.
- `failed`: hydration or metadata collection has a hard error marker.

Group-level status values for `time_status`, `performance_status`, and `processing_fit_status`:

- `captured`: required canonical evidence exists.
- `missing`: evidence is absent after metadata was captured/attempted.
- `failed`: hard metadata error applies to the item/group.
- `pending`: evidence is absent and hydration has not been attempted.

## Computation Rules

- Time is captured when `posted_at` exists or a reliable `posted_text` exists.
- Performance is captured when at least `view_count` or `like_count` exists. Other statistics remain evidence in the source summary when present.
- Processing fit is captured when `duration_seconds` exists, including zero.
- Item status is complete only when all three groups are captured.
- Item status is partial when at least one group is captured and at least one group is missing or pending.
- Item status is missing when none of the groups are captured and metadata has been attempted or canonical metadata evidence exists.
- Item status is pending hydration when none of the groups are captured and there is no attempted hydration/metadata evidence.
- Item status is failed when a hard item error or metadata hydration error marker exists.

## Evidence Fields

API responses expose:

- `metadata_missing_reason`
- `time_missing_reason`
- `performance_missing_reason`
- `processing_fit_missing_reason`
- `metadata_source_summary`
- `last_metadata_hydrated_at`

The first implementation computes these fields at response serialization time so old rows remain safe and do not require migration.

## Implementation Notes

The Phase 1 implementation should keep status derivation deterministic and local to Capture Inbox API serialization. Persisting durable hydration attempts, retries, and worker progress remains a later phase.
