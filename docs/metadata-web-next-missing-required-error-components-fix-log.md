# Web Next.js Missing Required Error Components Fix Log

Date: 2026-05-10

## Browser error observed

The local web app at `http://localhost:3000` showed a blank page with:

```txt
missing required error components, refreshing...
```

The dev server also showed repeated 404s for app/static assets such as:

```txt
GET / 404
GET /ops 404
GET /_next/static/css/app/layout.css 404
GET /_next/static/chunks/main-app.js 404
GET /_next/static/chunks/app-pages-internals.js 404
GET /_next/static/chunks/app/layout.js 404
```

## Actual root cause found

No source compile error was found. Typecheck and production build both passed.

The actual cause was stale/corrupted generated Next.js dev output plus stale running Node/Next processes. After stopping old dev services, force-stopping remaining stale Node processes, and deleting only generated cache/build folders, Next regenerated `.next` cleanly and both tested routes returned HTTP 200.

## Commands run

Stopped stale dev services/processes and removed only generated cache/build folders:

```powershell
Get-Process node -ErrorAction SilentlyContinue
npm run dev:stop
Stop-Process -Name node -Force
Remove-Item -Recurse -Force .\apps\web\.next -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\.next -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\node_modules\.cache -ErrorAction SilentlyContinue
```

Actual combined cleanup command used also printed verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "Write-Host 'Node processes before:'; Get-Process node -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path | Format-Table -AutoSize; if (Test-Path .\scripts\dev-stop.ps1) { & .\scripts\dev-stop.ps1 }; Start-Sleep -Seconds 1; $nodes = Get-Process node -ErrorAction SilentlyContinue; if ($nodes) { Write-Host 'Stopping remaining node processes:'; $nodes | Select-Object Id,ProcessName,Path | Format-Table -AutoSize; $nodes | Stop-Process -Force }; Remove-Item -Recurse -Force .\apps\web\.next -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force .\.next -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force .\node_modules\.cache -ErrorAction SilentlyContinue; Write-Host 'apps/web/.next exists after clean:' (Test-Path .\apps\web\.next); Write-Host '.next exists after clean:' (Test-Path .\.next); Write-Host 'node_modules/.cache exists after clean:' (Test-Path .\node_modules\.cache); Write-Host 'Node processes after:'; Get-Process node -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path | Format-Table -AutoSize"
```

Inspected package scripts, lock files, Next config, TypeScript config, and App Router files:

```powershell
Get-Content package.json -Raw
Get-Content apps/web/package.json -Raw
Get-ChildItem -Name pnpm-lock.yaml,package-lock.json,yarn.lock -ErrorAction SilentlyContinue
Get-ChildItem -Name next.config.js,next.config.mjs,apps/web/next.config.js,apps/web/next.config.mjs -ErrorAction SilentlyContinue
Get-Content apps/web/tsconfig.json -Raw
```

Ran checks:

```powershell
npm run typecheck
npm run web:build
```

Restarted web dev server:

```powershell
npm --workspace @reup-douyin/web run dev
```

Verified local routes:

```powershell
powershell -NoProfile -Command "Start-Sleep -Seconds 2; $root = Invoke-WebRequest -Uri http://localhost:3000 -UseBasicParsing -TimeoutSec 20; Write-Host 'GET / status:' $root.StatusCode; $route = Invoke-WebRequest -Uri http://localhost:3000/ops/extensions/douyin/capture-inbox -UseBasicParsing -TimeoutSec 20; Write-Host 'GET /ops/extensions/douyin/capture-inbox status:' $route.StatusCode; Write-Host 'apps/web/.next exists:' (Test-Path .\apps\web\.next); Write-Host 'dev static main exists:' (Test-Path .\apps\web\.next\static\chunks\main-app.js)"
```

## Files changed

- `docs/metadata-web-next-missing-required-error-components-fix-log.md`

No source files, package files, lock files, backend data, backend APIs, or Douyin extension crawler logic were changed.

## Validation result

Cleanup verification:

```txt
apps/web/.next exists after clean: False
.next exists after clean: False
node_modules/.cache exists after clean: False
```

Typecheck:

```txt
npm run typecheck
exit code: 0
```

Build:

```txt
npm run web:build
exit code: 0
```

Build emitted only existing CSS/autoprefixer warnings about `start`/`end` alignment values and Windows path-case webpack cache warnings. It completed successfully and listed `/` plus `/ops/extensions/douyin/capture-inbox` in the generated routes.

Dev verification:

```txt
GET / status: 200
GET /ops/extensions/douyin/capture-inbox status: 200
apps/web/.next exists: True
dev static main exists: True
```

The dev server compiled `/` and `/ops/extensions/douyin/capture-inbox` and returned 200 for both. No `missing required error components` message was reproduced after the clean restart.

## Whether source code needed fixing

Cache cleanup and stale process cleanup fixed the issue. No source code fix was needed because typecheck and build passed.

## How to fix if it happens again

From `C:\Users\PC\Desktop\reup_douyin`:

```powershell
npm run dev:stop
Get-Process node -ErrorAction SilentlyContinue
Stop-Process -Name node -Force
Remove-Item -Recurse -Force .\apps\web\.next -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\.next -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\node_modules\.cache -ErrorAction SilentlyContinue
npm --workspace @reup-douyin/web run dev
```

Use `Stop-Process -Name node -Force` only when stale local dev Node processes remain after `npm run dev:stop` and they are safe to stop.

For the full local stack, use:

```powershell
npm run dev
```
