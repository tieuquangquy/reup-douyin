# Douyin Browser Connect Architecture

## V1 Browser-Assisted Flow
Canonical V1 flow:

1. Operator opens `/accounts/douyin`.
2. Operator clicks `Connect with browser` / `Start QR login`.
3. API creates a short-lived `DouyinBrowserConnectSession`.
4. API launches a local browser session pointed at the real Douyin login page.
5. Operator completes login in that browser. If Douyin presents a QR code, the operator scans it on the real page.
6. Browser connect service detects authenticated Douyin cookies.
7. Service captures only the session artifacts needed for live fetch.
8. Service creates a canonical `DouyinAccountConnection` through the existing account service.
9. Service validates the created connection.
10. `/accounts/douyin` polls the connect session until it completes or fails.
11. `/intake` sees the new account through the existing account list endpoint.

## QR-Style UX Mapping
This implementation does not reverse engineer Douyin's native QR protocol.

`Start QR login` means:
- open a real Douyin login browser
- let Douyin render its normal login/QR experience
- capture browser session after successful login

This keeps the code honest and avoids a fake OAuth or fake QR API.

## Session Capture Flow
The browser capture layer is separate from persistence:

- browser runtime opens Douyin
- status moves through launch/wait/capture/validate states
- cookies are converted into a standard cookie header
- raw cookies are used only inside the API process
- raw cookies are not logged and are not returned to the frontend

## Validation Flow
Validation reuses `DouyinAccountService.validate_account`.

V1 validation is a practical local-first check:
- missing session -> invalid
- login/expired markers -> expired
- block/security markers -> blocked
- reachable session without obvious login blocker -> active

This is not a production-grade account health proof.

## Persistence Flow
The final saved account is always `DouyinAccountConnection`.

Browser-assisted connect sets metadata such as:
- `connection_source = browser_assisted`
- connect session id

Manual import can still set:
- `connection_source = manual_import`

Both paths share the same account model, validation service, and `/intake` live fetch integration.

## No-Duplication Strategy
This step does not add:
- a second account model
- a second source ingest pipeline
- a second candidate discovery path
- password login
- native QR protocol reverse engineering
- a cloud auth broker

## Security Model And Limitations
- Passwords are never requested or stored.
- Raw cookies are never echoed to UI responses.
- Logs must not include raw cookies.
- V1 local blob storage is not a production secret vault.
- Browser cleanup is best effort after completion, failure, or cancellation.
- The API declares `playwright` as the browser runtime dependency. After installing API dependencies, run `python -m playwright install chromium` if Chromium is not already available.
- If Playwright/browser runtime is unavailable, the connect session fails clearly with `browser_runtime_unavailable`.

## Intake Integration
`/intake` does not need a new pipeline.

Existing flow remains:

`/intake` -> `POST /intake/discover` -> selected `douyin_account_connection_id` -> `DouyinAccountService` -> `DouyinLiveFetchClient` -> `SourceIngestService` -> `CandidateEvaluationService` -> review board.
