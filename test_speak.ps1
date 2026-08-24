# M4 Speak Test - Auto detect token
param(
    [string]$LanlanName = "yui",
    [string]$Text = "Hello, this is M4 speak test",
    [string]$BaseUrl = "http://127.0.0.1:48911"
)

# Try to get token from common locations
$token = ""

# Method 1: Try environment variable
$token = $env:LUMO_PROXY_TOKEN

# Method 2: Try reading from a token file
$tokenFile = "$env:TEMP\lumo_proxy_token.txt"
if (-not $token -and (Test-Path $tokenFile)) {
    $token = (Get-Content $tokenFile -ErrorAction SilentlyContinue).Trim()
}

if (-not $token) {
    Write-Host "Error: LUMO_PROXY_TOKEN not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please run this in the PowerShell window that started NEKO:" -ForegroundColor Yellow
    Write-Host '  $env:LUMO_PROXY_TOKEN'
    Write-Host ""
    Write-Host "Then pass the token to this script:" -ForegroundColor Yellow
    Write-Host '.\test_speak.ps1 -Token "your_token"'
    exit 1
}

$shortToken = $token.Substring(0, [Math]::Min(8, $token.Length))
Write-Host "Found Token: $shortToken..." -ForegroundColor Gray

$body = @{
    lanlan_name = $LanlanName
    text = $Text
} | ConvertTo-Json -Compress

$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
}

Write-Host "Sending request to $BaseUrl/api/lumo/speak ..." -ForegroundColor Cyan
Write-Host "  Character: $LanlanName"
Write-Host "  Text: $Text"
Write-Host ""

try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/lumo/speak" -Method POST -Headers $headers -Body $body
    Write-Host "Success!" -ForegroundColor Green
    Write-Host "Response:" -ForegroundColor Yellow
    $response | ConvertTo-Json
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Write-Host "Error (HTTP $statusCode):" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host $responseBody
    } else {
        Write-Host $_.Exception.Message
    }
    
    if ($statusCode -eq 401) {
        Write-Host ""
        Write-Host "Tip: Authentication failed, check your LUMO_PROXY_TOKEN" -ForegroundColor Yellow
    } elseif ($statusCode -eq 404) {
        Write-Host ""
        Write-Host "Tip: Character '$LanlanName' not found" -ForegroundColor Yellow
    }
}