# List available characters
$BaseUrl = "http://127.0.0.1:48911"

# Try to get character list
try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/character-card/list" -Method GET
    Write-Host "Available characters:" -ForegroundColor Green
    $response | ConvertTo-Json
} catch {
    Write-Host "Error listing characters: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    
    # Try alternative endpoint
    Write-Host "Trying alternative endpoints..." -ForegroundColor Yellow
    try {
        $response2 = Invoke-RestMethod -Uri "$BaseUrl/api/characters" -Method GET
        Write-Host "Characters:" -ForegroundColor Green
        $response2 | ConvertTo-Json
    } catch {
        Write-Host "Still failed" -ForegroundColor Red
    }
}