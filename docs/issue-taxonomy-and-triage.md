# Issue Taxonomy And Triage

Use this taxonomy for pilot findings, bug bash reports, and go/no-go review.

## Categories

- `INGEST_BUG`: profile/video ingest, adapter normalization, crawl session, dedupe.
- `FILTER_SCORE_BUG`: filter config, preset resolution, Reup Score, candidate persistence.
- `REVIEW_UI_BUG`: review board card, selection, detail drawer, bulk actions.
- `DOWNLOAD_STORAGE_BUG`: downloader, local storage, media asset, manifest, checksum.
- `AUDIO_ANALYSIS_BUG`: audio resolution, separation, STT, transcript draft.
- `TRANSCRIPT_EDITOR_BUG`: segment edit, dirty state, timing, merge/split, save/discard.
- `TTS_SUBTITLE_BUG`: TTS clips, narration, subtitle generation, timing fit.
- `RENDER_BUG`: render input, ffmpeg/export, output validation, RenderOutput state.
- `FINAL_REVIEW_BUG`: compare viewer, approve export, publish-ready state, rerender.
- `PUBLISH_DRAFT_BUG`: caption/CTA/hashtags, target platform, scheduling, mark-ready.
- `RISK_POLICY_BUG`: risk scan, severity, status, gate policy, operator decisions.
- `OPERATOR_USABILITY_ISSUE`: workflow friction, confusing copy, excess clicks.
- `PERFORMANCE_ISSUE`: slow stage, backlog, unnecessary recompute, UI sluggishness.
- `RELIABILITY_ISSUE`: intermittent failure, stale state, unclear retry/resume behavior.
- `DOCS_GAP`: setup, runbook, workflow, or API docs missing or misleading.

## Severity

- `P0_BLOCKER`: cannot run pilot, data loss, wrong final output selected, critical risk bypass, unrecoverable state.
- `P1_HIGH`: major workflow blocked, repeated job failure, publish-ready ambiguity, or high operator confusion.
- `P2_MEDIUM`: recoverable issue, unclear warning/error, moderate slowdown, or local workaround exists.
- `P3_LOW`: minor UI/docs/copy/polish issue that does not block pilot.

## Repro Quality

- `ALWAYS`: deterministic or reproduced at least twice with same steps.
- `INTERMITTENT`: seen more than once but not deterministic.
- `UNKNOWN`: one-off finding or incomplete evidence.

## Triage Decisions

- `FIX_BEFORE_NEXT_PILOT`: P0/P1, state ambiguity, or common path breakage.
- `ACCEPTABLE_FOR_PILOT`: known limitation with clear workaround and low risk.
- `DEFER_POST_BETA`: low-severity improvement or feature beyond Phase 1 validation.

## Triage Rules

- A P0 always blocks go/no-go until fixed or downgraded with evidence.
- P1 issues block publish connector work if they affect final output, publish draft, risk gate, or operator ability to recover.
- P2 issues can continue through pilot if documented in the daily operator log.
- P3 issues should be grouped and fixed only if they are cheap or high-friction.

## Required Evidence

Every issue should include:

- taxonomy category
- severity
- repro quality
- affected source video, render output, publish draft, job, or asset id when available
- expected behavior
- actual behavior
- evidence path, screenshot, API payload, or log excerpt
- workaround if any
- triage decision

