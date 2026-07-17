Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
  param(
    [scriptblock]$Command,
    [string]$Label
  )
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE"
  }
}

Write-Host "== Python compile =="
Invoke-CheckedCommand { python -m compileall apps\api apps\worker } "Python compile"

Write-Host "== API unit tests =="
Push-Location apps\api
try {
  Invoke-CheckedCommand { python -c "from src.main import app; print(app.title)" } "API app import"
  Invoke-CheckedCommand { python -m unittest discover tests } "API unit tests"
  Invoke-CheckedCommand { python -c "import asyncio; policy=getattr(asyncio,'WindowsProactorEventLoopPolicy',None); policy and asyncio.set_event_loop_policy(policy()); from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop(); print('playwright launch ok')" } "Playwright runtime smoke"
}
finally {
  Pop-Location
}

Write-Host "== Worker import =="
Push-Location apps\worker
try {
  Invoke-CheckedCommand { python -c "import sys, runpy; sys.path.insert(0, 'src'); runpy.run_path('src/main.py', run_name='__worker_import_check__'); print('worker import ok')" } "Worker app import"
}
finally {
  Pop-Location
}

Write-Host "== Web tests and typecheck =="
Push-Location apps\web
try {
  Invoke-CheckedCommand { npm test } "Web tests"
  Invoke-CheckedCommand { npm run typecheck } "Web typecheck"
}
finally {
  Pop-Location
}

Write-Host "Smoke check completed."
Write-Host "Tip: run scripts/dev-doctor.ps1 for environment and dependency checks."
Write-Host "Tip: run npm --workspace @reup-douyin/web run build before release packaging."
