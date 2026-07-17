# Operator Pilot Workflow

This workflow simulates real use over several days before building a real publish connector.

## Daily Setup

1. Run `scripts/dev-doctor.ps1`.
2. Start services with `scripts/dev-start.ps1`.
3. Open `/ops/metrics`.
4. Open the daily log template from `docs/templates/daily-operator-log-template.md`.
5. Confirm local storage has enough free disk space for the planned load.

## Load Levels

### Light: 10-20 Videos / Day

Purpose: validate one operator can complete the full flow without fatigue.

Expected:

- 3-5 candidates kept.
- 1-3 videos reach final review.
- Most issues are UX clarity or provider placeholder limits.

### Medium: 30-50 Videos / Day

Purpose: expose batch review, job backlog, and transcript editing bottlenecks.

Expected:

- 8-15 candidates kept.
- 3-8 videos processed deeply.
- `/ops/metrics` should show manageable queued/retryable counts.

### Heavy: 80-100+ Videos / Day

Purpose: stress local workflow, not guarantee throughput.

Expected:

- Operator should identify bottlenecks within the first hour.
- Worker backlog is expected; hidden failures are not acceptable.
- This level is a pre-beta stress signal, not a Phase 1 promise.

## Daily Workflow

### 1. Ingest Batch

- Submit profile URLs or use seeded/demo data.
- Record source profile, crawl session ids, and discovered video counts.
- Check duplicate ingest behavior if crawling same profile again.

### 2. Filter And Review Batch

- Apply presets: `viral_discovery`, `safe_reup`, `affiliate_priority`.
- Review candidates in `/review-board`.
- Bulk keep/reject.
- Record number kept, rejected, and unclear.

### 3. Process Selected Subset

- Trigger download/media pipeline where available.
- Monitor jobs and `/ops/metrics`.
- Record retryable/failed jobs by type and error code.

### 4. Transcript Work

- Open transcript editor for processed videos.
- Edit only flagged or visibly bad segments first.
- Record number of segments edited, merged, split, and timing-adjusted.

### 5. TTS, Subtitle, Render

- Generate TTS/subtitle/render-prep.
- Render final video.
- Record timing fit warnings, render failures, and rerenders.

### 6. Final Review

- Compare original/final.
- Approve export only if playable, subtitle is readable, and narration timing is acceptable.
- Jump back to transcript editor if timing/text is wrong.

### 7. Publish Draft

- Create or open publish draft.
- Edit caption, CTA, hashtags, platform, schedule.
- Check risk summary before mark-ready.

### 8. Risk Decisions

- Run or review risk scan.
- Acknowledge low/medium warnings if understood.
- Resolve warnings only when fixed.
- Use `accept_with_warning` for explicit operator override.
- Mark `needs_fix` or reject when quality/risk is not acceptable.

## Daily Metrics To Record

- videos ingested
- candidates kept
- candidates rejected
- downloads completed
- audio analyses completed
- transcript segments edited
- renders completed
- renders approved
- publish drafts created
- publish drafts ready
- jobs failed by type
- retries attempted
- top 3 friction points
- most common error code
- operator time spent per stage

## Pilot Notes

Use seeded data for repeatability first. Use real media only after the operator can complete a seeded light session without code-level intervention.

