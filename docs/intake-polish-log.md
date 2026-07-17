# Intake Polish Log

## Findings

- `/intake` exists and uses the Operator Studio shell with breadcrumb context.
- The existing screen already covers profile URL, basic filters, preset loading, discover action, and result states.
- Operator Home and sidebar both link to `/intake`; review board remains available at `/review-board` and canonical `/selection/review-board`.

## UX Problems Found

- Presets are shown as a raw dropdown with API-style names such as `viral_discovery`, so the operator has to interpret technical labels.
- The Review Board CTA appears before discovery completes, which weakens the primary action hierarchy.
- Filter fields are grouped in one grid but not visually separated into time, views, and likes.
- Status panel states are functional but too terse for zero-result/error recovery.
- Reusing the same profile/preset between daily runs requires retyping or reselecting; a light local recent helper can reduce this.

## Decisions Made

- Keep backend/API unchanged for this polish step.
- Keep the existing page shell, navigation, route contracts, and `/review-board?fresh=1` success path.
- Replace the preset dropdown with small selectable preset cards while preserving the same payload shape.
- Hide the Review Board CTA from the form until discovery has produced a result; keep navigation available through topbar/sidebar.
- Add a local-only recent setup helper using `localStorage` for the last submitted profile URL and preset.
- Add clearer visual grouping for Source, Preset, Time range, Views, Likes, and Actions.

## Files Touched

- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/intakeState.ts`
- `apps/web/src/types/intake.ts`
- `apps/web/src/app/globals.css`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/test/intake.test.ts`
- `docs/intake-polish-log.md`
- `docs/intake-polish-resume.md`

## Verification Notes

- `npm --workspace @reup-douyin/web run typecheck` passed.
- `npm --workspace @reup-douyin/web test` passed.
- `npm --workspace @reup-douyin/web run build` passed and generated `/intake`.
- Live smoke after restarting the stale web listener:
  - `GET http://localhost:3000/` returned 200.
  - `GET http://localhost:3000/intake` returned 200.
  - `GET http://localhost:3000/review-board` returned 200 and resolved to `/selection/review-board`.

## Known Remaining Simple Parts

- Recent setup is intentionally local-only via `localStorage`; no backend history or profile table was added.
- Review board still only receives `?fresh=1`; a dedicated intake-result banner/filter on review board remains a separate future polish step.
- Error messages continue to surface backend wording where useful, especially for the known live Douyin fetch-client gap.

## Status

Completed.
