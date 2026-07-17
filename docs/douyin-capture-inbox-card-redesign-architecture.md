# Douyin Capture Inbox Card Redesign Architecture

## Goal

Make `/ops/extensions/douyin/capture-inbox` feel like a video moderation and staging console for a local-first operator while preserving SaaS-ready boundaries.

The redesign changes presentation and explicit staged-item actions. It does not change the capture pipeline, enrichment semantics, promotion target, Review Board contract, queue orchestration, or video processing responsibilities.

## Current architecture

### Route

`apps/web/src/app/ops/extensions/douyin/capture-inbox/page.tsx` renders `CaptureInboxPage` directly.

### Web component

`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` owns the browser workflow:

- Load sessions.
- Load selected session detail.
- Filter and sort captured items.
- Track selected item IDs.
- Track focused item ID.
- Run Capture Inbox actions through `runCaptureInboxAction`.
- Render summary cards, search/filter controls, item cards, session list, detail panel, and batch actions.

### Web API client

`apps/web/src/lib/api.ts` exposes:

- `fetchCaptureInboxSessions`
- `fetchCaptureInboxSession`
- `fetchCaptureInboxItems`
- `runCaptureInboxAction`

The generic action client can support delete by extending the request action type.

### Backend HTTP boundary

`apps/api/src/api/routes/capture_inbox.py` owns Capture Inbox HTTP routes. The action endpoint currently handles:

- `retry_enrich`
- `retry_preview`
- `exclude`
- `promote_now`
- `open_source`
- `view_raw_details`

### Backend service boundary

`apps/api/src/services/capture_inbox_service.py` owns session/item persistence behavior and action orchestration. It already has item selection, retry, exclude, promotion, preview readiness, and session reconciliation helpers.

## Data and thumbnail strategy

### Existing fields

The staged item model and API response already include:

- `thumbnail_url`
- `preview_url`
- `preview_ready`
- `media_ready`

The card UI should use a helper such as `thumbnailUrlForItem(item)` to keep rendering rules centralized.

### Backend extraction

Current extraction reads:

```py
thumbnail_url = _first_string(raw_item, "thumbnail_url", "cover_url")
```

The redesign should extend this to include `poster_url` as a safe additional fallback:

```py
thumbnail_url = _first_string(raw_item, "thumbnail_url", "cover_url", "poster_url")
```

This is not a new processing pipeline. It only preserves more of the already-captured extension payload.

### Missing thumbnail state

If no thumbnail-like field exists, the card renders a clear visual placeholder:

- label: `No thumbnail available`
- secondary state text from preview readiness, for example `Preview pending` or `Source available`

## UI architecture

### Overall shell

Keep the shared Ops Console structure:

- `OpsConsoleShell`
- `PageShell`
- `OpsConsolePage`
- summary/filter primitives
- batch action primitive

### Main staging area

Replace the text-heavy stacked list with a visual card grid/list container.

Card requirements:

- 16:9 thumbnail/placeholder area.
- Status badge.
- Selection checkbox.
- Caption/title area.
- Source/video ID summary.
- Compact metadata strip for duration, posted date, views/likes/comments when available.
- Next-action hint.
- Contextual action buttons.

The card component can be local to `CaptureInboxPage.tsx` so app-specific workflow logic stays in `apps/web`.

### Detail drawer

Dense technical and downstream information belongs in a right-side detail drawer/panel.

Expected behavior:

- Opening details focuses the item and opens the drawer.
- Drawer has a visible close button.
- Drawer remains aligned with shared Ops Console visual language.
- On narrow screens, CSS may make the drawer behave like a full-width modal-like panel.
- Diagnostics remain collapsed by default.

### Contextual action model

Keep state-aware actions:

- Ready: preview/details/promote/delete.
- Duplicate: open existing/details/dismiss/delete.
- Needs enrichment/raw: retry enrich/retry preview/details/delete.
- Preview missing: retry preview/details/delete.
- Failed: view error/retry/exclude/delete.
- Promoted: open candidate/view details. Delete should be blocked/hidden/disabled for promoted items to avoid silently removing downstream references.
- Excluded: details/delete.

## Delete architecture

### User intent

Delete means delete selected staged item rows from Capture Inbox. It is distinct from `exclude`, which keeps a staged row but marks it skipped.

### Safety rules

- Require explicit selected item IDs.
- Require UI confirmation before per-item or bulk delete.
- Do not delete promoted items through the staged delete action.
- Reconcile capture session counts after deletion.
- Return a clear response message containing deleted/skipped counts.

### Backend contract

Add a new Capture Inbox action literal, preferably `delete_items`, to avoid ambiguity with account/profile deletion actions elsewhere.

`CaptureInboxActionRequest.action` should include `delete_items`.

The backend route should call a service method such as:

```py
delete_items(capture_session_id, item_ids)
```

The service should:

1. Load the capture session.
2. Require at least one item ID.
3. Select matching session items.
4. Delete only non-promoted staged items.
5. Skip promoted items.
6. Reconcile the session.
7. Commit.
8. Return counts for route messaging.

No schema migration is required for hard deleting staged rows from the existing table.

## Responsive behavior

- Desktop: card grid/list with right-side drawer.
- Medium/narrow: card grid collapses to fewer columns; detail drawer can span full width.
- Bulk action bar remains sticky and visible only when items are selected.
- Avoid CSS-only masking of workflow problems; the component state should explicitly model drawer and confirmation behavior.

## Non-goals

- No crawler implementation.
- No video processing implementation.
- No scoring changes.
- No queue or worker changes.
- No object storage changes.
- No auto-publish changes.
- No broad design-system rewrite.
