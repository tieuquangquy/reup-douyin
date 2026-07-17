# Live Metadata Part E Frontend Log (Part E only)

## Task

Part E only: frontend live render + filter verification for Capture Inbox / Tile Gallery using fields already fixed through Parts A–D.

In-scope fields:

- `posted_at`
- `posted_text`
- `duration_seconds`
- `duration_text`
- `view_count`
- `like_count`
- `comment_count`
- `share_count`

Out of scope:

- extension normalization changes
- backend persistence/API changes
- broad Capture Inbox redesign
- unrelated metadata semantics

## Audit findings (before code changes)

### 1) Frontend item type / API consumption

- [`CapturedItem`](../apps/web/src/types/capture-inbox.ts) already includes all Part E target fields.
- [`CaptureInboxAdvancedFilter`](../apps/web/src/types/capture-inbox.ts) already includes all required filter keys:
  - `from_date`, `to_date`
  - `min_duration_seconds`, `max_duration_seconds`
  - `min_views`, `max_views`
  - `min_likes`, `max_likes`
  - `min_comments`, `max_comments`
  - `min_shares`, `max_shares`
- [`queryCaptureInboxItems()`](../apps/web/src/lib/api.ts) posts full payload to backend query endpoint; no local-only filtering bypass observed.

### 2) Tile Gallery compact rendering

- Compact card uses [`compactQuickMetaForItem()`](../apps/web/src/components/capture-inbox/CaptureInboxPage.tsx) and [`compactMetricMetaForItem()`](../apps/web/src/components/capture-inbox/CaptureInboxPage.tsx).
- Quick meta currently includes `Duration`, `Posted`, and `Preview`.
- Metrics strip currently includes compact values for views/likes/comments/shares (plus engagement in current implementation).
- Missing-value behavior currently falls back to visible placeholders (e.g., `Not captured`) via shared resolvers.

### 3) Inspector/details rendering

- Inspector Overview currently shows `Duration` and `Posted` via canonical resolvers.
- Inspector Metadata section currently emphasizes source/provenance and processing semantics; target performance values are not explicitly surfaced as a dedicated value list.

### 4) Advanced filter wiring

- UI inputs exist for all required Part E filter fields in [`AdvancedFilterPanel`](../apps/web/src/components/capture-inbox/CaptureInboxPage.tsx).
- Payload mapping in [`buildAdvancedFilterPayload()`](../apps/web/src/components/capture-inbox/CaptureInboxPage.tsx) maps all required keys to backend contract.
- Apply path uses backend query endpoint with session scope (`capture_session_id` + `advanced_filter`), then sets queried results into state.
- Reset path clears draft/applied/query state.

## Gap summary

1. Target fields already reach frontend state and backend query payload shape.
2. Card compact display mostly exists; Part E should tighten honest missing behavior and compactness around posted/duration/4 counts.
3. Inspector should explicitly present richer target values (posted/duration/views/likes/comments/shares) in a clear, non-cluttered section.
4. Filter wiring appears present; Part E should verify mapping/tests specifically for target fields and apply/reset behavior.

## Planned Part E touchpoints

- [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](../apps/web/src/components/capture-inbox/CaptureInboxPage.tsx)
- [`apps/web/src/lib/captureInboxCanonical.ts`](../apps/web/src/lib/captureInboxCanonical.ts) (only if needed for honest compact rendering)
- [`apps/web/src/types/capture-inbox.ts`](../apps/web/src/types/capture-inbox.ts) (tiny alignment only if needed)
- frontend tests under [`apps/web/src/test`](../apps/web/src/test)

## Verification plan

1. Card shows posted/duration/counts compactly when available.
2. Card remains compact and honest for missing values.
3. Inspector shows richer target values clearly.
4. Advanced filter mapping for target fields is verified.
5. Apply/reset behavior preserves backend-driven filtering flow.

## Implementation (Part E)

### Changed files

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - Compact tile metrics now use canonical resolvers for all target metric fields (`views/likes/comments/shares`) instead of direct numeric-only formatting.
  - Added a dedicated inspector section **"Live capture fields"** to surface:
    - duration
    - posted
    - views
    - likes
    - comments
    - shares
  - Kept compact card shape and existing quick metadata strip (`Duration`, `Posted`, `Preview`) unchanged in structure.

- `apps/web/src/lib/captureInboxCanonical.ts`
  - Added `resolveShareCount(item)` resolver aligned with existing resolver semantics.
  - Resolver uses canonical-first behavior and honest fallback (`Not captured`) via shared `resolveMetric(...)`.

- `apps/web/src/types/capture-inbox.ts`
  - Added `share_count_text: string | null` to `CapturedItem` so share text fallback is explicitly typed in the frontend contract.

- `apps/web/src/test/capture-inbox.test.ts`
  - Added assertions to verify:
    - `resolveShareCount(...)` is exported.
    - share metric canonical resolver wiring is present.
    - `share_count_text` is present in frontend item type contract.

- `apps/web/src/test/capture-inbox-canonical.test.ts`
  - Updated canonical fixture shape to include `share_count_text` for typecheck compatibility.

## Verification

Executed from workspace root:

- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web exec tsx src/test/capture-inbox.test.ts`
- `npm --workspace @reup-douyin/web exec tsx src/test/capture-inbox-canonical.test.ts`

Result:

- typecheck passed
- capture inbox source assertions passed
- capture inbox canonical resolver behavior tests passed
