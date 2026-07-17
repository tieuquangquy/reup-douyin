# Reup Pipeline Dashboard User Guide

## What This Dashboard Is

The Reup Pipeline Dashboard is the top-level operator command view for the full workflow:

Capture -> Review -> Reup Queue -> Export Package -> Publish Handoff -> Publish progress.

It helps operators answer:

- What is happening across the pipeline now?
- Where is work blocked?
- Where is the biggest backlog?
- What needs attention next?
- How much content has progressed from capture toward publish?

## Route

Open the dashboard at:

- `/ops/pipeline`

## Main Sections

### Header

Shows overall pipeline status, generated time, and a short operator-focused summary.

### Pipeline summary strip

Shows high-level counts such as captures in the last 24 hours, active backlog, attention items, export-ready content, handoff-ready content, and publish progress.

### Stage cards

Each card represents one canonical stage:

1. Capture
2. Review
3. Reup Queue
4. Export Package
5. Publish Handoff
6. Publish progress

Each stage card includes:

- Current stage health.
- Primary backlog or throughput count.
- Secondary progress count.
- Short next action recommendation.
- Link to the canonical workflow surface.

### Stage visualization

The visualization shows progress from left to right across the canonical workflow. It is a summary only; operators should use the canonical stage pages for detailed work.

### Attention / blockers

This panel lists items that may require operator action, such as:

- Capture failures.
- Capture items ready but not promoted.
- Review backlog.
- Approved candidates not yet queued.
- Reup Queue blocked or failed items.
- Queue items waiting for media or metadata.
- Export packages ready for handoff.
- Handoffs ready for operator acceptance.
- Publish attempts that failed or need reconciliation.

### Recent activity

Shows recent high-level lifecycle events across stages. This helps operators confirm that content is moving through the pipeline.

### Quick actions

Quick links take operators to the canonical surfaces:

- Capture Inbox
- Review Board
- Reup Queue
- Export Packages
- Publish Handoffs
- Publish Drafts
- Publish Health
- Publish Attempts
- Reconciliation

## Status Labels

The dashboard uses operator-facing status labels:

- Healthy: no obvious blocker.
- In progress: active work is moving.
- Needs attention: backlog or warning exists.
- Blocked: failures or blockers require action.
- Quiet: no active backlog or recent movement.

These labels summarize pipeline health. They do not replace the underlying canonical statuses used by each stage.

## Recommended Operator Flow

1. Start at `/ops/pipeline`.
2. Check the overall status and summary strip.
3. Review the attention panel first.
4. Open the canonical stage link for the highest-severity blocker.
5. Complete actions in the stage-specific surface.
6. Return to `/ops/pipeline` to confirm the pipeline moved forward.

## Safety Notes

- The dashboard is read-only.
- It does not run crawlers, video processing, rendering, or publish actions.
- It does not expose raw secrets, tokens, cookies, credentials, or private local paths.
- Publishing remains controlled by the dedicated publish surfaces and existing guardrails.

## Empty State

If there is no data, the dashboard should show a quiet pipeline and guide the operator to start with Capture Inbox.

## Error State

If the dashboard cannot load, operators should retry the page and then check whether the API service is running. The dashboard should not hide canonical stage pages; operators can still open those pages directly if needed.
