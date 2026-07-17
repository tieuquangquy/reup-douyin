# All-Failing Aweme Checkpoint Trace Resume

## Current Task

Trace only three real failing aweme IDs across checkpoints 1-5 and identify the first missing checkpoint for posted, duration, and counts metadata.

Target IDs:

- `7628281732369796388`
- `7631223404342857006`
- `7628596519502892307`

There is no confirmed passing baseline. This task is not a pass-vs-fail comparison.

## Required Output

- Per-aweme checkpoint table for checkpoints 1-5.
- Cross-item summary showing whether all three fail at the same checkpoint for posted, duration, and counts.
- Exact likely next narrow fix boundary.

## Completed So Far

- Read repository working rules in `AGENTS.md`.
- Confirmed existing diagnostics still used older target IDs in extension and API.
- Created `docs/all-failing-aweme-checkpoint-trace-log.md` with scope, checkpoints, evidence tables, and non-goals.
- Retargeted checkpoint 1-3 diagnostics to the three real failing IDs.
- Added narrow checkpoint 4 API response logging with marker `targeted_aweme_checkpoint4_api_response`.
- Added narrow checkpoint 5 frontend render logging with marker `[targeted-aweme-checkpoint5-frontend-render]`.
- Rebuilt the extension dist artifact so the unpacked extension output contains the three target IDs.
- Verified compile/typecheck/build commands pass.

## Next Steps

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Run one real capture on the Douyin page containing the three target IDs.
3. Copy evidence from these markers:
   - `[targeted-aweme-checkpoint1-precanonical]`
   - `[targeted-aweme-checkpoint2-canonical]`
   - `targeted_aweme_one_shot_summary_full`
   - `targeted_aweme_checkpoint4_api_response`
   - `[targeted-aweme-checkpoint5-frontend-render]`
4. Update `docs/all-failing-aweme-checkpoint-trace-log.md` with observed checkpoint values.
5. Report first missing checkpoint and narrowest next fix boundary.

## Non-goals

- No permanent metadata extraction fix.
- No broad refactor.
- No UI redesign.
- No unrelated telemetry.
- No assumptions about passing items.

## Known Relevant Files

- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/web/src/lib/captureInboxCanonical.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`

## Evidence State

Instrumentation is ready. Live capture evidence is still missing. Until a real capture is run with the retargeted diagnostics, the first missing checkpoint remains unknown.
