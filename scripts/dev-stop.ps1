$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$pidFile = Join-Path $root ".dev/pids.json"

if (-not (Test-Path $pidFile)) {
    Write-Host "No PID file found at $pidFile"
    exit 0
}

$processes = Get-Content $pidFile -Raw | ConvertFrom-Json

function Stop-ProcessTree {
    param([int]$RootPid)
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $RootPid" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree -RootPid ([int]$child.ProcessId)
    }
    Stop-Process -Id $RootPid -ErrorAction SilentlyContinue
}

foreach ($entry in $processes) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Write-Host "$($entry.name) is already stopped."
        continue
    }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($entry.pid)" -ErrorAction SilentlyContinue
    $commandLine = if ($processInfo) { [string]$processInfo.CommandLine } else { "" }
    if ($process.ProcessName -notlike "powershell*" -or $commandLine -notlike "*$($entry.working_directory)*" -or $commandLine -notlike "*$($entry.command)*") {
        Write-Warning "Skipping $($entry.name) pid=$($entry.pid): process no longer matches the recorded dev command."
        continue
    }
    Write-Host "Stopping $($entry.name) process tree pid=$($entry.pid)"
    Stop-ProcessTree -RootPid ([int]$entry.pid)
}

Remove-Item $pidFile -Force
Write-Host "Dev services stopped."
