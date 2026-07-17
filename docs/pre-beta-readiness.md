# Pre-Beta Readiness

## Overall Assessment

The repo is close to a local-first pre-beta foundation: the major Phase 1 modules exist, docs and seed data are present, and the new operational scripts reduce setup friction. The biggest remaining risks are provider realism, local dependency variance, and failure recovery in real long-running media jobs.

## Strengths

- Clear app boundaries between web, API, worker, shared packages, and docs.
- Durable domain model for source videos, candidates, media assets, transcripts, render outputs, publish drafts, jobs, and risk flags.
- Job/step state machine is explicit and test-covered.
- UI flow covers review board, transcript editor, final review, publish draft, and risk warning surfaces.
- Media, audio, TTS, render, and publish modules use abstractions instead of hardcoding future providers.
- Alpha fixture and seed data allow demos without live Douyin or real render providers.
- Runbooks exist for common pipeline failure classes.
- `/ops/metrics` gives a first operational view of backlog, failures, duration, assets, render, publish, and risk state.

## Weaknesses And Risks

- Many media providers are placeholders or mocked; real provider integration will expose timing and artifact edge cases.
- Local dependency setup still depends on Python, Node, PostgreSQL, and ffmpeg being installed correctly.
- Queueing is still a local worker loop, not Redis-backed distributed processing.
- Some stale/current policies rely on service discipline rather than database-enforced invariants.
- Real playable media validation is limited until actual downloaded/rendered assets exist.
- UI tests cover state helpers more than browser-level behavior.
- No production auth, multi-user ownership, or billing.

## Fix Before Pre-Beta

- Verify `dev-doctor`, migration, seed, API, web, and worker on a clean Windows machine.
- Run a real local render with ffmpeg installed and capture any missing validation.
- Confirm `/ops/metrics` loads against a seeded database.
- Add one manual smoke pass for each primary screen using seeded data.
- Tighten any provider error messages that are ambiguous during first real pipeline run.

## Can Wait Until After Pre-Beta

- Redis queue backend.
- Object storage backend.
- Publish connectors and OAuth.
- Multi-user auth and permissions.
- Advanced OCR/compliance/legal moderation.
- Browser E2E suite.
- Cloud deployment packaging.

## Recommended Operator Workflow

1. Run `scripts/dev-doctor.ps1`.
2. Run migrations and seed demo data.
3. Start API, web, and worker with `scripts/dev-start.ps1`.
4. Use review board to shortlist candidates.
5. Inspect transcript editor and final review for seeded processed videos.
6. Open publish draft and risk warnings before marking ready.
7. Check `/ops/metrics` after running jobs or simulated failures.

## Step 17 Validation Artifacts

- `docs/pre-beta-test-plan.md`: suite-by-suite validation plan.
- `docs/bug-bash-plan.md`: controlled breakage scenarios.
- `docs/operator-pilot-workflow.md`: daily pilot workflow and load levels.
- `docs/issue-taxonomy-and-triage.md`: issue categories, severity, repro quality, and triage rules.
- `docs/go-no-go-criteria.md`: decision framework for whether to build the first real publish connector.
- `docs/templates/`: report templates for daily logs, issue capture, bug bash, and pilot summary.
- `scripts/new-pilot-report.ps1`: creates a working report folder from templates.

## Exit Criteria For Step 17

- A clean local machine can follow docs and run the demo without code spelunking.
- At least one real media item can pass download, audio/TTS/render, and final review locally.
- Common failures are visible in job state, runbooks, and `/ops/metrics`.
- Publish draft contract is stable enough for a real connector to consume.
- Known provider placeholders are explicitly listed before beta users see them.

## Area Review

- Architecture: strong boundaries, still needs real queue/storage adapters later.
- Backend: good service layering; needs real provider stress tests.
- Frontend: usable operator screens; should gain browser E2E before wider beta.
- Worker pipeline: clear job templates; local-only claim/backpressure remains the main limit.
- Operational readiness: improved by scripts, doctor, seed, smoke, and metrics.
- Performance: reuse policy is documented; real cache invalidation must be tested with real assets.
- Local packaging: acceptable for pre-beta dev/operator usage, not yet one-click installer.
- Docs: broad coverage with setup, demo, runbooks, readiness, and policies.
- Test reliability: core logic covered; provider and browser integration still thin.
- Demo readiness: seeded happy/warning/failure paths exist and should be validated on a clean setup.
