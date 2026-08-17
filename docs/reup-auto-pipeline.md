# Reup Queue auto pipeline

How a queue item walks from a downloaded Douyin clip to a finished Vietnamese video, and
where the operator is expected to step in.

## Step plan

`src/services/reup_pipeline_plan.py` is the single source of truth for step order:

```
download → analyze_audio → translate → tts → ocr → render
```

The orchestrator (`src/services/reup_pipeline_orchestrator.py`) never decides the next
step on its own. When a linked job reaches a terminal state it asks
`next_pipeline_step(current_step=…, mode=…, skip_dubbing=…)` and enqueues whatever comes
back; `None` means the plan is finished and the item moves to `ready_final`.

Adding a stage means adding one entry to `PIPELINE_STEP_ORDER` plus one entry in
`_ENSURE_METHOD_BY_STEP`, not editing a chain of per-stage handlers.

## Modes (stop points)

| `pipeline_mode` | Runs through | Operator does |
| --- | --- | --- |
| `manual` | nothing automatically | drives every stage by hand |
| `auto_to_tts` | download → tts | reviews transcript/voice, then runs OCR + render |
| `auto_to_render` | download → render | only watches the finished video; deterministic local quality policy promotes safe OCR/visual/audio checkpoints |

`auto_to_render` is the default behind the primary **Start auto** button in the Reup
Queue hero rail. **Auto→TTS** is the explicit opt-out for clips you want to edit before
render. **Start manual** downloads only.

### Full-auto quality checkpoints

`auto_to_render` does not bypass QA. It replaces interactive approvals with the
versioned local policy `quality_auto_to_render_v1`:

- OCR rows classified only as `EDITOR_OVERLAY` are approved; source-intrinsic and
  platform-UI rows are preserved. Mixed or unknown provenance fails closed.
- Existing Vietnamese visual-translation candidates are promoted as a batch; the
  policy never retranslates or invents text.
- Visual approval is written only after the encoded preview passes the existing
  hash-bound Output QA.
- Audio approval is written only after the joined narration and original background
  mix preview exist and no unresolved timing-fit status remains.
- A residual-CJK gate, missing candidate, ambiguous provenance, or failed QA changes
  the item to `FAILED_NEEDS_ATTENTION` with a concrete `AUTO_*_BLOCKED` code.

Manual and `auto_to_tts` workflows keep their interactive review surfaces.

## Switching automation mid-flight

The `SET_AUTOMATION` action (single item and batch, carrying `pipeline_mode`) moves an
item between lanes without losing its place:

- A **live job keeps running**; the new stop point applies when it finishes.
- An **idle item** continues from `pipeline_last_completed_step`, which
  `on_job_terminal` records for manual items too. Without that record — older items, or
  work interrupted before anything finished — the pinned `pipeline_step` is resumed
  instead.
- Switching to an auto mode clears any pause; switching to `manual` only stops future
  advancement and starts nothing.

In the UI this is the Automation picker in the item inspector (Full auto / Auto→TTS /
Manual) and the bulk actions *Hand to full auto* and *Take over manually*.

## Skipping dubbing without skipping render

`skip_dubbing` is derived from the audio analysis verdict (`dialogue_phase`,
`has_speech`, `skip_dubbing` flag). It removes only `translate` and `tts` from the plan,
because burned-in Chinese text is independent of the audio track: a clip with no speech
still needs hardsub cleanup and render. Under `auto_to_render` a silent clip therefore
continues to `ocr → render` instead of stopping.

## Where the pipeline stops for a human

- **Uncertain dialogue** — speech exists but the ASR quality contract is not translation-ready
  (zero transcript or low-confidence review rows). The item goes to
  `FAILED_NEEDS_ATTENTION` with `DIALOGUE_DETECTION_UNCERTAIN`. Reviewable rows link directly
  to Transcript; empty output asks for re-analysis or an explicit no-dialogue decision.
  Guessing here either drops needed dubbing or voices corrupt text, so this gate is deliberate.
  See `docs/audio-analysis-pipeline.md`.
- **Any failed job** — the item records the job's error code and stops. Metadata preserves
  `pipeline_failed_step` plus a secret-safe `pipeline_error` object (`error_domain`, retry
  class, provider HTTP/code when available, and recovery action), while `pipeline_step`
  moves to `needs_attention`. The Queue UI uses this authority to distinguish Download,
  Analyze Audio, Translation, TTS, OCR, Preview and Final Render failures.
- **Hold / pause** — `pipeline_hold` (or `held_at`) blocks advancement; `resume_item`
  re-enqueues the step the item was paused on.

## Guardrails for unattended runs

### Concurrency caps per job type

`claim_next_job` refuses to claim a job when its own type already has enough RUNNING jobs
in that workspace. Caps live in settings (`job_type_concurrency_limits`); types not listed
run unlimited.

| Job type | Env var | Default |
| --- | --- | --- |
| `DOWNLOAD_VIDEO` | `DOWNLOAD_VIDEO_MAX_CONCURRENT_RUNNING` | 1 |
| `ANALYZE_AUDIO` | `ANALYZE_AUDIO_MAX_CONCURRENT_RUNNING` | 1 |
| `SYNTHESIZE_TTS` | `SYNTHESIZE_TTS_MAX_CONCURRENT_RUNNING` | 2 |
| `ANALYZE_OCR` | `ANALYZE_OCR_MAX_CONCURRENT_RUNNING` | 1 |
| `RENDER_FINAL` | `RENDER_FINAL_MAX_CONCURRENT_RUNNING` | 1 |

Slots are per type, so a busy download never blocks a render and vice versa.

### One shared GPU budget

Per-type slots keep each stage honest but say nothing about the machine: ANALYZE_AUDIO,
SYNTHESIZE_TTS, ANALYZE_OCR and RENDER_* each hold their own slot and can still land on the
same card together, which on a small GPU means OOM or a silent crawl on CPU. `GPU_JOB_TYPES`
in `job_runner.py` groups those stages behind one budget, `GPU_MAX_CONCURRENT_RUNNING`
(default 1). Download and crawl are outside the group, so network work keeps flowing while
the card is busy.

### Bounded work in progress

Start auto on fifty clips promises that fifty clips get done, not that fifty start now.
`REUP_MAX_ITEMS_IN_FLIGHT` (default 5) caps how many clips the lane moves at a time. Extra
clips are parked with their chosen mode (`pipeline_awaiting_slot` in item metadata,
`src/services/reup_pipeline_admission.py`) and `admit_waiting_items` starts the next one —
highest priority, then oldest — whenever a job reaches a terminal state and frees a slot.
Finished videos therefore arrive in a steady stream instead of fifty clips crawling
together, and an incident costs a handful of clips rather than the whole batch.

Parked clips read as `Auto · Queued` on the tile with the hint "starts automatically when a
slot frees", so nobody mistakes a queued clip for a stuck one. Batch Start auto no longer
caps the selection either — the manual `START_PROCESSING` batch keeps its download-session
cap, while auto accepts every clip and parks the overflow.

### Durable stage handoff and stall visibility

Start auto and slot admission both enter through `ReupPipelineOrchestrator.set_automation`.
They resume from `pipeline_last_completed_step`; they do not reset an already analyzed clip
to Download. Core stage jobs are created with `commit=False`, then the job row, queue
`job_id`, stage-specific job id and `pipeline_step` become visible in one database commit.
This prevents a fast cache-hit worker from finishing before the queue binding exists.

As a second line of defense, `_ensure_step` immediately consumes a reused job that is already
terminal. Completed progress is monotonic, and a delayed callback from an older stage cannot
advance or rewind a newer stage. The frontend also detects `pipeline_last_completed_step`
being ahead of `pipeline_step` and renders **Auto pipeline stalled** instead of an indefinite
waiting message.

### Several workers, one card

A worker claims one job and runs it to completion, so with a single worker process a
20-minute render blocks every download and translation behind it — the caps above are
ceilings the system never reaches. `scripts/dev-start.ps1` now starts `WORKER_COUNT`
workers (default 2, each with its own `WORKER_ID`), which is only safe because the GPU
budget keeps one heavy job on the card while the others handle network and CPU stages.

Slot counting is done with subqueries, so two workers claiming at the same instant could
both see a free GPU slot. `claim_next_job` takes a Postgres transaction-scoped advisory
lock (`CLAIM_ADVISORY_LOCK_KEY`) first; a claim lasts milliseconds, and other dialects skip
the lock. Note each worker loads its own copies of the models, so more workers cost RAM.

### Disk headroom before heavy work

ffmpeg does not stop politely when the volume fills: the render "succeeds" with a truncated
file that then flows into QA. Before any DOWNLOAD/ANALYZE/TTS/RENDER job runs its steps,
`src/services/disk_guard.py` checks that the storage root has at least `MIN_FREE_DISK_GB`
(default 10) free. If not, the job fails with `DISK_SPACE_LOW`, which the retry policy
classifies as transient, so it waits and retries instead of corrupting an output. An
unreadable path never blocks work, and `MIN_FREE_DISK_GB=0` disables the guard.

### Reclaiming finished clips' intermediates

The guard above stops the damage; `src/services/artifact_retention.py` stops the growth.
Every localized clip leaves separated stems, extracted audio, per-line TTS clips and OCR
frames behind — all regenerable, all large. A worker sweeps them every
`ARTIFACT_RETENTION_SWEEP_INTERVAL_SECONDS` (default 15 minutes) under deliberately narrow
conditions, because deleting media is unforgiving:

- the clip reached a finished status **and** its render QA verdict is not `fail` (a stranded
  or failed clip keeps the evidence somebody needs to diagnose it),
- a deliverable exists (`FINAL_RENDER_VIDEO` or `RENDER_OUTPUT`),
- the file is older than `ARTIFACT_RETENTION_MIN_AGE_HOURS` (default 24), so an operator
  reviewing today still has everything,
- the type is regenerable. Source video, renders, thumbnails, transcripts and subtitles are
  never touched; the cleaned hardsub-free video needs
  `ARTIFACT_RETENTION_INCLUDE_CLEANED_VIDEO=true` because some flows re-render from it.

Reclaimed rows become `ARCHIVED` rather than disappearing, a vanished file is treated as
success, and a locked file is left for the next pass. The whole feature is off until you set
`ARTIFACT_RETENTION_ENABLED=true`.

### Consistent loudness

Dub level varies by voice and line, background music varies by source, and nothing evened
them out: a single clip sounded fine while a feed of them jumped in volume. The delivered
render now passes through single-pass EBU R128 `loudnorm`
(`src/render_pipeline/audio_loudness.py`) at `RENDER_LOUDNESS_TARGET_LUFS` (default -14
LUFS, true peak -1.5 dBTP). It lives in `FfmpegRenderRunner` because that is the one place
the deliverable's audio is encoded rather than copied.

### One visual encode per approved revision

The adaptive visual preview is already a full-resolution encoded artifact with
full-timeline edit coverage, residual-CJK, damage and flicker QA. After it passes,
Final does not repeat the Python frame render. It validates the current render-input
hash, visual-remediation ref, preview file hash and preview QA, then muxes approved
narration/background audio with `-c:v copy`. Final QA compares the preview and final
encoded video-packet SHA-256 and reuses visual evidence only on an exact match; audio,
duration, frame-count and color/container checks are measured again. A mismatch uses
the original full-render/full-QA path.

### Heartbeats instead of wall-clock guesses

`locked_at` used to be stamped once at claim time and judged against a single threshold
derived from download budgets, so a healthy 40-minute render looked exactly like a hung
download and was requeued forever. A running job now refreshes its lock every
`JOB_HEARTBEAT_SECONDS` (`src/services/job_heartbeat.py`, wrapped around `run_job` in the
worker), and `job_type_stale_seconds` gives each type its own patience — 45 minutes for OCR
and final render, 10 for download. A dead worker is still caught immediately by
`release_orphaned_locks` on restart; the stale sweeper is only the backstop.

### Auto-retry of transient failures

`resolve_failure_outcome` in `src/services/job_runner.py` is the one place that decides
what a failed step means. Download keeps its Douyin-specific policy; every stage after it
uses `src/services/pipeline_retry_policy.py`:

- **Transient** (timeouts, connection resets, 5xx, rate limits, busy file handles, OOM):
  requeued as `RETRYABLE` with exponential backoff
  (`PIPELINE_RETRY_BACKOFF_BASE_SECONDS` → `PIPELINE_RETRY_BACKOFF_MAX_SECONDS`) up to
  `PIPELINE_TRANSIENT_MAX_ATTEMPTS`.
- **Terminal** (deterministic Python errors such as `KeyError`, missing/invalid inputs):
  fails immediately so a defect never burns repeated render minutes.

The chosen class and the retry decision are written to `job.metadata_json`
(`pipeline_failure_class`, `pipeline_will_auto_retry`) and into the operator-facing error
message.

### QA gate after render

When `RENDER_FINAL` completes, the orchestrator grades the output through
`src/services/render_qa_gate.py` before calling the item ready. Checks: duration match
against the source, audio present when dubbing was expected, burned subtitles, output
resolution, the risk gate for the render output, and renderer warnings. Anything the
pipeline cannot measure is reported as `skipped`, never guessed.

- `fail` → item goes to `FAILED_NEEDS_ATTENTION` with `RENDER_QA_FAILED`.
- `warn` → item still reaches review, with the warning in `last_action_note`.
- The verdict is stored on the item as `metadata_json.render_qa` (status, summary, per
  check detail) and is what Output Review renders as a badge.

A defect inside the gate itself is logged and ignored; a finished render is never stranded
by QA.

## Output Review

`/production/output-review` lists every item that has a rendered file, worst QA verdict
first, with a 9:16 player, the per-check breakdown and the item's own available actions.
It is a reading surface over the QA gate — it does not compute quality itself.

Reviewing back to back is the point, so the page pages with `J`/`↓` and `K`/`↑` (ignored
while a field or the video element has focus), and the primary link routes by *which*
check failed rather than to a generic details page: a missing dub or missing subtitles
opens the Transcript Editor, while duration, resolution, renderer warnings and risk flags
open Final Review. The mapping lives in `outputReviewFixTarget`.

## Phase 5 frontend handoff

The quality path now continues inside Final Review after encoded-output QA:

1. **Approve output** records the hash-bound `FINAL_APPROVED` artifact and creates the
   local operator package boundary.
2. The **Export** rail saves and explicitly approves Facebook Reels metadata.
3. The operator must check all source-video and retained-music attestations before
   `SOURCE_RIGHTS_AND_MUSIC_APPROVED` can be written.
4. After the normal Final Review checklist marks the render publish-ready, **Create
   MANUAL_EXPORT_ONLY** generates the verified ZIP and persists matching
   `ExportPackage` and `PublishHandoff` database rows.
5. **Download ZIP** streams the archive through the existing localization-artifact
   boundary. No external publish request is created or executed.

These actions are idempotent and hash-bound to the active quality run. The API facade is
`QualityHandoffService`; the underlying artifact authority remains
`local_final_handoff.py`.

## Not implemented yet

- Subtitle overflow detection: the production render burns an SRT, so no per-line bounding
  boxes are persisted to check against frame bounds.
- Auto publish remains a non-goal (see `AGENTS.md`).
