# Continuation Handoff

This document preserves the working context for continuing `reup-douyin` after Step 22. Read this file before starting Step 23 or any later work.

## Current Status

The project has completed Steps 1 through 22.

`reup-douyin` is a local-first, SaaS-ready monorepo:

- `apps/web`: Next.js + TypeScript operator UI.
- `apps/api`: FastAPI, SQLAlchemy, Alembic, API contracts, service layer, domain models.
- `apps/worker`: Python local worker loop for durable jobs.
- `packages/shared`: shared contracts/placeholders.
- `packages/config`: shared config conventions.
- `docs`: architecture, lifecycle, runbooks, validation plans, operational docs.

The repository currently contains nearly the full Phase 1 workflow:

```text
ingest profile/video
  -> filter + Reup Score
  -> review board
  -> download + media assets
  -> audio analysis
  -> transcript editor
  -> TTS + subtitle prep
  -> render final
  -> final review
  -> publish draft
  -> risk scan/gating
  -> Facebook Reels publish connector foundation
  -> publish reconciliation/status hardening
  -> post-publish analytics-lite and operator feedback loop
  -> multi-Page/account publish control plane
  -> feedback-driven optimization and semi-automation hints
```

## Completed Steps Summary

1. Monorepo scaffold, `AGENTS.md`, root/app/package READMEs, foundational docs.
2. Core domain schema, SQLAlchemy models, enums, Alembic migration, lifecycle docs.
3. Job system foundation: `Job`, `JobStep`, state machine, progress tracking, API, worker skeleton.
4. Source adapter architecture and Douyin profile ingest foundation.
5. Filter engine, Reup Score v1, presets, candidate persistence/API/docs/tests.
6. Review board UI for candidate scanning, bulk keep/reject, score breakdown.
7. Media download/storage abstraction, local storage backend, asset manifest.
8. Audio analysis pipeline, transcript and translation draft persistence.
9. Transcript editor UI and review pass.
10. TTS pipeline, subtitle generation, render-prep manifest.
11. Render engine foundation, RenderOutput persistence/API/docs/tests.
12. Final review UI, compare flow, approve export, publish-ready state.
13. Publish draft domain, scheduling skeleton, caption/CTA/hashtag UI/API.
14. Risk scan taxonomy, warnings, gate policy, operator decision flow.
15. Fixtures, seed data, runbooks, alpha readiness report.
16. Stabilization pass: scripts, doctor/smoke checks, `/ops/metrics`, pre-beta readiness.
17. Pre-beta validation: test plan, bug bash, operator pilot workflow, taxonomy, go/no-go criteria.
18. First real connector foundation: Facebook Reels publishing for Facebook Pages.
19. Publish connector hardening: reconciliation service, publish history, publication summary, refresh/reconcile APIs, minimal post-publish tracking.
20. Analytics-lite: publish health dashboard, operator feedback, failure/account summaries, pipeline outcome grouping.
21. Multi-account scaling: account health-aware routing recommendations, draft assignment/reassignment, publish control plane.
22. Feedback-driven optimization: outcome score, optimization dashboard, routing/scheduling hints, semi-automation guardrails.
23. SaaS readiness hardening: JWT-gated app routes, bootstrap auth UI, AES-256-GCM Douyin secret envelopes, Redis worker broker, and tenant-scoped Ops Console queries.

## SaaS Readiness Hardening State

The current commercial-readiness pass upgrades the local-first stack without changing Phase 1 product scope.

Implemented upgrades:

- API routes are protected by bearer JWT; public auth surfaces: `/auth/ui` (backend HTML login), `/auth/login`, `/auth/register` (flaggable), `/auth/refresh`, `/auth/logout`, `/auth/invites`, `/auth/invites/accept`, `/auth/me`.
- Phase A (2026-07-17): durable `operators` table, PBKDF2 password hashing, JWT workspace bound to DB (`local` / alias `local-workspace`).
- Phase B (2026-07-17): rotatable refresh tokens (hashed in DB), short access TTL (`AUTH_ACCESS_TOKEN_TTL_MINUTES`, default 30), login/register rate limit, `AUTH_REGISTRATION_ENABLED`, Next.js middleware soft HTML gate via `reup_douyin_session` cookie, web refresh-on-401.
- Phase C (2026-07-17): JWT `iss`/`aud` write+verify when configured; `workspace_memberships` roles; minimal invite create/accept (`/auth/invite` UI).
- Login surfaces (Next.js): Operator Studio at `/auth/login` (`client=operator`); Ops Console at `/auth/ops/login` (`client=ops`, **owner/admin only**). Cross-surface HTML routes are blocked (Capture Inbox stays Operator despite `/ops/...` path).
- API `/ops/*` requires Ops token; Operator Studio token receives 403 on Ops APIs. Swagger helper `:8000/auth/ui` remains tertiary `api-ui` read-only tooling.
- Local owner bootstrap: `python -m scripts.ensure_local_admin` (from `apps/api`) creates/updates `admin@local.test` with role `owner`.
- Web: localStorage access + refresh tokens, `/auth/me` hydrate (includes memberships), revoke refresh on logout, allowlisted `?next=`, default redirect to Operator Home `/`.
- Douyin session secrets now use AES-256-GCM `envelope-v1` encryption when `DOUYIN_SECRET_ENCRYPTION_KEY_REF` is configured.
- `local-v1` Douyin secret values are still readable only for backwards-compatible local development data.
- The worker can use Redis via `REDIS_URL` as a broker/wake-up queue while PostgreSQL remains the durable job source of truth.
- Ops Console metrics and pipeline dashboard services are scoped by the authenticated `workspace_id` from `get_current_workspace`.
- Docker Compose now includes PostgreSQL, Redis, API, worker, and web services with explicit environment validation hooks.

Important boundaries:

- Redis messages are broker hints only; the worker still claims executable jobs from PostgreSQL to preserve locking/idempotency behavior.
- Refresh tokens are stored hashed server-side; browser still keeps refresh in localStorage (extension Bearer bridge). Full httpOnly cookie session remains optional hardening.
- Full OIDC IdP remains future work; internal HS256 issuer stays IdP-replaceable at `src/core/auth.py`.
- Production deployments must replace local placeholder secrets with real secret manager/KMS-backed key material.
- `APP_ENV=production` intentionally rejects localhost CORS origins; use production origins for real deployments and local/non-production environment names for host-local Compose validation.
- Old Phase A access-only JWTs without refresh still work until expiry; operators should re-login to obtain a refresh session.

## Step 22 Optimization State

Step 22 adds an explainable optimization loop. It does not add ML, connector #2, or full autopublish.

New backend package:

- `apps/api/src/optimization`

New API endpoints:

- `GET /optimization/dashboard-snapshot`
- `GET /optimization/outcome-summaries`
- `GET /optimization/outcome-score/{target_id}`
- `GET /optimization/routing-hints`
- `GET /optimization/scheduling-hints`
- `GET /optimization/manual-touch-summary`
- `GET /optimization/preset-feedback`

New frontend route:

- `/optimization`

New docs:

- `docs/outcome-quality-model.md`
- `docs/feedback-driven-optimization.md`
- `docs/routing-and-scheduling-hints.md`
- `docs/semi-automation-guardrails.md`
- `docs/manual-touch-reduction.md`

Optimization strategy:

- `OUTCOME_SCORE_V1` is computed on read from existing data.
- Outcome summaries group by source profile, niche, preset, account, and score bucket.
- Routing hints refine Step 21 recommendations with outcome score.
- Scheduling hints are slot suggestions only, not an automatic scheduler.
- Guardrails block auto-assign/schedule when confidence, risk, account health, or draft state is not safe.

## Step 21 Multi-Account Routing State

Step 21 scales the first connector across multiple Facebook Pages/accounts. It does not add a second platform connector.

New backend concepts:

- `PublishAccountAssignmentStatus`
- `PublishRoutingRuleStatus`
- `PlatformAccountHealthStatus`
- `PublishRoutingRule`

Updated persistence:

- `PlatformAccount` now has priority, hold/cooldown, allowed-niche hints, and routing notes.
- `PublishDraft` now has assignment fields for intended platform account routing.
- Alembic migration: `0015_publish_multi_account_routing.py`

New API endpoints:

- `GET /publish-control/accounts`
- `GET /publish-control/queue`
- `GET /publish-routing/recommendations`
- `POST /publish-drafts/{publish_draft_id}/assign-account`
- `POST /publish-drafts/{publish_draft_id}/unassign-account`
- `POST /publish-drafts/bulk-assign`
- `GET /routing-rules`
- `POST /routing-rules`
- `PATCH /routing-rules/{rule_id}`

New frontend route:

- `/publish-control`

New docs:

- `docs/multi-account-scaling-phase1.md`
- `docs/publish-routing-rules.md`
- `docs/operator-control-plane.md`
- `docs/account-health-model.md`

Routing strategy:

- manual assignment remains the base flow
- routing recommendations are deterministic hints
- account health blocks `HELD` and `UNHEALTHY` accounts
- operator override is allowed but recorded as `OVERRIDDEN`
- no ML routing, no cross-platform routing, no automatic publish scheduler

## Step 20 Analytics-Lite State

Step 20 added a small operational analytics layer. It does not implement deep engagement analytics.

New backend concept:

- `OperatorFeedback`

New API endpoints:

- `GET /analytics/publish-health`
- `GET /analytics/dashboard-snapshot`
- `GET /analytics/publication-outcomes`
- `GET /analytics/failure-summary`
- `GET /analytics/pipeline-feedback`
- `POST /operator-feedback`
- `GET /operator-feedback`

New dashboard route:

- `apps/web`: `/dashboard/publish-health`

New docs:

- `docs/post-publish-analytics-lite.md`
- `docs/publish-health-dashboard.md`
- `docs/operator-feedback-loop.md`
- `docs/pipeline-outcome-feedback.md`

Analytics-lite strategy:

- Existing publish/source/candidate/risk tables remain source of truth.
- Dashboard summaries are computed on read.
- `OperatorFeedback` is the only new persistence table.
- No views/likes/comments/revenue attribution are tracked yet.

## Step 18/19 Publish State

Step 18 added the first real publish connector path for Facebook Reels/Page publishing.

New/updated backend concepts:

- `PlatformAccount`
- `PublishAttempt`
- `PlatformAccountStatus`
- `PublishAttemptStatus`
- `ExternalPublicationStatus`
- `PublishReconciliationStatus`
- `JobType.PUBLISH_CONTENT`
- `JobType.REFRESH_PUBLISH_STATUS`
- `JobType.RECONCILE_PUBLISH_ATTEMPT`
- Alembic migration: `0011_facebook_publish_connector.py`
- Alembic migration: `0012_publish_reconciliation_hardening.py`
- Alembic migration: `0013_publish_reconciliation_job_types.py`

New API endpoints:

- `POST /platform-accounts`
- `GET /platform-accounts`
- `GET /platform-accounts/{platform_account_id}`
- `PATCH /platform-accounts/{platform_account_id}`
- `POST /publish-drafts/{publish_draft_id}/publish`
- `GET /publish-attempts`
- `GET /publish-attempts/{publish_attempt_id}`
- `POST /publish-attempts/{publish_attempt_id}/refresh-status`
- `POST /publish-drafts/{publish_draft_id}/reconcile`
- `GET /publish-drafts/{publish_draft_id}/publish-history`
- `GET /publish-drafts/{publish_draft_id}/publication-summary`
- `GET /publish-drafts/{publish_draft_id}/publish-status`

New publish connector files:

- `apps/api/src/publish/types.py`
- `apps/api/src/publish/connectors/base.py`
- `apps/api/src/publish/connectors/facebook_reels.py`
- `apps/api/src/publish/services/platform_account_service.py`
- `apps/api/src/publish/services/publish_gate_service.py`
- `apps/api/src/publish/services/publish_lifecycle_service.py`
- `apps/api/src/publish/services/publish_reconciliation_service.py`
- `apps/api/src/publish/services/publish_attempt_service.py`

Frontend adjustment:

- `apps/web/src/components/publish-draft/PublishDraftPage.tsx` now has a small Facebook Page publish panel:
  - select active Facebook Page account
  - click `Publish now`
  - view recent attempt history
  - refresh ambiguous Facebook publish status
  - reconcile a draft and see canonical publication summary

Docs added:

- `docs/facebook-reels-connector.md`
- `docs/platform-account-setup-phase1.md`
- `docs/publish-attempt-lifecycle.md`
- `docs/publish-retry-and-idempotency.md`
- `docs/publish-connector-hardening.md`
- `docs/publish-reconciliation-flow.md`
- `docs/minimal-post-publish-tracking.md`
- `docs/canonical-publish-success-model.md`
- `docs/runbooks/facebook-publish-fail.md`

## Publish Connector Architecture

Current flow:

```text
PublishDraft READY
  -> PublishGateService
  -> PlatformAccountService
  -> PublishAttemptService
  -> PublishConnector interface
  -> FacebookReelsConnector
  -> PublishAttempt SUCCEEDED / FAILED / NEEDS_RECONCILIATION
  -> PublishLifecycleService syncs canonical/latest draft publication state
```

Important boundaries:

- `PublishDraft` remains the publish metadata contract.
- `PublishAttempt` records external publish side effects and retry history.
- `PublishGateService` owns risk/readiness gating.
- `PlatformAccountService` owns account/token config resolution.
- `FacebookReelsConnector` owns only Meta transport mapping.
- `PublishLifecycleService` owns canonical/latest publication state and reconciliation mapping.
- `PublishReconciliationService` owns manual status refresh, stale attempt handling, draft reconciliation, and publication summary assembly.
- Route handlers should stay thin.
- Facebook-specific logic should not be scattered inside `PublishDraftService`.

## Facebook Reels Flow Implemented

The connector follows Meta's Reels Publishing flow:

1. Create Reel upload session:
   - `POST /{page-id}/video_reels`
   - `upload_phase=start`
2. Upload local render file to `rupload.facebook.com`:
   - `Authorization: OAuth <page-access-token>`
   - `offset: 0`
   - `file_size: <bytes>`
3. Finish/publish:
   - `upload_phase=finish`
   - `video_state=PUBLISHED`
   - `title`
   - `description`

Reference docs used:

- Meta Postman Reels Publishing overview: `https://www.postman.com/meta/facebook/folder/simabyk/reels-publishing`
- Create Reel: `https://www.postman.com/meta/facebook/request/rgkn91u/1-create-reel`
- Upload Local Reel: `https://www.postman.com/meta/facebook/request/ps1ahe4/2-a-upload-local-reel`
- Publish Reel: `https://www.postman.com/meta/facebook/request/juhnm3q/4-publish-reel`

## Idempotency And Retry Strategy

Publishing has irreversible external side effects, so the current design is conservative.

Rules:

- Only one active `PublishAttempt` is allowed per `PublishDraft`.
- Active statuses:
  - `QUEUED`
  - `RUNNING`
  - `UPLOADING`
  - `PUBLISHING`
  - `AWAITING_PLATFORM_CONFIRMATION`
  - `RECONCILING`
- Duplicate active publish requests return `duplicate_active_attempt`.
- Failed attempts remain in DB for trace/debug.
- Retry creates the next `attempt_number`.
- Attempts with external ids and uncertain result move to `NEEDS_RECONCILIATION`.
- Operators should refresh/check `NEEDS_RECONCILIATION` attempts before retrying.
- `PublishDraft.READY` means metadata is ready for publishing.
- `PublishAttempt.FAILED` means one external attempt failed.
- `PublishDraft.NEEDS_ATTENTION` means latest publish state needs operator attention.
- `PublishDraft.PUBLISHED` is set only when a canonical attempt is confirmed published.

## Status Reconciliation

The current phase has explicit pull-based reconciliation, not webhooks.

```http
POST /publish-attempts/{publish_attempt_id}/refresh-status
```

This calls Facebook using the attempt external reference and updates:

- `PublishAttempt.external_status`
- `PublishAttempt.external_permalink`
- `PublishAttempt.reconciliation_status`
- `PublishDraft.current_publication_status`
- `PublishDraft.current_external_publish_id`
- `PublishDraft.current_external_permalink`
- `PublishDraft.canonical_publish_attempt_id`
- `PublishDraft.latest_publish_attempt_id`

Draft-level reconciliation:

```http
POST /publish-drafts/{publish_draft_id}/reconcile
```

Publication visibility:

```http
GET /publish-drafts/{publish_draft_id}/publish-history
GET /publish-drafts/{publish_draft_id}/publication-summary
```

## Security And Token Handling

Phase 1 uses manual account/token setup.

Current token resolution:

- `PlatformAccount.token_reference` stores the name of an environment variable.
- Default token reference: `FACEBOOK_PAGE_ACCESS_TOKEN`.
- The raw token value should live in the environment, not in code or docs.

Rules:

- Do not hardcode Facebook tokens.
- Do not commit real tokens.
- Do not log full tokens.
- Do not put full tokens in `metadata_json`.
- Rotate the token if it leaks into logs/screenshots/reports.

## Verification After Step 18

Last known verification:

- `python -m compileall apps\api apps\worker`: passed.
- `python -m unittest discover tests` from `apps/api`: passed, 56 tests.
- `npx --package tsx tsx src/test/publish-draft.test.ts`: passed after allowing `npx` network/cache outside the sandbox.

No real Facebook publish was run because no real Page access token/account config was provided.

## Known Environment Caveats

- The active Python environment previously lacked `sqlalchemy` until API dependencies were installed.
- `git` was not available in PATH during prior work.
- `npx --package tsx` may fail in sandbox/cache-only mode unless network/cache access is available.
- Facebook connector requires a real Page access token, for example:

```text
FACEBOOK_PAGE_ACCESS_TOKEN=<page-token>
```

## Important Files To Read Before Step 23

Start with:

- `AGENTS.md`
- `docs/continuation-handoff.md`
- `docs/publish-draft-overview.md`
- `docs/facebook-reels-connector.md`
- `docs/platform-account-setup-phase1.md`
- `docs/publish-attempt-lifecycle.md`
- `docs/publish-retry-and-idempotency.md`
- `docs/pre-beta-readiness.md`
- `docs/go-no-go-criteria.md`
- `docs/multi-account-scaling-phase1.md`
- `docs/outcome-quality-model.md`
- `docs/feedback-driven-optimization.md`
- `docs/semi-automation-guardrails.md`

Then inspect code:

- `apps/api/src/models/publish.py`
- `apps/api/src/schemas/publish.py`
- `apps/api/src/api/routes/publish.py`
- `apps/api/src/publish/connectors/facebook_reels.py`
- `apps/api/src/publish/services/platform_account_service.py`
- `apps/api/src/publish/services/publish_gate_service.py`
- `apps/api/src/publish/services/publish_attempt_service.py`
- `apps/api/src/services/job_templates.py`
- `apps/api/src/services/job_runner.py`
- `apps/api/src/optimization/services/outcome_score_service.py`
- `apps/api/src/optimization/services/routing_hint_service.py`
- `apps/web/src/components/publish-draft/PublishDraftPage.tsx`
- `apps/web/src/components/optimization/OptimizationPage.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/publish-draft.ts`

## Do Not Do Accidentally

Do not start these unless explicitly requested:

- TikTok connector.
- YouTube connector.
- OAuth onboarding flow.
- Analytics/reporting dashboard.
- Social comment inbox/moderation.
- Multi-user approval workflow.
- Cloud deployment.
- Major architecture rewrite.
- Legal/compliance engine beyond the current risk warning layer.

## Suggested Step 23

Recommended next step: run a real multi-account pilot and validate whether the optimization hints improve operator decisions before adding connector #2.

Suggested scope:

1. Run migrations through `0015_publish_multi_account_routing`.
2. Configure at least two Facebook Page `PlatformAccount` records.
3. Seed or process enough `PublishDraft READY` items for routing comparison.
4. Use `/publish-control` for assignment/reassignment.
5. Use `/optimization` to inspect outcome, routing, and scheduling hints.
6. Publish a small controlled batch and capture real Meta API errors:
   - permissions
   - app mode/live mode
   - token expiration
   - video requirements
   - upload failures
7. Harden error mapping based on real responses.
8. Use `docs/runbooks/facebook-publish-fail.md` to handle real failures.
9. Add optional manual verification helper only if real testing proves it necessary:
   - validate account config
   - dry-run request builder
   - token reachability check

## Suggested Step 24+

Possible future directions after Step 19:

- Add webhook or scheduled polling for ambiguous Facebook publish results if manual refresh is not enough.
- Add a minimal account validation endpoint.
- Add browser-level manual QA checklist for publish draft and attempts.
- Only after Facebook connector is stable, choose the second connector pattern.

Do not add a second connector until Facebook publish has been manually verified against a real Page and the error handling has been hardened.
