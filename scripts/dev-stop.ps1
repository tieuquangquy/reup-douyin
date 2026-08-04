$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$pidFile = Join-Path $root ".dev/pids.json"

if (-not (Test-Path $pidFile)) {
    Write-Host "No PID file found at $pidFile"
    exit 0
}

$processes = Get-Content $pidFile -Raw | ConvertFrom-Json
$pidFileTimestampUtc = (Get-Item $pidFile).LastWriteTimeUtc
$unsafeEntries = @()

function Stop-ProcessTree {
    param([int]$RootPid)
    if (-not (Get-Process -Id $RootPid -ErrorAction SilentlyContinue)) {
        return
    }

    # Get-CimInstance can be unavailable to a non-elevated Windows operator. When
    # that happens a recursive CIM walk silently misses node/python/cloudflared
    # children and the next start binds to the stale process. taskkill /T uses the
    # native process tree and does not require querying Win32_Process first.
    & taskkill.exe /PID $RootPid /T /F | Out-Host
    # taskkill can report SUCCESS a few milliseconds before PowerShell's process
    # table drops the wrapper. Give Windows a bounded grace period so a clean
    # shutdown is not misreported as a failure and does not leave the stack
    # half-stopped.
    $deadline = [datetime]::UtcNow.AddSeconds(3)
    while (
        (Get-Process -Id $RootPid -ErrorAction SilentlyContinue) -and
        [datetime]::UtcNow -lt $deadline
    ) {
        Start-Sleep -Milliseconds 100
    }
    if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $RootPid -ErrorAction SilentlyContinue)) {
        # Sandboxed/non-interactive shells can reject taskkill's tree traversal even
        # when the operator owns the wrapper. Still terminate the verified wrapper;
        # an interactive Windows run normally succeeds through taskkill above.
        Stop-Process -Id $RootPid -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $RootPid -Timeout 2 -ErrorAction SilentlyContinue
    }
    if (Get-Process -Id $RootPid -ErrorAction SilentlyContinue) {
        throw "Failed to stop process tree rooted at pid=$RootPid."
    }
}

foreach ($entry in $processes) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Write-Host "$($entry.name) is already stopped."
        continue
    }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($entry.pid)" -ErrorAction SilentlyContinue
    $commandLine = if ($processInfo) { [string]$processInfo.CommandLine } else { "" }
    $expectedStartUtc = if ($entry.PSObject.Properties.Name -contains "started_at_utc") {
        [datetime]::Parse([string]$entry.started_at_utc).ToUniversalTime()
    } else {
        $pidFileTimestampUtc
    }
    $startDeltaSeconds = [Math]::Abs(($process.StartTime.ToUniversalTime() - $expectedStartUtc).TotalSeconds)
    $workingDirectoryMatches = -not $commandLine -or $commandLine -like "*$($entry.working_directory)*"
    if ($process.ProcessName -notlike "powershell*" -or $startDeltaSeconds -gt 3600 -or -not $workingDirectoryMatches) {
        Write-Warning "Skipping $($entry.name) pid=$($entry.pid): PID identity no longer matches the recorded dev process."
        $unsafeEntries += $entry
        continue
    }
    Write-Host "Stopping $($entry.name) process tree pid=$($entry.pid)"
    Stop-ProcessTree -RootPid ([int]$entry.pid)
}

if ($unsafeEntries.Count -gt 0) {
    Write-Error "Some recorded PIDs could not be verified. PID file was kept to prevent duplicate dev services."
    exit 1
}

Remove-Item $pidFile -Force
Write-Host "Dev services stopped."
