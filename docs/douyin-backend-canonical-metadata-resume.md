# Douyin Backend Canonical Metadata Resume

## Current objective

Continue the real Douyin visible profile-grid hard-fix on the backend by giving Capture Inbox one trustworthy canonical contract for thumbnail and metadata fields.

## Scope

Allowed:

- `apps/api` schemas, services, routes, and focused tests related to Douyin extension capture and Capture Inbox staging.
- Backend canonical metadata docs.

Not allowed:

- Capture Inbox UI redesign.
- Crawler implementation.
- Media download/video processing implementation.
- Fabricated metadata.
- Broad unrelated workflow rewrites.

## Audit status

Read and audited:

- `AGENTS.md`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/models/capture_inbox.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`

## Key findings

1. The backend already accepts many enriched extension fields, but status literals are too narrow and some new diagnostics are unmodeled.
2. Existing database columns are sufficient for narrow canonical persistence: `thumbnail_url`, `duration_seconds`, `posted_at`, source ids/URLs, readiness booleans, raw payload JSON, and metadata JSON.
3. `metadata_json` is the right narrow place for companion canonical fields such as `duration_text`, `posted_text`, metric counts/text, preview/media status strings, thumbnail source diagnostics, network source, and extraction diagnostics.
4. API responses already expose many canonical fields, but status literals and hydration should be made explicit and truthful.
5. Safe logging exists at coarse request/staging points, but needs clearer end-to-end canonical field checkpoints.

## Implementation checklist

1. Create docs first. Completed.
2. Update request schema to accept richer canonical fields and diagnostics. Completed.
3. Add canonical preview/media status helpers. Completed.
4. Update `_build_item()` normalization/persistence. Completed.
5. Update response schema status literals and hydration. Completed.
6. Add safe route/service logs. Completed.
7. Add focused backend tests. Completed.
8. Run backend verification. Completed with `unittest`; `pytest` is unavailable in the current Python environment.
9. Update docs with final results. Completed.

## Resume point

Part 2 backend canonical metadata work is complete. The next part can start from the API contract now exposing canonical `thumbnail_url`, duration, posted, metric, `preview_status`, and `media_status` fields directly through Capture Inbox responses, with raw JSON retained only as diagnostics.
