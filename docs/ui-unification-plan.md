# UI Unification Plan

Started: 2026-04-21 23:09:33 +07:00

## Goal

Unify the current web app into two clear surfaces without changing core business logic:

- Operator Studio at `/`
- Ops Console at `/ops`

This step is planning only. It audits the existing routes, proposes the target information architecture, and records the next execution path. It does not wire a new app shell, move route files, or refactor feature components.

## Current Findings

The current `apps/web` app has useful feature screens, but they are exposed as separate direct URLs:

- `/` redirects to `/review-board`
- `/review-board`
- `/source-videos/[id]/transcript-editor`
- `/source-videos/[id]/final-review`
- `/source-videos/[id]/publish`
- `/dashboard/publish-health`
- `/publish-control`
- `/optimization`

The feature components are already separated well enough to be reused:

- Review board: `components/review-board`
- Transcript editor: `components/transcript-editor`
- Final review: `components/final-review`
- Publish draft: `components/publish-draft`
- Publish health: `components/publish-health`
- Publish control: `components/publish-control`
- Optimization: `components/optimization`
- Shared risk widgets: `components/risk`

The missing layer is an application shell with navigation, section grouping, and home/dashboard pages.

## Target Information Architecture

### Operator Studio

Operator Studio is the default workspace for daily content production. It should optimize for moving one video through the pipeline.

Proposed responsibilities:

- Candidate review and keep/reject decisions
- Transcript editing
- Final render review
- Publish draft preparation
- Inline risk summary where relevant
- Fast navigation between the next operator actions

Primary route group:

- `/`
- `/review-board`
- `/source-videos/[id]/transcript-editor`
- `/source-videos/[id]/final-review`
- `/source-videos/[id]/publish`

### Ops Console

Ops Console is the operational/control surface. It should optimize for monitoring health, routing, account state, and optimization signals.

Proposed responsibilities:

- Publish health dashboard
- Account/page control plane
- Routing and backlog control
- Optimization loop and outcome summaries
- Future job/asset health views

Primary route group:

- `/ops`
- `/ops/publish-health`
- `/ops/publish-control`
- `/ops/optimization`

### Shared

Shared UI includes elements that appear in either surface but do not own routing:

- Risk summary cards and warning lists
- Status badges
- Empty/loading/error states
- API client functions
- Type definitions

## Target Route Map

| Current route | Target route | Group | Notes |
| --- | --- | --- | --- |
| `/` | `/` | Operator Studio | Should become Operator Studio home instead of redirect-only. |
| `/review-board` | `/review-board` | Operator Studio | Keep route; add app shell/navigation later. |
| `/source-videos/[id]/transcript-editor` | Same | Operator Studio | Keep route; link from review/final review. |
| `/source-videos/[id]/final-review` | Same | Operator Studio | Keep route; link to transcript/publish. |
| `/source-videos/[id]/publish` | Same | Operator Studio | Keep route; link to final review and ops status. |
| `/dashboard/publish-health` | `/ops/publish-health` | Ops Console | Keep compatibility redirect later if needed. |
| `/publish-control` | `/ops/publish-control` | Ops Console | Move behind ops shell later. |
| `/optimization` | `/ops/optimization` | Ops Console | Move behind ops shell later. |
| None | `/ops` | Ops Console | New ops home/dashboard later. |

## Proposed Navigation Model

### Operator Studio Nav

- Studio Home
- Review Board
- Transcript Editor
- Final Review
- Publish Draft

Dynamic video-specific links should be contextual. The global nav should not require a source video id.

### Ops Console Nav

- Ops Home
- Publish Health
- Publish Control
- Optimization

Ops routes should make it clear they are operational health/control screens, not individual content editing screens.

## Step-by-Step Execution Plan

1. Create shared app-shell components:
   - `AppShell`
   - `OperatorStudioShell`
   - `OpsConsoleShell`
   - navigation config
   - section breadcrumbs or contextual action links
2. Replace `/` redirect with Operator Studio home:
   - show primary workflow entry points
   - show seeded/demo quick links only if implemented as non-production helper copy
   - link to review board and ops console
3. Add `/ops` route:
   - summarize publish health, account control, optimization
   - link to existing ops screens
4. Add new ops route aliases:
   - `/ops/publish-health`
   - `/ops/publish-control`
   - `/ops/optimization`
5. Keep current direct routes temporarily:
   - either leave them functional
   - or redirect old ops routes to `/ops/*` after verifying links/tests
6. Wrap current feature pages with the proper shell:
   - Operator pages get Operator Studio shell
   - Ops pages get Ops Console shell
7. Update tests for route rendering and nav links.
8. Update demo docs so users no longer need manual URL lists.

## Non-Goals

- No backend API changes.
- No business workflow change.
- No new publish connector.
- No redesign of feature components.
- No replacement of existing review/editor/publish/control screens.
- No deep dashboard/analytics expansion.

## Risks and Assumptions

- Dynamic source-video routes require a selected video id; global navigation cannot always link directly to transcript/final/publish screens.
- Existing seed data provides stable demo IDs during one seed run, but IDs are regenerated on reseed. The shell should avoid hardcoded IDs.
- Old routes are already used in docs and demos. Keep compatibility until docs and tests are updated.
- The global layout is currently minimal. Adding app-shell wrappers should be done incrementally to avoid breaking existing client-side state.

## Recommended Next Step

Implement a minimal navigation config and app shell, then create:

- Operator Studio home at `/`
- Ops Console home at `/ops`
- ops route aliases that reuse existing components

After that, wrap pages and update tests/docs in one focused pass.
