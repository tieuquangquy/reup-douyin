# Next.js Missing Chunk Recovery Log

## Error Observed

The web app repeatedly showed a Next.js server chunk resolution error on Windows:

```txt
Error: Cannot find module './5409.js'
Require stack includes:
- C:\Users\PC\Desktop\reup_douyin\apps\web\.next\server\webpack-runtime.js
- C:\Users\PC\Desktop\reup_douyin\apps\web\.next\server\pages\_document.js
- C:\Users\PC\Desktop\reup_douyin\node_modules\next\dist\server\require.js
- C:\Users\PC\Desktop\reup_douyin\node_modules\next\dist\server\load-components.js
```

The same class of issue previously appeared as:

```txt
Cannot find module './3135.js'
```

## Root Cause

This is consistent with a stale or corrupted Next.js generated build cache, or a dev server chunk mismatch after code changes or an interrupted dev process. It is not a product behavior bug unless a fresh typecheck/build surfaces a real source error.

The project already disables persistent webpack cache for local dev in `apps/web/next.config.mjs`, which helps reduce recurrence. The safe recovery is to stop stale Node/Next dev servers and remove only generated cache/build folders so Next can regenerate `.next` from source.

## Safe Fix

Run from the repository root:

```sh
npm run clean:next
npm run dev
```

For a web-only fresh dev server, run:

```sh
npm run dev:web:fresh
```

For a fresh production build, run:

```sh
npm run build:fresh
```

## What The Cleanup Removes

`npm run clean:next` removes only generated cache/build folders when present:

- `apps/web/.next`
- `.next`
- `node_modules/.cache`
- `.turbo`

## What Not To Delete

Do not delete these for this issue unless there is a separate, confirmed dependency or data problem:

- Source files under `apps/`, `packages/`, `scripts/`, or `docs/`
- `node_modules`
- `package-lock.json`
- Backend data, local databases, or captured Douyin payloads
- Extension crawler or capture logic

## When To Run

Use the fresh cleanup command when any of these happen:

- Browser shows `Cannot find module './####.js'` from `.next/server/webpack-runtime.js`
- A blank page appears after many frontend changes
- Next dev server was interrupted during compile
- Windows file locks or stale Node processes leave `.next` inconsistent
- Switching branches or moving between large Capture Inbox/frontend changes

## Validation Performed

After cleaning generated caches, the web workspace passed:

```sh
npm run typecheck
npm run web:build
```

The dev server was started with:

```sh
npm --workspace @reup-douyin/web run dev
```

Both routes returned HTTP 200:

```txt
http://localhost:3000 200 OK
http://localhost:3000/ops/extensions/douyin/capture-inbox 200 OK
```

Build/dev still report existing CSS autoprefixer warnings about `start`/`end` alignment values, but these warnings do not block compilation and are unrelated to missing Next.js chunks.
