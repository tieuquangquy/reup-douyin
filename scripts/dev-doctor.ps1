param(
    [string]$ApiUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message
    )
    $checks.Add([pscustomobject]@{ Name = $Name; Status = $Status; Message = $Message }) | Out-Null
}

function Test-CommandExists {
    param([string]$CommandName)
    return $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

Set-Location $root
Add-Check "repo root" "PASS" "Using $root"

if (Test-Path "AGENTS.md") {
    Add-Check "AGENTS.md" "PASS" "Repo operating rules found."
} else {
    Add-Check "AGENTS.md" "FAIL" "AGENTS.md is missing."
}

foreach ($envFile in @("apps/api/.env", "apps/web/.env.local", "apps/worker/.env")) {
    if (Test-Path $envFile) {
        Add-Check $envFile "PASS" "Environment file exists."
    } else {
        Add-Check $envFile "WARN" "Missing; copy from the matching .env.example before full local runs."
    }
}

foreach ($command in @("python", "node", "npm")) {
    if (Test-CommandExists $command) {
        Add-Check $command "PASS" "$command is available."
    } else {
        Add-Check $command "FAIL" "$command is not available on PATH."
    }
}

if ((Test-Path "apps/web/node_modules") -or (Test-Path "node_modules")) {
    Add-Check "web dependencies" "PASS" "Node dependencies exist for the npm workspace."
} else {
    Add-Check "web dependencies" "WARN" "Node dependencies are missing; run npm install from the repo root."
}

if (Test-CommandExists "ffmpeg") {
    Add-Check "ffmpeg" "PASS" "ffmpeg is available for render/probe flows."
} else {
    Add-Check "ffmpeg" "WARN" "ffmpeg is missing; render flows will fail until installed."
}

$storageRoot = Join-Path $root "apps/api/data/storage"
try {
    New-Item -ItemType Directory -Force -Path $storageRoot | Out-Null
    $probeFile = Join-Path $storageRoot ".doctor-write-check"
    "ok" | Set-Content -Path $probeFile -Encoding utf8
    Remove-Item -Path $probeFile -Force
    Add-Check "storage root" "PASS" "$storageRoot is writable."
} catch {
    Add-Check "storage root" "FAIL" "Cannot write to ${storageRoot}: $($_.Exception.Message)"
}

Push-Location "apps/api"
try {
    python -c "import fastapi, sqlalchemy, alembic, playwright.sync_api" *> $null
    if ($LASTEXITCODE -eq 0) {
        Add-Check "api dependencies" "PASS" "FastAPI, SQLAlchemy, Alembic, and Playwright import successfully."
    } else {
        Add-Check "api dependencies" "WARN" "API dependencies are not installed in the active Python environment."
    }
} catch {
    Add-Check "api dependencies" "WARN" "Could not import API dependencies: $($_.Exception.Message)"
}

try {
    python -c "import asyncio; policy=getattr(asyncio,'WindowsProactorEventLoopPolicy',None); policy and asyncio.set_event_loop_policy(policy()); from playwright.sync_api import sync_playwright; p = sync_playwright().start(); path = p.chromium.executable_path; print(path); p.stop()" *> $null
    if ($LASTEXITCODE -eq 0) {
        Add-Check "playwright browser binary" "PASS" "Playwright Chromium executable is available."
    } else {
        Add-Check "playwright browser binary" "WARN" "Playwright Chromium binary is missing. Run npm run playwright:install."
    }
} catch {
    Add-Check "playwright browser binary" "WARN" "Playwright runtime check failed: $($_.Exception.Message)"
}

try {
    python -c "import asyncio; policy=getattr(asyncio,'WindowsProactorEventLoopPolicy',None); policy and asyncio.set_event_loop_policy(policy()); from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop()" *> $null
    if ($LASTEXITCODE -eq 0) {
        Add-Check "playwright launch" "PASS" "Playwright Chromium launch smoke passed in API runtime."
    } else {
        Add-Check "playwright launch" "WARN" "Playwright Chromium launch failed. Verify local browser policy/runtime dependencies."
    }
} catch {
    Add-Check "playwright launch" "WARN" "Playwright Chromium launch check failed: $($_.Exception.Message)"
}
Pop-Location

Push-Location "apps/api"
try {
    python -c "from sqlalchemy import text; from src.db.session import get_engine; engine = get_engine(); conn = engine.connect(); print(conn.execute(text('select 1')).scalar()); conn.close()" *> $null
    if ($LASTEXITCODE -eq 0) {
        Add-Check "database" "PASS" "DATABASE_URL is reachable."
    } else {
        Add-Check "database" "FAIL" "DATABASE_URL is not reachable; start PostgreSQL and verify apps/api/.env."
    }
} catch {
    Add-Check "database" "FAIL" "DATABASE_URL is not reachable: $($_.Exception.Message)"
}
Pop-Location

Push-Location "apps/api"
try {
    python -c "from src.main import app" *> $null
    if ($LASTEXITCODE -eq 0) {
        Add-Check "api app import" "PASS" "FastAPI app imports successfully."
    } else {
        Add-Check "api app import" "FAIL" "FastAPI app import failed in the active Python environment."
    }
} catch {
    Add-Check "api app import" "FAIL" "Could not import FastAPI app: $($_.Exception.Message)"
}
Pop-Location

Push-Location "apps/worker"
try {
    python -c "import sys, runpy; sys.path.insert(0, 'src'); runpy.run_path('src/main.py', run_name='__worker_import_check__')" *> $null
    if ($LASTEXITCODE -eq 0) {
        Add-Check "worker import" "PASS" "Worker entrypoint imports successfully."
    } else {
        Add-Check "worker import" "FAIL" "Worker entrypoint import failed in the active Python environment."
    }
} catch {
    Add-Check "worker import" "FAIL" "Could not import worker entrypoint: $($_.Exception.Message)"
}
Pop-Location

$apiEnvPath = Join-Path $root "apps/api/.env"
$facebookTokenInApiEnv = $false
if (Test-Path $apiEnvPath) {
    $facebookTokenInApiEnv = [bool](Select-String -Path $apiEnvPath -Pattern "^\s*FACEBOOK_PAGE_ACCESS_TOKEN\s*=\s*.+" -Quiet)
}
if ($env:FACEBOOK_PAGE_ACCESS_TOKEN -or $facebookTokenInApiEnv) {
    Add-Check "facebook token" "PASS" "FACEBOOK_PAGE_ACCESS_TOKEN is configured for real publish attempts."
} else {
    Add-Check "facebook token" "WARN" "FACEBOOK_PAGE_ACCESS_TOKEN is not set in the process or apps/api/.env; only required for real Facebook Page/Reels publish attempts."
}

try {
    $response = Invoke-WebRequest -Uri "$ApiUrl/docs" -Method GET -TimeoutSec 2 -UseBasicParsing
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        Add-Check "api server" "PASS" "$ApiUrl responds."
    } else {
        Add-Check "api server" "WARN" "$ApiUrl returned HTTP $($response.StatusCode)."
    }
} catch {
    Add-Check "api server" "WARN" "$ApiUrl is not running or not reachable. Start it with scripts/dev-start.ps1."
}

$checks | Format-Table -AutoSize
$failCount = @($checks | Where-Object { $_.Status -eq "FAIL" }).Count
$warnCount = @($checks | Where-Object { $_.Status -eq "WARN" }).Count
Write-Host ""
Write-Host "Doctor summary: $failCount fail, $warnCount warn, $($checks.Count) total checks."

if ($failCount -gt 0) {
    exit 1
}
