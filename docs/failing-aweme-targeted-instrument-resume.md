# Resume — Failing aweme Targeted Instrumentation

## Scope lock
Only evidence collection for two failing aweme IDs:
- `7489123456789012346`
- `7489123456789012347`

No broad fixes. No frontend changes.

## Files touched
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/api/src/services/capture_inbox_service.py`
- `docs/failing-aweme-targeted-instrument-log.md`
- `docs/failing-aweme-targeted-instrument-resume.md`

## How to collect evidence
1. Run extension capture flow on profile grid containing both failing IDs.
2. Collect browser console lines containing:
   - `[targeted-aweme-checkpoint1-precanonical]`
   - `[targeted-aweme-checkpoint2-canonical]`
3. Submit capture payload to API as normal.
4. Collect API logs containing:
   - `targeted_aweme_checkpoint3_build_item`

## Minimal command hints (Windows)
- Web app logs (if needed): run existing project start command.
- API logs: run API service and copy matching log lines.

## Next analysis step
Map field presence at checkpoints 1→2→3 and identify first missing boundary per field group.
