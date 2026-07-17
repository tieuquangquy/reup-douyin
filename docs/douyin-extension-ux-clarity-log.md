# Douyin Extension UX Clarity Log

## Scope

Clarify the operator-facing difference between the real browser-extension capture path and the backend manual test form in the Douyin Extension Manager.

## Audit

- Primary extension path is represented by install/setup instructions, connection status, and popup guidance in the manager UI.
- Real current-page actions live in the browser extension popup as `Detect current page` and `Capture current page`.
- The web manager currently contains a form named `Current page tools` with buttons named `Detect current page` and `Capture current page`.
- Those web-manager button names can be mistaken for active-tab browser capture even though they submit manually typed safe page fields to backend endpoints.
- The backend form already preserves safe manual payload submission behavior and should remain available for troubleshooting.

## Implementation Plan

1. Add explicit primary-flow language and a `Real capture via extension` badge to the extension setup/connection area.
2. Move the web-manager backend form into a collapsed advanced troubleshooting section.
3. Add a `Manual backend test only` badge to the advanced form.
4. Rename manual-form buttons to test-oriented labels while preserving existing handlers and API contracts.
5. Verify web typecheck and focused web tests.

## Non-goals

- No backend contract changes.
- No extension popup behavior changes.
- No crawler, queue, database, scoring, or publish implementation.
- No dependency changes.

## Implementation Completed

- Added the `Real capture via extension` badge to the install/setup area.
- Updated install/setup copy to tell operators to use the extension popup for real active-tab detection and capture.
- Moved the manual backend form below capture status and into a collapsed advanced troubleshooting `<details>` panel.
- Added the `Manual backend test only` badge to the advanced form summary.
- Renamed the manual backend detect button from `Detect current page` to `Test detect from form`.
- Renamed the manual backend capture button from `Capture current page` to `Submit manual capture test`.
- Preserved the existing web handlers and API wrapper calls.
- Added a focused source-level UX regression test.

## Verification

- `npm --workspace @reup-douyin/web run typecheck` passed.
- `npm --workspace @reup-douyin/web exec tsx src/test/douyin-extension-manager-ux.test.ts` passed.
- `npm --workspace @reup-douyin/web run test` passed.
