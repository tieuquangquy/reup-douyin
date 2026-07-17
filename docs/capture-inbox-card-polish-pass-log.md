# Capture Inbox Card Polish Pass — Implementation Log

## 1) Current UI issues (narrow audit)

Target: Capture Inbox item card only in [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx) + tightly related styles in [`apps/web/src/app/globals.css`](apps/web/src/app/globals.css).

Observed issues:

1. **Select pill clumsy**
   - Current Select control still feels bulky and visually layered (checkbox + indicator + text), not premium enough for media-first cards.
2. **Ready duplication on card**
   - `Ready` appears both in overlay badge and again in lower on-card meta (via preview/meta interpretation), causing redundancy/noise.
3. **Meta clutter still high**
   - Quick chips still include technical/context-heavy info (`Source`, and other low-signal metadata in prior variants), slowing visual triage.

## 2) Select pill redesign (planned)

- Keep one single compact one-line chip control.
- Left: checkbox/checkmark, right: `Select`/`Selected` label.
- Remove extra detached/duplicated ornament behavior.
- Reduce height/spacing and improve polish (surface, border, elevation, selected tint).

## 3) Duplicated Ready removal (planned)

- Keep primary readiness display in top-right overlay badge.
- Remove lower duplicated readiness meaning from quick chips.
- Preserve readiness semantics (do not change business logic).

## 4) Meta simplification (planned)

Reduce on-card quick chips to 3–4 high-value items:
- Duration
- Posted
- Views
- Preview

Move/retain technical details in inspector where needed (without broad inspector redesign).

## 5) Files expected to change

- [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx)
- [`apps/web/src/app/globals.css`](apps/web/src/app/globals.css)
- [`apps/web/src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts)
- [`docs/capture-inbox-card-polish-pass-log.md`](docs/capture-inbox-card-polish-pass-log.md)
- [`docs/capture-inbox-card-polish-pass-resume.md`](docs/capture-inbox-card-polish-pass-resume.md)

## 6) Tests run

- `npx tsx apps/web/src/test/capture-inbox.test.ts` ✅
- `npm run typecheck --workspace apps/web` ✅

## 7) Verification result

Implemented exactly the requested 3-point UI polish pass on Capture Inbox item cards:

1. Select pill redesigned to a single compact one-line control.
2. Duplicated lower card status removed while preserving top-right overlay readiness/status badge.
3. On-card quick metadata reduced to 4 high-value chips: Duration, Posted, Views, Preview.

No backend/API/extraction/selection semantics or broader page layout changes were made.
