$path = "d:\my git\scratchpad\wt-overwatch-v6\js\main.js"
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
$lines | Out-File -FilePath $path -Encoding utf8 -Force
Write-Host "OK"