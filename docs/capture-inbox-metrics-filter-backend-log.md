# Capture Inbox Metrics + Advanced Filter Backend Log

## Scope Lock
- Implement only backend/data/API wiring for Capture Inbox metrics visibility + advanced filter panel contract synced with `/intake` schema.
- Keep filtering in backend/API.
- Preserve raw staged items (no deletion/mutation from filter queries).
- No frontend redesign; only shared type/api contract alignment if needed.

## Required Audit Findings

### 1) `/intake` filter schema location and persistence
- Canonical intake request schema is [`IntakeDiscoverRequest`](apps/api/src/schemas/intake.py:12).
- Intake filter payload field is [`filter_config: FilterConfigRequest | None`](apps/api/src/schemas/intake.py:17).
- Canonical filter field definitions are in [`FilterConfigRequest`](apps/api/src/schemas/candidates.py:10), backed by dataclass [`FilterConfig`](apps/api/src/services/candidate_types.py:72).
- Preset persistence is workspace-scoped via [`IntakeSavedPreset.filter_config_json`](apps/api/src/models/intake.py:22) and unique per workspace/name in [`IntakeSavedPreset.__table_args__`](apps/api/src/models/intake.py:14).

### 2) Current Capture Inbox item API shape
- Capture Inbox item response already includes metrics in [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:47):
  - `view_count`, `like_count`, `comment_count`, `share_count`, `engagement_rate`.
- Intake evaluation fields already included in same response model (`intake_evaluation_status`, `matches_intake`, failed/missing/filter metadata) at [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:73).
- Web shared type already mirrors these metrics in [`CapturedItem`](apps/web/src/types/capture-inbox.ts:65).

### 3) Current backend Capture Inbox filtering/query path
- Route [`GET /capture-inbox/items`](apps/api/src/api/routes/capture_inbox.py:81) supports only:
  - `capture_session_id`, `status`, `limit`, `offset`.
- Service [`CaptureInboxService.list_items()`](apps/api/src/services/capture_inbox_service.py:494) only filters by `capture_session_id` and `status`.
- No backend search or advanced `/intake`-style filtering contract currently wired for item listing.

### 4) Current metrics availability on staged items
- Canonical metrics are normalized/stored in staged item `metadata_json` during build at [`_build_item()`](apps/api/src/services/capture_inbox_service.py:687), including:
  - `view_count`, `like_count`, `comment_count`, `share_count`, `engagement_rate`.
- Response hydrator maps them deterministically from metadata/raw payload in [`CapturedItemResponse.hydrate_card_grid_metadata()`](apps/api/src/schemas/capture_inbox.py:88).

## Reuse Decision
- Reuse `/intake` filter schema by accepting an aligned subset based on [`FilterConfigRequest`](apps/api/src/schemas/candidates.py:10).
- Implement Capture Inbox list filter schema as explicit derivative (field parity/mapping documented), not a divergent ad-hoc model.

## Planned Backend Wiring
1. Add Capture Inbox query schema with advanced filter payload aligned to intake fields.
2. Add deterministic query helper in `apps/api` service layer for backend filtering within capture session scope.
3. Extend list route contract to accept advanced filter payload.
4. Keep existing item response metrics fields and ensure test coverage for presence/null-safe behavior.

## Non-goals
- No extension-side filter execution.
- No raw item deletion on filter exclusion.
- No queue/review/publish scope changes.

## Implementation Completed
- Added advanced filter schema in [`CaptureInboxAdvancedFilterRequest`](apps/api/src/schemas/capture_inbox.py:171) with `/intake`-aligned threshold fields and range validation.
- Added explicit query payload contract in [`CaptureInboxItemQueryRequest`](apps/api/src/schemas/capture_inbox.py:209).
- Added backend query endpoint [`query_captured_items()`](apps/api/src/api/routes/capture_inbox.py:105) at `POST /capture-inbox/items/query`.
- Extended backend list/query logic in [`CaptureInboxService.list_items()`](apps/api/src/services/capture_inbox_service.py:495) with search + advanced filter arguments.
- Added backend advanced filter matcher in [`CaptureInboxService._matches_advanced_filter()`](apps/api/src/services/capture_inbox_service.py:1126), including date, metric ranges, speech, text-density cap, watermark/complexity/copyright excludes.
- Added alias compatibility for complexity exclusion (`exclude_high_complexity` + `exclude_high_processing_complexity`) in [`CaptureInboxAdvancedFilterRequest`](apps/api/src/schemas/capture_inbox.py:171) and matcher logic in [`_matches_advanced_filter()`](apps/api/src/services/capture_inbox_service.py:1126).
- Added web type contract in [`CaptureInboxItemQueryRequest`](apps/web/src/types/capture-inbox.ts:175) and [`CaptureInboxAdvancedFilter`](apps/web/src/types/capture-inbox.ts:155).
- Added web API helper [`queryCaptureInboxItems()`](apps/web/src/lib/api.ts:356).
- Added focused backend tests for advanced complexity filtering in [`DouyinExtensionCaptureServiceTests`](apps/api/tests/test_douyin_extension_capture_service.py:198).

## Verification Evidence
- Web typecheck passed via [`npm run -w apps/web typecheck`](apps/web/package.json:1).
- Backend test run passed via `python -m unittest tests.test_douyin_extension_capture_service -q` from [`apps/api`](apps/api):
  - `Ran 28 tests in 0.099s`
  - `OK`
- Note: direct `pytest` invocation was unavailable in this environment (`No module named pytest`), so repository-compatible `unittest` command was used.
