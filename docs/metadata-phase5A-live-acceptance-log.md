# Metadata Phase 5A Live Acceptance Audit Log (Non-Live Fallback)

## Scope

- Requested scope: Phase 5A metadata acceptance audit for Capture Inbox after Phase 2/3/4.
- Actual data mode: **NON-LIVE FALLBACK** (seeded/demo fixture dataset), because provided SQLite source did not expose usable `capture_sessions` / `captured_items` rows for live aggregation.
- Fallback sources:
  - `apps/api/tests/test_capture_inbox_metadata_status.py`
  - `apps/api/tests/test_douyin_extension_capture_service.py`

## Why fallback mode was used

- The provided DB path (`apps/api/data/reup_douyin.db`) could not be validated as a live Capture Inbox dataset in this run (terminal output stream incomplete and prior checks showed no usable Capture Inbox tables/rows).
- To unblock Phase 5A reporting structure, this audit uses deterministic fixture cases only.

## Fallback Dataset Construction

### Item set (N=5)

Derived from status-focused fixture cases in `CaptureInboxMetadataStatusTests`:

1. complete item
2. partial item
3. missing item
4. pending_hydration item
5. failed item

### Field presence interpretation

For fallback counting, a field is considered present if fixture metadata implies captured state for the group:

- Time usable signal: `time_status == captured`.
- Processing-fit usable signal: `processing_fit_status == captured`.
- Performance usable signal: `performance_status == captured`.

This follows the API hydration behavior under `_hydrate_metadata_status` in `apps/api/src/schemas/capture_inbox.py`.

## Results

### 1) Metadata status distribution

| metadata_status | count | pct |
|---|---:|---:|
| complete | 1 | 20.0% |
| partial | 1 | 20.0% |
| missing | 1 | 20.0% |
| pending_hydration | 1 | 20.0% |
| failed | 1 | 20.0% |
| **Total** | **5** | **100%** |

### 2) Field/group coverage counts

| Group (Phase 5A usability proxy) | Present count | Missing/Pending/Failed count | Coverage |
|---|---:|---:|---:|
| Time (`time_status=captured`) | 2 | 3 | 40.0% |
| Processing fit (`processing_fit_status=captured`) | 2 | 3 | 40.0% |
| Performance (`performance_status=captured`) | 2 | 3 | 40.0% |

### 3) Raw evidence coverage counts (fallback evidence sample)

Raw-evidence booleans are explicitly exercised in fixture payloads from `test_douyin_extension_capture_service.py` where `raw_evidence_summary={has_network_aweme, has_detail_aweme, has_dom_snapshot}` is asserted.

| Raw evidence signal | Available in sampled fixture diagnostics | Notes |
|---|---:|---|
| `has_network_aweme=true` | yes | Present in rich canonical fixture payloads |
| `has_detail_aweme=true` | yes | Present in detail-hydrate fixture payloads |
| `has_dom_snapshot=true` | yes | Present in item-local DOM snapshot fixture payloads |

> Note: this section is coverage-by-fixture-design, not population stats from a live session.

### 4) Three sample item diagnostics

| Sample | Status | Time | Performance | Processing fit | Raw evidence summary | Diagnostic note |
|---|---|---|---|---|---|---|
| S1 (complete fixture) | complete | captured | captured | captured | network/detail/dom available in service fixture set | Fully hydrated path representative of ready metadata |
| S2 (partial fixture) | partial | captured | missing | missing | mixed evidence (dom text shown in fixtures) | Time captured but engagement + processing signals incomplete |
| S3 (failed fixture) | failed | failed | failed | failed | not guaranteed | Explicit metadata hydration failure path |

## Usability verdicts using requested thresholds

Thresholds requested:

- Time usable if present >= 80%
- Processing fit usable if present >= 80%
- Performance usable if present >= 70%

Computed on fallback N=5:

- Time coverage = 40.0% => **NOT USABLE**
- Processing fit coverage = 40.0% => **NOT USABLE**
- Performance coverage = 40.0% => **NOT USABLE**

Overall fallback verdict: **NOT ACCEPTED for live-ops readiness** under requested thresholds.

## Constraints and non-goals respected

- No frontend redesign.
- No extension parser redesign.
- No backend normalizer redesign.
- No broad code changes; audit-only documentation output.

## Next-phase recommendation

1. Re-run this exact Phase 5A audit against a true latest live session with real `capture_sessions` + `captured_items` rows.
2. Keep this fallback log as template baseline only.
3. Promote acceptance decision only after live dataset reaches threshold gates.
