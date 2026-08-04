# Operator Home V2

## Purpose

`/` is the single-operator command center for the local-first workflow. It answers:

1. What is blocked or needs a decision?
2. What production work is moving now?
3. Which stage or checkpoint should the operator open next?

## Authority

The web page reads one workspace-scoped contract:

- `GET /operator/home-summary`

`apps/api/src/services/operator_home_summary_service.py` owns aggregation. The web app does not count paginated candidate/job lists or read local artifact paths.

The contract contains:

- overall status and freshness;
- four decision metrics;
- top priority items;
- exclusive workload buckets for each stage (`waiting`, `running`, `manual review`, `failed`, `ready`);
- canonical Output QA totals (`passed`, `warned`, `failed`, `ungraded`);
- an exclusive attention breakdown (`critical`, non-review `warning`, `manual_review`);
- Capture → Review → Reup Queue → Download → Audio → Translate → TTS → OCR → Render → Output Review → Draft → Export → Handoff stages;
- one active durable job context;
- manual checkpoints;
- recent render outputs and canonical render QA status;
- local API/worker/OCR/TTS/extension readiness.

Render QA continues to use `ReupQueueItem.metadata_json.render_qa` as its canonical read authority. The Home service does not re-run or re-derive QA.

## Visualization rules

- The four decision metrics render as visual summary cards below the overall status bar.
- Pipeline workload uses stacked horizontal bars on one shared scale across all stages. It is a backlog snapshot, not a conversion funnel.
- Attention categories are computed by the API, not from the web's top-five priority list. Manual-review warnings are excluded from the generic warning bucket, and failed Output QA items remain critical rather than being counted twice.
- Attention categories use a compact donut with an exact-value legend.
- Output QA uses a 100% segmented bar only when canonical outputs exist; an empty workspace renders a neutral track.
- Manual checkpoint bars link to the page that owns the operator decision.
- Priority Inbox, Active Work, Recent Outputs, and System Readiness remain visible actionable lists because their primary purpose is navigation and diagnosis, not comparison.

## Historical boundary

- The current endpoint is a point-in-time snapshot and must not claim throughput trends, lead-time trends, or forecasts.
- A future Bottleneck Quadrant or seven-day throughput chart requires persisted workspace-scoped snapshots, retention rules, and a documented sampling job before UI work begins.
- Until that authority exists, Home shows point-in-time workload and QA counts only. Canonical `oldest_at` metadata remains available in the API for future age-aware views.

## Boundaries

- Home is read-only. Actions are links to the stage that owns the mutation.
- No browser-side database access or local-path parsing.
- No trend percentage is shown until historical snapshots exist.
- Phase-2 artifact folders are not scraped directly. Their state appears only after a canonical API/DB adapter records it.
- Ops-only monitoring URLs are projected onto safe Operator Studio destinations.

## Failure behavior

- A summary request failure uses the shared async error/retry state.
- Provider readiness may be `unknown` when no canonical job history exists.
- Empty workspaces render quiet/empty states without inventing counts.
- Workspace scoping is applied to every database aggregation.

## Tests

- `apps/api/tests/test_operator_home_summary_service.py`
- `apps/web/src/test/operator-home-ui.test.ts`
- Existing operator boundary, async UX, and route-navigation tests remain applicable.
