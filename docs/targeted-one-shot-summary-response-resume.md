# Resume — Targeted One-shot Summary in Capture Response

## Scope lock
Diagnostics convenience only.
No metadata fix.
No UI redesign.

## Goal
After one real `Capture current page`, operator can copy one combined targeted summary block directly from capture response surface.

## Where to copy now
- API response payload field:
  - `targeted_aweme_one_shot_summary.items`

## Preferred surface
- API response for `POST /douyin-extension/capture-current-page`.

## Files in scope
- `apps/api` response/service/schema path
- this docs pair only

## Trigger and copy steps
1. Start stack with [`npm run dev`](package.json:12).
2. Run one real `Capture current page` on a page containing either target aweme id.
3. Open capture response JSON (same place operator already sees capture response payload).
4. Copy block:
   - `targeted_aweme_one_shot_summary`

## Verification checklist
1. Real capture response includes `targeted_aweme_one_shot_summary` when target IDs are present.
2. `items` contains only present target IDs.
3. Summary remains easy to copy as one JSON block.
4. No unrelated capture flow changes.

## Verification executed
- Syntax/contract check passed:
  - [`python -m compileall apps/api/src/services/douyin_extension_capture_service.py apps/api/src/schemas/douyin_extension.py`](apps/api/src/services/douyin_extension_capture_service.py:1)
