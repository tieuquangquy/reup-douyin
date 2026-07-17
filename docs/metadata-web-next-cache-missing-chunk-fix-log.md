# Web Next.js Cache Missing Chunk Fix Log

Date: 2026-05-10

## Error observed

The web app at `http://localhost:3000` reported a Next.js runtime chunk resolution failure:

```txt
Error: Cannot find module './3135.js'
```

The require stack pointed into generated Next.js output under `apps/web/.next/server`, including `webpack-runtime.js` and `app/_not-found/page.js`.

## Diagnosis

Working directory was confirmed as:

```txt
C:\Users\PC\Desktop\reup_douyin
```

Package manager and scripts were inspected:

- Root package manager: `npm@11.11.0`
- Lock file present: `package-lock.json`
- Web workspace: `@reup-douyin/web`
- Web dev command: `npm --workspace @reup-douyin/web run dev`
- Web build command: `npm --workspace @reup-douyin/web run build`
- Web typecheck command: `npm --workspace @reup-douyin/web run typecheck`

Generated cache state before cleanup:

```txt
apps/web/.next exists: True
apps/web/.next/server/chunks/3135.js exists: True
apps/web/.next/server/app/_not-found/page.js exists: True
apps/web/.next/server/webpack-runtime.js exists: True
```

Because the chunk existed on disk during diagnosis while the running app had reported it missing, the likely cause was a stale/corrupted `.next` cache or an old dev-server runtime holding mismatched generated chunk state.

## Commands run

Diagnosis:

```powershell
powershell -NoProfile -Command "Write-Host 'PWD:' (Get-Location).Path; Write-Host 'Root package:'; Get-Content package.json -Raw; Write-Host 'Web package:'; Get-Content apps/web/package.json -Raw; Write-Host 'Locks:'; Get-ChildItem -Name pnpm-lock.yaml,package-lock.json,yarn.lock -ErrorAction SilentlyContinue; Write-Host '.next exists:' (Test-Path apps/web/.next); Write-Host 'chunk 3135:' (Test-Path apps/web/.next/server/chunks/3135.js); Write-Host '_not-found page:' (Test-Path apps/web/.next/server/app/_not-found/page.js); Write-Host 'webpack runtime:' (Test-Path apps/web/.next/server/webpack-runtime.js)"
```

Stop dev services and clean generated cache directories only:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path .\scripts\dev-stop.ps1) { & .\scripts\dev-stop.ps1 }; Remove-Item -Recurse -Force .\apps\web\.next -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force .\.next -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force .\node_modules\.cache -ErrorAction SilentlyContinue; Write-Host 'apps/web/.next exists after clean:' (Test-Path .\apps\web\.next); Write-Host '.next exists after clean:' (Test-Path .\.next); Write-Host 'node_modules/.cache exists after clean:' (Test-Path .\node_modules\.cache)"
```

Restart web dev server:

```powershell
npm --workspace @reup-douyin/web run dev
```

Verify routes:

```powershell
powershell -NoProfile -Command "$root = Invoke-WebRequest -Uri http://localhost:3000 -UseBasicParsing -TimeoutSec 10; Write-Host 'GET / status:' $root.StatusCode; $route = Invoke-WebRequest -Uri http://localhost:3000/ops/extensions/douyin/capture-inbox -UseBasicParsing -TimeoutSec 10; Write-Host 'GET /ops/extensions/douyin/capture-inbox status:' $route.StatusCode"
```

Check whether `rimraf` was already available before adding any clean script:

```powershell
powershell -NoProfile -Command "Select-String -Path package.json,apps/web/package.json,package-lock.json -Pattern 'rimraf' -SimpleMatch -ErrorAction SilentlyContinue | ForEach-Object { $_.Path + ':' + $_.LineNumber + ': ' + $_.Line.Trim() }"
```

## Result

The cache cleanup removed only generated directories:

```txt
apps/web/.next exists after clean: False
.next exists after clean: False
node_modules/.cache exists after clean: False
```

The restarted web dev server rebuilt successfully. Verified routes returned HTTP 200:

```txt
GET / status: 200
GET /ops/extensions/douyin/capture-inbox status: 200
```

No `Cannot find module './3135.js'` error appeared after the clean restart.

## Files changed

- `docs/metadata-web-next-cache-missing-chunk-fix-log.md`

No source files, package files, lock files, backend APIs, or Douyin extension crawler logic were changed.

## Notes

- `rimraf` was not found in `package.json`, `apps/web/package.json`, or `package-lock.json`, so no `clean:web` script was added and no dependency was installed.
- The web-only dev server logs show expected proxy failures to `127.0.0.1:8000` when the backend API is not running. That is separate from the Next.js missing chunk issue. Use the root dev script if the full API-backed app is needed:

```powershell
npm run dev
```

## Manual steps if the missing chunk appears again

Run this from the repository root:

```powershell
npm run dev:stop
Remove-Item -Recurse -Force .\apps\web\.next -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\.next -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\node_modules\.cache -ErrorAction SilentlyContinue
npm --workspace @reup-douyin/web run dev
```

For the full local stack, use:

```powershell
npm run dev
```
