# Phase 17B Modal Data Integrity Log

## Scope

Phase 17B enforces that Douyin modal metrics are never committed to the wrong video item. The implementation is scoped to the Douyin extension modal harvest flow and the API full-modal harvest ingest path.

## Root Cause

The modal harvest loop previously derived the current modal aweme id and then called the integrity assertion with that same value. That made the target check tautological: current modal id was effectively compared to itself instead of the expected queue target. The extension also queued an OK recent item before backend flush success.

## Changes

- Extension payload types now carry target, source video, page, modal, and raw metric identity fields.
- Modal harvest now selects the expected queue target first, navigates directly to it, clears stale extracted/current metrics on target transition, and only extracts after modal identity matches the target.
- Modal settle now requires stable modal identity, an active finite-duration metric probe, and two stable metric reads.
- Commit now goes through `commitValidatedModalMetrics`; failed integrity records `data_integrity_mismatch` and is not enqueued.
- Flush payloads include `commit_policy: finalized_only`.
- Recent OK rows are added only after backend flush success.
- Backend full-modal ingest validates top-level and raw metric identity fields before update/create and returns `data_integrity_mismatch` for identity failures.
- Added read-only duplicate modal metrics audit script.

## Verification

- API targeted unittest: passed.
- API compileall: passed.
- Extension typecheck: passed.
- Extension build: passed.
