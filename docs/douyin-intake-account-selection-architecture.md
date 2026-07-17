# Douyin Intake Account Selection Architecture

## Objective
Make `/intake` live-fetch account selection health-aware, deterministic, and explainable while reusing canonical Douyin account health and validation logic.

## Canonical Source of Truth
- Account status and health projection: `DouyinAccountService.health_summary`.
- Account list/default resolution source: `DouyinAccountService` + `DouyinAccountConnection`.
- Intake final decision source: `IntakeDiscoveryService` (backend only).

## Selection Model

### Terms
- `selected_account_id`: operator-chosen account id from request (nullable).
- `resolved_account_id`: account id actually used for live fetch.
- `selection_mode`:
  - `selected` (operator choice used)
  - `default` (default account used)
  - `fallback` (operator/default account replaced by healthier usable account)
- `selection_reason`: stable reason code for diagnostics/UI copy.
- `fallback_notice`: human-readable summary when fallback happened.

### Usability Policy
Usable:
- `HEALTHY`
- `STALE`
- `EXPIRING_SOON`

Unusable:
- `INVALID`
- `EXPIRED`
- `BLOCKED`
- `DISABLED`
- `UNKNOWN`

### Deterministic Ranking Policy
When fallback candidate is needed:
1. Filter to usable accounts.
2. Rank by health bucket (`HEALTHY` > `STALE` > `EXPIRING_SOON`).
3. Tie-break by latest `last_successful_validation_at`.
4. Final tie-break by latest `updated_at`.

## Resolution Flow
1. Intake decides whether live fetch is required (existing profile reuse path unchanged).
2. If live fetch required:
   - evaluate requested account (if any);
   - else evaluate default account;
   - if unusable/missing, rank fallback from other usable accounts.
3. If no usable account exists: return deterministic 422 with account-required remediation.
4. Build adapter from `resolved_account_id` only.
5. Return response metadata including selection mode/reason and optional fallback notice.

## API Contract Additions (`/intake/discover` response)
- `selected_douyin_account_connection_id: UUID | null`
- `resolved_douyin_account_connection_id: UUID | null`
- `douyin_account_selection_mode: str | null`
- `douyin_account_selection_reason: str | null`
- `douyin_account_fallback_notice: str | null`

## Operator Override Guardrails
- Operator can explicitly choose accounts that are usable-with-warning (`STALE`, `EXPIRING_SOON`).
- Operator cannot force unusable accounts (`INVALID`/`EXPIRED`/`BLOCKED`/`DISABLED`/`UNKNOWN`) into live fetch.
- If explicit selection is unusable, backend attempts fallback and returns explainability metadata.

## No-Duplication Strategy
- No new health enums or shadow health calculators in intake.
- No UI-only account resolution authority.
- No direct status-string parsing in intake; always use canonical health projection data.

## Non-Goals (This Step)
- New scheduler platform for periodic revalidate.
- New account persistence model.
- Full account history/event table.
