function createBackendRuntime(context) {
  const {
    NEKO_DEFAULT_PORTS,
    app,
    console,
    fs,
    getAppConfig,
    getNekoActivePorts,
    getOriginalUrl,
    http,
    https,
    loadingText,
    log,
    logStream,
    path,
    process,
    reloadAndShow,
    resolveServerUrl,
    setNekoActivePorts,
    setOriginalUrl,
    spawn,
    spawnSync,
    stopPetGameModeWatcher,
    stopStorageGatePolling,
    stopTopReassertion,
    updateLoadingWindowStatus,
    windowManager,
  } = context;
  const initialParentPid = process.ppid;

  let pythonProcess = null;
  let openfangProcess = null;
  let jobHolderProcess = null;
  let openfangJobHolderProcess = null;
  let hasCleanedUp = false;
  let hasCompletedFinalCleanup = false;
  let appQuitRequested = false;
  let currentLaunchId = null;
  let backendReadyResolver = null;

  const nekoActivePorts = new Proxy({}, {
    get(_target, prop) {
      return getNekoActivePorts()[prop];
    },
    set(_target, prop, value) {
      const ports = getNekoActivePorts();
      ports[prop] = value;
      setNekoActivePorts(ports);
      return true;
    },
    ownKeys() {
      return Reflect.ownKeys(getNekoActivePorts());
    },
    getOwnPropertyDescriptor() {
      return { enumerable: true, configurable: true };
    },
  });

  function createBackendReadyPromise() {
    return new Promise((resolve) => {
      backendReadyResolver = resolve;
    });
  }

  function isAppQuitRequested() {
    return appQuitRequested;
  }

  function markAppQuitRequested() {
    appQuitRequested = true;
  }

// ===== N.E.K.O 后端健康探测 =====

/**
 * 通过 GET /health 探测单个端口是否为运行中的 N.E.K.O 服务。
 * 若响应包含 N.E.K.O 指纹（{ app: "N.E.K.O", service: "..." }），
 * 返回解析后的 JSON；否则返回 null。
 */
function probeNekoHealth(port, timeoutMs = 2000) {
  return new Promise((resolve) => {
    const req = http.request(
      { hostname: '127.0.0.1', port, path: '/health', method: 'GET', timeout: timeoutMs },
      (res) => {
        let body = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => { body += chunk; });
        res.on('end', () => {
          try {
            const json = JSON.parse(body);
            if (json && json.app === 'N.E.K.O') {
              resolve(json);
              return;
            }
          } catch (_) { /* 非合法 JSON 或非 N.E.K.O 服务 */ }
          resolve(null);
        });
      },
    );
    req.on('timeout', () => { req.destroy(); resolve(null); });
    req.on('error', () => resolve(null));
    req.end();
  });
}

/**
 * 扫描默认端口，检查是否已有 N.E.K.O 后端在运行。
 *
 * 命中判定（P0-1 修复，A 方案）：
 *   MAIN_SERVER_PORT + TOOL_SERVER_PORT 必须命中；
 *   MEMORY_SERVER_PORT 视为可选——neko_launcher_wrapper.py 设计性移除
 *   memory_server 进程（_patch_servers_list，陆墨侧 summer_memory 接管），
 *   wrapper 模式下 48912 永不启动，强制三端口全中会导致 scan 永远 found=false，
 *   进而触发 Step B 拉起未注入 lumo provider 的第二个后端 / 90s 空等。
 *   官版场景 memory_server 正常启动时仍三端口全中，本判定兼容。
 *
 * @returns {{ found: boolean, ports: object, services: object }}
 *   - found: MAIN + TOOL 命中即为 true；memory 可选
 *   - ports: port_key -> port 的映射（仅包含有响应的服务）
 *   - services: port_key -> health 响应体
 */
async function scanForExistingBackend() {
  const portMap = {
    MAIN_SERVER_PORT: NEKO_DEFAULT_PORTS.MAIN_SERVER_PORT,
    MEMORY_SERVER_PORT: NEKO_DEFAULT_PORTS.MEMORY_SERVER_PORT,
    TOOL_SERVER_PORT: NEKO_DEFAULT_PORTS.TOOL_SERVER_PORT,
  };
  const results = {};
  const ports = {};
  const entries = Object.entries(portMap);

  // 三端口并行探测；memory 缺失不阻断判定（见函数头注释）
  const probes = entries.map(async ([key, port]) => {
    const health = await probeNekoHealth(port);
    if (health) {
      results[key] = health;
      ports[key] = port;
    }
  });
  await Promise.all(probes);

  // P0-1：MAIN + TOOL 必命中，memory 可选（wrapper 设计性移除 memory_server）
  const REQUIRED_PORTS = ['MAIN_SERVER_PORT', 'TOOL_SERVER_PORT'];
  const found = REQUIRED_PORTS.every((k) => results[k]);
  return { found, ports, services: results };
}

function findLinuxXauthorityFile(env) {
  const candidates = [];
  if (env.XAUTHORITY) candidates.push(env.XAUTHORITY);

  try {
    const runtimeDir = env.XDG_RUNTIME_DIR || (typeof process.getuid === 'function' ? `/run/user/${process.getuid()}` : '');
    if (runtimeDir && fs.existsSync(runtimeDir)) {
      for (const name of fs.readdirSync(runtimeDir)) {
        if (name.startsWith('.mutter-Xwaylandauth.')) {
          candidates.push(path.join(runtimeDir, name));
        }
      }
    }
  } catch (_) { /* best effort */ }

  if (env.HOME) candidates.push(path.join(env.HOME, '.Xauthority'));

  for (const candidate of candidates) {
    try {
      if (candidate && fs.existsSync(candidate)) return candidate;
    } catch (_) { /* best effort */ }
  }
  return '';
}

function prepareLinuxDesktopAutomationEnv(env) {
  if (process.platform !== 'linux') return env;

  const next = { ...env };
  if (!next.DISPLAY) {
    log('[Linux desktop automation] DISPLAY is missing; pyautogui desktop control may remain unavailable.');
    return next;
  }

  if (!next.XAUTHORITY) {
    const xauthority = findLinuxXauthorityFile(next);
    if (xauthority) {
      next.XAUTHORITY = xauthority;
      log('[Linux desktop automation] XAUTHORITY resolved:', xauthority);
    }
  }

  try {
    const user = next.USER || next.LOGNAME;
    if (!user) {
      log('[Linux desktop automation] local user is unknown; skipped xhost authorization.');
      return next;
    }
    const result = spawnSync('xhost', [`+SI:localuser:${user}`], {
      env: next,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 1500,
    });
    if (result.status === 0) {
      log('[Linux desktop automation] authorized local user for X display:', user);
    } else {
      const detail = (result.stderr || result.stdout || '').trim();
      log('[Linux desktop automation] xhost authorization skipped/failed:', detail || `status=${result.status}`);
    }
  } catch (error) {
    log('[Linux desktop automation] xhost authorization failed:', error.message || error);
  }

  return next;
}

// ===== NEKO_EVENT stdout 解析 =====

/**
 * 解析单行 stdout 中的 NEKO_EVENT 包。
 * 解析成功返回事件对象，否则返回 null。
 */
function parseNekoEvent(line) {
  const prefix = 'NEKO_EVENT ';
  const idx = line.indexOf(prefix);
  if (idx === -1) return null;
  try {
    return JSON.parse(line.slice(idx + prefix.length));
  } catch (_) {
    return null;
  }
}

/**
 * NEKO_EVENT 中央处理器：处理 launcher 发出的所有事件。
 * 用于更新全局状态（端口/启动会话）并在需要时触发 Promise 解析。
 */
function handleNekoEvent(evt) {
  if (!evt || !evt.event) return;

  // 忽略过期 launcher 会话事件
  if (currentLaunchId && evt.launch_id && evt.launch_id !== currentLaunchId) {
    log('[NEKO_EVENT] Ignoring stale event:', evt.event, 'launch_id:', evt.launch_id);
    return;
  }

  const payload = evt.payload || {};

  switch (evt.event) {
    case 'startup_begin':
      currentLaunchId = payload.launch_id || evt.launch_id || null;
      log('[NEKO_EVENT] startup_begin, launch_id:', currentLaunchId);
      updateLoadingWindowStatus({
        title: loadingText('loadingPreparingTitle'),
        detail: loadingText('loadingPreparingDetail'),
      });
      break;

    case 'port_plan': {
      const selected = payload.selected || {};
      if (selected.MAIN_SERVER_PORT) nekoActivePorts.MAIN_SERVER_PORT = selected.MAIN_SERVER_PORT;
      if (selected.MEMORY_SERVER_PORT) nekoActivePorts.MEMORY_SERVER_PORT = selected.MEMORY_SERVER_PORT;
      if (selected.TOOL_SERVER_PORT) nekoActivePorts.TOOL_SERVER_PORT = selected.TOOL_SERVER_PORT;
      // 将 getOriginalUrl() 更新为（可能变化后的）主服务端口
      setOriginalUrl(resolveServerUrl('MAIN_SERVER'));
      log('[NEKO_EVENT] port_plan received. Active ports:', JSON.stringify(nekoActivePorts),
        'fallback_applied:', payload.fallback_applied);
      updateLoadingWindowStatus({
        title: loadingText('loadingBackendTitle'),
        detail: loadingText('loadingBackendDetail'),
      });
      break;
    }

    case 'startup_ready': {
      const selected = payload.selected || {};
      if (selected.MAIN_SERVER_PORT) nekoActivePorts.MAIN_SERVER_PORT = selected.MAIN_SERVER_PORT;
      if (selected.MEMORY_SERVER_PORT) nekoActivePorts.MEMORY_SERVER_PORT = selected.MEMORY_SERVER_PORT;
      if (selected.TOOL_SERVER_PORT) nekoActivePorts.TOOL_SERVER_PORT = selected.TOOL_SERVER_PORT;
      setOriginalUrl(resolveServerUrl('MAIN_SERVER'));
      log('[NEKO_EVENT] startup_ready. Final URL:', getOriginalUrl());
      updateLoadingWindowStatus({
        title: loadingText('loadingReadyTitle'),
        detail: loadingText('loadingReadyDetail'),
      });
      // 解析“后端就绪”Promise（如果存在等待方）
      if (backendReadyResolver) {
        backendReadyResolver();
        backendReadyResolver = null;
      }
      break;
    }

    case 'attach_existing': {
      const selected = payload.selected || {};
      if (selected.MAIN_SERVER_PORT) nekoActivePorts.MAIN_SERVER_PORT = selected.MAIN_SERVER_PORT;
      if (selected.MEMORY_SERVER_PORT) nekoActivePorts.MEMORY_SERVER_PORT = selected.MEMORY_SERVER_PORT;
      if (selected.TOOL_SERVER_PORT) nekoActivePorts.TOOL_SERVER_PORT = selected.TOOL_SERVER_PORT;
      setOriginalUrl(resolveServerUrl('MAIN_SERVER'));
      log('[NEKO_EVENT] attach_existing. URL:', getOriginalUrl());
      updateLoadingWindowStatus({
        title: loadingText('loadingAttachedTitle'),
        detail: loadingText('loadingReadyDetail'),
      });
      if (backendReadyResolver) {
        backendReadyResolver();
        backendReadyResolver = null;
      }
      break;
    }

    case 'startup_in_progress':
      log('[NEKO_EVENT] startup_in_progress:', payload.message);
      updateLoadingWindowStatus({
        title: loadingText('loadingExistingStartupTitle'),
        detail: loadingText('loadingExistingStartupDetail'),
      });
      // 另一个 launcher 正在启动，当前仅等待。
      break;

    case 'storage_migration_processing':
      log('[NEKO_EVENT] storage_migration_processing:',
        'source_root:', payload.source_root || '-',
        'target_root:', payload.target_root || '-');
      updateLoadingWindowStatus({
        title: loadingText('loadingMigrationProcessingTitle'),
        detail: loadingText('loadingMigrationProcessingDetail'),
      });
      break;

    case 'storage_migration_completed':
      log('[NEKO_EVENT] storage_migration_completed:',
        'source_root:', payload.source_root || '-',
        'target_root:', payload.target_root || '-');
      updateLoadingWindowStatus({
        title: loadingText('loadingMigrationCompletedTitle'),
        detail: loadingText('loadingMigrationCompletedDetail'),
      });
      break;

    case 'storage_migration_failed':
      log('[NEKO_EVENT] storage_migration_failed:',
        'error_code:', payload.error_code || '-',
        'error_message:', payload.error_message || '-');
      updateLoadingWindowStatus({
        title: loadingText('loadingMigrationFailedTitle'),
        detail: loadingText('loadingMigrationFailedDetail'),
      });
      break;

    case 'storage_migration_restart':
      log('[NEKO_EVENT] storage_migration_restart:',
        'restart_reason:', payload.restart_reason || '-',
        'completed:', payload.completed,
        'source_root:', payload.source_root || '-',
        'target_root:', payload.target_root || '-');
      currentLaunchId = null;
      updateLoadingWindowStatus({
        title: payload.completed ? loadingText('loadingMigrationRestartCompletedTitle') : loadingText('loadingMigrationRestartRecoveryTitle'),
        detail: loadingText('loadingMigrationRestartDetail'),
      });
      break;

    case 'startup_failure':
      log('[NEKO_EVENT] startup_failure:', payload.message);
      updateLoadingWindowStatus({
        title: loadingText('loadingStartupFailureTitle'),
        detail: loadingText('loadingStartupFailureDetail'),
      });
      break;

    default:
      log('[NEKO_EVENT] Unhandled event:', evt.event);
  }
}

// 启动 Python exe 并监听输出
function startPythonProcess() {
  return new Promise((resolve, reject) => {
    const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
    // 修改这里的路径为你的 Python exe 的实际位置
    // exe 和所有依赖都在 bin 目录下
    const pythonExePath = process.platform === 'win32'
      ? path.join(basePath, 'bin', 'projectneko_server.exe')
      : path.join(basePath, 'bin', 'projectneko_server');

    log('startPythonProcess() - basePath:', basePath);
    log('startPythonProcess() - pythonExePath:', pythonExePath);
    log('startPythonProcess() - 文件是否存在:', fs.existsSync(pythonExePath));

    // 检查文件是否存在
    if (!fs.existsSync(pythonExePath)) {
      log(`Python exe 未找到: ${pythonExePath}，跳过启动`);
      console.log(`Python exe 未找到: ${pythonExePath}，跳过启动`);
      resolve(); // 如果没有找到，直接继续
      return;
    }

    log(`正在启动 Python 服务: ${pythonExePath}`);
    console.log(`正在启动 Python 服务: ${pythonExePath}`);

    // 配置启动参数
    const command = pythonExePath;
    const args = [];
    const binPath = path.join(basePath, 'bin');

    // 构建 Python 进程环境变量：直连模式下清理常见代理变量，避免后端继续走梯子
    const pythonEnv = {
      ...process.env,
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
      PYTHONLEGACYWINDOWSSTDIO: '0'
    };
    // 注入自定义端口环境变量，供 Python _read_port_env() 读取
    pythonEnv['NEKO_MAIN_SERVER_PORT'] = String(NEKO_DEFAULT_PORTS.MAIN_SERVER_PORT);
    pythonEnv['NEKO_MEMORY_SERVER_PORT'] = String(NEKO_DEFAULT_PORTS.MEMORY_SERVER_PORT);
    pythonEnv['NEKO_TOOL_SERVER_PORT'] = String(NEKO_DEFAULT_PORTS.TOOL_SERVER_PORT);
    pythonEnv['NEKO_USER_PLUGIN_SERVER_PORT'] = String(NEKO_DEFAULT_PORTS.USER_PLUGIN_SERVER_PORT);
    pythonEnv['NEKO_OPENFANG_PORT'] = String(NEKO_DEFAULT_PORTS.OPENFANG_PORT);
    try {
      // useSystemProxy=false 表示直连/禁用代理
      if (!getAppConfig()?.useSystemProxy) {
        const proxyEnvKeys = [
          'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
          'http_proxy', 'https_proxy', 'all_proxy',
          'npm_config_proxy', 'npm_config_https_proxy'
        ];
        for (const key of proxyEnvKeys) {
          if (key in pythonEnv) {
            delete pythonEnv[key];
          }
        }
        // 关键：设置 NO_PROXY=* 使 Python httpx/aiohttp/urllib 跳过 Windows 注册表系统代理
        // 仅清除 HTTP_PROXY 等环境变量不够，Python 的 urllib.request.getproxies()
        // 在 Windows 上还会读取注册表中的系统代理设置（如 Clash/V2Ray 写入的代理）
        pythonEnv['NO_PROXY'] = '*';
        pythonEnv['no_proxy'] = '*';
        log('Python 启动环境：已清理代理相关环境变量并设置 NO_PROXY=*（直连模式）');
      }
    } catch (e) {
      log('构建 Python 环境变量失败（忽略）:', e.message);
    }

    const desktopAutomationEnv = prepareLinuxDesktopAutomationEnv(pythonEnv);

    const spawnOptions = {
      cwd: binPath,
      windowsHide: process.platform === 'win32',
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: false,
      env: desktopAutomationEnv
    };

    // 启动进程，隐藏 console 窗口
    pythonProcess = spawn(command, args, spawnOptions);

    // 创建 Job Object 管理进程生命周期
    // 从 Electron（父进程）侧创建 Job Object 并将 Python 进程加入，
    // 这样无论通过何种方式退出，OS 都会自动清理所有子进程。
    if (pythonProcess.pid) {
      setupJobObjectHolder(pythonProcess.pid);
    }

    // 设置流的编码为 UTF-8
    if (pythonProcess.stdout) {
      pythonProcess.stdout.setEncoding('utf8');
    }
    if (pythonProcess.stderr) {
      pythonProcess.stderr.setEncoding('utf8');
    }

    // 监听 stdout
    pythonProcess.stdout.on('data', (data) => {
      // data 已经是字符串，因为我们设置了 setEncoding('utf8')
      const output = typeof data === 'string' ? data : data.toString('utf-8');
      log('[Python Server]:', output.trimEnd());
      console.log(`[Python Server]: ${output}`);

      // 解析 NEKO_EVENT 行（一个 data 块内可能有多个事件）
      for (const line of output.split('\n')) {
        const evt = parseNekoEvent(line);
        if (evt) {
          handleNekoEvent(evt);
        }
      }

      // 兼容旧版：保留中文文本检测（旧 launcher 可能不发 startup_ready）。
      if (output.includes('所有服务器已启动完成！')) {
        console.log('检测到服务器启动完成！');
        resolve();
      }
    });

    // 监听 stderr
    pythonProcess.stderr.on('data', (data) => {
      const output = typeof data === 'string' ? data : data.toString('utf-8');
      log('[Python Server Error]:', output.trimEnd());
      console.error(`[Python Server Error]: ${output}`);
    });

    // 监听进程退出
    pythonProcess.on('exit', (code, signal) => {
      log('Python 进程已退出', 'code:', code, 'signal:', signal);
      console.log(`Python 进程退出，代码: ${code}, 信号: ${signal}`);
      pythonProcess = null;
    });

    // 监听进程错误
    pythonProcess.on('error', (err) => {
      log('Python 进程启动失败:', err.message);
      console.error(`Python 进程启动失败:`, err);
      reject(err);
    });

    // 设置超时，如果 30 秒内没有检测到启动完成消息，也继续
    setTimeout(() => {
      console.log('等待超时，继续启动主窗口');
      resolve();
    }, 30000);
  });
}

// ===== OpenFang Agent 执行后端 =====
// vendor/openfang/ 目录中存放各平台的压缩包（随 N.E.K.O 打包分发，不被 Python 编译清空）。
// 首次启动时自动按当前平台解压到 vendor/openfang/ 得到可执行文件。
// 运行时数据目录固定为 ~/.openfang/（config.toml、data/ 等）。
// 默认监听 127.0.0.1:4200（通过 ~/.openfang/config.toml [network] listen_addr 配置）
// Electron 负责：解压→定位二进制 → spawn "openfang start" → 健康检查 → 生命周期管理

/**
 * 通过监听端口反查守护进程的真实 PID。
 * daemon 模式中 launcher 退出后 PID 丢失，只能靠端口定位。
 * @returns {number|null}
 */
function findDaemonPidByPort(port) {
  try {
    if (process.platform === 'win32') {
      const result = spawnSync('powershell', [
        '-NoProfile', '-Command',
        `(Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess`,
      ], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 5000 });
      const pid = parseInt(result.stdout?.trim(), 10);
      if (pid > 0) return pid;
    } else {
      const result = spawnSync('lsof', ['-ti', `:${port}`, '-sTCP:LISTEN'], {
        encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 5000,
      });
      const pid = parseInt(result.stdout?.trim().split('\n')[0], 10);
      if (pid > 0) return pid;
    }
  } catch (e) {
    log(`findDaemonPidByPort(${port}) 失败:`, e.message);
  }
  return null;
}

/**
 * 为 OpenFang daemon 创建独立的 Job Object holder。
 * 与 Python 的 setupJobObjectHolder 完全隔离，互不干扰。
 * daemon 的 PID 由 findDaemonPidByPort 反查获得。
 */
function setupOpenFangJobObjectHolder(targetPid) {
  if (process.platform !== 'win32') return;
  if (!targetPid || targetPid <= 0) return;

  const psScript = `
$ErrorActionPreference='Stop'
try{
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class OFNJ {
  [DllImport("kernel32.dll",SetLastError=true)] public static extern IntPtr CreateJobObject(IntPtr a,string n);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool SetInformationJobObject(IntPtr j,int c,IntPtr i,uint s);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool AssignProcessToJobObject(IntPtr j,IntPtr p);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern IntPtr OpenProcess(uint a,bool b,uint id);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool CloseHandle(IntPtr h);
  [StructLayout(LayoutKind.Sequential)] public struct BLI{public long a,b;public uint F;public UIntPtr c,d;public uint e;public UIntPtr f;public uint g,h;}
  [StructLayout(LayoutKind.Sequential)] public struct IOC{public ulong a,b,c,d,e,f;}
  [StructLayout(LayoutKind.Sequential)] public struct ELI{public BLI B;public IOC I;public UIntPtr a,b,c,d;}
  public static IntPtr Init(){
    var j=CreateJobObject(IntPtr.Zero,null);
    if(j==IntPtr.Zero)return IntPtr.Zero;
    var i=new ELI();i.B.F=0x2000;
    int sz=Marshal.SizeOf(typeof(ELI));
    var p=Marshal.AllocHGlobal(sz);
    Marshal.StructureToPtr(i,p,false);
    bool r=SetInformationJobObject(j,9,p,(uint)sz);
    Marshal.FreeHGlobal(p);
    if(!r){CloseHandle(j);return IntPtr.Zero;}
    return j;
  }
  public static bool Assign(IntPtr j,uint pid){
    var h=OpenProcess(0x1F0FFF,false,pid);
    if(h==IntPtr.Zero)return false;
    bool r=AssignProcessToJobObject(j,h);
    CloseHandle(h);
    return r;
  }
}
"@
}catch{
  Write-Host "OF_JOB_FAIL compile: $_"
  exit 1
}
$j=[OFNJ]::Init()
if($j -eq [IntPtr]::Zero){
  Write-Host "OF_JOB_FAIL init err=$([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
  exit 1
}
Write-Host "OF_JOB_READY"
try{ $line=[Console]::ReadLine() }catch{ exit 0 }
if($line -ne 'GO'){
  [OFNJ]::CloseHandle($j)
  exit 0
}
if([OFNJ]::Assign($j,${targetPid})){
  Write-Host "OF_JOB_OK"
  while(\$true){Start-Sleep -Seconds 3600}
}else{
  Write-Host "OF_JOB_FAIL assign err=$([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
  [OFNJ]::CloseHandle($j)
  exit 1
}`;

  const STABILITY_DELAY_MS = 8000;
  const READY_TIMEOUT_MS = 30000;

  try {
    openfangJobHolderProcess = spawn(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psScript],
      { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true }
    );

    let holderConfirmed = false;
    let readyTimer = null;
    let stabilityTimer = null;

    const killHolder = (reason) => {
      if (readyTimer) { clearTimeout(readyTimer); readyTimer = null; }
      if (stabilityTimer) { clearTimeout(stabilityTimer); stabilityTimer = null; }
      if (openfangJobHolderProcess && !openfangJobHolderProcess.killed) {
        log('[OpenFang-JobObject]', reason);
        try { openfangJobHolderProcess.stdin.end(); } catch (_) {}
        try { openfangJobHolderProcess.kill(); } catch (_) {}
      }
    };

    readyTimer = setTimeout(() => {
      readyTimer = null;
      if (!holderConfirmed) {
        killHolder('holder 未在超时内就绪，已放弃 Job Object（OpenFang 进程不受影响）');
      }
    }, READY_TIMEOUT_MS);

    openfangJobHolderProcess.stdout.setEncoding('utf8');
    openfangJobHolderProcess.stdout.on('data', (data) => {
      for (const msg of data.toString().split('\n')) {
        const trimmed = msg.trim();
        if (!trimmed) continue;
        log('[OpenFang-JobObject]', trimmed);

        if (trimmed.includes('OF_JOB_READY')) {
          if (readyTimer) { clearTimeout(readyTimer); readyTimer = null; }
          stabilityTimer = setTimeout(() => {
            stabilityTimer = null;
            if (openfangJobHolderProcess && !openfangJobHolderProcess.killed) {
              try {
                openfangJobHolderProcess.stdin.write('GO\n');
                log('[OpenFang-JobObject] 已发送 GO 信号，等待分配确认...');
              } catch (e) {
                log('[OpenFang-JobObject] 发送 GO 信号失败:', e.message);
              }
            }
          }, STABILITY_DELAY_MS);
        }

        if (trimmed.includes('OF_JOB_OK')) {
          holderConfirmed = true;
          log('[OpenFang-JobObject] Job Object 已生效 (PID=' + targetPid + ')，daemon 将在主进程退出时自动清理');
        }
      }
    });

    openfangJobHolderProcess.stderr.setEncoding('utf8');
    openfangJobHolderProcess.stderr.on('data', (data) => {
      const msg = data.toString().trim();
      if (msg) log('[OpenFang-JobObject stderr]', msg);
    });

    openfangJobHolderProcess.on('exit', (code) => {
      if (readyTimer) { clearTimeout(readyTimer); readyTimer = null; }
      if (stabilityTimer) { clearTimeout(stabilityTimer); stabilityTimer = null; }
      if (holderConfirmed) {
        log('[OpenFang-JobObject] holder 已退出, code:', code, '（Job Object 曾生效）');
      } else {
        log('[OpenFang-JobObject] holder 已退出, code:', code, '（未分配到 Job Object）');
      }
      openfangJobHolderProcess = null;
    });

    log('[OpenFang-JobObject] 已为 daemon PID', targetPid, '启动 Job Object holder');
  } catch (err) {
    log('[OpenFang-JobObject] 启动失败:', err.message);
    openfangJobHolderProcess = null;
  }
}

/**
 * 根据当前平台确定对应的 OpenFang 压缩包文件名。
 * @returns {{ archiveName: string, isZip: boolean } | null}
 */
function getOpenFangArchiveInfo() {
  const platform = process.platform;  // win32 | darwin | linux
  const arch = process.arch;          // x64 | arm64 | ...

  const archMap = {
    'win32-x64':    { archiveName: 'openfang-x86_64-pc-windows-msvc.zip',        isZip: true  },
    'win32-arm64':  { archiveName: 'openfang-aarch64-pc-windows-msvc.zip',       isZip: true  },
    'darwin-x64':   { archiveName: 'openfang-x86_64-apple-darwin.tar.gz',        isZip: false },
    'darwin-arm64': { archiveName: 'openfang-aarch64-apple-darwin.tar.gz',       isZip: false },
    'linux-x64':    { archiveName: 'openfang-x86_64-unknown-linux-gnu.tar.gz',  isZip: false },
    'linux-arm64':  { archiveName: 'openfang-aarch64-unknown-linux-gnu.tar.gz', isZip: false },
  };

  return archMap[`${platform}-${arch}`] || null;
}

/**
 * 从 vendor/openfang/ 中的压缩包解压出当前平台的 openfang 可执行文件。
 * 解压后的二进制直接放在 vendor/openfang/ 目录下。
 * @returns {string|null} 解压后的可执行文件路径，或 null
 */
function extractOpenFangBinary() {
  const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
  const vendorDir = path.join(basePath, 'vendor', 'openfang');
  const archiveInfo = getOpenFangArchiveInfo();

  if (!archiveInfo) {
    log(`extractOpenFangBinary() - 不支持的平台: ${process.platform}-${process.arch}`);
    return null;
  }

  const archivePath = path.join(vendorDir, archiveInfo.archiveName);
  if (!fs.existsSync(archivePath)) {
    log(`extractOpenFangBinary() - 压缩包不存在: ${archivePath}`);
    return null;
  }

  const exeName = process.platform === 'win32' ? 'openfang.exe' : 'openfang';

  try {
    log(`extractOpenFangBinary() - 正在解压 ${archiveInfo.archiveName} ...`);

    if (archiveInfo.isZip) {
      // Windows: 使用 PowerShell 解压 zip
      const psCmd = `Expand-Archive -Path '${archivePath}' -DestinationPath '${vendorDir}' -Force`;
      const result = spawnSync('powershell', ['-NoProfile', '-Command', psCmd], {
        encoding: 'utf-8', stdio: 'pipe', timeout: 30000,
      });
      if (result.status !== 0) {
        log('extractOpenFangBinary() - PowerShell 解压失败:', result.stderr);
        return null;
      }
    } else {
      // macOS/Linux: 使用 tar 解压
      const result = spawnSync('tar', ['-xzf', archivePath, '-C', vendorDir], {
        encoding: 'utf-8', stdio: 'pipe', timeout: 30000,
      });
      if (result.status !== 0) {
        log('extractOpenFangBinary() - tar 解压失败:', result.stderr);
        return null;
      }
    }

    // 解压后文件可能在子目录里，递归查找
    const exePath = path.join(vendorDir, exeName);
    if (fs.existsSync(exePath)) {
      // 确保有执行权限（macOS/Linux）
      if (process.platform !== 'win32') {
        try { fs.chmodSync(exePath, 0o755); } catch (_) {}
      }
      log(`extractOpenFangBinary() - 解压成功: ${exePath}`);
      return exePath;
    }

    // 如果不在根目录，搜索一层子目录
    const entries = fs.readdirSync(vendorDir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory()) {
        const nested = path.join(vendorDir, entry.name, exeName);
        if (fs.existsSync(nested)) {
          // 移到 vendorDir 根目录
          const dest = path.join(vendorDir, exeName);
          fs.renameSync(nested, dest);
          if (process.platform !== 'win32') {
            try { fs.chmodSync(dest, 0o755); } catch (_) {}
          }
          log(`extractOpenFangBinary() - 从子目录移出: ${nested} → ${dest}`);
          return dest;
        }
      }
    }

    log('extractOpenFangBinary() - 解压后未找到可执行文件');
    return null;
  } catch (e) {
    log('extractOpenFangBinary() - 解压出错:', e.message);
    return null;
  }
}

/**
 * 查找 openfang 可执行文件。
 * 搜索顺序：1) vendor/openfang/ 已解压的二进制
 *           2) 尝试从 vendor/openfang/ 压缩包自动解压
 *           3) ~/.openfang/bin/（用户独立安装）
 *           4) PATH
 * @returns {string|null} 找到的可执行文件完整路径，或 null
 */
function findOpenFangBinary() {
  const exeName = process.platform === 'win32' ? 'openfang.exe' : 'openfang';
  const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
  const homeDir = process.env.HOME || process.env.USERPROFILE || '';

  // 1) 已解压的二进制
  const vendorExe = path.join(basePath, 'vendor', 'openfang', exeName);
  if (fs.existsSync(vendorExe)) {
    log(`findOpenFangBinary() - 找到已解压的: ${vendorExe}`);
    return vendorExe;
  }

  // 2) 尝试从压缩包自动解压
  const extracted = extractOpenFangBinary();
  if (extracted) return extracted;

  // 3) 用户独立安装
  const userInstall = path.join(homeDir, '.openfang', 'bin', exeName);
  if (fs.existsSync(userInstall)) {
    log(`findOpenFangBinary() - 找到用户安装的: ${userInstall}`);
    return userInstall;
  }

  // 4) PATH
  try {
    const cmd = process.platform === 'win32' ? 'where' : 'which';
    const result = spawnSync(cmd, [exeName], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] });
    if (result.status === 0 && result.stdout.trim()) {
      const found = result.stdout.trim().split('\n')[0].trim();
      log(`findOpenFangBinary() - PATH 中找到: ${found}`);
      return found;
    }
  } catch (_) { /* ignore */ }

  return null;
}

/**
 * 确保 OpenFang config.toml 中的 listen_addr 与 NEKO 期望的端口一致。
 * 如果 config.toml 不存在或端口不匹配，会创建/修改 [network] 段。
 */
function ensureOpenFangPort(port) {
  const homeDir = process.env.HOME || process.env.USERPROFILE || '';
  const configPath = path.join(homeDir, '.openfang', 'config.toml');
  const targetAddr = `127.0.0.1:${port}`;

  try {
    if (fs.existsSync(configPath)) {
      let content = fs.readFileSync(configPath, 'utf-8');
      // 检查是否已是正确端口
      if (content.includes(`listen_addr = "${targetAddr}"`)) {
        log(`ensureOpenFangPort() - config.toml 已配置为 ${targetAddr}`);
        return;
      }
      // 替换已有 listen_addr
      if (/listen_addr\s*=\s*"[^"]*"/.test(content)) {
        content = content.replace(/listen_addr\s*=\s*"[^"]*"/, `listen_addr = "${targetAddr}"`);
        log(`ensureOpenFangPort() - 已更新 listen_addr 为 ${targetAddr}`);
      } else if (content.includes('[network]')) {
        // [network] 段存在但没有 listen_addr
        content = content.replace('[network]', `[network]\nlisten_addr = "${targetAddr}"`);
        log(`ensureOpenFangPort() - 已在 [network] 段添加 listen_addr`);
      } else {
        // 没有 [network] 段，追加
        content += `\n\n[network]\nlisten_addr = "${targetAddr}"\n`;
        log(`ensureOpenFangPort() - 已追加 [network] 段`);
      }
      fs.writeFileSync(configPath, content, 'utf-8');
    } else {
      // config.toml 不存在，创建最小配置
      const dir = path.dirname(configPath);
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(configPath, `[network]\nlisten_addr = "${targetAddr}"\n`, 'utf-8');
      log(`ensureOpenFangPort() - 已创建 config.toml (${targetAddr})`);
    }
  } catch (e) {
    log('ensureOpenFangPort() - 配置端口失败（忽略）:', e.message);
  }
}

/**
 * 启动 OpenFang Agent 执行后端进程（与 Python 并行，由 Electron 管理）。
 *
 * 流程：查找已安装的 openfang → 确保端口配置 → spawn `openfang start`
 *       → 健康检查轮询 → ready / timeout。
 * 异常退出后自动重启（最大 3 次）。
 */
function startOpenFangProcess() {
  return new Promise((resolve) => {
    const openfangExePath = findOpenFangBinary();

    if (!openfangExePath) {
      log('OpenFang 未安装，跳过启动。用户可通过 irm https://openfang.sh/install.ps1 | iex 安装');
      resolve({ started: false, reason: 'not_installed' });
      return;
    }

    const ofPort = NEKO_DEFAULT_PORTS.OPENFANG_PORT;
    log(`正在启动 OpenFang Agent 后端 (port=${ofPort}): ${openfangExePath}`);

    // 确保 config.toml 端口正确
    ensureOpenFangPort(ofPort);

    const ofEnv = { ...process.env };

    // 直连模式下清理代理
    try {
      if (!getAppConfig()?.useSystemProxy) {
        const proxyEnvKeys = [
          'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
          'http_proxy', 'https_proxy', 'all_proxy',
        ];
        for (const key of proxyEnvKeys) {
          if (key in ofEnv) delete ofEnv[key];
        }
        ofEnv['NO_PROXY'] = '*';
        ofEnv['no_proxy'] = '*';
      }
    } catch (_) { /* ignore */ }

    const spawnOptions = {
      cwd: path.dirname(openfangExePath),
      windowsHide: process.platform === 'win32',
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: false,
      env: ofEnv,
    };

    let restartCount = 0;
    const MAX_RESTARTS = 3;

    function spawnOpenFang() {
      // "openfang start" 启动守护进程
      openfangProcess = spawn(openfangExePath, ['start'], spawnOptions);
      log(`OpenFang 进程已启动, PID: ${openfangProcess.pid}`);

      if (openfangProcess.stdout) {
        openfangProcess.stdout.setEncoding('utf8');
        openfangProcess.stdout.on('data', (data) => {
          log('[OpenFang]:', data.trimEnd());
        });
      }
      if (openfangProcess.stderr) {
        openfangProcess.stderr.setEncoding('utf8');
        openfangProcess.stderr.on('data', (data) => {
          log('[OpenFang Error]:', data.trimEnd());
        });
      }

      openfangProcess.on('exit', (code, signal) => {
        log(`OpenFang 进程退出, code=${code}, signal=${signal}`);
        openfangProcess = null;

        // 非正常退出时自动重启（最大 MAX_RESTARTS 次）
        if (code !== 0 && !hasCleanedUp && restartCount < MAX_RESTARTS) {
          restartCount++;
          log(`OpenFang 异常退出，${restartCount}/${MAX_RESTARTS} 次自动重启...`);
          setTimeout(() => spawnOpenFang(), 2000);
        }
      });

      openfangProcess.on('error', (err) => {
        log('OpenFang 进程启动失败:', err.message);
        openfangProcess = null;
      });
    }

    spawnOpenFang();

    // 健康检查轮询：等待 OpenFang HTTP 就绪
    const startTime = Date.now();
    const HEALTH_TIMEOUT = 30000; // 30s
    const HEALTH_INTERVAL = 500;  // 500ms

    const healthTimer = setInterval(() => {
      if (Date.now() - startTime > HEALTH_TIMEOUT) {
        clearInterval(healthTimer);
        log('OpenFang 健康检查超时，继续运行（后台可能稍后就绪）');
        resolve({ started: true, ready: false, reason: 'health_timeout' });
        return;
      }

      const req = http.request(
        { hostname: '127.0.0.1', port: ofPort, path: '/api/health', method: 'GET', timeout: 2000 },
        (res) => {
          let body = '';
          res.setEncoding('utf8');
          res.on('data', (chunk) => { body += chunk; });
          res.on('end', () => {
            if (res.statusCode === 200) {
              clearInterval(healthTimer);
              log(`OpenFang 健康检查通过 (${Date.now() - startTime}ms): ${body.substring(0, 200)}`);

              // daemon 已就绪，反查真实 PID 并加入 Job Object
              const daemonPid = findDaemonPidByPort(ofPort);
              if (daemonPid) {
                log(`OpenFang daemon 真实 PID: ${daemonPid}`);
                setupOpenFangJobObjectHolder(daemonPid);
              } else {
                log('OpenFang daemon PID 反查失败，仅依赖 HTTP shutdown + 进程名兜底');
              }

              resolve({ started: true, ready: true });
            }
          });
        },
      );
      req.on('timeout', () => req.destroy());
      req.on('error', () => { /* 还没就绪，继续轮询 */ });
      req.end();
    }, HEALTH_INTERVAL);
  });
}

let isRestartingPython = false;

async function stopPythonProcessForRestart() {
  if (!pythonProcess || pythonProcess.killed) {
    pythonProcess = null;
    return;
  }
  try {
    log('stopPythonProcessForRestart() - 正在终止 Python 进程...');

    // 先终止 Job Object holder → KILL_ON_JOB_CLOSE 清理所有子进程
    if (jobHolderProcess && !jobHolderProcess.killed) {
      try {
        jobHolderProcess.kill();
        log('stopPythonProcessForRestart() - Job holder 已终止');
      } catch (e) {
        log('stopPythonProcessForRestart() - 终止 Job holder 失败:', e.message);
      }
    }
    jobHolderProcess = null;

    // 等待片刻让 OS 完成 Job 清理
    await new Promise(r => setTimeout(r, 500));

    // 兜底：按进程名强杀残留
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/im', 'projectneko_server.exe', '/f'], { stdio: 'ignore' });
    } else {
      pythonProcess.kill('SIGTERM');
      spawnSync('killall', ['-9', 'projectneko_server'], { stdio: 'ignore' });
    }
  } catch (err) {
    log('stopPythonProcessForRestart() - 终止 Python 进程失败:', err.message);
  } finally {
    pythonProcess = null;
    // 给系统一点时间释放端口/资源
    await new Promise(r => setTimeout(r, 800));
  }
}

async function restartPythonServiceAndReload() {
  if (isRestartingPython) {
    return;
  }
  isRestartingPython = true;
  try {
    await stopPythonProcessForRestart();
    await startPythonProcess();
    try {
      await waitForServerReady(getOriginalUrl());
    } catch (e) {
      // 即使检测失败也尝试刷新
      log('restartPythonServiceAndReload() - 等待服务可用失败（继续）:', e.message);
    }
    reloadAndShow(getOriginalUrl());
  } finally {
    isRestartingPython = false;
  }
}

function waitForServerReady(targetUrl, { timeout = 90000, interval = 500 } = {}) {
  log('waitForServerReady() - 开始检测服务可用性:', targetUrl);
  const urlObj = new URL(targetUrl);
  const client = urlObj.protocol === 'https:' ? https : http;
  const pathWithQuery = `${urlObj.pathname || '/'}${urlObj.search || ''}`;
  const deadline = Date.now() + timeout;
  let attemptCount = 0;

  return new Promise((resolve, reject) => {
    let finished = false;

    const scheduleNext = () => {
      if (finished) return;
      if (Date.now() > deadline) {
        finished = true;
        const err = new Error('等待服务器可用超时');
        log('waitForServerReady() - 超时:', err.message);
        reject(err);
        return;
      }
      setTimeout(() => attempt(), interval);
    };

    const attempt = () => {
      if (finished) {
        return;
      }
      attemptCount += 1;
      const requestOptions = {
        hostname: urlObj.hostname,
        port: urlObj.port ? Number(urlObj.port) : undefined,
        path: pathWithQuery === '' ? '/' : pathWithQuery,
        method: 'GET',
        timeout: 2000,
      };

      const req = client.request(requestOptions, (res) => {
        res.resume();
        if (finished) {
          return;
        }

        if (res.statusCode >= 200 && res.statusCode < 500) {
          finished = true;
          log('waitForServerReady() - 服务可用, status:', res.statusCode, 'attempts:', attemptCount);
          resolve();
        } else {
          log('waitForServerReady() - 非预期状态码:', res.statusCode);
          scheduleNext();
        }
      });

      req.on('timeout', () => {
        req.destroy(new Error('Request timeout'));
      });

      req.on('error', (err) => {
        if (finished) {
          return;
        }
        log('waitForServerReady() - 请求错误:', err.message);
        scheduleNext();
      });

      req.end();
    };

    attempt();
  });
}

// ===== Windows Job Object（模仿 Steam 的进程管理方式） =====
// 创建一个持有 Job Object handle 的 PowerShell 后台进程。
// Job 设置了 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE 标志，
// 当 handle 关闭时（holder 进程退出），OS 内核会自动终止 Job 内所有进程。
//
// 安全协议（两阶段分配）：
//   Phase 1: PowerShell 编译 C#、创建 Job Object（不分配目标进程）→ 打印 NEKO_JOB_READY
//   Phase 2: Electron 确认 holder 稳定后，通过 stdin 发送 "GO" → PowerShell 分配进程 → 打印 NEKO_JOB_OK
// 如果 holder 在 Phase 1 就崩溃（如 Add-Type 编译失败），目标进程不受影响。
function setupJobObjectHolder(targetPid) {
  if (process.platform !== 'win32') return;

  // C# 内联代码：分为 Init（创建 Job Object）和 Assign（分配进程）两阶段
  const psScript = `
$ErrorActionPreference='Stop'
try{
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class NJ {
  [DllImport("kernel32.dll",SetLastError=true)] public static extern IntPtr CreateJobObject(IntPtr a,string n);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool SetInformationJobObject(IntPtr j,int c,IntPtr i,uint s);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool AssignProcessToJobObject(IntPtr j,IntPtr p);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern IntPtr OpenProcess(uint a,bool b,uint id);
  [DllImport("kernel32.dll",SetLastError=true)] public static extern bool CloseHandle(IntPtr h);
  [StructLayout(LayoutKind.Sequential)] public struct BLI{public long a,b;public uint F;public UIntPtr c,d;public uint e;public UIntPtr f;public uint g,h;}
  [StructLayout(LayoutKind.Sequential)] public struct IOC{public ulong a,b,c,d,e,f;}
  [StructLayout(LayoutKind.Sequential)] public struct ELI{public BLI B;public IOC I;public UIntPtr a,b,c,d;}
  public static IntPtr Init(){
    var j=CreateJobObject(IntPtr.Zero,null);
    if(j==IntPtr.Zero)return IntPtr.Zero;
    var i=new ELI();i.B.F=0x2000;
    int sz=Marshal.SizeOf(typeof(ELI));
    var p=Marshal.AllocHGlobal(sz);
    Marshal.StructureToPtr(i,p,false);
    bool r=SetInformationJobObject(j,9,p,(uint)sz);
    Marshal.FreeHGlobal(p);
    if(!r){CloseHandle(j);return IntPtr.Zero;}
    return j;
  }
  public static bool Assign(IntPtr j,uint pid){
    var h=OpenProcess(0x1F0FFF,false,pid);
    if(h==IntPtr.Zero)return false;
    bool r=AssignProcessToJobObject(j,h);
    CloseHandle(h);
    return r;
  }
}
"@
}catch{
  Write-Host "NEKO_JOB_FAIL compile: $_"
  exit 1
}
$j=[NJ]::Init()
if($j -eq [IntPtr]::Zero){
  Write-Host "NEKO_JOB_FAIL init err=$([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
  exit 1
}
Write-Host "NEKO_JOB_READY"
try{ $line=[Console]::ReadLine() }catch{ exit 0 }
if($line -ne 'GO'){
  [NJ]::CloseHandle($j)
  exit 0
}
if([NJ]::Assign($j,${targetPid})){
  Write-Host "NEKO_JOB_OK"
  while(\$true){Start-Sleep -Seconds 3600}
}else{
  Write-Host "NEKO_JOB_FAIL assign err=$([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
  [NJ]::CloseHandle($j)
  exit 1
}`;

  // holder 稳定性确认等待时间（毫秒）
  // PowerShell Add-Type 编译通常需要 2-5 秒，
  // 等 READY 后再额外等待此时间以确认 holder 不会崩溃。
  const STABILITY_DELAY_MS = 8000;
  // 从启动到收到 READY 的最长等待时间
  const READY_TIMEOUT_MS = 30000;

  try {
    jobHolderProcess = spawn(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', psScript],
      { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true }
    );

    let holderConfirmed = false;
    let readyTimer = null;
    let stabilityTimer = null;

    const killHolder = (reason) => {
      if (readyTimer) { clearTimeout(readyTimer); readyTimer = null; }
      if (stabilityTimer) { clearTimeout(stabilityTimer); stabilityTimer = null; }
      if (jobHolderProcess && !jobHolderProcess.killed) {
        log('[JobObject]', reason);
        try { jobHolderProcess.stdin.end(); } catch (_) {}
        try { jobHolderProcess.kill(); } catch (_) {}
      }
    };

    // 安全超时：如果 READY 迟迟不来，放弃 Job Object
    readyTimer = setTimeout(() => {
      readyTimer = null;
      if (!holderConfirmed) {
        killHolder('holder 未在超时内就绪，已放弃 Job Object（Python 进程不受影响）');
      }
    }, READY_TIMEOUT_MS);

    jobHolderProcess.stdout.setEncoding('utf8');
    jobHolderProcess.stdout.on('data', (data) => {
      for (const msg of data.toString().split('\n')) {
        const trimmed = msg.trim();
        if (!trimmed) continue;
        log('[JobObject]', trimmed);

        if (trimmed.includes('NEKO_JOB_READY')) {
          // Phase 1 完成：C# 编译成功、Job Object 已创建（但目标进程未分配）
          // 等待一段时间确认 holder 稳定，再发送 GO 信号
          if (readyTimer) { clearTimeout(readyTimer); readyTimer = null; }
          stabilityTimer = setTimeout(() => {
            stabilityTimer = null;
            if (jobHolderProcess && !jobHolderProcess.killed) {
              try {
                jobHolderProcess.stdin.write('GO\n');
                log('[JobObject] 已发送 GO 信号，等待分配确认...');
              } catch (e) {
                log('[JobObject] 发送 GO 信号失败:', e.message);
              }
            }
          }, STABILITY_DELAY_MS);
        }

        if (trimmed.includes('NEKO_JOB_OK')) {
          holderConfirmed = true;
          log('[JobObject] Job Object 已生效，子进程将在主进程退出时自动清理');
        }
      }
    });

    jobHolderProcess.stderr.setEncoding('utf8');
    jobHolderProcess.stderr.on('data', (data) => {
      const msg = data.toString().trim();
      if (msg) log('[JobObject stderr]', msg);
    });

    jobHolderProcess.on('exit', (code) => {
      if (readyTimer) { clearTimeout(readyTimer); readyTimer = null; }
      if (stabilityTimer) { clearTimeout(stabilityTimer); stabilityTimer = null; }
      if (holderConfirmed) {
        log('[JobObject] holder 进程已退出, code:', code, '（Job Object 曾生效）');
      } else {
        log('[JobObject] holder 进程已退出, code:', code, '（Python 进程不受影响 — 未分配到 Job Object）');
      }
      jobHolderProcess = null;
    });

    log('setupJobObjectHolder() - 已为 PID', targetPid, '启动 Job Object holder');
  } catch (err) {
    log('setupJobObjectHolder() - 启动失败:', err.message);
    jobHolderProcess = null;
  }
}

function cleanupResources(reason = 'unknown', options = {}) {
  const {
    destroyWindows = true,
    closeLogStream = true,
  } = options || {};
  const isFinalCleanup = destroyWindows || closeLogStream;

  if (hasCleanedUp && (!isFinalCleanup || hasCompletedFinalCleanup)) {
    log('cleanupResources 已执行过，跳过（原因:', reason, '）');
    return;
  }

  if (!hasCleanedUp) {
    hasCleanedUp = true;

    try {
      log('开始清理资源:', reason);
    } catch (e) {
      // 忽略日志写入错误
    }

    // 停止周期性 Z-order 重断言 timer + Pet 游戏模式 watcher
    try { stopTopReassertion(); } catch (e) { /* ignore */ }
    try { stopPetGameModeWatcher(); } catch (e) { /* ignore */ }

    // ===== 核心清理：终止 Job Object holder =====
    // 当 holder 进程退出时，它持有的 Job Object handle 关闭，
    // OS 内核触发 KILL_ON_JOB_CLOSE，自动终止 Job 内的所有进程
    // （包括 projectneko_server.exe 主进程及其所有 multiprocessing 子进程）。
    if (jobHolderProcess && !jobHolderProcess.killed) {
      try {
        log('正在终止 Job Object holder（将触发 KILL_ON_JOB_CLOSE）...');
        try { jobHolderProcess.stdin.end(); } catch (_) {}
        jobHolderProcess.kill();
        log('Job Object holder 终止命令已发送');
      } catch (err) {
        log('终止 Job Object holder 时出错:', err.message);
      }
    }

    // 等待片刻让 OS 内核完成 Job 清理
    if (process.platform === 'win32') {
      spawnSync('cmd', ['/c', 'timeout /t 1 /nobreak >nul 2>&1'], { stdio: 'ignore' });
    }

    // ===== 兜底清理：按进程名强杀所有残留 =====
    // 防止 Job Object 未正常创建或失败的情况
    if (process.platform === 'win32') {
      try {
        log('兜底清理：taskkill /im projectneko_server.exe /f');
        const result = spawnSync('taskkill', ['/im', 'projectneko_server.exe', '/f'], {
          stdio: 'pipe',
          encoding: 'utf-8'
        });
        log('taskkill 结果 - 退出码:', result.status,
          result.stdout ? result.stdout.trim() : '',
          result.stderr ? result.stderr.trim() : '');
      } catch (err) {
        log('兜底 taskkill 出错:', err.message);
      }
    } else if (pythonProcess && !pythonProcess.killed) {
      try {
        log('尝试发送 SIGTERM 到进程组');
        // process.kill(-pid) 发送信号给进程组，依赖于启动时 { detached: true }
        process.kill(-pythonProcess.pid, 'SIGTERM');
      } catch (e) {
        log('发送 SIGTERM 到进程组失败:', e.message);
        try { pythonProcess.kill('SIGTERM'); } catch (_) { /* ignore */ }
      }
    }

    // 增加对 macOS/Linux 的兜底清理：强杀由项目启动的 projectneko_server 进程
    if (process.platform !== 'win32') {
      try {
        log('兜底清理 (macOS/Linux)：killall -9 projectneko_server');
        const result = spawnSync('killall', ['-9', 'projectneko_server'], {
          stdio: 'pipe',
          encoding: 'utf-8'
        });
        log('killall 结果 - 退出码:', result.status,
          result.stdout ? result.stdout.trim() : '',
          result.stderr ? result.stderr.trim() : '');
      } catch (err) {
        log('兜底 killall 出错:', err.message);
      }
    }

    // ===== OpenFang 清理 =====
    // 层级 1: OpenFang Job Object holder（与 Python 隔离）
    if (openfangJobHolderProcess && !openfangJobHolderProcess.killed) {
      try {
        log('正在终止 OpenFang Job Object holder...');
        try { openfangJobHolderProcess.stdin.end(); } catch (_) {}
        openfangJobHolderProcess.kill();
      } catch (err) {
        log('终止 OpenFang Job Object holder 出错:', err.message);
      }
    }
    // 层级 2: HTTP 优雅关闭（覆盖 Job Object 未建立、非 Windows 等情况）
    try {
      log('正在发送 OpenFang HTTP shutdown...');
      const req = http.request(
        { hostname: '127.0.0.1', port: NEKO_DEFAULT_PORTS.OPENFANG_PORT, path: '/api/shutdown', method: 'POST', timeout: 2000 },
        () => { log('OpenFang HTTP shutdown 已发送'); },
      );
      req.on('error', () => { /* 可能已停止 */ });
      req.end();
    } catch (_) {}
    // 层级 3: launcher 子进程句柄兜底（daemon fork 前 launcher 可能还活着）
    if (openfangProcess && !openfangProcess.killed) {
      try {
        if (process.platform === 'win32') {
          spawnSync('taskkill', ['/pid', String(openfangProcess.pid), '/f', '/t'], { stdio: 'ignore' });
        } else {
          openfangProcess.kill('SIGTERM');
        }
      } catch (_) {}
    }
    // 层级 4: 进程名核弹兜底
    if (process.platform === 'win32') {
      try { spawnSync('taskkill', ['/im', 'openfang.exe', '/f'], { stdio: 'ignore' }); } catch (_) {}
    } else {
      try { spawnSync('killall', ['-9', 'openfang'], { stdio: 'ignore' }); } catch (_) {}
    }

    pythonProcess = null;
    openfangProcess = null;
    jobHolderProcess = null;
    openfangJobHolderProcess = null;
  } else {
    try {
      log('继续完成最终清理:', reason);
    } catch (e) {
      // 忽略日志写入错误
    }
  }

  if (destroyWindows) {
    // 强制销毁所有窗口（destroy 不触发 close 事件，绕过 reactChatWindow 的 preventDefault）
    try {
      windowManager.destroyAllWindows();
    } catch (e) {
      log('destroyAllWindows 出错:', e.message);
    }
  }

  if (closeLogStream) {
    try {
      logStream.end();
    } catch (e) {
      // 忽略
    }
  }

  if (isFinalCleanup) hasCompletedFinalCleanup = true;
}

function requestAppQuit(reason = 'unknown') {
  appQuitRequested = true;
  cleanupResources(reason);
  app.quit();
}

function startDevParentExitWatchdog() {
  if (app.isPackaged) return;
  if (process.platform !== 'darwin') return;
  if (!initialParentPid || initialParentPid <= 1) return;

  const timer = setInterval(() => {
    if (appQuitRequested || hasCleanedUp) {
      clearInterval(timer);
      return;
    }

    let parentAlive = true;
    try {
      process.kill(initialParentPid, 0);
    } catch (err) {
      parentAlive = err && err.code === 'EPERM';
    }

    if (!parentAlive || process.ppid === 1) {
      log('[dev] 父进程已退出，关闭 Electron。initialParentPid:', initialParentPid,
        'currentParentPid:', process.ppid);
      appQuitRequested = true;
      cleanupResources('dev parent process exited');
      process.exit(0);
    }
  }, 1000);
  try { timer.unref(); } catch (_) {}
  log('[dev] macOS 父进程退出 watchdog 已启用, parentPid:', initialParentPid);
}

  return {
    cleanupResources,
    createBackendReadyPromise,
    isAppQuitRequested,
    markAppQuitRequested,
    requestAppQuit,
    restartPythonServiceAndReload,
    scanForExistingBackend,
    startDevParentExitWatchdog,
    startOpenFangProcess,
    startPythonProcess,
    waitForServerReady,
  };
}

module.exports = {
  createBackendRuntime,
};
