# Resume — One-shot Debug Dump

## Scope lock
Temporary diagnostics helper only. No broad fixes.

Target IDs:
- `7489123456789012346`
- `7489123456789012347`

## Files in scope
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/api/src/services/capture_inbox_service.py`
- `docs/one-shot-debug-dump-log.md`
- `docs/one-shot-debug-dump-resume.md`

## Exact commands
1. Start stack from repo root using [`npm run dev`](package.json:12).
2. Build extension bundle (already verified once) using [`npm run extension:build`](package.json:23).

## Operator flow (target)
1. Ensure API logs are visible in the terminal started by [`npm run dev`](package.json:12).
2. Reload the unpacked extension in Chrome.
3. Open Douyin profile/feed page that includes `7489123456789012346` and `7489123456789012347`.
4. Click `Capture current page` exactly once.
5. Copy backend log lines with marker `targeted_aweme_one_shot_summary`.

## Summary log marker
- `targeted_aweme_one_shot_summary`
- payload key: `one_shot_summary`

## Deterministic first-missing stage rule
For each field, first missing among checkpoints 1→2→3.
Overall object-level `first_missing_stage` uses priority:
1) any field missing at checkpoint1 => `checkpoint1`
2) else any field missing at checkpoint2 => `checkpoint2`
3) else any field missing at checkpoint3 => `checkpoint3`
4) else `none`
