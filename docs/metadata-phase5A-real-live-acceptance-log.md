# Metadata Phase 5A-R Real Live Acceptance Log

## Scope

- Requested scope: Phase 5A-R only.
- Goal: run the Capture Inbox metadata acceptance audit against the latest real capture session.
- Hard rule: no fixture, demo, or test-data fallback.
- Non-goals:
  - no hydration job
  - no extension change
  - no backend normalizer change
  - no frontend/UI redesign

## Initial audit findings

### Real live data source

- Runtime settings source: `apps/api/.env`
- Effective database target: PostgreSQL on `localhost:5432`, database `reup_douyin`
- Confirmed live tables and row counts from PostgreSQL:
  - `capture_sessions`: 1
  - `captured_items`: 49

### Rejected non-live candidate

- Checked SQLite candidate: `apps/api/data/reup_douyin.db`
- Result:
  - `capture_sessions`: table missing
  - `captured_items`: table missing
- Conclusion: this SQLite file is not the real Capture Inbox source used by the running local backend for this audit.

### Why prior Phase 5A fell back

- Previous Phase 5A relied on the SQLite candidate path and could not find usable live Capture Inbox rows there.
- That made the audit ambiguous and it fell back to fixture-based status tests.
- Phase 5A-R corrects this by auditing the actual configured PostgreSQL source directly.

## Latest live session discovery

- Latest real `capture_session_id`: `7a0084ad-20a7-4135-a6e1-db6f847e87af`
- Latest session status at discovery time: `READY_FOR_REVIEW`
- Latest session capture id: `efe44110-179d-473c-818f-93d69963e553`

## Implementation approach

- Build a live-only audit helper under `apps/api`.
- Reuse canonical ORM + `CapturedItemResponse` hydration logic to derive:
  - `metadata_status`
  - `time_status`
  - `performance_status`
  - `processing_fit_status`
  - missing reasons
  - `raw_evidence_summary`
- If no real rows exist, return `LIVE_DATA_NOT_FOUND` and stop without fallback.

## Files touched

- `docs/metadata-phase5A-real-live-acceptance-log.md`
- `docs/metadata-phase5A-real-live-acceptance-resume.md`
- `apps/api/tests/metadata_phase5a_real_live_audit.py`
- `apps/api/tests/test_metadata_phase5a_real_live_audit.py`

## Live audit run

### Live data source used

- Source kind: PostgreSQL
- Settings source: `apps/api/.env`
- Host: `localhost`
- Port: `5432`
- Database: `reup_douyin`

### Latest real session inspected

- `capture_session_id`: `7a0084ad-20a7-4135-a6e1-db6f847e87af`
- `capture_id`: `efe44110-179d-473c-818f-93d69963e553`
- session status: `READY_FOR_REVIEW`
- created at: `2026-04-29T18:23:21.258777+00:00`
- total live items: `49`

## Metadata status distribution

| metadata_status | count | pct |
|---|---:|---:|
| complete | 0 | 0.0% |
| partial | 48 | 98.0% |
| missing | 1 | 2.0% |
| pending_hydration | 0 | 0.0% |
| failed | 0 | 0.0% |
| unknown/null | 0 | 0.0% |

## Field coverage

| Field | Present | Total | Coverage |
|---|---:|---:|---:|
| posted_at | 47 | 49 | 95.9% |
| posted_text | 48 | 49 | 98.0% |
| time_status=captured | 48 | 49 | 98.0% |
| duration_seconds | 0 | 49 | 0.0% |
| duration_text | 0 | 49 | 0.0% |
| processing_fit_status=captured | 0 | 49 | 0.0% |
| view_count | 0 | 49 | 0.0% |
| like_count | 0 | 49 | 0.0% |
| comment_count | 0 | 49 | 0.0% |
| share_count | 0 | 49 | 0.0% |
| engagement_rate | 0 | 49 | 0.0% |
| performance_status=captured | 0 | 49 | 0.0% |

## Raw evidence coverage

| Evidence | Present | Total | Coverage |
|---|---:|---:|---:|
| raw_network_aweme | 0 | 49 | 0.0% |
| raw_detail_aweme | 0 | 49 | 0.0% |
| raw_dom_snapshot | 49 | 49 | 100.0% |
| raw_evidence_summary | 49 | 49 | 100.0% |
| raw_evidence_summary.has_network_aweme | 0 | 49 | 0.0% |
| raw_evidence_summary.has_detail_aweme | 0 | 49 | 0.0% |
| raw_evidence_summary.has_dom_snapshot | 49 | 49 | 100.0% |

## Sample item diagnostics

### 1) Best metadata item

- item id: `9311a4a0-0f92-4514-8e04-97c0cb9e6ec0`
- aweme_id / source_video_external_id: `7623101429737213226`
- metadata_status: `partial`
- time: `captured` / missing reason: none
- performance: `missing` / `No view_count or like_count captured.`
- processing fit: `missing` / `No duration_seconds captured.`
- posted_at / posted_text: `2026-09-06T17:00:00+00:00` / `9.7`
- duration_seconds / duration_text: `null` / `null`
- view_count / like_count / comment_count / share_count: `null / null / null / null`
- raw_evidence_summary: `{ has_network_aweme: false, has_detail_aweme: false, has_dom_snapshot: true }`

### 2) Representative partial item

- item id: `7f652cfa-9e1f-4335-877e-e2c77c4c7065`
- aweme_id / source_video_external_id: `7621768123175210282`
- metadata_status: `partial`
- time: `captured`
- performance: `missing`
- processing fit: `missing`
- posted_at / posted_text: `2026-09-07T17:00:00+00:00` / `9.8`
- raw_evidence_summary: `{ has_network_aweme: false, has_detail_aweme: false, has_dom_snapshot: true }`

### 3) Needs metadata / missing item

- item id: `80f2ea76-01a3-4083-9480-4a672e3de768`
- aweme_id / source_video_external_id: `7632753242501319972`
- metadata_status: `missing`
- time: `missing` / `No posted_at or reliable posted_text captured.`
- performance: `missing` / `No view_count or like_count captured.`
- processing fit: `missing` / `No duration_seconds captured.`
- posted_at / posted_text: `null` / `null`
- raw_evidence_summary: `{ has_network_aweme: false, has_detail_aweme: false, has_dom_snapshot: true }`

### 4) Additional live partial sample

- item id: `024ed79c-56de-4d9b-9c1e-8666edb9a5ff`
- aweme_id / source_video_external_id: `7626371492074310975`
- metadata_status: `partial`
- posted_at / posted_text: `2026-09-07T17:00:00+00:00` / `9.8`
- raw_evidence_summary: `{ has_network_aweme: false, has_detail_aweme: false, has_dom_snapshot: true }`

### 5) Additional live partial sample

- item id: `08ba67aa-0862-4071-9821-b8f5a5e0c01c`
- aweme_id / source_video_external_id: `7621228840903347483`
- metadata_status: `partial`
- posted_at / posted_text: `2026-09-07T17:00:00+00:00` / `9.8`
- raw_evidence_summary: `{ has_network_aweme: false, has_detail_aweme: false, has_dom_snapshot: true }`

### Not present in latest live session

- complete item: none
- failed item: none

## Usability verdict

- Time: `usable`
  - threshold: `>= 80%`
  - observed: `98.0%` (`posted_at` or `posted_text`)
- Performance: `not usable`
  - threshold: `>= 70%`
  - observed: `0.0%` (`view_count` or `like_count`)
- Processing fit: `not usable`
  - threshold: `>= 80%`
  - observed: `0.0%` (`duration_seconds` or `duration_text`)

## Root cause boundary from live evidence

- This is not a fixture problem anymore.
- This latest real session shows:
  - strong DOM snapshot coverage
  - near-complete time capture
  - zero structured `raw_network_aweme`
  - zero structured `raw_detail_aweme`
  - zero duration/performance usable fields
- The immediate boundary is upstream evidence collection, not hydration-job implementation.

## Exact next recommended boundary

- `extension evidence collection fix`
- Reason:
  - without real `raw_network_aweme` or `raw_detail_aweme`, the current live session cannot support duration/performance usability no matter how the acceptance audit is computed.

## Tests run

- `python -m unittest tests.test_metadata_phase5a_real_live_audit tests.test_capture_inbox_metadata_status`
- `python tests/metadata_phase5a_real_live_audit.py`

## Status

- Live source audit: complete
- Live-only helper: complete
- Real metrics run: complete
- Final acceptance verdict: complete
