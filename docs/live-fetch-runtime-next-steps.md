# Live Fetch Runtime Next Steps

## Current Go / No-Go

- Runtime config: go.
- Adapter injection: go.
- `/intake` disabled-client error: fixed.
- Fallback mode: go.
- Real Douyin profile harvesting: conditional go, because actual success depends on Douyin returning public embedded payloads for the submitted profile.

## Canonical Env Vars

API local env file: `apps/api/.env`

Worker local env file: `apps/worker/.env`

Required for live mode:

```env
DOUYIN_ENABLE_LIVE_FETCH=true
```

Optional but often needed if Douyin blocks or withholds payloads:

```env
DOUYIN_SESSION_COOKIE=
DOUYIN_PROXY_URL=
DOUYIN_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36
DOUYIN_FETCH_TIMEOUT_SECONDS=15
DOUYIN_FETCH_MAX_VIDEOS=50
```

Never commit real cookie/session values.

## How To Re-run

Start or restart the local stack:

```powershell
.\scripts\dev-stop.ps1
.\scripts\dev-start.ps1
```

Then open:

```text
http://localhost:3000/intake
```

Submit a real Douyin profile URL, not a single video URL.

## Expected Outcomes

If Douyin returns public profile/video payloads:

- `/intake/discover` creates a `CrawlSession`.
- `SourceProfile`, `SourceVideo`, and `VideoMetricSnapshot` rows are persisted.
- `CandidateEvaluationService` creates `VideoCandidate` rows.
- `/review-board` shows the matched candidates.

If Douyin blocks or returns a shell page without videos:

- Live mode is still enabled, but the result can be zero videos or an adapter fetch error.
- Add `DOUYIN_SESSION_COOKIE` and/or `DOUYIN_PROXY_URL`, then restart API and worker.

## Intentionally Unchanged

- No new crawler framework.
- No duplicate ingest pipeline.
- No UI redesign.
- No video download during intake.
- `/intake` remains synchronous until a real profile proves the live request is too slow for local UX.
