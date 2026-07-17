# Ops Route Migration Map

## Old Ops Routes

- `/dashboard/publish-health`
- `/publish-control`
- `/publishing/health`

## Canonical New Ops Routes

- `/ops`
- `/ops/publish-health`
- `/ops/publish-control`

## Redirects / Aliases

- `/dashboard/publish-health` -> `/ops/publish-health`
- `/publish-control` -> `/ops/publish-control`
- `/publishing/health` -> `/ops/publish-health`

## Operator Routes Kept

- `/`
- `/review-board`
- `/selection/review-board`
- `/source-videos/[id]/transcript-editor`
- `/source-videos/[id]/final-review`
- `/source-videos/[id]/publish`
- `/production/transcript-editor/[sourceVideoId]`
- `/production/final-review/[sourceVideoId]`
- `/publishing/drafts`
- `/publishing/drafts/[draftId]`
- `/optimization`

Deprecated operator/ops mixed route:

- `/publishing/health` now redirects to `/ops/publish-health`

## Final Nav Grouping

### Operator Studio

- Home
- Selection / Review Board
- Production / Transcript Work
- Production / Final Review
- Publishing / Publish Drafts
- Optimization
- Surface switch: Open Ops Console

Operator Studio primary navigation intentionally does not include:

- Publish Health
- Publish Control
- Swagger/API tools

### Ops Console

- Ops Home
- Health
- Jobs
- Assets
- Publish Health
- Publish Control
- Publish Attempts
- Reconciliation
- Accounts
- Routing Rules
- Risk
- Tools
- Swagger API shortcut
- Surface switch: Open Operator Studio

## Verification Snapshot

- `/` opens Operator Studio and does not render Publish Health or Publish Control in the Operator menu.
- `/ops` opens Ops Console and renders Publish Health, Publish Control, Swagger, and the Operator Studio switch.
- Legacy `/dashboard/publish-health`, `/publish-control`, and `/publishing/health` redirect to canonical `/ops/...` routes.
