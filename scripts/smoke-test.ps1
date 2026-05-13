$ErrorActionPreference = "Stop"

function Invoke-Json {
    param(
        [Parameter(Mandatory = $true)] [string] $Method,
        [Parameter(Mandatory = $true)] [string] $Uri,
        [object] $Body = $null
    )

    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $Uri
    }

    return Invoke-RestMethod -Method $Method -Uri $Uri -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 10)
}

Write-Host "Checking payment-api health..."
Invoke-Json -Method Get -Uri "http://localhost:8080/healthz" | ConvertTo-Json -Depth 10

Write-Host "Checking order-api health..."
Invoke-Json -Method Get -Uri "http://localhost:8081/healthz" | ConvertTo-Json -Depth 10

Write-Host "Creating successful order..."
$order = Invoke-Json -Method Post -Uri "http://localhost:8081/api/orders" -Body @{
    customer_id = "cust_smoke"
    items = @(
        @{
            sku = "platform-course"
            quantity = 1
            price = 1499
        }
    )
}
$order | ConvertTo-Json -Depth 10

Write-Host "Breaking payment service..."
Invoke-Json -Method Post -Uri "http://localhost:8080/admin/break" | ConvertTo-Json -Depth 10

Write-Host "Creating order while payment is broken. A 502 response is expected."
try {
    Invoke-Json -Method Post -Uri "http://localhost:8081/api/orders" -Body @{
        customer_id = "cust_broken"
        items = @(
            @{
                sku = "platform-course"
                quantity = 1
                price = 1499
            }
        )
    } | ConvertTo-Json -Depth 10
} catch {
    Write-Host $_.Exception.Message
}

Write-Host "Recovering payment service..."
Invoke-Json -Method Post -Uri "http://localhost:8080/admin/recover" | ConvertTo-Json -Depth 10

Write-Host "Smoke test completed."
