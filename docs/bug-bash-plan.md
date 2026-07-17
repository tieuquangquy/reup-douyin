# Bug Bash Plan

The bug bash intentionally stresses fragile boundaries before pre-beta. The goal is to expose bad states, not to prove the happy path.

## Session Setup

1. Run `scripts/dev-doctor.ps1`.
2. Run migrations and reseed demo data.
3. Start API, web, and worker.
4. Keep `/ops/metrics` open.
5. Use `docs/templates/bug-bash-report-template.md` for findings.

## Severity Guidelines

- `P0_BLOCKER`: data loss, publish-ready ambiguity, unrecoverable job state, or unable to run core app.
- `P1_HIGH`: common workflow blocked, wrong output selected, critical risk bypass, or retry/resume broken.
- `P2_MEDIUM`: confusing UI, recoverable bad state, degraded performance, unclear but traceable error.
- `P3_LOW`: copy, layout, docs, or non-blocking polish.

## 1. Job System Stress

Scenario: create multiple `DOWNLOAD_VIDEO`, `ANALYZE_AUDIO`, `SYNTHESIZE_TTS`, and `RENDER_FINAL` jobs for the same source video.

Expected:

- Jobs remain individually traceable.
- Current assets/render outputs are unambiguous.
- Retryable backlog appears in `/ops/metrics`.

Suspicious:

- More than one current final render without a clear latest policy.
- Job stuck in `RUNNING` after worker restart.
- Step progress regresses without error.

## 2. Asset / Manifest Inconsistency

Scenarios:

- Delete a local asset file but keep DB record.
- Create stale manifest references by rerunning TTS then render without refresh.
- Mark old asset non-current and open final review.

Expected:

- Asset health or resolver fails clearly.
- UI shows missing preview/output gracefully.
- Render does not consume stale manifest silently.

Suspicious:

- Final review shows success with missing file.
- Render-prep manifest references old subtitle or narration after rerun.
- Error message does not include source video/render id.

## 3. UI Workflow Confusion

Scenarios:

- Change review board filters while bulk selection is active.
- Open detail drawer, update candidate, then apply another filter.
- Jump from final review to transcript editor and back.
- Edit publish draft after scheduling.

Expected:

- Selection/action state is reset or clearly scoped.
- Dirty state is visible.
- Navigation does not lose unsaved edits without warning.

Suspicious:

- Bulk action applies to hidden candidates.
- Publish draft schedule disappears after save.
- Final review still shows old warning state after risk action.

## 4. Retry / Resume Abuse

Scenarios:

- Retry a completed job.
- Resume a failed non-retryable job.
- Change transcript while TTS job is retryable.
- Retry render after deleting narration asset.

Expected:

- Invalid transitions return conflict or clear UI error.
- Retry only resets failed steps.
- Input changes make downstream outputs stale or fail clearly.

Suspicious:

- Completed job returns to queued.
- Retry hides original error.
- TTS uses stale translated text.

## 5. Bad Input Data

Scenarios:

- Invalid Douyin URL.
- Source video without source URL.
- Translation segment with empty text.
- Subtitle segment with end time before start.
- Publish draft with empty caption and no target platform.

Expected:

- Validation blocks action with useful reason.
- Job error categories are specific.
- No partial ready state is set.

Suspicious:

- Generic `500` without error code.
- Publish draft ready despite invalid metadata.
- Render starts with invalid subtitle timing.

## 6. State Desync Tests

Scenarios:

- Mark publish-ready, then rerender a newer output.
- Waive risk warnings, then edit transcript and rerender.
- Schedule draft, then change target platform.
- Re-seed demo data while UI is open.

Expected:

- New render requires final review again.
- Risk decision remains traceable but does not falsely certify new output.
- Scheduled draft shows current platform and planned time.

Suspicious:

- Old accept-with-warning applies silently to new render.
- UI does not reveal stale publish-ready state.
- Seed duplicates candidates or publish drafts.

## 7. Heavy Operator Session

Scenario: run a 2-hour session using 30-50 seeded or real videos.

Expected:

- UI remains responsive.
- Operator can batch decisions without losing context.
- Failed jobs are visible and triageable.

Suspicious:

- Memory/browser slowdown affects decisions.
- Loading states hide errors.
- Operator spends more time hunting IDs than reviewing content.

## Reporting

For each bug:

- record taxonomy category, severity, repro quality, target id, current status, expected behavior, actual behavior, evidence link/path, and next decision
- use `docs/templates/issue-template.md`
- summarize the session with `docs/templates/bug-bash-report-template.md`

