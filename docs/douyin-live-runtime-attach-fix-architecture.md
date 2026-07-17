# Douyin Live Runtime Attach Fix Architecture

## Decision

Browser-backed Douyin validation must treat the browser context as the reusable runtime boundary and the page as a replaceable handle. A closed page is not proof that the persistent browser profile is unavailable.

## Runtime Ownership Model

- `DouyinAccountConnection` owns the account identity and persisted browser profile metadata.
- `DouyinBrowserContextRegistry` owns in-process Playwright runtime records.
- `_ContextRecord.context` is the important live runtime object for a saved profile.
- `_ContextRecord.page` is a convenience handle and may become stale.
- Account workflows must not allocate a new browser profile when saved profile metadata already exists.

## Validation Hierarchy

The canonical validation/recovery hierarchy is:

1. Look for an existing registry record bound to the account.
2. Verify the context is usable with `_ensure_usable`.
3. Ensure a usable page inside that context:
   - keep `record.page` if still usable,
   - otherwise choose an existing open page from `record.context.pages`,
   - otherwise create `record.context.new_page()` in the same context.
4. Navigate/prevalidate using the reacquired page.
5. If no live context exists, reopen the same saved persistent profile path/id.
6. After reopen, verify the reopened summary still matches the expected account/profile identity.

## Page Reacquisition Semantics

The registry should report safe internal categories such as:

- `live_runtime_attached`: an existing runtime/context was found and usable.
- `live_context_page_reacquired`: a stale remembered page was replaced by another existing page in the same context.
- `live_context_new_page_created`: no usable existing page was available, so a new page was created in the same context.
- `first_page_closed_but_recovered`: profile open or validation recovered from a closed first page.
- `runtime_missing_reopen_required`: no usable live context exists, so account service may reopen the same saved profile.
- `reopen_success`: same saved profile was reopened and attached.
- `reopen_failed`: same saved profile could not be reopened.
- `runtime_attach_failed`: reopened runtime did not safely bind to the expected account/profile.
- `challenge_still_required`: browser validation reached visible challenge evidence.
- `browser_validation_success`: authenticated browser context was reachable.
- `browser_validation_inconclusive`: authenticated cookies exist, but page evidence is not conclusive.

## Error Handling

- A page-level exception should not automatically invalidate and close the entire browser context.
- The registry may invalidate the context only when context-level health checks fail, such as cookies/context calls throwing because the context/browser is closed.
- Reopen fallback should be explicit and recorded as fallback, not as the first action for saved profiles.

## Diagnostics Policy

Diagnostics may include:

- status/category strings,
- runtime context id,
- browser profile id/path already stored in account metadata,
- timestamps,
- boolean flags for page reacquisition or reopen fallback.

Diagnostics must not include:

- cookies,
- credentials,
- tokens,
- raw local private paths beyond existing safe profile metadata conventions,
- full page HTML.

## Boundary Notes

- `apps/api` coordinates validation and persists account metadata.
- `apps/web` may display safe diagnostics but must not infer browser runtime internals.
- `apps/worker` is not part of this change.
- `packages/shared` and `packages/config` are not expected to change.
