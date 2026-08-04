#Requires -Version 5.1
<#
.SYNOPSIS
  Build (if needed) and run local PaddleOCR API on http://127.0.0.1:8080

.DESCRIPTION
  Same /predict contract as Cloud Run. Default engine=auto:
  classic on low Docker RAM, VL-1.6 when RAM is enough.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File deploy/hf-paddle-ocr/run_local.ps1
  powershell -ExecutionPolicy Bypass -File deploy/hf-paddle-ocr/run_local.ps1 -Engine classic
  powershell -ExecutionPolicy Bypass -File deploy/hf-paddle-ocr/run_local.ps1 -Engine vl16
#>
param(
    [switch]$Rebuild,
    [string]$ImageName = "paddle-ocr-api",
    [string]$ContainerName = "paddle-ocr-local",
    [int]$Port = 8080,
    [ValidateSet("auto", "vl16", "classic")]
    [string]$Engine = "auto",
    [string]$VlDevice = "cpu",
    [switch]$ForceVl
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Test-DockerReady {
    docker info 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker is not running. Start Docker Desktop, then re-run this script."
    }
}

Test-DockerReady

$existing = docker ps -aq --filter "name=^/${ContainerName}$"
if ($existing) {
    Write-Host "Removing existing container $ContainerName ..."
    docker rm -f $ContainerName | Out-Null
}

$hasImage = docker images -q $ImageName
if ($Rebuild -or -not $hasImage) {
    Write-Host "Building image $ImageName (first build can take several minutes) ..."
    docker build -t $ImageName .
    if ($LASTEXITCODE -ne 0) { throw "docker build failed" }
} else {
    Write-Host "Using existing image $ImageName (pass -Rebuild to force)."
}

Write-Host "Starting $ContainerName on port $Port (engine=$Engine device=$VlDevice forceVl=$ForceVl) ..."
$envArgs = @(
    "-e", "OCR_PADDLE_ENGINE=$Engine",
    "-e", "OCR_PADDLE_VL_DEVICE=$VlDevice",
    # Keep MKLDNN off: this image's Paddle 3.3.x crashes (PIR↔oneDNN) when enabled.
    "-e", "OCR_PADDLE_ENABLE_MKLDNN=0"
)
if ($ForceVl -or $Engine -eq "vl16") {
    $envArgs += @("-e", "OCR_PADDLE_VL_INPROCESS=1")
}
if ($Engine -eq "vl16") {
    # Strict VL QA: never silently switch to classic mid-session.
    $envArgs += @("-e", "OCR_PADDLE_NO_FALLBACK=1")
}
docker run -d --name $ContainerName -p "${Port}:8080" `
    @envArgs `
    --restart unless-stopped $ImageName | Out-Null
if ($LASTEXITCODE -ne 0) { throw "docker run failed" }

$health = "http://127.0.0.1:${Port}/health"
Write-Host "Waiting for $health ..."
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri $health -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -eq 200) {
            $ok = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 3
    }
}

if (-not $ok) {
    Write-Host "Container logs:"
    docker logs --tail 80 $ContainerName
    throw "Health check failed. Container may still be loading models. Retry: $health"
}

try {
    $info = Invoke-RestMethod -Uri $health -TimeoutSec 10
    Write-Host ("  requested={0} resolved={1} ram_gb={2}" -f `
        $info.ocr_paddle_engine_requested, `
        $info.ocr_paddle_engine_resolved, `
        $info.ocr_paddle_ram_gb)
} catch {
    # health shape may differ on older image until first restart with new app.py
}

Write-Host ""
Write-Host "OK: local PaddleOCR is up."
Write-Host "  Health : $health"
Write-Host "  Predict: http://127.0.0.1:${Port}/predict"
Write-Host "  Env    : OCR_ENDPOINT_URL=http://127.0.0.1:${Port}/predict"
Write-Host "  Stop   : docker stop $ContainerName"
Write-Host "Restart API/worker after changing OCR_ENDPOINT_URL."
