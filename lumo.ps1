<#
.SYNOPSIS
  陆墨 一键启动脚本
.DESCRIPTION
  双击 lumo.bat 即可启动 Neo4j + 后端 + 前端
.PARAMETER NoNeo4j
  加此参数跳过 Neo4j（仅后端 + 前端）
.EXAMPLE
  .\lumo.bat              # 默认启动 Neo4j + 后端 + 前端
  .\lumo.bat -NoNeo4j     # 跳过 Neo4j
#>

param(
  [switch]$NoNeo4j
)

# ============================================================
# 路径配置（换机器时只改这里）
# ============================================================
$PROJECT_DIR  = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON_EXE   = "C:\Users\ASUS\python-sdk\python3.13.2\python.exe"
$NODE_EXE     = "C:\Users\ASUS\.trae-cn\binaries\node\versions\24.18.0\node.exe"
$NPM_CMD      = Join-Path (Split-Path $NODE_EXE) "npm.cmd"
$NEO4J_BAT    = "d:\my git\neo4j-community-5.26.2\bin\neo4j.bat"
$JAVA_HOME    = "C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot"

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

# ============================================================
# 清理上次残留的僵尸进程（关闭窗口时子进程可能没被清理）
# ============================================================
function Clear-ResidualProcesses {
  Write-Host "[清理] 扫描残留进程..." -ForegroundColor DarkGray
  $killed = 0

  # 1. 后端 Python（main.py）
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" | 
    Where-Object { $_.CommandLine -match 'main\.py' } |
    ForEach-Object {
      Write-Host "[清理] 终止后端残留 PID $($_.ProcessId)" -ForegroundColor DarkYellow
      taskkill /PID $_.ProcessId /F /T 2>$null | Out-Null
      $killed++
    }

  # 2. Neo4j（java.exe 运行 neo4j）
  if (-not $NoNeo4j) {
    Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
      Where-Object { $_.CommandLine -match 'neo4j|Neo4j' } |
      ForEach-Object {
        Write-Host "[清理] 终止 Neo4j 残留 PID $($_.ProcessId)" -ForegroundColor DarkYellow
        taskkill /PID $_.ProcessId /F /T 2>$null | Out-Null
        $killed++
      }
  }

  # 3. 前端 Electron（仅清理 scratchpad/frontend 的 electron 进程，避免误杀 VS Code 等）
  Get-CimInstance Win32_Process -Filter "Name='electron.exe'" |
    Where-Object { $_.CommandLine -match 'scratchpad[\\/\\\\]frontend|lumo' } |
    ForEach-Object {
      Write-Host "[清理] 终止 Electron 残留 PID $($_.ProcessId)" -ForegroundColor DarkYellow
      taskkill /PID $_.ProcessId /F /T 2>$null | Out-Null
      $killed++
    }

  # 4. 前端 vite dev server（node.exe 运行 vite，命令行含 scratchpad/frontend）
  Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -match 'scratchpad[\\/\\\\]frontend|vite.*dev' } |
    ForEach-Object {
      Write-Host "[清理] 终止 vite 残留 PID $($_.ProcessId)" -ForegroundColor DarkYellow
      taskkill /PID $_.ProcessId /F /T 2>$null | Out-Null
      $killed++
    }

  if ($killed -gt 0) {
    Write-Host "[清理] 已终止 $killed 个残留进程" -ForegroundColor Green
    Start-Sleep -Seconds 2  # 等端口和文件句柄释放
  } else {
    Write-Host "[清理] 无残留进程" -ForegroundColor DarkGray
  }

  # 清理 Electron userData 目录下的残留锁文件和端口文件
  # taskkill /F 强杀 Electron 时 before-quit 钩子不执行，这些文件会残留并导致下次启动 EPERM
  $userDataDir = Join-Path $env:APPDATA "lumo"
  if (Test-Path $userDataDir) {
    foreach ($f in @('SingletonLock', 'SingletonCookie', 'SingletonSocket', '.safe_storage_port')) {
      $fp = Join-Path $userDataDir $f
      if (Test-Path $fp) {
        try { Remove-Item $fp -Force 2>$null; Write-Host "[清理] 删除残留文件 $f" -ForegroundColor DarkGray }
        catch {}
      }
    }
  }
}

Write-Host "`n=== 陆墨 启动器 ===" -ForegroundColor Cyan
Test-Path-Or-Exit $PYTHON_EXE "Python"
Test-Path-Or-Exit $NODE_EXE   "Node"
Test-Path-Or-Exit $NPM_CMD    "npm"

# npm.cmd/vite 等包装脚本内部直接调 `node`，必须保证 node 目录在 PATH 里
$nodeDir = Split-Path $NODE_EXE
if ($env:PATH -notlike "*$nodeDir*") {
  $env:PATH = "$nodeDir;$env:PATH"
  Write-Host "[环境] 已把 Node 目录加入 PATH: $nodeDir" -ForegroundColor DarkGray
}
$WithNeo4j = -not $NoNeo4j
if ($WithNeo4j) {
  Test-Path-Or-Exit $NEO4J_BAT "Neo4j"
  Test-Path-Or-Exit (Join-Path $JAVA_HOME "bin\java.exe") "JDK 17"
}

# 启动前先清理上次可能残留的僵尸进程
Clear-ResidualProcesses

# ============================================================
# 进程跟踪
# ============================================================
$script:childJobs = @()

function Start-ChildProcess($label, $filePath, $argumentList, $workingDir) {
  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $filePath
  $psi.Arguments = $argumentList -join " "
  $psi.WorkingDirectory = $workingDir
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true

  $proc = [System.Diagnostics.Process]::new()
  $proc.StartInfo = $psi

  # 输出带上前缀，方便区分
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

# ============================================================
# 清理函数：Ctrl+C 或退出时调用
# ============================================================
function Stop-AllChildren {
  Write-Host "`n[清理] 正在关闭所有子进程..." -ForegroundColor Yellow
  foreach ($proc in $script:childJobs) {
    if ($proc -and -not $proc.HasExited) {
      try {
        # 先尝试温和关闭整个进程树
        taskkill /PID $proc.Id /T /F 2>$null | Out-Null
        $proc.Kill()
      } catch {}
    }
  }
  Write-Host "[清理] 完成" -ForegroundColor Green
}

# 注册退出钩子（Ctrl+C / 窗口关闭 / 正常退出）
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Stop-AllChildren }
trap { Stop-AllChildren; break }

# ============================================================
# 启动 Neo4j（可选）
# ============================================================
if ($WithNeo4j) {
  $env:JAVA_HOME = $JAVA_HOME
  $env:PATH = "$JAVA_HOME\bin;$env:PATH"
  Write-Host "[Neo4j] 启动中..." -ForegroundColor Cyan
  Start-ChildProcess "Neo4j" $NEO4J_BAT @("console") (Split-Path $NEO4J_BAT)
  Start-Sleep -Seconds 5  # 等 Neo4j Bolt 就绪
  Write-Host "[Neo4j] bolt://localhost:7687" -ForegroundColor Green
}

# ============================================================
# 启动后端 + 前端（并行，让 splash 窗口尽早弹出）
# ============================================================
# 强制嵌入引擎用 CPU，避免与前端 WebGL 抢 GPU 资源
# （Live2D 用 WebGL 渲染，CUDA 嵌入占用显存易触发 webglcontextlost）
# 如需启用 GPU 加速嵌入，把下面这行改成 "auto" 或 "cuda"
$env:LUMO_EMBEDDING_DEVICE = "cpu"
Write-Host "[环境] LUMO_EMBEDDING_DEVICE=$($env:LUMO_EMBEDDING_DEVICE) (嵌入引擎用 CPU，GPU 留给前端 WebGL)" -ForegroundColor DarkGray

Write-Host "[后端] 启动中..." -ForegroundColor Cyan
Start-ChildProcess "后端" $PYTHON_EXE @("main.py") $PROJECT_DIR
Write-Host "[后端] http://127.0.0.1:8000 (后台启动中)" -ForegroundColor Green

# 检查 node_modules 是否存在，不存在则自动安装
$nodeModules = Join-Path $PROJECT_DIR "frontend\node_modules"
if (-not (Test-Path $nodeModules)) {
  Write-Host "[前端] 首次启动，正在安装依赖（npm install）..." -ForegroundColor Yellow
  $installProc = Start-Process $NPM_CMD -ArgumentList "install --legacy-peer-deps" -WorkingDirectory (Join-Path $PROJECT_DIR "frontend") -Wait -NoNewWindow -PassThru
  if ($installProc.ExitCode -ne 0) {
    Write-Host "[前端] 依赖安装失败！" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
  }
  Write-Host "[前端] 依赖安装完成" -ForegroundColor Green
}

Write-Host "[前端] 启动中..." -ForegroundColor Cyan
Start-ChildProcess "前端" $NPM_CMD @("run", "dev") (Join-Path $PROJECT_DIR "frontend")

# ============================================================
# 等待退出
# ============================================================
Write-Host "`n=== 全部启动完成 ===" -ForegroundColor Cyan
Write-Host "按 Ctrl+C 关闭所有服务" -ForegroundColor Yellow
Write-Host ""

try {
  # 持续等待，直到所有子进程退出或用户 Ctrl+C
  while ($script:childJobs | Where-Object { -not $_.HasExited }) {
    Start-Sleep -Seconds 1
  }
} finally {
  Stop-AllChildren
}
