# douyin-reopen-notimplemented-hard-fix-user-guide.md

## What This Fix Targets

This fix targets the specific local runtime failure where a saved Douyin browser profile cannot be reopened and the UI shows:

```text
profile_reopen_failed
browser_validation_runtime_unavailable
persistent_profile_open_failed:NotImplementedError
```

That error means the app found the saved reusable profile and reached the reopen step, but the local Playwright/browser runtime failed before a live context could be attached.

## Expected Behavior After The Fix

For a browser-backed account with a saved reusable profile:

1. `Reopen profile` opens the same saved local browser profile.
2. `Validate` uses the same canonical reopen implementation when the live runtime is missing.
3. The runtime registry is reattached to the same account/profile after reopen.
4. Validate continues after successful reopen.
5. `NotImplementedError` is no longer shown as the active reopen failure.

## Operator Diagnostics

The backend should distinguish these states instead of collapsing everything into a generic reopen failure:

- `reopen_not_supported_current_runtime`: local runtime/dependency is unsupported or unavailable.
- `browser_launch_failed`: the browser could not launch.
- `profile_locked_by_existing_process`: the saved profile is already locked by another browser process.
- `persistent_profile_open_failed`: profile open failed and no sharper category applies.
- `first_page_closed_early`: the profile opened but page/context acquisition failed too early.
- `runtime_attach_failed`: browser opened but did not attach to the same account/profile.
- `reopen_success`: live runtime attached to the same saved account/profile.

## Operator Action After Updating

After applying code changes, restart the API process so the browser runtime setup is loaded by the active backend process. Then use `Reopen profile` or run `Validate` again on the same saved browser-backed account.

The old persisted failure row will not change until a new reopen/validate attempt writes new diagnostics.

## Verified Local Behavior

The canonical backend reopen helper was verified directly in the local Windows environment:

- Playwright persistent Chromium context launches after applying the runtime policy setup.
- The exact supplied saved profile path is reused.
- `DouyinBrowserContextRegistry.open_profile_for_account()` returns `reopen_success`.
- `summary_for_account()` sees the same active runtime id after reopen.

This proves the previous `persistent_profile_open_failed:NotImplementedError` path is no longer the active result for the local persistent-profile reopen implementation.

## Security Notes

Diagnostics must not expose raw cookies, credentials, auth tokens, or private session payloads.
