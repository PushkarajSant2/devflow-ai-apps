$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $root ".devflow"

$jobs = Get-Job -Name "devflow-*" -ErrorAction SilentlyContinue

if (-not $jobs) {
    Write-Host "No DevFlow AI jobs found in this PowerShell session."
    exit 0
}

foreach ($job in $jobs) {
    Stop-Job -Job $job -ErrorAction SilentlyContinue
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped $($job.Name)"
}

Write-Host "DevFlow AI sample app stopped."
