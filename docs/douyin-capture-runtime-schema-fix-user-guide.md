# Douyin Capture Runtime Schema Fix User Guide

## What This Fix Addresses

If the Douyin extension can connect to the backend and detect the active Douyin tab, but capture fails with a generic backend HTTP 500, the problem is likely in the backend Capture Inbox runtime rather than the browser extension payload.

This fix makes those failures explicit. Instead of a generic 500, the popup and manager should show a backend-provided message with a code, stage, and diagnostics id when available.

## Expected Operator Messages

### `schema_missing`

Meaning: the backend database does not contain one or both Capture Inbox tables.

Recommended action:

1. Stop the running backend.
2. Apply migrations from `apps/api` with Alembic.
3. Restart the backend process used by the extension.
4. Run extension connection check again, then capture again.

### `migration_mismatch`

Meaning: Capture Inbox tables exist, but required columns are missing. The backend code and database migration state do not match.

Recommended action:

1. Apply the latest migrations.
2. Confirm the backend process was restarted after code changes.
3. Retry capture.

### `capture_session_persist_failed`

Meaning: the backend could not create or update the Capture Session row.

Recommended action:

1. Check backend logs using the diagnostics id shown in the popup or manager.
2. Confirm database connectivity and migration state.
3. Retry after the backend is restarted and migrations are current.

### `captured_item_persist_failed`

Meaning: the Capture Session was created, but one or more captured item rows could not be persisted.

Recommended action:

1. Use the diagnostics id to inspect backend logs.
2. Review the Capture Inbox session if it was created.
3. Retry capture after resolving the persistence issue.

### `backend_version_mismatch`

Meaning: the extension and backend runtime are not aligned, or the extension is connected to a stale backend process.

Recommended action:

1. Restart the backend on the configured extension API port.
2. Rebuild/reload the extension if required.
3. Run the extension connection check and confirm the expected backend extension version.

## Verification Checklist

- Backend process restarted on the active API port.
- Latest migrations applied.
- Extension connection check reports compatible backend/extension versions.
- Capture returns either structured success or a structured backend error with `code`, `stage`, and `diagnostics_id`.
