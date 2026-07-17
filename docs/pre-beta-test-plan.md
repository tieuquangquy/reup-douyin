# Pre-Beta Test Plan

This plan validates whether the current Phase 1 pipeline is stable enough to justify building a real publish connector. It is not a product feature roadmap.

## Validation Strategy

### Core Hypotheses

- A local Windows operator can run the daily workflow without touching code.
- The system can ingest, filter, process, render, review, and prepare publish drafts with traceable state.
- Job failures are visible, retryable when appropriate, and not hidden behind partial DB/asset state.
- Operator effort is concentrated on review and editing, not debugging stale manifests or unclear statuses.
- Risk warnings are useful enough to prevent obvious bad publish decisions without pretending to be legal judgment.

### Acceptable Pilot Failures

- Provider placeholders or mocked outputs when explicitly documented.
- Isolated job failures that leave clear `Job`, `JobStep`, `MediaAsset`, `RenderOutput`, or `RiskFlag` evidence.
- Manual rerun needed after operator edits transcript or publish metadata.
- Low/medium risk warnings that require operator judgment.

### Blockers Before Real Publish Connector

- Current/latest render or publish-ready state becomes ambiguous.
- Failed jobs leave no actionable error code/message.
- Render output cannot be traced back to source video, narration, subtitle, and render-prep manifest.
- Publish draft can be marked ready while critical open risk is unhandled.
- Operator cannot recover from common failures using runbooks.
- The same daily workflow cannot be repeated after reset/reseed.

### Mission-Critical Flows

- Demo environment setup: doctor, migrate, seed, start, smoke.
- Ingest and candidate scoring.
- Review board bulk keep/reject.
- Download/media manifest integrity.
- Transcript editor save/discard/merge/split.
- TTS/subtitle/render-prep generation.
- Final render and final review.
- Publish draft ready flow.
- Risk scan and gating before publish draft ready.

### Nice-To-Have During Pilot

- Perfect media provider quality.
- Advanced subtitle styling.
- Frame-level editing.
- Auto publish.
- Distributed queueing.
- Full browser E2E automation.

## Suites

### 1. Ingest Validation Suite

Goal: verify profile ingest creates normalized profiles, videos, crawl sessions, and metric snapshots.

Preconditions:

- API running.
- Database migrated.
- Demo seed available or mocked Douyin adapter configured.

Test cases:

- Submit a valid profile URL.
- Submit the same profile URL twice.
- Submit invalid/unsupported URL.
- Simulate adapter failure.

Expected result:

- Valid ingest creates or updates `SourceProfile`, dedupes `SourceVideo`, inserts `VideoMetricSnapshot`, and records `CrawlSession`.
- Duplicate ingest updates metadata without duplicate external video IDs.
- Invalid input maps to clear error category.

Evidence:

- Crawl session status and counts.
- Source profile/video IDs.
- Error code if failed.

Likely failures:

- URL normalization mismatch.
- Snapshot duplication.
- Raw payload stored but normalized field missing.

Pass/fail:

- Pass if duplicate crawl leaves one source profile per external id and one source video per external id.
- Fail if crawl session finishes without counts or actionable error on failure.

### 2. Filter + Score Validation Suite

Goal: verify deterministic filtering and explainable Reup Score.

Test cases:

- Apply `viral_discovery`, `safe_reup`, and `affiliate_priority`.
- Override min views, date mode, duration, and risk exclusions.
- Preview filter without persistence.
- Apply filter and persist `VideoCandidate`.

Expected result:

- Preview does not mutate candidates.
- Apply stores score version, total score, breakdown, inclusion/exclusion reasons.
- Sorting is stable and explainable.

Evidence:

- Candidate response payload.
- Score breakdown JSON.
- Rejection summary.

Likely failures:

- Missing metrics snapshot treated as zero without warning.
- Ratio division by zero.
- Preset override not reflected in persisted config.

### 3. Review Board Workflow Suite

Goal: verify operator can scan, select, and act on many candidates quickly.

Test cases:

- Load seeded candidates.
- Filter by status/score/source profile.
- Bulk keep selected.
- Bulk reject selected.
- Open detail drawer and score breakdown.
- Trigger next-step action only for kept candidates.

Expected result:

- Selection state is stable across action completion.
- Bulk action feedback is clear.
- Candidate status updates match API response.

Evidence:

- Screenshot or notes of card/detail state.
- Candidate status before/after.

Likely failures:

- Selection persists after filter changes.
- Score reasons too noisy or missing.
- Detail drawer uses stale candidate.

### 4. Download / Media Asset Integrity Suite

Goal: validate source video assets are registered, versioned, and manifest-readable.

Test cases:

- Trigger download for kept candidate.
- Rerun download on same source video.
- Simulate thumbnail failure.
- Simulate missing source URL.

Expected result:

- Current `MediaAsset` records are clear.
- Manifest lists source video, thumbnail, metadata mirror, and status.
- Partial asset failures are traceable.

Evidence:

- Asset manifest.
- MediaAsset status/version/current fields.
- Download job steps.

Likely failures:

- File exists but DB asset failed.
- DB asset exists but storage file missing.
- Rerun creates unclear duplicate current asset.

### 5. Audio Analysis + Transcript Draft Suite

Goal: validate source audio resolution, transcript segments, translation drafts, and flags.

Test cases:

- Analyze a downloaded video.
- Analyze with missing source audio/video asset.
- Simulate low STT confidence.
- Simulate overlapping speech/background too loud.

Expected result:

- Transcript segments have ordered timing and confidence.
- Translation segments preserve segment mapping and duration budget.
- Difficulty flags are visible.

Evidence:

- Transcript and translation APIs.
- Audio analysis job steps.
- Generated metadata assets if present.

Likely failures:

- Timing overlap.
- Segment index mismatch.
- Translation too long without flag.

### 6. Transcript Editor Usability Suite

Goal: verify a long editing session is practical.

Test cases:

- Edit source and translated text in 20 consecutive segments.
- Adjust timing with invalid values.
- Merge adjacent segments.
- Split one segment and save.
- Discard unsaved changes.
- Rerun draft generation with confirmation.

Expected result:

- Dirty state and before/after compare are obvious.
- Invalid timing is blocked or clearly warned.
- Save clears dirty state.

Evidence:

- Operator notes: time to edit 20 segments.
- Before/after sample.
- API payload after save.

Likely failures:

- Lost edits after selecting another segment.
- Merge/split creates overlapping timing.
- Unsaved warning not shown.

### 7. TTS / Subtitle / Render-Prep Suite

Goal: validate translation draft can produce TTS clips, joined narration, subtitle data, and render-prep manifest.

Test cases:

- Generate TTS/subtitles from edited translation.
- Simulate one TTS provider failure.
- Use a too-long translated segment.
- Rerun after translation edit.

Expected result:

- Clip assets and joined narration are registered.
- Subtitle DB records and JSON/SRT assets match current translation.
- Render-prep manifest references exact current inputs.
- Timing fit warnings are present.

Evidence:

- TTS summary.
- Subtitle payload.
- Render-prep manifest.

Likely failures:

- Old TTS clip reused after text changed.
- Subtitle timing mismatch.
- Manifest references stale asset.

### 8. Render Final Quality + Stability Suite

Goal: validate render engine consumes render-prep manifest and produces traceable final output.

Test cases:

- Render a normal seeded video.
- Rerender same source video multiple times.
- Render with missing narration asset.
- Render with missing subtitle asset.
- Validate output metadata.

Expected result:

- `RenderOutput` has status, format, dimensions, fps, duration, audio strategy, subtitle burned flag.
- Render manifest references source asset, narration, subtitle, output asset, probe summary.
- Failures are clear and do not mark output approved.

Evidence:

- RenderOutput detail.
- Output manifest.
- Job logs/steps.

Likely failures:

- ffmpeg unavailable.
- Output duration mismatch.
- Current/latest render confusion.

### 9. Final Review + Publish Draft Suite

Goal: validate final review decisions and publish draft metadata preparation.

Test cases:

- Open latest render final review.
- Toggle original/final compare.
- Approve export.
- Mark publish-ready.
- Create publish draft for target platform.
- Edit caption, CTA, hashtags, schedule.
- Mark publish draft ready.

Expected result:

- Approve export and publish-ready are distinct.
- Publish draft ready validates media-ready and metadata-ready state.
- Schedule skeleton persists planned time/timezone.

Evidence:

- Final review state.
- Publish draft response.
- Operator notes on clarity.

Likely failures:

- Operator confuses approve export with publish draft ready.
- Draft points to old render.
- Hashtag structure becomes raw unparseable text.

### 10. Risk Scan / Gating Suite

Goal: validate warning usefulness and gate rules.

Test cases:

- Run risk scan for source video.
- Run risk scan for render output.
- Run risk scan for publish draft.
- Acknowledge, resolve, waive warning.
- Try mark-ready with open high/critical risk.

Expected result:

- Risk flags include severity, status, title, evidence, target type/id.
- Gate blocks or strongly warns according to policy.
- `accept_with_warning` is explicit.

Evidence:

- Risk summary.
- OperatorRiskDecision record.
- UI warning copy.

Likely failures:

- Warnings too vague.
- Waived flags still block unexpectedly.
- Critical open risk can be bypassed without explicit decision.

### 11. End-To-End Happy Path Suite

Goal: validate one normal video can move through the whole local workflow.

Path:

`ingest -> score -> keep -> download -> audio analysis -> edit transcript -> TTS/subtitle -> render -> final review -> publish draft -> risk check`

Pass/fail:

- Pass if every stage has traceable DB status and operator can identify next action.
- Fail if any stage requires code inspection to recover.

### 12. End-To-End Degraded / Failure Path Suite

Goal: validate recovery and runbook usefulness.

Cases:

- Missing source asset before audio analysis.
- Provider failure during TTS.
- Render failure.
- Risk blocked publish draft.
- Retryable job resumes after input fixed.

Pass/fail:

- Pass if operator can use status, `/ops/metrics`, and runbook to decide retry/resume/needs_fix/reject.
- Fail if failure is silent, stale, or ambiguous.

