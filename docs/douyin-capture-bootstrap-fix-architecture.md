# Douyin Capture Bootstrap Fix Architecture

## Purpose

The Douyin capture-current-page model depends on an operator-controlled browser page. The system must therefore distinguish three separate facts:

1. A saved persistent browser profile exists for the account.
2. The app has a live managed Playwright runtime attached to that saved profile.
3. The live runtime has a usable current page whose classification supports capture.

This fix makes those facts explicit and prevents downstream actions from treating saved profile metadata as equivalent to a live app-managed runtime.

## Boundaries

### apps/web

- Shows saved-profile versus managed-runtime state.
- Lets the operator open or reopen the saved profile.
- Lets the operator detect the current visible page.
- Enables Capture current page only when the backend reports a live managed runtime and supported page classification.
- Does not perform crawling, persistence, or page parsing directly.

### apps/api

- Owns HTTP routes and account projections.
- Coordinates runtime bootstrap, account metadata updates, current-page detection, capture, and challenge recovery.
- Must not run long video processing inline beyond current-page ingest behavior already present.
- Must not expose Playwright implementation details as public contracts beyond stable diagnostic status categories.

### apps/worker

- Not changed by this fix.

### packages/shared and packages/config

- Not expected to change for this fix unless shared status constants are later introduced.

## Runtime model

### Saved profile identity

For every account-backed browser profile, the canonical identity comes from saved account metadata:

- browser_profile_id.
- browser_profile_path.

For an account that already has saved profile metadata, Open/Reopen must reuse that identity. It must not allocate a new profile id/path.

### App-managed runtime

The app-managed runtime is represented by a _ContextRecord in the Douyin browser context registry. It contains:

- runtime_context_id.
- account_connection_id.
- browser_profile_id/browser_profile_path.
- Playwright handle.
- Browser context handle.
- Preferred page handle.
- lifecycle timestamps and reason.

Only records in this registry count as app-managed runtime evidence.

### Current page

The current page is the recovered preferred page in the managed context. The page recovery path should be:

1. Use the existing preferred page if it is usable.
2. If preferred page is closed, search context.pages for another usable page in the same context.
3. If no usable page exists, create a new page in the same context.
4. If page creation fails because the context/browser is closed, mark runtime as stale/missing.

The fix should classify recovery precisely:

- live_runtime_attached for existing usable preferred page.
- page_reacquired_same_context for another usable page in the same context.
- page_created_same_context for a new page in the same context.
- managed_runtime_reopen_failed when profile bootstrap fails.
- capture_not_ready_runtime_missing when capture cannot proceed because runtime is missing.

## Open/Reopen profile architecture

For existing account-backed profiles, Open/Reopen should be a bootstrap action:

1. Resolve the account's saved browser_profile_id/browser_profile_path.
2. Close stale or conflicting registry records that point at the same profile but are not usable.
3. Launch a persistent Playwright context using the same saved profile path.
4. Recover or create a page in that same context.
5. Register _ContextRecord only after the context and page are usable.
6. Return success only if summary/watchdog reports managed_runtime_active.

Open/Reopen should not require a login validation probe to pass before the app-managed runtime exists. The operator may still need to log in or solve a challenge in the opened browser.

## Downstream action architecture

### Detect current page

Detect current page reads only from the managed runtime snapshot.

- If runtime is missing, it returns unknown_page with supported_capture false and recommended action Open/Reopen profile.
- If runtime is active, it classifies the page as login, challenge, home/feed, profile/feed, video detail, unsupported, or unknown.
- It includes runtime diagnostics so the UI can explain whether capture is ready.

### Capture current page

Capture current page is stricter than detection.

It requires:

- managed_runtime_active.
- Usable current-page snapshot.
- page classification profile_page or profile_feed_page.
- normalized profile URL derived from the current page.

If any requirement fails, it returns a typed 422 diagnostic and does not ingest.

### Mark challenge solved

Mark challenge solved should operate against the same saved profile and app-managed runtime:

1. Verify saved browser profile metadata exists.
2. Ensure a managed runtime is active for that saved profile, using the canonical Open/Reopen bootstrap path if missing.
3. Reuse the recovered page/context.
4. Run post-challenge validation/classification.
5. Record whether the same profile and same runtime were reused or reopened.
6. Refuse success if the runtime was missing, profile mismatched, or detached HTTP fallback was the only evidence.

## Status vocabulary

The implementation should preserve existing public fields where possible and add/normalize values carefully.

Important result categories for this fix:

- managed_runtime_active.
- managed_runtime_missing.
- managed_runtime_reopen_failed.
- page_reacquired_same_context.
- page_created_same_context.
- current_page_detected_supported.
- current_page_detected_challenge.
- current_page_detected_login.
- current_page_detected_unsupported.
- capture_ready.
- capture_not_ready_runtime_missing.

## Observability

Logs and metadata should include stable identifiers:

- account_connection_id.
- runtime_context_id.
- connect_session_id where applicable.
- browser_profile_id when safe.

Do not log secrets, cookies, auth tokens, credentials, or private local paths unless explicitly safe. Existing code logs profile_path in launch warnings; this should be reviewed carefully and avoided in new logging.

## Failure handling

- TargetClosedError from a page should not automatically mean profile reopen failed if the context is still alive.
- TargetClosedError from the context/browser should be classified as managed_runtime_reopen_failed or managed_runtime_missing.
- Profile lock/process singleton means the saved profile is open outside the app-managed runtime.
- A saved profile without a live registry record is not capture-ready.

## Test strategy

Focused tests should cover:

- Closed preferred page recovered by another page in the same context.
- Closed preferred page recovered by creating a new page in the same context.
- Context/browser closure marks runtime unavailable.
- Open/Reopen preserves saved profile identity.
- Current-page capture fails when runtime is missing.
- Current-page capture remains disabled/not ready for login, challenge, home/feed, unsupported, and unknown pages.
- Mark challenge solved bootstraps/reuses managed runtime before validation.
