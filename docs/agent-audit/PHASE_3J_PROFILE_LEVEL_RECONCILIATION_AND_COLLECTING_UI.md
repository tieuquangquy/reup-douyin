# Phase 3J Profile-Level Reconciliation and Collecting UI

## Scope

Phase 3J fixes the backend reconciliation source used by the Douyin extension after Reset / Refresh Profile and stabilizes the extension primary collecting UI while safe-batch collection is actively running.

Non-goals:

- No scanner discovery changes.
- No auto-scroll changes.
- No profile discovery changes.
- No backend full-modal harvest schema changes.
- No loosening of backend validation or local payload guards.
- No changes to Phase 3E profile-safe capture-session verification.
- No queue, calibration, current-index, pending-item, or session reset behavior changes outside the requested reconciliation and UI state fixes.

## Root causes

### Backend reconciliation source mismatch

The web Capture Inbox card is session/detail/count based, while the extension reconciliation path was still limited to session-oriented APIs. That meant a Reset / Refresh Profile could under-count already captured same-profile videos when matching data existed in Capture Inbox but was outside the current extension session subset or lacked enough session-list proof for the old fallback path.

### Collecting UI flicker

Safe-batch collection writes multiple intermediate item checkpoints. Between individual item operations, the canonical primary-action selector could see a temporarily startable queue and render `Start Collecting` even though the safe-batch runner still owned the active collection lock.

## Backend endpoint

Phase 3J adds a safe profile-level endpoint for extension reconciliation:

```text
GET /douyin-extension/capture-inbox/profile-items?profile_url=<douyin-profile-url>&limit=1000
```

The endpoint returns only safe profile/item identifiers and status fields:

- profile identifier
- normalized profile URL
- `same_profile_only` scope
- captured item counts
- item id
- capture session id
- item status
- profile URL / normalized profile URL
- aweme aliases: `source_video_external_id`, `video_external_id`, `external_id`, `aweme_id`
- safe metadata status
- created/updated timestamps

The endpoint intentionally does not expose raw payloads, raw HTML, headers, cookies, tokens, debug payloads, enrichment JSON, or metadata JSON.

## Reconciliation behavior

The extension now prefers the profile-level Capture Inbox source before falling back to the older session/session-items source.

Profile rules:

- Same Douyin profile only.
- Normalize by `/user/<identifier>`.
- Ignore URL query parameters such as `modal_id`.
- Match scanned queue items primarily by `aweme_id`.
- Accept backend aweme aliases: `source_video_external_id`, `video_external_id`, and `external_id`.
- Mark `Already collected` only when a matching backend item id exists.
- Backend lookup failure remains non-blocking.

Expected reported-case behavior:

- If Capture Inbox has 15 same-profile backend items among 110 scanned profile items, the extension should reconcile about 15 already collected and leave about 95 pending/new, subject to exact scanned aweme membership.

## Phase 3N post-scan popup counter authority

After Scan Profile / Refresh Profile finalization, the popup's profile tiles are derived from the same Capture Inbox profile-card source as the backend card when that backend source is available. The extension calls `GET /douyin-extension/capture-inbox/profile-items?profile_url=<douyin-profile-url>&limit=1000` with the normalized `/user/<profile_identifier>` URL, so modal query parameters such as `modal_id` do not split the profile identity.

Counter rules:

- `Already collected` = Capture Inbox profile card `captured`.
- `Incomplete` = `max(0, captured - ready - dup - fail)`.
- `Need retry` = `fail` for the current MVP.
- `New` = `max(0, scanned_total - captured)`.
- `Queue` = `New` for the current MVP.

The reconciled snapshot diagnostics include the scanned total, backend captured/ready/duplicate/failed/incomplete counts, derived new/queue counts, backend endpoint, backend profile identifier, snapshot source, whether the snapshot was applied, whether local overwrite was blocked, and an explicit fallback reason when the backend profile source is unavailable. Scan finalization must not rewrite the five popup tiles back to local queue defaults after the backend card snapshot has been applied.

## Phase 3O mandatory durable post-scan counter snapshot

Phase 3O makes the post-scan counter authority durable instead of diagnostics-only. When Scan Profile / Refresh Profile succeeds, scan finalization stores `post_scan_counter_snapshot` on the canonical extension state. Scanner discovery still only supplies `scanned_total`; the backend Capture Inbox profile summary supplies `captured`, `ready`, `dup`, and `fail` from the profile-level card source.

Applied snapshot rules:

- `status: "applied"` only when the backend Capture Inbox profile source returns successfully.
- `source: "backend_capture_inbox_profile_summary"` for the authoritative backend profile-card source.
- `already_collected = backend.captured`.
- `incomplete = max(0, backend.captured - backend.ready - backend.dup - backend.fail)`.
- `need_retry = backend.fail`.
- `new = max(0, scanned_total - backend.captured)`.
- `queue = new`.

If the backend profile summary is unavailable, scan finalization stores an explicit `status: "backend_unavailable"` snapshot with `source: "local_fallback_backend_unavailable"` and nullable backend fields. The popup must not treat fallback backend counts as authoritative zeroes; it only prefers the durable snapshot for the five profile tiles when the snapshot status is `applied`.

For the reported case, the durable snapshot should contain `scanned_total: 111`, `backend_captured: 30`, `backend_ready: 19`, `backend_dup: 0`, `backend_fail: 0`, `already_collected: 30`, `incomplete: 11`, `need_retry: 0`, `new: 81`, and `queue: 81` before the operator clicks Start Collecting.

## Diagnostics

Phase 3J reconciliation diagnostics include:

- `backend_reconciliation_source`
- `backend_reconciliation_endpoint`
- `backend_reconciliation_profile_identifier`
- `backend_reconciliation_profile_scope`
- `backend_reconciliation_backend_profile_captured_count`
- `backend_reconciliation_backend_item_count`
- `backend_reconciliation_matched_count`
- `backend_reconciliation_unmatched_backend_count`
- `backend_reconciliation_unmatched_queue_count`
- `backend_reconciliation_current_session_only`
- `backend_reconciliation_used_capture_inbox_card_source`

The preferred source is `capture_inbox_profile_items` with endpoint `/douyin-extension/capture-inbox/profile-items` and `backend_reconciliation_current_session_only: "no"`.

## Collecting UI behavior

While the safe-batch runner is active and non-terminal, the canonical primary action remains stable:

- title: `Collecting videos`
- label: `Collecting videos...`
- enabled: `false`
- disabled reason: `Collection is already running.`

The footer Pause control remains the operator path for pausing where current semantics allow it. The primary action lock is preserved until terminal safe-batch states such as completed, user-paused, unrecoverable failure, or all queue completed.

## Tests and validation

Added/updated focused coverage:

- Backend route test for safe profile-items response aliases and redaction.
- Extension reconciliation test for preferred profile-level endpoint, aweme aliases, diagnostics, and same-profile counts.
- Readiness test for non-reentrant active collecting primary action.

Commands run:

```cmd
cd apps\extension-douyin-capture && npm run typecheck && npx tsx src/wholeProfileHarvest.readiness.test.ts && npx tsx src/wholeProfileHarvest.test.ts
```

Result: passed.

```cmd
cd apps\api && python -m pytest tests/test_douyin_extension_routes.py
```

Result: not runnable in the current Python environment because `pytest` is not installed.

```cmd
cd apps\api && set API_AUTH_REQUIRED=false&& python -m unittest tests.test_douyin_extension_routes
```

Result: passed.

## Manual validation checklist

1. Open the target Douyin profile.
2. In the extension, Reset without clearing calibration unless specifically testing calibration reset.
3. Refresh / Scan Profile.
4. Confirm diagnostics show `backend_reconciliation_source: capture_inbox_profile_items`.
5. Confirm `backend_reconciliation_current_session_only: no`.
6. Confirm `backend_reconciliation_used_capture_inbox_card_source: yes`.
7. Confirm `Already collected` aligns with the web Capture Inbox same-profile captured count.
8. Start safe-batch collection.
9. Confirm the primary action stays `Collecting videos...` and disabled between items.
10. Confirm Pause remains available in the footer and Continue Next 10 behavior is preserved after terminal batch states.
