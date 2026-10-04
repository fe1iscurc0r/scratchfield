# ============================================================
#  scratchpad 一键部署（Windows 优先，PowerShell 5.1+ 自带，零新依赖）
#
#  用法：
#     .\setup.ps1                        # 自检 → uv sync → 前端 npm install + build
#     .\setup.ps1 -WithExtras pdf2md     # 额外装 pdf2md extra（判例/论文 PDF→MD）
#     .\setup.ps1 -SkipBuild             # 只装依赖不构建（开发时用 npm run dev）
#     .\setup.ps1 -Force                 # 已装步骤也重跑
#
#  设计（卷165）：
#    · 第一步先跑 python doctor_env.py，有必装项缺失就「列出来 → 停下」，绝不半残继续装
#    · 任一步失败即停，错误原样透传（不吞异常、不静默降级）
#    · 幂等：重复运行安全；已装步骤会提示跳过（-Force 可强制重跑）
# ============================================================
[CmdletBinding()]
param(
  [string]$WithExtras = "",
  [switch]$SkipBuild,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Note($msg) { Write-Host "    $msg" -ForegroundColor DarkGray }
function Fail($msg) {
  Write-Host "`n[失败] $msg" -ForegroundColor Red
  Write-Host "[停] 不继续后续步骤。修好上面的问题再重跑 .\setup.ps1" -ForegroundColor Yellow
  exit 1
}

# ---------------- 1/4 环境自检 ----------------
Write-Step "1/4 环境自检（doctor_env.py）"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  Fail "未找到 python。请先安装 Python 3.12.x（严格 3.12，不是 3.13）：winget install -e --id Python.Python.3.12"
}
& python "$RepoRoot\doctor_env.py"
if ($LASTEXITCODE -ne 0) {
  Fail "环境自检未通过：上面列出的【缺失】项必须先装好（每条后面就是可粘贴的安装命令）。"
}
Write-Ok "环境自检通过"

# ---------------- 2/4 后端依赖（uv sync）----------------
Write-Step "2/4 后端依赖（uv sync）"
$uvArgs = @("sync")
if ($WithExtras) {
  foreach ($e in $WithExtras.Split(",")) {
    $extra = $e.Trim()
    if ($extra) { $uvArgs += @("--extra", $extra) }
  }
}
Write-Note ("uv " + ($uvArgs -join " "))
& uv @uvArgs
if ($LASTEXITCODE -ne 0) { Fail "uv sync 失败（错误见上方原样输出）。常见原因：Python 版本不是 3.12、或网络拉不下包。" }
Write-Ok "后端依赖就绪"

# ---------------- 3/4 前端依赖与构建 ----------------
Write-Step "3/4 前端（frontend/）"
$frontend = Join-Path $RepoRoot "frontend"
if (-not (Test-Path $frontend)) { Fail "找不到 frontend 目录：$frontend" }
Push-Location $frontend
try {
  $nodeModules = Join-Path $frontend "node_modules"
  if ((Test-Path $nodeModules) -and (-not $Force)) {
    Write-Note "node_modules 已存在，跳过 npm install（要强制重装用 -Force）"
  } else {
    Write-Note "npm install"
    & npm install
    if ($LASTEXITCODE -ne 0) { Fail "npm install 失败。注意：本仓有 package-lock.json，请只用 npm，不要混用 pnpm/yarn。" }
    Write-Ok "前端依赖就绪"
  }

  if ($SkipBuild) {
    Write-Note "已指定 -SkipBuild，跳过构建（开发时用: npm run dev）"
  } else {
    $distDir = Join-Path $frontend "dist"
    if ((Test-Path $distDir) -and (-not $Force)) {
      Write-Note "dist 已存在，跳过构建（要强制重建用 -Force）"
    } else {
      Write-Note "npm run build"
      & npm run build
      if ($LASTEXITCODE -ne 0) { Fail "前端构建失败（错误见上方）。" }
      Write-Ok "前端构建完成"
    }
  }
} finally {
  Pop-Location
}

# ---------------- 4/4 收尾：启动方式 + 局域网访问 ----------------
Write-Step "4/4 安装完成"
$lanIp = $null
try {
  $lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
            Select-Object -First 1 -ExpandProperty IPAddress)
} catch { $lanIp = $null }
if (-not $lanIp) { $lanIp = "<本机局域网IP>" }

Write-Host ""
Write-Host "启动方式（二选一）：" -ForegroundColor Green
Write-Host "  桌面端（托盘 + 桌宠）：  python main.py"
Write-Host "  纯 web 模式：           uv run uvicorn apiserver.api_server:app --host 0.0.0.0 --port 8000"
Write-Host ""
Write-Host "局域网访问（平板/手机浏览器）：" -ForegroundColor Green
Write-Host ("  http://{0}:5173/   （前端 dev；需要先 cd frontend; npm run dev）" -f $lanIp)
Write-Host ("  http://{0}:8000/   （后端 API；纯 web 模式用 --host 0.0.0.0 才对外）" -f $lanIp)
Write-Host ""
Write-Host "环境依赖细节见 docs/环境依赖清单-Windows装机-2026-09-27.md" -ForegroundColor DarkGray
Write-Host "自检随时可跑：python doctor_env.py（--json 供 CI 用）" -ForegroundColor DarkGray
exit 0
