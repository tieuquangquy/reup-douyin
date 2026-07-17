# UI Unification Handoff

This document captures the final state of the UI unification work for the `reup-douyin` project. It is the authoritative reference for what was built, how it's structured, and what remains open.

---

## Final Route Map

### Operator Studio (`/`)

| Route | Description | Status |
|---|---|---|
| `/` | Home dashboard — metrics, action queue, quick launch, continue panel | Available |
| `/selection/review-board` | Candidate review board with score, risk, bulk actions | Available |
| `/selection/candidates` | Alias — redirects to `/selection/review-board` | Redirect |
| `/production/transcript-editor/[sourceVideoId]` | Transcript editing and translation draft | Available |
| `/production/final-review/[sourceVideoId]` | Final render output review | Available |
| `/production/downloads` | Media asset download list | Placeholder |
| `/publishing/drafts` | Publish drafts index | Available |
| `/publishing/drafts/[draftId]` | Individual publish draft editor | Available |
| `/publishing/health` | Publish outcome dashboard | Available |
| `/optimization` | Outcome quality, routing hints, scheduling hints | Available |
| `/intake` | Source intake home | Placeholder |
| `/intake/profiles` | Source profile list | Placeholder |
| `/intake/crawl-sessions` | Crawl session list | Placeholder |

### Ops Console (`/ops`)

| Route | Description | Status |
|---|---|---|
| `/ops` | Ops home | Available |
| `/ops/health` | System health — API, DB, worker, queue, storage, risk | Available |
| `/ops/jobs` | Job monitor — running, failed, retryable, stale | Available |
| `/ops/assets` | Media asset state | Available |
| `/ops/publish-attempts` | Publish attempt history | Available |
| `/ops/reconciliation` | Publish reconciliation queue | Available |
| `/ops/accounts` | Platform account list | Available |
| `/ops/publish-control` | Draft-to-account assignment and rebalancing | Available |
| `/ops/routing-rules` | Routing rule viewer | Available |
| `/ops/risk` | Risk flag and decision management | Available |
| `/ops/publish-health` | Publish outcome analytics | Available |
| `/ops/optimization` | Operator outcome hints | Available |
| `/ops/tools` | Local runbooks and API reference | Available |

### Legacy Compatibility Redirects

| Old Route | Redirects To |
|---|---|
| `/review-board` | `/selection/review-board` |
| `/source-videos/[id]/transcript-editor` | `/production/transcript-editor/[id]` |
| `/source-videos/[id]/final-review` | `/production/final-review/[id]` |
| `/dashboard/publish-health` | `/publishing/health` |
| `/publish-control` | `/ops/publish-control` |
| `/source-videos/[id]/publish` | Kept as functional alias — source-video scoped publish editor |

---

## Operator Areas

The Operator Studio is the primary frontend surface for the single local operator. It covers the video reup workflow end-to-end:

1. **Review** — scan scored candidates from Douyin ingest, keep/reject, bulk actions
2. **Production** — open transcript editor and final review from selected source videos
3. **Publishing** — prepare captions, CTAs, hashtags; schedule, assign accounts, publish
4. **Optimization** — operator-facing outcome hints and routing recommendations

The home dashboard (`/`) aggregates metrics from all areas and surfaces a prioritized action queue so the operator always knows what needs attention next.

---

## Ops Areas

The Ops Console (`/ops`) is the operational control surface for running and debugging the system. It does not participate in the content workflow; it exposes infrastructure state:

- **Health** — API, database, worker, queue, storage summary
- **Jobs** — all durable job states; retry/cancel controls
- **Assets** — media asset lifecycle state
- **Publish Ops** — attempt history, reconciliation, outcome tracking
- **Accounts & Routing** — platform account health, assignment queue, routing rules
- **Risk & Policies** — risk flag management and decisions
- **Tools** — local runbooks and API Swagger link

---

## Component and Layout Structure

```
apps/web/src/
  app/                          # Next.js App Router pages (thin wrappers)
  components/
    app-shell/
      AppShell.tsx               # Root layout: sidebar + topbar + content area
      Sidebar.tsx                # Nav sidebar with surface-aware highlight
      Topbar.tsx                 # Surface label, page title, quick actions menu
      OperatorStudioShell.tsx    # Wraps Operator Studio pages with operatorNavSections
      OpsConsoleShell.tsx        # Wraps Ops Console pages with opsNavSections
    operator-home/               # Home dashboard components
    operator-routes/             # Thin page-level components for operator routes
    review-board/                # Review board components
    transcript-editor/           # Transcript editor components
    final-review/                # Final review components
    publish-draft/               # Publish draft components
    ops-console/                # Ops console page components
    optimization/                # Optimization components
    risk/                        # Risk components
    publish-health/              # Publish health components
    publish-control/             # Publish control components
  lib/
    navigationConfig.ts          # operatorNavSections + opsNavSections
    operatorHomeState.ts         # State builders for home dashboard
    statusLabels.ts             # Human-readable enum formatters
    api.ts                       # API client (all /api/* calls)
  test/
    *.test.ts                   # State/logic tests
    route-nav.test.ts           # Route map validation test
  types/
    *.ts                        # Shared TypeScript types
```

**Layout pattern:** every page in the app router is a thin wrapper that delegates to a component. The component is wrapped by `OperatorStudioShell` or `OpsConsoleShell`, which provide the shared sidebar + topbar. This keeps the shell consistent across all pages.

**State pattern:** `operatorHomeState.ts` exposes pure functions (`buildOperatorMetrics`, `buildActionQueue`, `buildQuickLaunchItems`, `buildContinueItems`) that derive UI state from API response data. These functions are tested in `operator-home.test.ts` and route links are validated in `route-nav.test.ts`.

---

## Known Limitations

These are honest gaps in the current Phase 1 implementation. Do not treat as bugs; treat as documented scope limits.

### Placeholder Routes
- `/intake/profiles` — no API list endpoint for source profiles yet
- `/intake/crawl-sessions` — no API list endpoint for crawl sessions yet
- `/production/downloads` — no download management UI yet

### Incomplete Operational Gaps
- **Redis health** — `/ops/health` does not query Redis; heartbeat is inferred from job state
- **Worker heartbeat** — no dedicated worker ping endpoint; liveness is implied by recent job timestamps
- **Asset missing/corrupt scan** — no scheduled scan that flags orphaned or corrupted media assets

### Publish Draft Editor
- The editor at `/source-videos/[id]/publish` is kept as a functional alias. Once a mechanism exists to look up a draft by source video ID, this route should redirect to `/publishing/drafts/{id}` instead.

### Feature Pages Still Own Their Headers
- Existing feature pages (`ReviewBoardPage`, `OperatorPublishDraftPage`, etc.) still render their own internal `<header>` elements. The shell wrapping is intentionally conservative to avoid layout breakage.

### No Multi-User Support
- The UI assumes a single operator. User/role/auth concepts are not modeled in the UI layer yet.

---

## Next Possible Improvements

Ordered roughly by priority for future sessions:

1. **API-backed intake screens** — add `GET /source-profiles` and `GET /crawl-sessions` endpoints, then wire up `/intake/profiles` and `/intake/crawl-sessions`
2. **Redirect `/source-videos/[id]/publish`** — once draft lookup by source video ID is possible
3. **Redis reachability check** — add to `/ops/health`
4. **Dedicated worker heartbeat endpoint** — `/ops/health` or a new `/ops/worker` route
5. **Asset scan result page** — expand `/ops/assets` beyond status listing
6. **Shell wrapping audit** — check whether existing feature page headers can be removed now that Topbar is consistent
7. **Auth/user model** — add operator identity once multi-user is planned

---

## Files Created During Unification

```
apps/web/src/components/app-shell/AppShell.tsx
apps/web/src/components/app-shell/Sidebar.tsx
apps/web/src/components/app-shell/Topbar.tsx
apps/web/src/components/app-shell/PageShell.tsx
apps/web/src/components/app-shell/NavSection.tsx
apps/web/src/components/app-shell/StatusBadge.tsx
apps/web/src/components/app-shell/OperatorStudioShell.tsx
apps/web/src/components/app-shell/OpsConsoleShell.tsx
apps/web/src/components/operator-home/OperatorHomePage.tsx
apps/web/src/components/operator-home/OverviewCards.tsx
apps/web/src/components/operator-home/ActionQueuePanel.tsx
apps/web/src/components/operator-home/RecentActivityPanel.tsx
apps/web/src/components/operator-home/QuickLaunchGrid.tsx
apps/web/src/components/operator-home/ContinuePanel.tsx
apps/web/src/components/operator-routes/OperatorReviewBoardPage.tsx
apps/web/src/components/operator-routes/OperatorTranscriptEditorPage.tsx
apps/web/src/components/operator-routes/OperatorFinalReviewPage.tsx
apps/web/src/components/operator-routes/OperatorPublishDraftPage.tsx
apps/web/src/components/operator-routes/PublishDraftsIndexPage.tsx
apps/web/src/components/operator-routes/PublishDraftByIdPage.tsx
apps/web/src/lib/operatorHomeState.ts
apps/web/src/test/operator-home.test.ts
apps/web/src/test/route-nav.test.ts
apps/web/src/app/                        # All page.tsx route files
```

---

## Verification Commands

```powershell
# Type check
npm --workspace @reup-douyin/web run typecheck

# All tests (10 suites)
npm --workspace @reup-douyin/web run test

# Production build
npm --workspace @reup-douyin/web run build

# Start dev services
.\scripts\dev-start.ps1
# Verify home at http://localhost:3000/
# Verify ops at http://localhost:3000/ops
# Verify API docs at http://127.0.0.1:8000/docs
```

---

## Log Reference

- `docs/ui-unification-log.md` — step-by-step implementation log
- `docs/ui-unification-resume.md` — current state and completion status
- `docs/ui-unification-plan.md` — original plan and scope definition
