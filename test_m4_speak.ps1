# M4 Speak Test - Simple and correct
# Usage: .\test_m4_speak.ps1 -Token "your-token"
param(
    [Parameter(Mandatory=$true)]
    [string]$Token,
    [string]$BaseUrl = "http://127.0.0.1:48911",
    [string]$LanlanName = "YUI"
)

Write-Host "M4 Speak Test" -ForegroundColor Cyan
Write-Host "  Character: $LanlanName" -ForegroundColor Green
Write-Host ""

# Build JSON body manually to ensure correct UTF-8
$jsonBody = '{"lanlan_name":"' + $LanlanName + '","text":"\u4f60\u597d\uff0c\u8fd9\u662f M4 speak \u6d4b\u8bd5"}'
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)

$headers = @{
    "Authorization" = "Bearer $Token"
}

Write-Host "Sending POST to /api/lumo/speak..." -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/lumo/speak" -Method POST -Headers $headers -ContentType "application/json; charset=utf-8" -Body $bodyBytes -UseBasicParsing
    Write-Host ""
    Write-Host "SUCCESS! (HTTP $($response.StatusCode))" -ForegroundColor Green
    
    $respBytes = $response.RawContentStream.ToArray()
    $respJson = [System.Text.Encoding]::UTF8.GetString($respBytes)
    Write-Host "Response: $respJson" -ForegroundColor White
    
    Write-Host ""
    Write-Host "CHECK NEKO:" -ForegroundColor Yellow
    Write-Host "  1. TTS audio played?"
    Write-Host "  2. Subtitle showed?"
    Write-Host "  3. Chat message showed?"
    Write-Host "  4. No LLM triggered?"
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Write-Host ""
    Write-Host "Error (HTTP $statusCode)" -ForegroundColor Red
    
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        $errBody = $reader.ReadToEnd()
        Write-Host "Response: $errBody" -ForegroundColor White
    }
    
    if ($statusCode -eq 401) {
        Write-Host ""
        Write-Host "Auth failed. Token mismatch." -ForegroundColor Yellow
        Write-Host "Make sure: $env:LUMO_PROXY_TOKEN = '" -NoNewline
        Write-Host $Token -NoNewline -ForegroundColor Cyan
        Write-Host "' before starting NEKO"
    } elseif ($statusCode -eq 404) {
        Write-Host ""
        Write-Host "Character '$LanlanName' not found in queue." -ForegroundColor Yellow
        Write-Host "Make sure NEKO frontend is open (WebSocket connected)." -ForegroundColor Yellow
    }
}