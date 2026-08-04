# Reup Pipeline Dashboard Architecture

## Boundary

`apps/web` renders `/ops/pipeline` from one read-only API contract. It does not query persistence, infer job state, or mutate work.

`apps/api` owns aggregation at `GET /pipeline-dashboard`. The endpoint is workspace-scoped and returns safe counts, labels, timestamps, and navigation targets. Long-running work remains in `apps/worker` and existing durable job orchestration.

## Canonical stage authority

`apps/api/src/services/pipeline_stage_snapshot.py` owns the shared 13-stage builder used by Pipeline and consumed by Home:

1. `capture`
2. `review`
3. `reup_queue`
4. `download`
5. `audio_analysis`
6. `translate`
7. `tts`
8. `ocr`
9. `render`
10. `output_review`
11. `draft`
12. `export_package`
13. `publish_handoff`

Each `PipelineDashboardStage` exposes exclusive buckets within that stage:

- `waiting_count`
- `running_count`
- `review_count`
- `failed_count`
- `ready_count`
- `total_count`

`total_count` is the sum of those five fields. Status is derived in priority order: failed, review/waiting, running, ready, quiet.

Legacy primary/secondary fields remain in the contract temporarily for older Home fallback consumers, but chart code must read the canonical bucket fields.

## Aggregation sources

- Capture: `captured_items`; the 24-hour metric counts items, not sessions.
- Review: `video_candidates` plus the absence of `reup_queue_items.video_candidate_id` for approved-not-queued work.
- Reup Queue: stage-owned `ReupQueueStatus` values.
- Download through Render: `jobs` grouped by `JobType` and `JobStatus`.
- Output Review: `reup_queue_items.metadata_json.render_qa` for rows linked to a render output.
- Draft: current `publish_drafts` states; lifetime Published is excluded from workload KPIs.
- Export Package: `export_packages` stage-owned statuses.
- Publish Handoff: `publish_handoffs` stage-owned statuses.

## Response contract

Top-level fields:

- `generated_at`
- `overall_status`
- `headline`
- `summary_metrics`
- `stages`
- `attention_items`
- `output_qa_summary`
- `recent_activity`
- `quick_links`

Attention workload is the sum of affected record counts, not the number of warning categories. Attention categories remain explicit because some stages use different entity types.

Output QA keeps four canonical buckets: `passed`, `warned`, `failed`, and `ungraded`.

Quick links are API-owned so the web does not maintain a second stage-navigation authority.

## Operations Board decisions

- Control strip: overall status, freshness, and four comparable metrics rendered inline rather than as KPI cards.
- Operations Board: semantic 13-row table grouped into Intake, Production, and Delivery.
- Bucket cells: exact values with column-relative heat intensity; intensity is never presented as progress.
- Stage Focus Rail: local selected-stage detail with recommended action and stage-scoped exceptions, composed beside the board in an approximately 70/30 desktop grid and moved below it responsively.
- Output QA: appears only when Output Review is selected, not as a permanent Home-style panel.
- Exception Queue: bounded severity-ranked action table.
- Event Tape: compact lifecycle timeline.

No chart dependency is required. The matrix uses semantic HTML and scoped CSS, preserving the local-first Windows setup and keyboard-accessible stage selection.

Historical throughput, cycle time, and backlog trend charts are deferred until persisted snapshots or event history provide a valid time-series authority. Funnel, Sankey, radar, and gauge views are intentionally excluded.

## Safety and observability

- All queries are scoped by authenticated `workspace_id`.
- The endpoint is read-only.
- No secrets, tokens, credentials, raw external payloads, or private local paths are returned.
- Recent Activity uses stable record IDs, safe status text, timestamps, and stage-owned links.

## Regression tests

API tests verify affected-workload Attention counts, the 13-stage order, exclusive production buckets, quiet state, Home reuse, and route authorization.

Web tests verify the API contract, flat Operations Board hierarchy, semantic table, heatmap cells, Stage Inspector selection, conditional Output QA, Exception Queue, Event Tape, accessibility labels, responsive CSS, and translation JSON validity.
