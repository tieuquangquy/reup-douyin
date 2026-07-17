# Phase 22D-2 — Studio filters redesign for Douyin metadata log

## Summary

Phase 22D-2 redesigned the Capture Inbox Studio filter toolbar around practical Douyin review metadata while keeping the change frontend-scoped. The work updates search, item status filters, metadata filters, quick toggles, sorting, count diagnostics, frontend item types, and source-based tests.

## Scope

Touched apps/packages:

- `apps/web`
  - Capture Inbox page filter state, toolbar, filtering, and sorting.
  - Capture Inbox frontend item type contract.
  - Capture Inbox source tests.
- `docs`
  - Phase implementation and resume notes.

Non-goals honored:

- No extension crawler changes.
- No batch collection or item collection changes.
- No Capture Inbox item save logic changes.
- No Tile Gallery card layout redesign.
- No Advanced filters implementation.
- No data deletion, fake data, or hardcoded samples.

## Current Studio filters audit

The Studio filters are rendered by `StudioFilterToolbar` in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.

Before this phase, state was split across `statusFilter`, `operatorFilter`, `searchQuery`, `metadataFilter`, `sortMode`, `onlyActionable`, `onlyWithThumbnail`, and `hideDuplicates`. Item filtering happened in the `visibleItems` memo pipeline with item status, search, metadata bucket, quick toggles, duplicate hiding, then sort.

Old sort support was limited to `newest`, `ready-first`, and `needs-action-first`. Old metadata filters were broad backend buckets: `complete`, `partial`, `needs-metadata`, and `failed`, rather than concrete Douyin completeness checks. Old search missed `title`, `aweme_id`, profile fields, and video URL fields.

Frontend `CapturedItem` already had canonical core fields such as `caption`, `title`, `source_video_external_id`, `aweme_id`, `source_url`, `share_url`, `profile_url`, `duration_seconds`, `duration_text`, `posted_at`, `posted_text`, `posted_display`, `thumbnail_url`, and metrics. It did not yet type the Phase 22D-1 normalized fields used by the redesigned filters.

## New filter state model

The page now uses the Phase 22D-2 filter model values:

- `searchQuery: string`
- `itemStatus: "all" | "ready" | "needs_action" | "failed" | "duplicate" | "promoted"`
- `metadataFilter: "all" | "complete" | "missing_posted" | "missing_thumbnail" | "missing_duration" | "missing_metrics"`
- `onlyActionable: boolean`
- `onlyWithThumbnail: boolean`
- `hideDuplicates: boolean`
- `sort: "ready_first" | "recently_captured" | "newest_posted" | "oldest_posted" | "highest_views" | "highest_likes" | "highest_comments" | "highest_shares" | "highest_engagement" | "shortest_duration" | "longest_duration"`

A `StudioFilters` type was introduced to document this shape in the Capture Inbox page.

## Item status filter behavior

- `All`: shows all current base items.
- `Ready`: requires a ready/enriched item and matched intake.
- `Needs action`: includes actionable non-ready, non-promoted, non-duplicate items.
- `Failed`: includes failed items, filtered-out/evaluation-error intake states, or `matches_intake === false`.
- `Duplicate`: includes duplicate items.
- `Promoted`: includes promoted items.

The compact status strip remains connected to the same item status filter values.

## Metadata filter behavior

- `All metadata`: no metadata completeness constraint.
- `Complete`: uses `has_all_core_metadata` when available, otherwise falls back to posted + thumbnail + duration + any metric checks.
- `Missing posted`: uses normalized `has_posted` when available, otherwise falls back to posted fields.
- `Missing thumbnail`: uses normalized `has_thumbnail` plus the existing canonical thumbnail resolver so rejected placeholders remain excluded.
- `Missing duration`: uses normalized `has_duration` when available, otherwise duration fields.
- `Missing metrics`: uses normalized metric flags when available, otherwise exact/estimated views, likes, comments, or shares.

## Quick toggle behavior

- `Only actionable`: reuses the named `isActionableItem` predicate.
- `Only with thumbnail`: uses `hasUsableThumbnail`, which respects `has_thumbnail === false` and the canonical thumbnail resolver.
- `Hide duplicates`: continues to hide `DUPLICATE` items without mutating backend state.

## Sort behavior

The toolbar now exposes all required sort options:

- Ready first
- Recently captured
- Newest posted
- Oldest posted
- Highest views
- Highest likes
- Highest comments
- Highest shares
- Highest engagement
- Shortest duration
- Longest duration

Missing numeric/date values sort after known values, with recently captured as a stable fallback.

## Backward compatibility behavior

The frontend `CapturedItem` type now includes optional Phase 22D-1 normalized fields. Filters gracefully fall back to existing legacy fields if normalized booleans or normalized estimated views are missing.

This keeps existing staged items usable without requiring data migration or re-capture.

## Tests run while implementing

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npx tsc --noEmit -p apps/web/tsconfig.typecheck.json`
- Combined targeted run: `npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsc --noEmit -p apps/web/tsconfig.typecheck.json`

All targeted runs passed at the time this log was written.
