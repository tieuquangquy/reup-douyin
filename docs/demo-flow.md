# Demo Flow

Use the alpha demo seed when you want to inspect the product flow without live Douyin crawling or real rendering.

For structured pre-beta validation, use `docs/pre-beta-test-plan.md` and create a report folder with:

```powershell
.\scripts\new-pilot-report.ps1 -Name pilot-001
```

## Prepare

```powershell
.\scripts\dev-doctor.ps1
.\scripts\dev-migrate.ps1
.\scripts\dev-reseed.ps1
```

Start API, web, and worker:

```powershell
.\scripts\dev-start.ps1
```

## Seeded Cases

The demo fixture creates:

- one mock Douyin profile
- one ingested-only video
- one high-score candidate
- one rendered final review video
- one warning/risk path video
- one publish-ready video with publish draft
- one completed job and one failed job

## Screens To Open

Operator Studio home (start here):

```text
/
```

Review board:

```text
/selection/review-board
```

Transcript editor:

```text
/production/transcript-editor/{source_video_id}
```

Final review:

```text
/production/final-review/{source_video_id}
```

Publish drafts index:

```text
/publishing/drafts
```

Publish draft by ID:

```text
/publishing/drafts/{draft_id}
```

Publishing health:

```text
/publishing/health
```

Ops Console:

```text
/ops
```

Use API list endpoints to find seeded IDs:

- `GET /candidates`
- `GET /source-videos/{id}/latest-render`
- `GET /publish-drafts`
- `GET /risk-flags`
- `GET /ops/metrics`

Stop local windows started by the script:

```powershell
.\scripts\dev-stop.ps1
```

## What Is Mocked

Seeded media assets are small placeholder local files. They verify contracts and UI paths, not real playable production media.

No live crawler, downloader, STT, TTS, render, or publish connector is executed by the demo seed.
