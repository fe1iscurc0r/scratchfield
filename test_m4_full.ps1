# M4 Emotion + Reverse Channel Test
# Usage: .\test_m4_full.ps1 -Token "m4-test-token-12345"
param(
    [Parameter(Mandatory=$true)]
    [string]$Token,
    [string]$BaseUrl = "http://127.0.0.1:48911",
    [string]$ApiServerUrl = "http://127.0.0.1:8000"
)

$LanlanName = "YUI"
$headers = @{
    "Authorization" = "Bearer $Token"
    "Content-Type" = "application/json; charset=utf-8"
}

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "M4 Full Verification" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

# ========== Part A: Emotion Injection ==========
Write-Host ""
Write-Host "--- Part A: Emotion Injection ---" -ForegroundColor Yellow

$emotions = @(
    @{ emotion = "happy"; confidence = 0.9 },
    @{ emotion = "sad"; confidence = 0.8 },
    @{ emotion = "angry"; confidence = 0.7 }
)

$emotionOk = 0
foreach ($e in $emotions) {
    $body = '{"lanlan_name":"' + $LanlanName + '","emotion":"' + $e.emotion + '","confidence":' + $e.confidence + '}'
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    
    Write-Host "  Testing emotion=$($e.emotion) confidence=$($e.confidence)..." -NoNewline
    
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/api/lumo/emotion" -Method POST -Headers $headers -Body $bodyBytes -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-Host " OK" -ForegroundColor Green
            $emotionOk++
        }
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-Host " FAIL ($statusCode)" -ForegroundColor Red
    }
}

Write-Host "  Emotion: $emotionOk/$($emotions.Count) passed" -ForegroundColor $(if ($emotionOk -eq $emotions.Count) { 'Green' } else { 'Red' })

# ========== Part B: Reverse Event Channel ==========
Write-Host ""
Write-Host "--- Part B: Reverse Event Channel ---" -ForegroundColor Yellow

# Test 6 event types
$events = @(
    @{ type = "user_input"; payload = '{"event_type":"user_input","character":"YUI","neko_session":"abc123de","event_id":"evt-001-' + [Guid]::NewGuid().ToString().Substring(0,8) + '","timestamp":"' + (Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffZ") + '","text":"hello world"}' },
    @{ type = "asr_result"; payload = '{"event_type":"asr_result","character":"YUI","neko_session":"abc123de","event_id":"evt-002-' + [Guid]::NewGuid().ToString().Substring(0,8) + '","timestamp":"' + (Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffZ") + '","text":"recognized text","language":"zh"}' },
    @{ type = "tts_start"; payload = '{"event_type":"tts_start","character":"YUI","neko_session":"abc123de","event_id":"evt-003-' + [Guid]::NewGuid().ToString().Substring(0,8) + '","timestamp":"' + (Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffZ") + '","text_len":42}' },
    @{ type = "tts_end"; payload = '{"event_type":"tts_end","character":"YUI","neko_session":"abc123de","event_id":"evt-004-' + [Guid]::NewGuid().ToString().Substring(0,8) + '","timestamp":"' + (Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffZ") + '","duration_ms":1500}' },
    @{ type = "user_action"; payload = '{"event_type":"user_action","character":"YUI","neko_session":"abc123de","event_id":"evt-005-' + [Guid]::NewGuid().ToString().Substring(0,8) + '","timestamp":"' + (Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffZ") + '","action":"click"}' },
    @{ type = "error"; payload = '{"event_type":"error","character":"YUI","neko_session":"abc123de","event_id":"evt-006-' + [Guid]::NewGuid().ToString().Substring(0,8) + '","timestamp":"' + (Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffZ") + '","severity":"warn","error_type":"tts_timeout","message":"TTS synthesis timed out"}' }
)

# Reverse channel needs auth too
$apiHeaders = @{
    "Authorization" = "Bearer $Token"
    "Content-Type" = "application/json; charset=utf-8"
}

$eventOk = 0
foreach ($evt in $events) {
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($evt.payload)
    Write-Host "  Testing $($evt.type)..." -NoNewline
    
    try {
        $response = Invoke-WebRequest -Uri "$ApiServerUrl/api/lumo/event" -Method POST -Headers $apiHeaders -Body $bodyBytes -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            $respJson = [System.Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray())
            Write-Host " OK" -ForegroundColor Green
            $eventOk++
        }
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-Host " FAIL ($statusCode)" -ForegroundColor Red
        if ($_.Exception.Response) {
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
            Write-Host "    Response: $($reader.ReadToEnd())" -ForegroundColor Gray
        }
    }
}

Write-Host "  Events: $eventOk/$($events.Count) passed" -ForegroundColor $(if ($eventOk -eq $events.Count) { 'Green' } else { 'Red' })

# Test duplicate event_id
Write-Host "  Testing duplicate event_id..." -NoNewline
$dupPayload = $events[0].payload
$dupBytes = [System.Text.Encoding]::UTF8.GetBytes($dupPayload)
try {
    $response = Invoke-WebRequest -Uri "$ApiServerUrl/api/lumo/event" -Method POST -Headers $apiHeaders -Body $dupBytes -UseBasicParsing
    $respJson = [System.Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray())
    if ($respJson -match '"duplicated":true') {
        Write-Host " OK (duplicated=true)" -ForegroundColor Green
    } else {
        Write-Host " WARN (no duplicated flag)" -ForegroundColor Yellow
        Write-Host "    Response: $respJson" -ForegroundColor Gray
    }
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Write-Host " FAIL ($statusCode)" -ForegroundColor Red
}

# ========== Summary ==========
Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "  Emotion injection: $emotionOk/$($emotions.Count)" -ForegroundColor $(if ($emotionOk -eq $emotions.Count) { 'Green' } else { 'Red' })
Write-Host "  Reverse events:    $eventOk/$($events.Count)" -ForegroundColor $(if ($eventOk -eq $events.Count) { 'Green' } else { 'Red' })
Write-Host ""
Write-Host "Check NEKO frontend:" -ForegroundColor Yellow
Write-Host "  1. Did YUI's expression change for each emotion?"
Write-Host "  2. Check apiserver logs for audit entries"