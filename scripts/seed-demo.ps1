Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location "$PSScriptRoot\..\apps\api"
try {
  python -m src.db.seed_demo
  if ($LASTEXITCODE -ne 0) {
    throw "seed demo failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
