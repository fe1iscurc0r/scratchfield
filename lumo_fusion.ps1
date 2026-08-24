<#
.SYNOPSIS
  陆墨 × NEKO 融合启动脚本（M1 文本打通）
.DESCRIPTION
  启动 scratchpad 后端（lumo_proxy）+ NEKO（wrapper 注入 lumo provider）
  NEKO 选 lumo provider 后，文本对话经 lumo_proxy 注入陆墨人格+记忆+RAG

  工具链路径外部化（issue #18）：不再写死本机绝对路径，按
  「脚本参数 > 环境变量 > 自动探测 > 历史默认值」顺序解析。
  环境变量清单见 .env.example 的 LUMO_FUSION 段。
.PARAMETER NoNeo4j
  跳过 Neo4j
.PARAMETER NoFrontend
  跳过 scratchpad 前端（纯 NEKO 验证用）
.PARAMETER PythonExe
  Python 解释器路径（覆盖 LUMO_FUSION_PYTHON）
.PARAMETER NodeExe
  node.exe 路径（覆盖 LUMO_FUSION_NODE）
.PARAMETER Neo4jBat
  neo4j.bat 路径（覆盖 LUMO_FUSION_NEO4J_BAT）
.PARAMETER JavaHome
  JDK 目录（覆盖 LUMO_FUSION_JAVA_HOME）
.EXAMPLE
  .\lumo_fusion.ps1              # 完整启动
  .\lumo_fusion.ps1 -NoNeo4j     # 跳过 Neo4j
  .\lumo_fusion.ps1 -NoNeo4j -NoFrontend  # 最小启动（后端+NEKO）
  .\lumo_fusion.ps1 -PythonExe D:\py\python.exe  # 显式指定解释器
#>

param(
  [switch]$NoNeo4j,
  [switch]$NoFrontend,
  [switch]$NoNekoShell,
  [string]$PythonExe,
  [string]$NodeExe,
  [string]$Neo4jBat,
  [string]$JavaHome
)

# ============================================================
# 路径配置（issue #18：外部化，参数 > 环境变量 > 探测 > 默认）
# ============================================================
$PROJECT_DIR  = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-ToolPath($paramValue, $envName, $candidates) {
  # 依优先级返回第一个存在的路径；全部缺失时返回首选候选供报错展示
  $envValue = [Environment]::GetEnvironmentVariable($envName)
  foreach ($c in @($paramValue, $envValue) + @($candidates)) {
    if ($c -and (Test-Path $c)) { return $c }
  }
  $fallback = @($paramValue, $envValue, $candidates[0]) | Where-Object { $_ } | Select-Object -First 1
  return $fallback
}

# Python：探测常见安装位置 + PATH 里的 python
$pythonCandidates = @(
  (Get-Command python -ErrorAction SilentlyContinue).Source,
  "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "C:\Users\ASUS\python-sdk\python3.13.2\python.exe"  # 历史默认（原开发机）
)
$PYTHON_EXE   = Resolve-ToolPath $PythonExe "LUMO_FUSION_PYTHON" $pythonCandidates

# Node：探测 PATH + 常见二进制缓存目录
$nodeCandidates = @(
  (Get-Command node -ErrorAction SilentlyContinue).Source,
  "$env:USERPROFILE\.trae-cn\binaries\node\versions\24.18.0\node.exe"  # 历史默认
)
$NODE_EXE     = Resolve-ToolPath $NodeExe "LUMO_FUSION_NODE" $nodeCandidates
$NPM_CMD      = if ($NODE_EXE) { Join-Path (Split-Path $NODE_EXE) "npm.cmd" } else { "npm.cmd" }

# Neo4j / JDK：仅 -NoNeo4j 关闭时才需要，缺失时由前置检查报错
$NEO4J_BAT    = Resolve-ToolPath $Neo4jBat "LUMO_FUSION_NEO4J_BAT" @(
  "D:\neo4j-community-5.26.2\bin\neo4j.bat",
  "d:\my git\neo4j-community-5.26.2\bin\neo4j.bat"  # 历史默认
)
$JAVA_HOME    = Resolve-ToolPath $JavaHome "LUMO_FUSION_JAVA_HOME" @(
  $env:JAVA_HOME,
  "C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot"  # 历史默认
)
$NEKO_ROOT    = Join-Path $PROJECT_DIR "NEKO\N.E.K.O"
$WRAPPER      = Join-Path $PROJECT_DIR "scripts\neko_launcher_wrapper.py"

# ============================================================
# 前置检查
# ============================================================
function Test-Path-Or-Exit($path, $name) {
  if (-not (Test-Path $path)) {
    Write-Host "[错误] 找不到 ${name}: $path" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
  }
}

Write-Host "`n=== 陆墨 × NEKO 融合启动器（M1）===" -ForegroundColor Cyan
Test-Path-Or-Exit $PYTHON_EXE "Python"
Test-Path-Or-Exit $WRAPPER "neko_launcher_wrapper.py"
Test-Path-Or-Exit $NEKO_ROOT "NEKO 源码目录"

# ============================================================
# 生成 LUMO_PROXY_TOKEN（两个进程共享的鉴权密钥）
# ============================================================
if (-not $env:LUMO_PROXY_TOKEN) {
  # 生成 32 字节随机 token（hex 编码）
  $bytes = New-Object byte[] 32
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng.GetBytes($bytes)
  $env:LUMO_PROXY_TOKEN = [BitConverter]::ToString($bytes).Replace("-", "").ToLower()
  Write-Host "[TOKEN] 生成 LUMO_PROXY_TOKEN: $($env:LUMO_PROXY_TOKEN.Substring(0,8))..." -ForegroundColor DarkGray
} else {
  Write-Host "[TOKEN] 使用已有 LUMO_PROXY_TOKEN" -ForegroundColor DarkGray
}

# M4：NEKO_EXEC_TOKEN（陆墨 agent → NEKO CUA 执行桥凭证，铁律7 不落盘）
# 后端（neko_cua.py）与 NEKO（lumo_inject_router.py）都从环境读取，必须同源。
# 若未在此生成，后端 main.py 会进程内兜底生成，但那样 wrapper 拿不到同一份，
# 所以 fusion 启动链路统一在这里生成，经环境继承传给后端与 NEKO wrapper。
if (-not $env:NEKO_EXEC_TOKEN) {
  $bytes2 = New-Object byte[] 32
  $rng2 = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng2.GetBytes($bytes2)
  $env:NEKO_EXEC_TOKEN = [BitConverter]::ToString($bytes2).Replace("-", "").ToLower()
  Write-Host "[TOKEN] 生成 NEKO_EXEC_TOKEN: $($env:NEKO_EXEC_TOKEN.Substring(0,8))..." -ForegroundColor DarkGray
} else {
  Write-Host "[TOKEN] 使用已有 NEKO_EXEC_TOKEN" -ForegroundColor DarkGray
}

# P0-2 修复：删除 token 明文落盘。
# 原实现将 LUMO_PROXY_TOKEN 写入 %TEMP%\lumo_proxy_token.txt（明文、无 ACL、退出不删），
# 任意本地进程可读取冒充 NEKO 注入人格/RAG。
# 铁律7（NEKO-Lumo-Fusion-Blueprint-v1.1.md:142）："NEKO 启动时从同机环境读取，不落盘明文"。
# 现改用环境变量直传子进程：Start-ChildProcess 已继承 $env:LUMO_PROXY_TOKEN，
# wrapper（neko_launcher_wrapper.py:15-18）从 os.environ 读取，无需文件中转。

# 设置 lumo_proxy base URL（默认 8000 端口）
if (-not $env:LUMO_PROXY_BASE_URL) {
  $env:LUMO_PROXY_BASE_URL = "http://127.0.0.1:8000/persona/v1"
}
Write-Host "[环境] LUMO_PROXY_BASE_URL=$($env:LUMO_PROXY_BASE_URL)" -ForegroundColor DarkGray

# 嵌入引擎用 CPU（避免与前端 WebGL 抢 GPU）
$env:LUMO_EMBEDDING_DEVICE = "cpu"

# ============================================================
# 清理残留进程
# ============================================================
function Clear-ResidualProcesses {
  Write-Host "[清理] 扫描残留进程..." -ForegroundColor DarkGray
  $killed = 0

  # 后端 Python（main.py 或直接 uvicorn 启动的 apiserver）
  # uvicorn 残留会导致 8000 端口被旧 token 的后端占用，新启动的 NEKO 用新 token 调用 → 401
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'main\.py|uvicorn.*apiserver' } |
    ForEach-Object {
      Write-Host "[清理] 终止后端残留 PID $($_.ProcessId)" -ForegroundColor DarkYellow
      taskkill /PID $_.ProcessId /F /T 2>$null | Out-Null
      $killed++
    }

  # NEKO Python（neko_launcher_wrapper 或 N.E.K.O 内的 python）
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'neko_launcher_wrapper|N\.E\.K\.O' } |
    ForEach-Object {
      Write-Host "[清理] 终止 NEKO 残留 PID $($_.ProcessId)" -ForegroundColor DarkYellow
      taskkill /PID $_.ProcessId /F /T 2>$null | Out-Null
      $killed++
    }

  # Neo4j
  if (-not $NoNeo4j) {
    Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
      Where-Object { $_.CommandLine -match 'neo4j|Neo4j' } |
      ForEach-Object {
        Write-Host "[清理] 终止 Neo4j 残留 PID $($_.ProcessId)" -ForegroundColor DarkYellow
        taskkill /PID $_.ProcessId /F /T 2>$null | Out-Null
        $killed++
      }
  }

  # 前端 Electron
  if (-not $NoFrontend) {
    Get-CimInstance Win32_Process -Filter "Name='electron.exe'" |
      Where-Object { $_.CommandLine -match 'scratchpad[\\/\\\\]frontend|lumo' } |
      ForEach-Object {
        Write-Host "[清理] 终止 Electron 残留 PID $($_.ProcessId)" -ForegroundColor DarkYellow
        taskkill /PID $_.ProcessId /F /T 2>$null | Out-Null
        $killed++
      }
  }

  # NEKO Electron Shell
  if (-not $NoNekoShell) {
    Get-CimInstance Win32_Process -Filter "Name='electron.exe'" |
      Where-Object { $_.CommandLine -match 'neko-electron-shell' } |
      ForEach-Object {
        Write-Host "[清理] 终止 NEKO Shell 残留 PID $($_.ProcessId)" -ForegroundColor DarkYellow
        taskkill /PID $_.ProcessId /F /T 2>$null | Out-Null
        $killed++
      }
  }

  if ($killed -gt 0) {
    Write-Host "[清理] 已终止 $killed 个残留进程" -ForegroundColor Green
    Start-Sleep -Seconds 2
  } else {
    Write-Host "[清理] 无残留进程" -ForegroundColor DarkGray
  }
}

Clear-ResidualProcesses

# ============================================================
# 进程跟踪
# ============================================================
$script:childJobs = @()

function Start-ChildProcess($label, $filePath, $argumentList, $workingDir) {
  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $filePath
  # 沈遥 P0：含空格路径需加引号，否则 CreateProcess 在空格处截断
  $psi.Arguments = ($argumentList | ForEach-Object {
    '"' + ($_ -replace '"', '\"') + '"'
  }) -join " "
  $psi.WorkingDirectory = $workingDir
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true

  $proc = [System.Diagnostics.Process]::new()
  $proc.StartInfo = $psi

  $prefix = "[$label]"
  $outAction = [ScriptBlock]::Create("if (`$EventArgs.Data) { Write-Host '$prefix ' `$EventArgs.Data -ForegroundColor Gray }")
  $errAction = [ScriptBlock]::Create("if (`$EventArgs.Data) { Write-Host '$prefix ' `$EventArgs.Data -ForegroundColor Yellow }")

  $null = Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -Action $outAction
  $null = Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived  -Action $errAction

  $proc.Start() | Out-Null
  $proc.BeginOutputReadLine()
  $proc.BeginErrorReadLine()

  $script:childJobs += $proc
  Write-Host "[启动] $label (PID: $($proc.Id))" -ForegroundColor Green
  return $proc
}

function Stop-AllChildren {
  Write-Host "`n[清理] 正在关闭所有子进程..." -ForegroundColor Yellow
  foreach ($proc in $script:childJobs) {
    if ($proc -and -not $proc.HasExited) {
      try {
        taskkill /PID $proc.Id /T /F 2>$null | Out-Null
        $proc.Kill()
      } catch {}
    }
  }
  Write-Host "[清理] 完成" -ForegroundColor Green
}

$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Stop-AllChildren }
trap { Stop-AllChildren; break }

# ============================================================
# 1. 启动 Neo4j（可选）
# ============================================================
$WithNeo4j = -not $NoNeo4j
if ($WithNeo4j) {
  Test-Path-Or-Exit $NEO4J_BAT "Neo4j"
  Test-Path-Or-Exit (Join-Path $JAVA_HOME "bin\java.exe") "JDK 17"
  $env:JAVA_HOME = $JAVA_HOME
  $env:PATH = "$JAVA_HOME\bin;$env:PATH"
  Write-Host "`n[Neo4j] 启动中..." -ForegroundColor Cyan
  Start-ChildProcess "Neo4j" $NEO4J_BAT @("console") (Split-Path $NEO4J_BAT)
  Start-Sleep -Seconds 5
  Write-Host "[Neo4j] bolt://localhost:7687" -ForegroundColor Green
}

# ============================================================
# 2. 启动 scratchpad 后端（提供 lumo_proxy 端点）
# ============================================================
Write-Host "`n[后端] 启动 scratchpad（lumo_proxy 端点）..." -ForegroundColor Cyan
Start-ChildProcess "后端" $PYTHON_EXE @("main.py") $PROJECT_DIR
Write-Host "[后端] lumo_proxy: $($env:LUMO_PROXY_BASE_URL)/chat/completions" -ForegroundColor Green

# 等待后端 API 就绪（最多 30 秒）
Write-Host "[后端] 等待 API 就绪..." -ForegroundColor DarkGray
$apiReady = $false
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 0.5
  try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
    if ($resp.StatusCode -eq 200) {
      $apiReady = $true
      break
    }
  } catch {}
}
if ($apiReady) {
  Write-Host "[后端] API 就绪" -ForegroundColor Green
} else {
  Write-Host "[后端] WARN: API 未在 30s 内就绪，NEKO 可能连接失败" -ForegroundColor Yellow
}

# ============================================================
# 3. 启动前端（可选）
# ============================================================
if (-not $NoFrontend) {
  $nodeModules = Join-Path $PROJECT_DIR "frontend\node_modules"
  if (-not (Test-Path $nodeModules)) {
    Write-Host "`n[前端] 首次启动，正在安装依赖..." -ForegroundColor Yellow
    $installProc = Start-Process $NPM_CMD -ArgumentList "install --legacy-peer-deps" -WorkingDirectory (Join-Path $PROJECT_DIR "frontend") -Wait -NoNewWindow -PassThru
    if ($installProc.ExitCode -ne 0) {
      Write-Host "[前端] 依赖安装失败！" -ForegroundColor Red
    }
  }
  Write-Host "`n[前端] 启动 scratchpad 前端..." -ForegroundColor Cyan
  Start-ChildProcess "前端" $NPM_CMD @("run", "dev") (Join-Path $PROJECT_DIR "frontend")
}

# ============================================================
# 4. 启动 NEKO（通过 wrapper 注入 lumo provider）
# ============================================================
Write-Host "`n[NEKO] 启动 NEKO（wrapper 模式）..." -ForegroundColor Cyan
# NEKO 需要自己的 Python 环境，复用 scratchpad 的 Python
Start-ChildProcess "NEKO" $PYTHON_EXE @($WRAPPER) $NEKO_ROOT
Write-Host "[NEKO] wrapper 已注入 lumo provider，在设置中选择 '陆墨（本地人格代理）'" -ForegroundColor Green

# ============================================================
# 5. 等待 NEKO 后端就绪，然后启动 NEKO Electron Shell（桌宠窗口）
# ============================================================
if (-not $NoNekoShell) {
  $nekoShellDir = Join-Path $PROJECT_DIR "neko-electron-shell"
  $nekoShellNodeModules = Join-Path $nekoShellDir "node_modules"

  # 等待 NEKO Main Server 就绪（最多 60 秒）
  Write-Host "`n[NEKO Shell] 等待 NEKO 后端就绪..." -ForegroundColor DarkGray
  $nekoReady = $false
  for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Seconds 0.5
    try {
      $resp = Invoke-WebRequest -Uri "http://127.0.0.1:48911/" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
      if ($resp.StatusCode -eq 200 -or $resp.StatusCode -eq 302) {
        $nekoReady = $true
        break
      }
    } catch {}
  }
  if ($nekoReady) {
    Write-Host "[NEKO Shell] NEKO 后端已就绪" -ForegroundColor Green

    # 检查依赖
    if (-not (Test-Path $nekoShellNodeModules)) {
      Write-Host "[NEKO Shell] 首次启动，正在安装依赖..." -ForegroundColor Yellow
      $installProc = Start-Process $NPM_CMD -ArgumentList "install --legacy-peer-deps" -WorkingDirectory $nekoShellDir -Wait -NoNewWindow -PassThru
      if ($installProc.ExitCode -ne 0) {
        Write-Host "[NEKO Shell] 依赖安装失败！跳过桌宠窗口" -ForegroundColor Red
      }
    }

    # 启动 NEKO Electron Shell
    if (Test-Path $nekoShellNodeModules) {
      Write-Host "[NEKO Shell] 启动桌宠窗口..." -ForegroundColor Cyan
      $npxCmd = Join-Path (Split-Path $NODE_EXE) "npx.cmd"
      Start-ChildProcess "NEKO-Shell" $NODE_EXE @("node_modules\electron\cli.js", ".") $nekoShellDir
      Write-Host "[NEKO Shell] 桌宠窗口已启动（加载 http://localhost:48911）" -ForegroundColor Green
    }
  } else {
    Write-Host "[NEKO Shell] WARN: NEKO 后端未在 60s 内就绪，跳过桌宠窗口" -ForegroundColor Yellow
  }
}

# ============================================================
# 等待退出
# ============================================================
Write-Host "`n=== 融合启动完成 ===" -ForegroundColor Cyan
Write-Host "NEKO 设置 → 辅助 API → 选择 '陆墨（本地人格代理）'" -ForegroundColor Yellow
Write-Host "按 Ctrl+C 关闭所有服务" -ForegroundColor Yellow
Write-Host ""

try {
  while ($script:childJobs | Where-Object { -not $_.HasExited }) {
    Start-Sleep -Seconds 1
  }
} finally {
  Stop-AllChildren
}
