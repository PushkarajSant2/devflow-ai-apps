$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $root ".devflow-verify"
$resolvedRoot = [System.IO.Path]::GetFullPath($root)
$resolvedRuntimeDir = [System.IO.Path]::GetFullPath($runtimeDir)

if (-not $resolvedRuntimeDir.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove verification directory outside project root: $resolvedRuntimeDir"
}

if (Test-Path $runtimeDir) {
    Remove-Item -Path $runtimeDir -Recurse -Force
}
New-Item -ItemType Directory -Path $runtimeDir | Out-Null

$paymentLog = Join-Path $runtimeDir "payment-api.log"
$orderLog = Join-Path $runtimeDir "order-api.log"
$frontendLog = Join-Path $runtimeDir "frontend.log"

$jobs = @()

try {
    $jobs += Start-Job -Name "devflow-verify-payment-api" -ScriptBlock {
        param($rootPath, $logPath)
        Set-Location $rootPath
        python .\services\payment-api\app\main.py *>> $logPath
    } -ArgumentList $root, $paymentLog

    Start-Sleep -Milliseconds 700

    $jobs += Start-Job -Name "devflow-verify-order-api" -ScriptBlock {
        param($rootPath, $logPath)
        Set-Location $rootPath
        $env:PAYMENT_API_URL = "http://localhost:8080"
        python .\services\order-api\app\main.py *>> $logPath
    } -ArgumentList $root, $orderLog

    $jobs += Start-Job -Name "devflow-verify-frontend" -ScriptBlock {
        param($rootPath, $logPath)
        Set-Location $rootPath
        python -m http.server 5173 --directory .\apps\frontend *>> $logPath
    } -ArgumentList $root, $frontendLog

    Start-Sleep -Seconds 2

    & (Join-Path $PSScriptRoot "smoke-test.ps1")
} finally {
    foreach ($job in $jobs) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
}
