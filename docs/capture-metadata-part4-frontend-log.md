# Capture Metadata Part 4 Frontend Log

Date: 2026-04-29
Scope: Part 4 only — wire canonical Time + Performance + Processing fit fields from Capture Inbox API into Tile Gallery / Capture Inbox UI.
Status: Completed

## Preconditions and scope guard

- Read `AGENTS.md` and applied repository boundaries.
- Scope locked to frontend only (`apps/web` + docs):
  - allowed: `apps/web/src/types/capture-inbox.ts`, `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`, frontend tests/docs.
  - disallowed in this task: extension changes, backend persistence/API changes, broad page redesign.
- Rendering semantic lock:
  - processing-fit nulls must remain honest (`null` = unknown/unavailable, not `false`).

## 1) Audit evidence (frontend consumption and UI wiring)

### Type layer (`apps/web/src/types/capture-inbox.ts`)

Findings:
- `CapturedItem` already includes core canonical fields (`duration_seconds`, `posted_at`, metric counts, `engagement_rate`, basic source links).
- Part 3 backend-exposed first-class fields are not fully represented in frontend types yet:
  - provenance fields missing in `CapturedItem` typing (`duration_source`, metric `*_source`, `engagement_rate_source`).
  - processing-fit semantic fields missing in `CapturedItem` typing (`has_speech`, `text_density`, `has_heavy_watermark`, `processing_complexity`, `copyright_risk`).
  - `posted_source` needs contract alignment to include `"detail_hydrate"`.

### API consumption and advanced query wiring (`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`)

Findings:
- `buildAdvancedFilterPayload(...)` already maps advanced Time/Performance/Processing-fit filters into request payload.
- `applyAdvancedFilters(...)` already submits via query endpoint; reset flow is already present.
- Filter panel already contains controls for processing-fit toggles (`speech`, text-density cap, heavy watermark, high complexity, high copyright risk).
- Contract conformance still needs explicit verification after type alignment.

### Compact card wiring (`MediaTile` helpers)

Findings:
- Compact card currently renders duration/posted/metrics in helper-driven rows (`compactQuickMetaForItem`, `compactMetricMetaForItem`).
- Existing compact behavior is already close to desired “useful subset” and should remain compact.
- Any field additions must avoid visual bloat and preserve existing compact layout.

### Inspector/detail wiring (`RightInspector` helpers)

Findings:
- Inspector currently shows overview/source/metadata/diagnostics sections.
- Rich canonical provenance and processing-fit semantics are not surfaced as clear first-class rows yet.
- Unknown semantics should be rendered explicitly and neutrally (unknown/unavailable), not interpreted as negative values.

### Tests

Findings:
- Existing Capture Inbox tests in `apps/web/src/test/capture-inbox.test.ts` provide source/structure assertions that can be extended.
- Canonical helper-oriented tests exist in `apps/web/src/test/capture-inbox-canonical.test.ts` and are good anchors for compact/inspector rendering expectations.

## 2) Intended implementation (Part 4)

1. **Type alignment first**
   - Extend `CapturedItem` in `apps/web/src/types/capture-inbox.ts` with Part 3 fields.
   - Align `posted_source` union with backend (`detail_hydrate` support).

2. **Compact card wiring (minimal)**
   - Keep compact card focused on key Time/Performance subset.
   - Preserve existing row density and avoid introducing verbose provenance into tile body.

3. **Inspector wiring (rich detail)**
   - Add explicit rows for canonical provenance + processing-fit semantics in details panel.
   - Ensure null semantics render as unknown/unavailable rather than false/negative.

4. **Advanced filter contract verification/tightening**
   - Confirm `buildAdvancedFilterPayload(...)` keys and value transforms match backend contract.
   - Keep payload omission behavior for empty values.

5. **Focused tests**
   - Add/adjust source tests to verify:
     - type/contract alignment,
     - compact card subset remains compact,
     - inspector field visibility and honest unknown rendering,
     - apply/reset advanced filter behavior mapping.

## 3) Implementation results

1. **Frontend type alignment completed** in `apps/web/src/types/capture-inbox.ts`:
   - `posted_source` now includes `"detail_hydrate"`.
   - Added provenance fields: `duration_source`, `view_count_source`, `like_count_source`, `comment_count_source`, `share_count_source`, `engagement_rate_source`.
   - Added processing-fit semantic fields: `has_speech`, `text_density`, `has_heavy_watermark`, `processing_complexity`, `copyright_risk`.

2. **Compact card wiring updated (kept compact)** in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`:
   - Retained compact metric strip and added concise `ER` metric via `compactPercentValue(...)`.
   - Did not add verbose provenance/semantic rows to card surface.

3. **Inspector wiring expanded (rich details)** in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`:
   - Added provenance rows: duration/posted/views/likes/comments/shares/engagement sources.
   - Added processing-fit semantic rows: speech, text density, heavy watermark, processing complexity, copyright risk.
   - Added explicit formatters:
     - `formatTriStateBoolean(...)` ensures `null => Unknown` (not false).
     - `formatSemanticLevel(...)` ensures nullable levels render safely.
     - `formatSourceLabel(...)` keeps provenance labels readable.

4. **Advanced-filter contract mapping preserved** in `buildAdvancedFilterPayload(...)`:
   - Existing payload key mapping for Time/Performance/Processing-fit remains aligned.
   - No backend/API changes required.

5. **Focused frontend tests updated** in `apps/web/src/test/capture-inbox.test.ts`:
   - Updated `posted_source` expectation to include `detail_hydrate`.
   - Added assertions for new `CapturedItem` type fields.
   - Added assertions for inspector provenance + processing-fit rows and honest tri-state formatter behavior.
   - Added assertions for compact `ER` metric helper.

## 4) Verification

- Executed focused tests from repo root:
  - `npx tsx apps/web/src/test/capture-inbox.test.ts`
  - `npx tsx apps/web/src/test/capture-inbox-canonical.test.ts`
- Result:
  - `capture inbox Media-first Triage Studio, canonical rendering, session ribbon, status strip, filter toolbar, right-side inspector, state sync, action hierarchy, and polish tests passed`
  - `capture inbox canonical resolver behavior tests passed`

## 5) Non-goals (enforced)

- No edits under `apps/extension-douyin-capture`.
- No backend schema/service/route/model changes under `apps/api`.
- No redesign of Capture Inbox page structure or unrelated UX refactors.
- No unrelated queue/worker/crawler/video-processing changes.
