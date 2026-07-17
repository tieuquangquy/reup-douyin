# Douyin Persistent Browser Context User Guide

## What This Changes

Browser-assisted connect can now keep a local Playwright browser context alive after login. While that context is alive, validation and live-fetch preparation can reuse it instead of relying only on previously captured cookies.

This reduces repeated QR/login prompts during local development.

## What It Does Not Change

This does not replace:

- `DouyinAccountConnection`
- manual session import fallback
- account health validation state
- `/intake` discovery/ingest pipeline
- `SourceProfile`, `SourceVideo`, `CrawlSession`, or candidate persistence

The browser context is runtime-only. If the API process restarts, the context disappears and the system falls back to saved account session artifacts.

## Config

Relevant API env flags:

```env
DOUYIN_PERSISTENT_BROWSER_CONTEXT_ENABLED=true
DOUYIN_REUSE_LIVE_BROWSER_FOR_VALIDATION=true
DOUYIN_REUSE_LIVE_BROWSER_FOR_FETCH=true
DOUYIN_BROWSER_CONTEXT_IDLE_TIMEOUT_SECONDS=1800
DOUYIN_BROWSER_CONTEXT_MAX_LIFETIME_SECONDS=14400
DOUYIN_BROWSER_CONNECT_STABILIZATION_SECONDS=8
```

These are local-first defaults. Do not treat this as a SaaS browser-session broker.

## Local Workflow

1. Open `/accounts/douyin`.
2. Start browser-assisted connect.
3. Login or scan QR in the opened Douyin browser.
4. Keep the browser open.
5. After validation succeeds, the Connected accounts table should show `Live browser attached`.
6. Run Validate/Revalidate or use `/intake` force refresh with that account.
7. The API will try to refresh session artifacts from the live browser context before falling back to saved cookies.

## Cleanup

The runtime context closes when:

- idle timeout expires;
- max lifetime expires;
- browser process dies;
- browser-connect reset is used;
- related account is disabled or deleted;
- the API process restarts.

## Failure Behavior

If the live context is stale, closed, or invalid, the account remains. The system falls back to the existing cookie-backed validation/fetch path and the UI shows that no live browser context is available.

## V1 Limitations

- Runtime context is in-memory only.
- No remote browser service exists.
- No browser-only intake pipeline exists.
- Manual browser verification is still needed for real Douyin behavior.
- Playwright handles may become invalid across local runtime/thread boundaries; if that happens the registry marks the context invalid and falls back.
