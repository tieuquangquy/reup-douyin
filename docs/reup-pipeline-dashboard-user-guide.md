# Reup Pipeline Dashboard User Guide

## Purpose

`/ops/pipeline` is the read-only operator command view for the full workflow:

Capture -> Review -> Reup Queue -> Download -> Audio -> Translate -> TTS -> OCR -> Render -> Output Review -> Draft -> Export Package -> Publish Handoff.

Use it to identify the largest current workload, blocked stages, manual checkpoints, and the next stage-owned surface to open.

## Main sections

### Control strip

The single-line control strip shows generation time, overall status, and four point-in-time metrics without Home-style KPI cards:

- Active backlog: waiting, running, manual-review, or failed records across the stage map.
- Attention workload: affected records represented by critical and warning categories.
- Running: durable records currently running.
- Ready downstream: QA-passed outputs, ready Export Packages, and ready Publish Handoffs.

Lifetime Published is intentionally not compared with these snapshot metrics.

### Pipeline Operations Board

The dominant view is a 13-row operational matrix grouped into Intake, Production, and Delivery. Every row exposes exact stage-owned bucket counts:

- Waiting
- Running
- Manual review
- Failed
- Ready

Cell background intensity highlights high workload relative to the same bucket column. It is not a completion percentage or conversion funnel.

On desktop, the Operations Board occupies roughly 70% of the workspace and a sticky Stage Focus Rail occupies the remaining 30%. Select a stage name to update that rail with its description, bucket totals, recommended action, exceptions, and owning-surface link. On narrower screens the rail moves below the board.

### Output QA

Output QA does not occupy a permanent dashboard card. Select Output Review in the Operations Board to show the canonical distribution inside Stage Inspector:

- Passed
- Warning
- Failed
- Ungraded

### Exception Queue

This compact table ranks critical and warning categories by severity and affected count. Each row links to the stage-owned surface where the operator can act.

### Event Tape

The Event Tape is a compact lifecycle timeline from capture, Reup Queue, production jobs, render outputs, export, handoff, and draft records.

## Status labels

- Healthy: ready work exists without a blocker.
- In progress: work is running.
- Needs attention: waiting or manual-review work exists.
- Blocked: failed records require action.
- Quiet: no current workload exists.

## Recommended operator flow

1. Check overall status and Attention workload in the control strip.
2. Scan the Failed and Manual review columns in the Operations Board.
3. Select the affected stage and read Stage Inspector.
4. Open the stage-owned surface from Inspector or Exception Queue.
5. Resolve the issue, return to `/ops/pipeline`, and refresh the snapshot.

## Safety and limitations

- The dashboard never starts jobs or publishes content.
- It does not expose secrets, credentials, raw payloads, or private local paths.
- Trend, throughput, cycle-time, funnel, and backlog-history charts are not shown until a persisted historical authority exists.
- If the dashboard cannot load, retry and check the API service; stage-owned pages remain available directly.
