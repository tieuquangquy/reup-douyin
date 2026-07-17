$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location (Join-Path $root "apps/api")
try {
    alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "alembic upgrade head failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
