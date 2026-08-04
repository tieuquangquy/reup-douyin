$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$devDir = Join-Path $root ".dev"
New-Item -ItemType Directory -Force -Path $devDir | Out-Null
$pidFile = Join-Path $devDir "pids.json"

if (Test-Path $pidFile) {
    $pidFileTimestampUtc = (Get-Item $pidFile).LastWriteTimeUtc
    $recordedProcesses = Get-Content $pidFile -Raw | ConvertFrom-Json
    $liveRecordedProcesses = @()
    foreach ($entry in $recordedProcesses) {
        $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            continue
        }
        $expectedStartUtc = if ($entry.PSObject.Properties.Name -contains "started_at_utc") {
            [datetime]::Parse([string]$entry.started_at_utc).ToUniversalTime()
        } else {
            $pidFileTimestampUtc
        }
        $startDeltaSeconds = [Math]::Abs(($process.StartTime.ToUniversalTime() - $expectedStartUtc).TotalSeconds)
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($entry.pid)" -ErrorAction SilentlyContinue
        $commandLine = if ($processInfo) { [string]$processInfo.CommandLine } else { "" }
        $workingDirectoryMatches = -not $commandLine -or $commandLine -like "*$($entry.working_directory)*"
        if ($process.ProcessName -like "powershell*" -and $startDeltaSeconds -le 3600 -and $workingDirectoryMatches) {
            $liveRecordedProcesses += $entry
        }
    }
    if ($liveRecordedProcesses.Count -gt 0) {
        Write-Host "Dev services are already running. No duplicate processes were started." -ForegroundColor Green
        $liveRecordedProcesses | Select-Object name, pid, working_directory | Format-Table -AutoSize
        Write-Host "Web:      http://localhost:3000"
        Write-Host "API docs: http://localhost:8000/docs"
        Write-Host "Use scripts/dev-stop.ps1 before a full restart."
        exit 0
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
    ) -WindowStyle Hidden -PassThru
    [pscustomobject]@{
        name = $Name
        pid = $process.Id
        started_at_utc = $process.StartTime.ToUniversalTime().ToString("o")
        working_directory = $WorkingDirectory
        command = $Command
    }
}

# One worker runs one job at a time, so a long render stalls downloads and translation
# behind it. Extra workers pick up the CPU/network stages; the GPU budget
# (GPU_MAX_CONCURRENT_RUNNING) still keeps a single heavy job on the card.
$workerCount = 2
if ($env:WORKER_COUNT) {
    $parsed = 0
    if ([int]::TryParse($env:WORKER_COUNT, [ref]$parsed) -and $parsed -ge 1) {
        $workerCount = $parsed
    }
}

$processes = @()
$processes += Start-DevProcess "api" (Join-Path $root "apps/api") "uvicorn src.main:app --reload"
$processes += Start-DevProcess "web" (Join-Path $root "apps/web") "npm run dev"
for ($i = 1; $i -le $workerCount; $i++) {
    # Keep the worker host alive if Python exits unexpectedly. Durable jobs stay in
    # PostgreSQL, so the restarted worker safely resumes/claims pending work.
    $workerCommand = (
        "`$env:WORKER_ID='local-worker-$i'; " +
        "while (`$true) { " +
        "python src/main.py; " +
        "Write-Warning 'Worker process exited; restarting in 3 seconds.'; " +
        "Start-Sleep -Seconds 3 " +
        "}"
    )
    $processes += Start-DevProcess "worker-$i" (Join-Path $root "apps/worker") $workerCommand
}

$fixedTunnelConfigPath = Join-Path $devDir "fixed-tunnel.json"
if (Test-Path $fixedTunnelConfigPath) {
    $fixedTunnel = Get-Content $fixedTunnelConfigPath -Raw | ConvertFrom-Json
    $cloudflaredCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
    $cloudflaredPath = if ($cloudflaredCommand) {
        $cloudflaredCommand.Source
    } else {
        "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    }
    if (-not (Test-Path $cloudflaredPath)) {
        Write-Warning "Fixed tunnel is configured but cloudflared is not installed: $cloudflaredPath"
    } elseif (-not $fixedTunnel.tunnel_id -or -not $fixedTunnel.origin_url) {
        Write-Warning "Fixed tunnel config must include tunnel_id and origin_url: $fixedTunnelConfigPath"
    } else {
        $tunnelId = [string]$fixedTunnel.tunnel_id
        $originUrl = [string]$fixedTunnel.origin_url
        $tunnelCommand = (
            "while (`$true) { " +
            "& '$cloudflaredPath' tunnel --no-autoupdate run --url '$originUrl' '$tunnelId'; " +
            "Write-Warning 'Cloudflare Tunnel exited; restarting in 3 seconds.'; " +
            "Start-Sleep -Seconds 3 " +
            "}"
        )
        $processes += Start-DevProcess "fixed-tunnel" $root $tunnelCommand
    }
}

$processes | ConvertTo-Json | Set-Content -Path $pidFile -Encoding utf8
Write-Host "Started dev services. PID file: $pidFile"
$processes | Format-Table -AutoSize
