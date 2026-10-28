# 遗留生成器（工单271 T3 / P0-20）：产物 wt-overwatch-v6/js/main.js 已入库。
# 要改行为请改这个源并重跑，别直接编辑产物 —— 重跑会把它盖掉。
# 输出路径不再写死在别人机器上：必须显式给 -OutPath。
param(
    [Parameter(Mandatory)][string]$OutPath,
    [switch]$Overwrite
)

$lines = @(
'/* WT Overwatch v6 --- 坦歼火控系统 弹道引擎 */',
'const R2M = 6400 / (2 * Math.PI);',
'const GRAV = 9.81;',
'const AIR_DENSITY = 1.225;',
'const PEN_DISTS = Object.freeze([0, 500, 1000, 1500, 2000]);',
'const GRID_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";',
'const DRAG_MODEL = true;',
'const DRAG_STEP = 0.02;',
'const DRAG_CD = 0.25;',
'const MAX_ANGLE = 0.5;',
'const BISECT_ITERS = 24;',
'const DRAG_MACH = true;',
'const SOUND_SPEED = 340;'
)
# 先落到临时件，再与现有产物比对：只有「确实不同」才要求 -Overwrite（同版本重跑不会被自己卡住），
# 覆盖前一律留 .bak-<时间戳>。工单271 T2 的 `*.bak*` 排除会把这些备份挡在公开仓外。
$staged = [System.IO.Path]::GetTempFileName()
try {
    $lines | Out-File -FilePath $staged -Encoding utf8
    if (Test-Path -LiteralPath $OutPath) {
        $same = @(Compare-Object (Get-Content -LiteralPath $staged) `
                                 (Get-Content -LiteralPath $OutPath) -SyncWindow 0).Count -eq 0
        if ($same) { Write-Host "产物与将写内容一致，未改动: $OutPath"; exit 0 }
        if (-not $Overwrite) {
            Write-Error "目标已存在且内容不同：确认覆盖请加 -Overwrite（会先自动备份 .bak-<时间戳>）"
            exit 1
        }
        $bak = '{0}.bak-{1}' -f $OutPath, (Get-Date -Format 'yyyyMMdd-HHmmss')
        Copy-Item -LiteralPath $OutPath -Destination $bak
        Write-Host "原产物已备份: $bak"
    }
    $lines | Out-File -FilePath $OutPath -Encoding utf8
    Write-Host "OK -> $OutPath"
} finally {
    Remove-Item -LiteralPath $staged -ErrorAction SilentlyContinue
}