# Douyin Hard Reset Architecture

## Objective

Make local-dev Douyin discovery reliable by using one primary happy path:

```text
DouyinAccountConnection
  -> persistent browser profile
  -> browser-profile-backed profile fetch
  -> DouyinProfileAdapter.normalize_fetch_payload()
  -> SourceIngestService
  -> CandidateEvaluationService
```

## One Account, One Persistent Browser Profile

Each connected account stores browser profile metadata on `DouyinAccountConnection.metadata_json`:

- `browser_profile_id`
- `browser_profile_path`
- `browser_profile_mode = persistent_profile`

Opening or reopening an account uses that same profile identity. Reconnect does not intentionally create a new random profile for an existing account.

## Primary Discovery Path

For connected-account `/intake` in local development:

1. Resolve selected/default Douyin account.
2. Run preflight.
3. Require a usable persistent browser profile unless legacy fallback is
   explicitly enabled.
4. Reopen the saved profile once if needed.
5. Execute browser-profile-backed fetch.
6. Wait briefly, scroll the rendered profile page, then extract browser network
   JSON, embedded JSON, and rendered `/video/` links.
7. Normalize and persist through the canonical pipeline.

## Legacy/Fallback Status

Manual cookie import:

- kept as troubleshooting/legacy,
- not the recommended operator path,
- not shown as the primary creation path.

HTTP HTML fetch:

- no longer the default connected-account happy path,
- disabled as automatic fallback by default,
- can be explicitly enabled with `DOUYIN_ALLOW_LEGACY_HTTP_FALLBACK_FOR_INTAKE=true` for debugging.

## Configuration Defaults

```text
DOUYIN_PREFER_BROWSER_PROFILE_FOR_FETCH=true
DOUYIN_ALLOW_LEGACY_HTTP_FALLBACK_FOR_INTAKE=false
DOUYIN_BROWSER_PROFILE_FETCH_SCROLL_PASSES=4
DOUYIN_BROWSER_PROFILE_FETCH_SETTLE_SECONDS=2
```

With these defaults, a connected account without a reusable browser profile is
not fetch-ready for `/intake`. The API returns `browser_profile_required`
instead of silently using HTTP shell parsing.

## Result And Diagnostics

Successful browser-profile fetch records:

- `strategy_policy = browser_primary`
- `primary_execution_path = browser_profile`
- `final_execution_path_used = browser_profile`
- `legacy_http_fallback_allowed = false`
- discovered, normalized, persisted, and matched counts

Preflight or fetch failures stay explicit:

- `browser_profile_required`
- `browser_profile_unavailable`
- `login_required`
- `blocked_response`
- `parse_zero_videos`
- `parse_failed`

## Failure Policy

If browser profile is missing, closed and unreopenable, login-required, blocked, or renders zero parseable videos, the run fails with a specific stage/code. It must not collapse into generic 500 or vague "No candidates matched".

## Acceptance Criteria

- Connected account opens/reopens the same persistent profile.
- Intake preflight selects browser profile as the primary path.
- Browser fetch produces canonical raw payload shape.
- Videos discovered by browser fetch enter `SourceVideo` and candidate discovery through existing services.
- Legacy HTTP/manual paths do not hijack the main operator experience.

## Canonical Pipeline Unchanged

The hard reset changes raw fetch execution and operator policy only. It does not introduce a second persistence path, second candidate pipeline, or alternate account model.
