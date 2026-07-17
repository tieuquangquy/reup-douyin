# Douyin Legacy Isolation Architecture

## Decision

The default Douyin runtime architecture is browser-profile-backed only. Legacy manual-import and detached HTTP-fallback code remains in the repository, but it is isolated behind explicit legacy/debug flags and must not be selected by default runtime orchestration or displayed as a normal main UI option.

## Context

The project is local-first for Phase 1 but must remain SaaS-ready. A reliable Douyin account flow needs one canonical browser profile per account because Douyin login, challenge, and anti-bot state are tied to a real browser session. Detached cookie/session material and manual imports can be useful for debugging old behavior, but they are weaker and should not dominate primary status or operator decisions.

## Primary browser-backed path

The default primary path is:

1. `DouyinAccountConnection` stores the canonical account row.
2. The account is associated with one persistent browser profile.
3. Browser connect opens or reopens that profile.
4. The operator logs in and solves challenges in the profile.
5. Validation uses the same browser profile.
6. Intake preflight confirms the same profile is available and reusable.
7. Fetch runs through the browser-backed path.
8. Results flow into the existing canonical downstream pipeline:
   - `SourceProfile`
   - `SourceVideo`
   - `CrawlSession`
   - `VideoMetricSnapshot`
   - `VideoCandidate`

## Legacy paths retained but isolated

### Manual import

Manual import code remains for legacy/debug use. It may still parse imported session material and produce manual import preflight information when explicitly enabled. It must not be presented as the ordinary way to create or repair a Douyin account in the main operator UI.

Default behavior:

- Main Douyin Accounts UI hides manual import.
- Browser connect guidance does not recommend manual import as a normal recovery path.
- Account response contracts may keep legacy fields for compatibility, but main UI should not elevate them by default.

Legacy/debug behavior when enabled:

- Manual import UI/debug surface can be shown.
- Existing parser/preflight code can run.
- Legacy account metadata remains understood.

### Detached HTTP fallback

Detached HTTP fallback code remains for legacy/debug use. It may still be used by tests, diagnostics, or explicit legacy operation. It must not silently replace browser profile validation/fetch in the default path.

Default behavior:

- Browser validation inconclusive or unavailable does not fall through to detached HTTP.
- Intake preflight without a usable browser profile reports browser profile required, not fallback ready.
- Ready Check does not treat HTTP fallback as a safe default run path.
- Health/status/evidence treats browser profile as the expected Intake path.
- Main UI does not offer fallback execution as a normal run button.

Legacy/debug behavior when enabled:

- HTTP fallback readiness may be reported.
- Fetch client may allow HTTP fallback.
- Debug UI may show HTTP fallback diagnostics.

## Settings model

Target explicit settings:

| Setting | Default | Purpose |
| --- | --- | --- |
| `DOUYIN_ENABLE_LEGACY_MANUAL_IMPORT` | `false` | Allows manual import creation/smoke behavior and related backend legacy handling. |
| `DOUYIN_ENABLE_LEGACY_HTTP_FALLBACK` | `false` | Allows detached HTTP fallback for validation/fetch/preflight when browser profile path fails or is unavailable. |
| `DOUYIN_ENABLE_LEGACY_DEBUG_SURFACES` | `false` | Allows main UI to expose legacy manual import and HTTP fallback diagnostics/debug controls. |

Existing `DOUYIN_ALLOW_LEGACY_HTTP_FALLBACK_FOR_INTAKE` should be treated as a compatibility alias or subordinate setting, not the primary policy flag.

## Backend isolation design

### Validation

Default validation path should be browser-profile-only:

- Use live or reopened persistent browser context.
- If the browser path cannot validate, return a browser-specific failure/retry/challenge state.
- Do not execute detached HTTP validation unless `DOUYIN_ENABLE_LEGACY_HTTP_FALLBACK=true`.

### Runtime config and fetch client

Default fetch client construction should preserve browser primary mode and pass `allow_http_fallback=false` unless legacy HTTP fallback is explicitly enabled.

### Preflight and Ready Check

Default preflight outcomes should include browser-profile states only:

- Ready with active/reopened browser profile.
- Challenge blocked.
- Browser profile required.
- Browser profile unavailable/reopen failed.

`FALLBACK_READY` should be impossible in default mode.

### Health and evidence precedence

Default health projection should prefer browser evidence:

- Effective validation path: browser profile when browser evidence exists or is required.
- Expected Intake path: browser profile.
- Detached HTTP state: suppressed, disabled, or debug-only in main projection unless legacy debug surfaces are enabled.

The system should not describe a no-profile account as aligned with detached HTTP in default mode.

### Intake orchestration

Default Intake orchestration must:

- Resolve an account that is usable for browser-backed Intake.
- Stop before live ingest if browser preflight fails.
- Avoid HTTP fallback execution by default.
- Preserve canonical downstream ingest/discovery behavior after a browser-backed fetch succeeds.

## Frontend isolation design

### Douyin Accounts page

Default UI should:

- Highlight browser connect/open/reopen/validate/challenge actions.
- Hide manual import panel.
- Hide manual import preflight details from normal account rows.
- Avoid presenting detached HTTP as a normal expected path.
- Use operator guidance that says browser profile is required.

Debug/legacy UI when enabled may:

- Show manual import panel in a clearly labeled legacy/debug section.
- Show detached HTTP diagnostics as debug-only evidence.

### Intake page

Default UI should:

- Treat Ready Check as browser-profile readiness.
- Avoid a normal `Run Intake with fallback` action.
- Hide HTTP fallback diagnostics unless debug surfaces are enabled.
- Show reopen/validate/challenge actions when browser profile is blocked or stale.

## Testing strategy

Backend tests should prove:

- Default validation does not call detached HTTP after browser validation is inconclusive.
- Explicit legacy HTTP fallback can still enable the old path.
- Default preflight without browser profile returns browser-profile-required, even when HTTP material exists.
- `FALLBACK_READY` is not safe-to-run in default mode.
- Health alignment expects browser profile by default.
- Manual import backend behavior is gated when legacy manual import is disabled.

Frontend tests/typecheck should prove:

- Main UI compiles with legacy surfaces hidden by default.
- Intake ready-check UI no longer presents fallback as a normal primary action in default mode.

## Operational notes

- Do not log cookies, tokens, raw credentials, or private local paths.
- Keep legacy diagnostics explicit and labeled when enabled.
- Preserve Windows-compatible commands and docs.
