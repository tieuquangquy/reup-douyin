# Douyin Factor 5 — Intake Wiring Resume

## Task
Implement **only Factor 5** intake evaluation wiring between `/intake` and Capture Inbox with backend as source of truth.

## Scope Lock
- Keep intake evaluation in backend.
- Frontend displays status/group/filter + triggers re-evaluation only.
- Keep raw captured items intact.
- Narrowly update only required files for Factor 5.

## Current Status
Completed.

## Completed So Far
- Read `AGENTS.md` and confirmed repository boundaries.
- Audited current state in:
  - `apps/api/src/services/capture_inbox_service.py`
  - `apps/api/src/api/routes/capture_inbox.py`
  - `apps/api/src/models/capture_inbox.py`
  - `apps/api/src/enums/__init__.py`
  - `apps/api/src/services/candidate_filter.py`
  - `apps/api/src/schemas/capture_inbox.py`
  - `apps/api/src/schemas/intake.py`
  - `apps/web/src/types/capture-inbox.ts`
  - `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- Identified existing partial wiring and gaps versus required 4-state semantic model.
- Created docs-first artifacts:
  - `docs/douyin-factor5-intake-wiring-log.md`
  - `docs/douyin-factor5-intake-wiring-architecture.md`
  - `docs/douyin-factor5-intake-wiring-resume.md`

## Final Verification
- `npm --workspace @reup-douyin/web run typecheck` ✅ passed
- `npx tsx apps/web/src/test/capture-inbox.test.ts` ✅ passed
- `python -m pytest apps/api/tests/test_douyin_extension_capture_service.py -k intake` ⛔ blocked in current environment (`No module named pytest`)

## Final Changed Files
- `apps/api/src/enums/__init__.py`
- `apps/api/src/models/capture_inbox.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/douyin-factor5-intake-wiring-log.md`
- `docs/douyin-factor5-intake-wiring-architecture.md`
- `docs/douyin-factor5-intake-wiring-resume.md`

## Non-goals
- No extension-side filtering move.
- No broad UX redesign.
- No unrelated infra or workflow changes.
