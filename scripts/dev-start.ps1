$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$devDir = Join-Path $root ".dev"
New-Item -ItemType Directory -Force -Path $devDir | Out-Null
$pidFile = Join-Path $devDir "pids.json"

if (Test-Path $pidFile) {
    $recordedProcesses = Get-Content $pidFile -Raw | ConvertFrom-Json
    $liveRecordedProcesses = @()
    foreach ($entry in $recordedProcesses) {
        $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            continue
        }
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($entry.pid)" -ErrorAction SilentlyContinue
        $commandLine = if ($processInfo) { [string]$processInfo.CommandLine } else { "" }
        if ($process.ProcessName -like "powershell*" -and $commandLine -like "*$($entry.working_directory)*" -and $commandLine -like "*$($entry.command)*") {
            $liveRecordedProcesses += $entry
        }
    }
    if ($liveRecordedProcesses.Count -gt 0) {
        Write-Error "Existing dev services are still running. Run scripts/dev-stop.ps1 before starting a new local stack."
        exit 1
    }
    Write-Host "Removing stale dev PID file: $pidFile"
    Remove-Item $pidFile -Force
}

$nextDir = Join-Path $root "apps/web/.next"
if (Test-Path $nextDir) {
    Write-Host "Clearing stale Next.js dev cache: $nextDir"
    Remove-Item -LiteralPath $nextDir -Recurse -Force
}

function Start-DevProcess {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$Command
    )
    $process = Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$WorkingDirectory'; $Command"
    ) -PassThru
    [pscustomobject]@{ name = $Name; pid = $process.Id; working_directory = $WorkingDirectory; command = $Command }
}

$processes = @()
$processes += Start-DevProcess "api" (Join-Path $root "apps/api") "uvicorn src.main:app --reload"
$processes += Start-DevProcess "web" (Join-Path $root "apps/web") "npm run dev"
$processes += Start-DevProcess "worker" (Join-Path $root "apps/worker") "python src/main.py"

$processes | ConvertTo-Json | Set-Content -Path $pidFile -Encoding utf8
Write-Host "Started dev services. PID file: $pidFile"
$processes | Format-Table -AutoSize
