# UI Consolidation Route Map

## Operator Studio Sidebar

- Home
  - `/`
- Intake
  - `/intake`
  - Contextual child routes: `/intake/profiles`, `/intake/crawl-sessions`
- Selection
  - `/selection/review-board`
  - Legacy redirect: `/review-board`
- Production
  - `/production/downloads`
  - Contextual active routes:
    - `/production/transcript-editor/[sourceVideoId]`
    - `/production/final-review/[sourceVideoId]`
    - `/source-videos/[id]/transcript-editor`
    - `/source-videos/[id]/final-review`
- Publishing
  - `/publishing/drafts`
  - `/publishing/health`
  - `/publish-control`
  - Contextual active routes:
    - `/publishing/drafts/[draftId]`
    - `/source-videos/[id]/publish`
    - `/dashboard/publish-health`
- Optimization
  - `/optimization`

## Ops Console Sidebar

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
- Accounts & Routing
  - `/ops/accounts`
  - `/ops/routing-rules`
- Risk & Tools
  - `/ops/risk`
  - `/ops/tools`
  - `http://localhost:8000/docs`
  - `/ops/optimization`

## Breadcrumb Strategy

- Static operator pages use `Home / Section / Page`.
- Dynamic production pages use:
  - `Home / Production / Transcript Editor`
  - `Home / Production / Final Review`
- Dynamic publish pages use:
  - `Home / Publishing / Publish Draft`
- Ops pages use:
  - `Ops Console / Section / Page`
- Unknown operator routes fall back to `Home`.
- Unknown ops routes fall back to `Ops Console`.

## Contextual Navigation Strategy

- Sidebar is for stable sections and workflow entry points.
- Topbar is for quick movement across common daily routes.
- Dynamic source-video/draft routes are entered through:
  - Home quick launch / continue panels
  - Review board candidate actions
  - Transcript editor, final review, and publish draft shell actions
  - Publish health and drafts queues
- Legacy routes remain available as redirects or context routes; they are not promoted as primary sidebar items.
