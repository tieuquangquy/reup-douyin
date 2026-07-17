# Douyin Accounts Architecture

## Root Architecture
The module adds a source-account layer for Douyin live fetch. It does not create a second intake or discovery pipeline.

Canonical flow:

1. `/accounts/douyin` imports and validates a Douyin session.
2. `/intake` selects a Douyin account connection for live fetch or force refresh.
3. `POST /intake/discover` passes `douyin_account_connection_id`.
4. `IntakeDiscoveryService` decides:
   - reuse usable existing data
   - live fetch using selected account
   - forced live fetch using selected account
5. Live path constructs `DouyinLiveFetchClient` with the selected account session context.
6. Existing `SourceIngestService.ingest_profile` persists:
   - `SourceProfile`
   - `SourceVideo`
   - `CrawlSession`
   - `VideoMetricSnapshot`
7. Existing `CandidateEvaluationService` creates or updates `VideoCandidate`.
8. Review board continues to read canonical candidates.

## Account Connection Domain
`DouyinAccountConnection` is a source fetch account. It is intentionally separate from publish-side `PlatformAccount`.

V1 fields:
- workspace id
- display name
- optional Douyin user id
- status
- default flag
- session secret blob
- user agent
- optional proxy URL
- optional headers metadata
- validation timestamps/status/errors
- notes/metadata

## Live Fetch Client Relationship
The account service resolves safe runtime config and creates a `DouyinLiveFetchClient`.

The fetch client remains transport-only:
- no persistence
- no candidate creation
- no UI/business branching

## Intake Integration
`/intake` can use existing data without an account if existing data is usable.

Live fetch and force live refresh should use a valid selected Douyin account connection. If no valid account is selected, the API returns a clear account error instead of a generic candidate/no-video result.

## Fallback Flow
Fallback remains:
- usable existing data can be reused
- dev fixtures can still be ingested through existing source ingest APIs/tests
- if live fetch is disabled or account is invalid, error messages should point to account validation or runtime config

## No-Duplication Strategy
This step does not add:
- a new crawler pipeline
- a new candidate discovery service
- a publish account reuse hack
- duplicate source profile/video/candidate models

## V1 Security Posture
V1 imports session cookies manually. It does not store passwords.

The API never returns raw session cookies. Logs must not include cookies. Local DB storage is isolated but not equivalent to a production secret manager. Production SaaS should replace the V1 blob with encrypted secret storage and account-scoped audit logs.

## V1 Limitations
- Browser-assisted login is now implemented through a local Playwright browser session.
- QR-style login relies on the real Douyin login page showing QR; the project does not reverse engineer a native QR protocol.
- Session validation is a lightweight network/session check that looks for login/blocking markers; it is not a complete Douyin account health model or production auth proof.
- Worker-backed account crawl is not forced in V1; synchronous intake remains the practical local-first path.

## Implemented Endpoints
- `GET /douyin-accounts`
- `POST /douyin-accounts`
- `GET /douyin-accounts/{id}`
- `PATCH /douyin-accounts/{id}`
- `POST /douyin-accounts/{id}/validate`
- `POST /douyin-accounts/{id}/disable`
- `DELETE /douyin-accounts/{id}`
- `POST /douyin-accounts/browser-connect/start`
- `GET /douyin-accounts/browser-connect/{id}`
- `POST /douyin-accounts/browser-connect/{id}/cancel`

## Implemented UI
- `/accounts/douyin`
- `/intake` account selector
