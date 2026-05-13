$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $root ".devflow"

if (-not (Test-Path $runtimeDir)) {
    New-Item -ItemType Directory -Path $runtimeDir | Out-Null
}

$existingJobs = Get-Job -Name "devflow-*" -ErrorAction SilentlyContinue
if ($existingJobs) {
    Write-Host "Existing DevFlow jobs found. Run .\scripts\stop-local.ps1 first if services are already running."
}

$paymentLog = Join-Path $runtimeDir "payment-api.log"
$orderLog = Join-Path $runtimeDir "order-api.log"
$frontendLog = Join-Path $runtimeDir "frontend.log"

$payment = Start-Job -Name "devflow-payment-api" -ScriptBlock {
    param($rootPath, $logPath)
    Set-Location $rootPath
    python .\services\payment-api\app\main.py *>> $logPath
} -ArgumentList $root, $paymentLog

$order = Start-Job -Name "devflow-order-api" -ScriptBlock {
    param($rootPath, $logPath)
    Set-Location $rootPath
    $env:PAYMENT_API_URL = "http://localhost:8080"
    python .\services\order-api\app\main.py *>> $logPath
} -ArgumentList $root, $orderLog

$frontend = Start-Job -Name "devflow-frontend" -ScriptBlock {
    param($rootPath, $logPath)
    Set-Location $rootPath
    python -m http.server 5173 --directory .\apps\frontend *>> $logPath
} -ArgumentList $root, $frontendLog

Start-Sleep -Seconds 2

Write-Host "DevFlow AI sample app started."
Write-Host "Frontend:    http://localhost:5173"
Write-Host "Order API:   http://localhost:8081/healthz"
Write-Host "Payment API: http://localhost:8080/healthz"
Write-Host "Logs:        $runtimeDir"
Write-Host "Jobs:        $($payment.Id), $($order.Id), $($frontend.Id)"
