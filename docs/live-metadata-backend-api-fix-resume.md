# Live Metadata Backend/API Fix Resume (Part D only)

## Status

- Part D implementation completed
- Inputs from Part B/Part C applied to backend/API contract alignment
- Focused backend verification passed

## Scope lock

Only fields in this task:

- `posted_at`
- `posted_text`
- `duration_seconds`
- `duration_text`
- `view_count`
- `like_count`
- `comment_count`
- `share_count`

Allowed code area:

- [`apps/api`](../apps/api)
- tiny shared API type alignment only if strictly required

Explicit non-goals:

- no extension normalization changes
- no frontend UI/render changes
- no unrelated metadata redesign

## Source references

- [`docs/live-posted-duration-extension-fix-log.md`](./live-posted-duration-extension-fix-log.md)
- [`docs/live-performance-extension-fix-log.md`](./live-performance-extension-fix-log.md)
- [`docs/live-metadata-gap-audit-log.md`](./live-metadata-gap-audit-log.md)

## Execution outcome

1. inspected staging persistence path for target fields
2. inspected Capture Inbox schema hydration for target fields
3. implemented API exposure gap for live source literals (`dom_text`, `derived_from_canonical_counts`)
4. updated focused backend/API tests to validate literal exposure and null-safe behavior
5. ran backend verification via `python -m unittest tests/test_douyin_extension_capture_service.py` from [`apps/api`](../apps/api)
6. updated Part D docs with changed files and verification result
