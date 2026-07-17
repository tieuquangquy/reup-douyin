# Douyin Factor 4 — Engagement Signals Resume

## Objective
Implement **Factor 4 only** for capture-inbox signal quality:
- Normalize and preserve trustworthy `view_count`, `like_count`, `comment_count`, `share_count`.
- Derive trustworthy `engagement_rate` when safe.
- Keep strict exact-id (`aweme_id`) source precedence:
  1. network JSON exact match
  2. detail hydrate exact match
  3. item-local DOM fallback only if needed

## Status Snapshot
- Audit coverage across extension, API, schema, and web type surfaces: **completed**.
- Docs-first requirement: **in progress**.
  - Created: `docs/douyin-factor4-engagement-signals-log.md`
  - Created: `docs/douyin-factor4-engagement-signals-resume.md` (this file)
  - Pending: `docs/douyin-factor4-engagement-signals-architecture.md`
- Implementation: **not started yet**.

## Confirmed Boundaries
- Do not rework duration/posted logic outside strict Factor-4 needs.
- Do not perform broad UI redesign.
- Do not refactor unrelated modules.
- Keep contract changes minimal and explicit.

## Planned Implementation Order (Locked)
1. Audit (done)
2. Docs first (in progress)
3. Extension normalization and source-priority engagement merge
4. Detail hydrate fallback parity
5. Compact parse confidence guards + invalid-value suppression
6. Minimal backend/API alignment for `share_count` and `engagement_rate`
7. Minimal frontend type/render alignment
8. Focused tests
9. Verification runs
10. Final docs update with evidence

## Risks to Watch
- Divergence between `extractor.ts` and popup direct-execution metric logic.
- Accidental acceptance of ambiguous compact metric text.
- Engagement-rate calculation on weak/zero denominator values.
- Contract drift across extension payload schema and API response schema.

## Next Immediate Action
Create `docs/douyin-factor4-engagement-signals-architecture.md` before any code edits, then begin scoped Factor-4 implementation patches.
