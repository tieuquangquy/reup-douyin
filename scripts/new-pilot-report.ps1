param(
    [string]$Name = (Get-Date -Format "yyyy-MM-dd"),
    [string]$OutputRoot = "pilot-reports"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$target = Join-Path $root (Join-Path $OutputRoot $Name)
$templateRoot = Join-Path $root "docs/templates"

New-Item -ItemType Directory -Force -Path $target | Out-Null

$templates = @(
    "pilot-session-template.md",
    "daily-operator-log-template.md",
    "bug-bash-report-template.md",
    "issue-triage-template.md",
    "issue-template.md"
)

foreach ($template in $templates) {
    Copy-Item (Join-Path $templateRoot $template) (Join-Path $target $template) -Force
}

Write-Host "Created pilot report skeleton: $target"
Get-ChildItem $target | Select-Object Name,Length | Format-Table -AutoSize
