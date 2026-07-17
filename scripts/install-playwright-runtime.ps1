$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

Push-Location (Join-Path $root "apps/api")
try {
    python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        throw "Playwright browser install failed with exit code $LASTEXITCODE"
    }
    Write-Host "Playwright Chromium runtime installed for apps/api Python environment."
}
finally {
    Pop-Location
}
