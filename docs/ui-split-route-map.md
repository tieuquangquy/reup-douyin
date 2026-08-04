# UI Split Route Map

## Current Route Inventory

### Business Routes Preserved

- `/review-board`
- `/review-board?fresh=1`
- `/source-videos/[id]/transcript-editor`
- `/source-videos/[id]/final-review`
- `/source-videos/[id]/publish`
- `/dashboard/publish-health`
- `/publish-control`
- `/optimization`

### Current Canonical Routes

- `/`
- `/selection/review-board`
- `/production/transcript-editor/[sourceVideoId]`
- `/production/final-review/[sourceVideoId]`
- `/publishing/drafts`
- `/publishing/drafts/[draftId]`
- `/publishing/health`
- `/ops`
- `/ops/publish-health`
- `/ops/publish-control`
- `/ops/jobs`
- `/publishing/accounts`
- `/ops/reconciliation`
- `/ops/routing-rules`
- `/ops/risk`
- `/ops/tools`
- `/ops/optimization`

## Target Grouping

### Operator Studio

Entry route:

- `/`

Groups:

- Home
  - `/`
- Intake
  - `/intake`
  - `/intake/profiles`
  - `/intake/crawl-sessions`
- Selection
  - `/selection/review-board`
  - Alias: `/review-board`
- Production
  - `/production/downloads`
  - `/production/transcript-editor/[sourceVideoId]`
  - `/production/final-review/[sourceVideoId]`
  - Aliases:
    - `/source-videos/[id]/transcript-editor`
    - `/source-videos/[id]/final-review`
- Publishing
  - `/publishing/drafts`
  - `/publishing/drafts/[draftId]`
  - `/source-videos/[id]/publish`
  - `/publishing/health`
- Optimization
  - `/optimization`

### Ops Console

Entry route:

- `/ops`

Groups:

- Ops Home
  - `/ops`
  - `/ops/health`
- Jobs
  - `/ops/jobs`
  - `/ops/assets`
- Publish Ops
  - `/ops/publish-health`
  - `/ops/publish-control`
  - `/ops/publish-attempts`
  - `/ops/reconciliation`
  - Aliases:
    - `/dashboard/publish-health`
    - `/publish-control`
- Accounts & Routing
  - `/publishing/accounts`
  - `/ops/routing-rules`
- Risk & Tools
  - `/ops/risk`
  - `/ops/tools`
  - `/ops/optimization`
  - External Swagger: `http://127.0.0.1:8000/docs`

## New Entry Routes

- `/` as Operator Studio home.
- `/ops` as Ops Console home.

## Redirects / Aliases

- `/review-board` -> `/selection/review-board`
- `/review-board?fresh=1` -> `/selection/review-board?fresh=1`
- `/source-videos/[id]/transcript-editor` -> `/production/transcript-editor/[id]`
- `/source-videos/[id]/final-review` -> `/production/final-review/[id]`
- `/dashboard/publish-health` -> `/ops/publish-health`
- `/publish-control` -> `/ops/publish-control`

## Routes Preserved As-Is

- `/source-videos/[id]/publish` remains a direct business route rendering the publish draft page.
- `/optimization` remains Operator Studio optimization.
- `/publishing/health` remains an Operator-facing publish health page.

## Verification Snapshot

- `/` is Operator Studio home.
- `/ops` is Ops Console home.
- Legacy business routes remain reachable through redirects/aliases.
- Swagger is linked as `http://127.0.0.1:8000/docs`.
