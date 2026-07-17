# Douyin Managed Runtime Fix Architecture

## Decision

Douyin browser-backed account operations must use app-managed Playwright persistent contexts only. A browser window visible to the operator is not an ownership signal unless it is represented by a live `_ContextRecord` in the app's runtime registry and its profile identity matches the account's canonical saved profile.

## Runtime ownership states

| State | Meaning | Operator impact |
| --- | --- | --- |
| `managed_runtime_active` | The app owns a live registered runtime/context for the account/profile. | Browser-backed actions may proceed. |
| `managed_runtime_missing` | No app-owned runtime record exists for the account. | App may open the saved profile, but must not assume a visible browser is usable. |
| `managed_runtime_stale` | A registry record exists but its context/page/runtime is no longer usable. | App should reconcile stale state and require reopen/retry. |
| `profile_locked_by_existing_process` | Playwright cannot open the saved profile because another process owns the Chromium profile lock. | Operator must close the external browser/process, then use `Open profile`. |
| `profile_opened_outside_managed_runtime` | The saved profile appears opened by an unmanaged process and no app-owned runtime can be attached. | App must not validate/intake from that visible window. |
| `first_page_closed_but_context_alive` | The remembered/first page closed, but the managed context is still usable. | App should recover by reacquiring or creating a page in the same context. |

## Boundaries

- `apps/api` owns runtime registration, validation, profile reopen, account metadata, and Intake preflight enforcement.
- `apps/web` only displays diagnostics and calls existing API endpoints; it must not infer runtime ownership from UI state.
- `apps/worker` is not part of this fix.
- `packages/shared` and `packages/config` are not expected to change unless a cross-app contract is introduced.

## Registry model

The registry is the source of truth for app-managed browser ownership during the local API process lifetime:

- `_records` contains live `_ContextRecord` entries.
- `_record_for_account()` identifies the canonical managed record for an account.
- `open_profile_for_account()` is responsible for creating or reusing the canonical managed runtime for an account/profile.
- `validate_account_context()` and `fetch_profile_page()` must fail closed when no managed runtime exists.

## External profile conflicts

Playwright persistent context launch is the practical conflict detector. When profile launch fails with singleton/user-data-directory lock text, the backend should classify the condition as both:

- low-level reason: `profile_locked_by_existing_process`
- ownership state: `profile_opened_outside_managed_runtime`

This avoids implying that the visible browser can be used. The correct recovery is: close externally opened windows for that profile, then use the app's `Open profile` action.

## Page recovery

The page handle is not the ownership boundary. The context is the ownership boundary.

- If the remembered page is closed but another context page is usable, reacquire it.
- If all pages are closed but the managed context can create a new page, create one.
- Report this as `first_page_closed_but_context_alive` / page recovery instead of a fatal runtime ownership failure.

## Non-goals

- No crawler implementation.
- No new database schema.
- No distributed runtime registry.
- No external browser DevTools attachment.
- No automatic killing of unmanaged browser processes.
