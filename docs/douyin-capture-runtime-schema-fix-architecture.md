# Douyin Capture Runtime Schema Fix Architecture

## Problem

The Capture Inbox path is now resilient to malformed captured items, but a true infrastructure failure can still occur before a structured response is returned. The most likely runtime failures are missing Capture Inbox tables, migration/model drift, stale backend code running on the configured port, or database persistence failure while creating the Capture Session or Captured Items.

## Runtime Boundary

`POST /douyin-extension/capture-current-page` should keep this sequence:

1. Validate extension request schema.
2. Reject secret-like payloads.
3. Classify the current Douyin page.
4. Stage a Capture Inbox session.
5. Persist captured items or item-level failure placeholders.
6. Return a structured capture response or a structured backend error detail.

## Schema Readiness Strategy

Capture Inbox schema readiness is checked at first use before writing the Capture Session. The check should verify:

- Required table `capture_sessions` exists.
- Required table `captured_items` exists.
- Required columns used by the ORM and route exist on both tables.

If a table is missing, the error code should be `schema_missing`. If tables exist but required columns are missing, the error code should be `migration_mismatch`.

## Error Contract

Backend errors returned to the extension and manager should use structured detail fields:

- `code`: stable machine-readable error code.
- `message`: actionable operator-facing summary.
- `stage`: precise stage where capture failed.
- `diagnostics_id`: stable id for correlating logs and UI reports.

Expected codes include:

- `schema_missing`
- `migration_mismatch`
- `capture_session_persist_failed`
- `captured_item_persist_failed`
- `backend_version_mismatch` if runtime/version evidence indicates an incompatible backend or extension build.

## Stage Mapping

- Schema readiness check: `capture_inbox_schema_readiness`
- Capture Session creation: `capture_session_persist`
- Captured Item write: `captured_item_persist`
- Final reconciliation/commit: `capture_session_reconcile`

## UI Projection

The manager and popup should not invent diagnostics. They should display backend-provided `detail.message` plus any `detail.code`, `detail.stage`, and `detail.diagnostics_id` returned by the API.

## Future SaaS Readiness

The readiness check is intentionally local and database-backed, but it does not hardcode deployment topology. A future SaaS deployment can replace first-use local checks with health endpoints, startup checks, or deployment gates while preserving the same structured error contract.
