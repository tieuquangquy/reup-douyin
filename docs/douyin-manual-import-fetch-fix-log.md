# Douyin Manual Import Fetch Fix Log

## Step: manual import account -> intake live fetch diagnostics

Started: 2026-04-23

Status: in progress

## Findings

- Manual session import persists a `DouyinAccountConnection` with `connection_source=manual_import` in `metadata_json`.
- `/intake` sends `douyin_account_connection_id` and `force_live_refresh` to `POST /intake/discover`.
- `IntakeDiscoveryService` resolves the selected account through `DouyinAccountService`, then builds a canonical `DouyinProfileAdapter` through `DouyinAccountService.build_douyin_adapter`.
- Exact reproduced 500 root cause:
  - `IntakeDiscoveryService.discover` called `SourceIngestService(self.db).ingest_profile(..., adapters={...})`.
  - `adapters` belongs to `SourceIngestService.__init__`, not `ingest_profile`.
  - Python raised `TypeError: SourceIngestService.ingest_profile() got an unexpected keyword argument 'adapters'`.
  - This happened before the error could be mapped into an `IntakeDiscoveryError`, so FastAPI returned a generic 500.
- The imported account currently stores a cookie-shaped value that appears to be a JSON browser-cookie export rather than a plain `Cookie` header. Runtime fetch currently forwards the decoded string as-is, which is fragile for manual imports.

## Decisions

- Keep one canonical intake/discovery pipeline.
- Fix live fetch wiring by passing the account-backed adapter into the `SourceIngestService` constructor.
- Normalize manual session input into a canonical Cookie header at account create/update/runtime resolution.
- Do not expose raw cookies in responses, logs, or docs.
- Map account/session/fetch failures into specific `IntakeDiscoveryError` codes so `/intake` does not show unexplained 500s.

## Files Touched

- Pending.

## Verification Notes

- Reproduced generic 500 through direct service call and `POST /intake/discover`.
- Verification after implementation must include unit tests and a live route call that returns a structured diagnostic instead of a generic 500.
