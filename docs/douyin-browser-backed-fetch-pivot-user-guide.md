# douyin-browser-backed-fetch-pivot-user-guide.md

## What Changed

Local-dev Douyin profile discovery now targets the connected account’s **persistent browser profile** as the preferred fetch path when that reusable profile is available.

The goal is to reduce failures where the plain HTTP profile-fetch path returns a challenge page or shell response instead of the real profile/video payload.

## Why This Changed

The previous zero-video issue was diagnosed as a transport problem, not a genuine zero-video profile:

- HTTP profile fetch could return a shell/challenge page.
- The old parser path could still see a partial profile shape with zero videos.
- That could be misread as a successful zero-video profile result.
- The connected account’s browser profile could still reach a more representative rendered state.

Because of that, HTTP-first parsing was too fragile as the primary local-dev happy path.

## What Stays Canonical

These core parts do **not** change:

- [`DouyinAccountConnection`](apps/api/src/models/source_accounts.py) remains the canonical connected-account model.
- Intake still uses the same discover flow through [`IntakeDiscoveryService.discover()`](apps/api/src/services/intake_discovery_service.py:99).
- Ingest still uses [`SourceIngestService.ingest_profile()`](apps/api/src/services/source_ingest_service.py:50).
- Persistence still writes to the same canonical entities:
  - `SourceProfile`
  - `SourceVideo`
  - `CrawlSession`
  - `VideoMetricSnapshot`
  - downstream candidate discovery results

This is an execution-strategy pivot, not a new product pipeline.

## New Local-Dev Fetch Preference

### When a reusable browser profile exists

If the selected/resolved Douyin account has a reusable persistent browser profile, the backend should prefer:

1. reuse/open the browser profile,
2. fetch from the browser-rendered profile state,
3. normalize and persist through the existing canonical ingest path.

### When no reusable browser profile exists

The backend falls back to the HTTP-based fetch path.

## Fallback Behavior

If browser-backed fetch is unavailable or cannot be opened safely:

- the system can fall back to HTTP fetch,
- or return an explicit classified fetch failure if no safe fallback path is usable.

If HTTP fetch returns a shell/challenge-like response and a reusable browser profile is available:

- the system should pivot to browser-backed fetch automatically,
- rather than stopping at an ambiguous zero-video/no-candidate outcome.

## What Operators Should Expect in [`/intake`](apps/web/src/components/intake/IntakePage.tsx)

Operator-facing intake results should become clearer:

- when browser-backed fetch was used,
- when HTTP fetch triggered browser fallback,
- when fetch failed specifically,
- when a run truly had zero videos,
- when filtering caused zero candidates after a successful fetch.

The Intake status panel now includes the fetch path when available:

- `Browser profile`
- `HTTP HTML`
- `HTTP, then browser profile`

## What This Does Not Do

- It does not create a new intake or ingest product path.
- It does not create a browser-only persistence model.
- It does not automate passwords or bypass Douyin challenges.
- It does not expose raw cookies, secrets, or unsafe local-machine state in UI/logs.
- It does not add a cloud browser service.

## Remaining Limitations

- If the browser profile itself reaches a challenge or blocked surface, the failure may still occur, but it should now be explicit and classified.
- Browser reuse remains local-machine behavior.
- If the persistent profile is locked, invalid, or Playwright runtime is unavailable, browser-backed fetch may not be possible.

## Recommended Operator Workflow

1. Connect and validate a Douyin account in [`/accounts/douyin`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx).
2. Ensure the account has a reusable persistent browser profile.
3. In [`/intake`](apps/web/src/components/intake/IntakePage.tsx), select that connected account when running live fetch.
4. If fetch fails, inspect the explicit fetch-path result instead of assuming the profile truly has zero videos.

## Verification Goal

After the pivot:

- a previously failing real profile should either return videos successfully through browser-backed fetch,
- or fail with an explicit classified fetch stage/code instead of an ambiguous zero-video/no-candidate outcome.
