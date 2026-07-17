# Alpha Test Checklist

Run this before internal alpha sessions.

## Setup

- [ ] `.env` files exist for API, web, and worker.
- [ ] PostgreSQL is running and `DATABASE_URL` is correct.
- [ ] `.\scripts\dev-doctor.ps1` completed with no failures.
- [ ] `.\scripts\dev-migrate.ps1` completed.
- [ ] `.\scripts\dev-reseed.ps1` completed.
- [ ] `.\scripts\smoke-check.ps1` completed.

## Services

- [ ] API, web, and worker start through `.\scripts\dev-start.ps1`.
- [ ] API can serve `/docs`.
- [ ] `GET /ops/metrics` returns operational metrics.
- [ ] `.\scripts\new-pilot-report.ps1 -Name pilot-001` creates a report folder if this is a pilot session.

## Demo Data

- [ ] `GET /candidates` returns seeded candidates.
- [ ] `GET /publish-drafts` returns at least one draft.
- [ ] `GET /risk-flags` returns warning-path flags.
- [ ] Local storage root contains demo media files.
- [ ] `GET /ops/metrics` shows seeded jobs, render outputs, publish drafts, and risk counts.

## Operator Flow

- [ ] Review board loads.
- [ ] Transcript editor opens a seeded rendered video.
- [ ] Final review opens a seeded render.
- [ ] Risk scan can run from final review.
- [ ] Publish draft page opens for a publish-ready video.
- [ ] Publish draft can save caption/CTA/hashtags.
- [ ] Scheduling skeleton can set and clear planned time.

## Known Alpha Limits

- [ ] No live publish connector.
- [ ] No real OAuth/account linking.
- [ ] No legal/compliance automation.
- [ ] Media demo assets are placeholders unless real pipeline steps were run.
- [ ] Local worker is not a distributed queue replacement.

## Pre-Beta Validation Links

- `docs/pre-beta-test-plan.md`
- `docs/bug-bash-plan.md`
- `docs/operator-pilot-workflow.md`
- `docs/issue-taxonomy-and-triage.md`
- `docs/go-no-go-criteria.md`
