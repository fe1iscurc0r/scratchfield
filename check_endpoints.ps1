# Check if M4 endpoints exist
$BaseUrl = "http://127.0.0.1:48911"

Write-Host "Checking M4 endpoints..." -ForegroundColor Cyan
Write-Host ""

# Check 1: Try the debug endpoint directly
Write-Host "1. Testing POST /api/lumo/speak/test..." -ForegroundColor Yellow
try {
    $body = '{"lanlan_name":"test","text":"test"}'
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/lumo/speak/test" -Method POST -ContentType "application/json" -Body $body -ErrorAction Stop
    Write-Host "   Status: $($response.StatusCode) - Endpoint EXISTS!" -ForegroundColor Green
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 404) {
        Write-Host "   Status: 404 - Endpoint DOES NOT EXIST" -ForegroundColor Red
        Write-Host "   NEKO was NOT restarted after code changes!" -ForegroundColor Red
    } else {
        Write-Host "   Status: $statusCode - Endpoint exists but got error" -ForegroundColor Yellow
        Write-Host "   $($_.Exception.Message)"
    }
}

Write-Host ""

# Check 2: Check if /api/lumo/speak exists (auth required)
Write-Host "2. Testing POST /api/lumo/speak (auth required)..." -ForegroundColor Yellow
try {
    $body = '{"lanlan_name":"test","text":"test"}'
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/lumo/speak" -Method POST -ContentType "application/json" -Body $body -ErrorAction Stop
    Write-Host "   Status: $($response.StatusCode)" -ForegroundColor Green
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 404) {
        Write-Host "   Status: 404 - Endpoint DOES NOT EXIST" -ForegroundColor Red
    } elseif ($statusCode -eq 401) {
        Write-Host "   Status: 401 - Endpoint EXISTS (needs auth)" -ForegroundColor Green
    } else {
        Write-Host "   Status: $statusCode" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "If both show 404, you MUST restart NEKO!" -ForegroundColor Red