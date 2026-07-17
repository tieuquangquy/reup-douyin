# Metadata Phase 5A-R Real Live Acceptance Resume

## Current step

- Build and run the live-only acceptance audit against the latest real Capture Inbox session.

## Done

- Read repo instructions and relevant API files.
- Confirmed effective backend DB source from `apps/api/.env`.
- Verified PostgreSQL contains real `capture_sessions` and `captured_items` rows.
- Verified `apps/api/data/reup_douyin.db` is not the live source for this audit.
- Identified latest real session:
  - `capture_session_id`: `7a0084ad-20a7-4135-a6e1-db6f847e87af`
  - live item count baseline: 49
- Identified canonical metadata status derivation in `apps/api/src/schemas/capture_inbox.py`.

## In progress

- None

## Final outcome

- Mode: `LIVE_DATA_FOUND`
- Real source used: PostgreSQL from `apps/api/.env`
- Latest session inspected: `7a0084ad-20a7-4135-a6e1-db6f847e87af`
- Total live items: `49`

### Metadata status distribution

- complete: `0`
- partial: `48`
- missing: `1`
- pending_hydration: `0`
- failed: `0`
- unknown/null: `0`

### Usability verdict

- Time: `usable` (`98.0%`)
- Performance: `not usable` (`0.0%`)
- Processing fit: `not usable` (`0.0%`)

## Next exact task

- Move to the next boundary: `extension evidence collection fix`

## Key files to continue

- `apps/api/tests/metadata_phase5a_real_live_audit.py`
- `apps/api/tests/test_metadata_phase5a_real_live_audit.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/models/capture_inbox.py`
- `apps/api/src/core/settings.py`
- `apps/api/src/db/session.py`
- `docs/metadata-phase5A-real-live-acceptance-log.md`
