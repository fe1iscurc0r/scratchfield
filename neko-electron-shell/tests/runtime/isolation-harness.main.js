/**
 * 隔离窗探针工装（WO-278 P1-c）
 *
 * 用指定的 preload + 指定 URL 起一个真 Electron 窗口，供 smoke-ws-isolation.py 探针。
 * 用途：reactChat / fullChat 是托盘触发的**懒创建**窗口，正常冒烟不会打开它们，
 * 而这个工装能直接以生产 preload 打开同一张页面（chat.html），验证隔离后桥是否成立。
 *
 * 环境变量：
 *   HARNESS_PRELOAD  preload 文件名（不含 .js），默认 preload-chat-full
 *   HARNESS_URL      要打开的页面，默认 http://localhost:48911/chat_full
 */
const path = require('path');
const { app, BrowserWindow, ipcMain } = require('electron');

// preload-pet 在加载期用 sendSync 读三个「主进程才有的」状态。
// 真实 app 的 main.js 注册了它们；工装没有 ⇒ 渲染进程会卡在同步 IPC 上，
// 表现为页面永远到不了 did-finish-load（这个坑排查了很久）。
// 这里补成 no-op，值给 undefined（与"主进程还没设置"同义）。
const SYNC_CHANNELS = ['neko:ws-next-session-epoch', 'neko:input-region-backend', 'neko:has-set-shape'];
for (const ch of SYNC_CHANNELS) {
  ipcMain.on(ch, (event) => { event.returnValue = undefined; });
}

const preloadName = process.env.HARNESS_PRELOAD || 'preload-chat-full';
const url = process.env.HARNESS_URL || 'http://localhost:48911/chat_full';
// 对照实验用：HARNESS_ISOLATION=0 复刻旧架构（非隔离），
// 用来区分「隔离导致的」和「页面本身就有的」问题。
const isolated = process.env.HARNESS_ISOLATION !== '0';
const preloadPath = path.join(__dirname, '..', '..', 'src', `${preloadName}.js`);

// 与 src/main.js 对齐的两个开关：透明窗在 Windows 上若走原生遮挡计算，
// GPU 进程会被异常终止（exit_code=143），表现为页面永远到不了 did-finish-load。
app.commandLine.appendSwitch('calculate-native-win-occlusion', 'false');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');

app.whenReady().then(() => {
  const win = new BrowserWindow({
    width: 1024,
    height: 768,
    // 默认**不显示**窗口：这些工装会跑几十秒，show:true 会在用户屏幕上弹出
    // 一个空白 Electron 窗（本项目真的被这个困扰过）。要肉眼看就设 HARNESS_SHOW=1。
    show: process.env.HARNESS_SHOW === '1',
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      contextIsolation: isolated,
      webSecurity: true,
      sandbox: false,
    },
  });
  console.log(`[harness] preload=${preloadName} url=${url} contextIsolation=${isolated}`);

  // ⚠️ 监听必须在 loadURL **之前**注册：轻量页可能在本行之后立刻加载完，
  // 之后再挂 did-finish-load 会永远等不到（这个曾让我误判"页面加载不了"）。
  let loaded = false;
  win.webContents.on('did-finish-load', () => {
    loaded = true;
    console.log('[harness] did-finish-load');
  });
  win.webContents.on('did-fail-load', (_e, code, desc, url2) =>
    console.log(`[harness] did-fail-load ${code} ${desc} ${url2}`));

  win.loadURL(url);

  // 重度页面（Live2D/VRM/MMD）会让 CDP 连不上，但主进程的 executeJavaScript 不受影响。
  // 设了 HARNESS_PROBE_JS 就在页面世界跑一段表达式并把结果打出来（供 python 侧解析）。
  const probeJs = process.env.HARNESS_PROBE_JS;
  if (probeJs) {
    const delay = Number(process.env.HARNESS_PROBE_DELAY_MS || 6000);
    const runProbe = () => {
      setTimeout(async () => {
        try {
          const value = await win.webContents.executeJavaScript(probeJs, true);
          console.log('[harness-probe] ' + JSON.stringify(value));
        } catch (err) {
          console.log('[harness-probe-error] ' + String(err && err.message).slice(0, 300));
        }
        if (process.env.HARNESS_PROBE_KEEP !== '1') app.quit();
      }, delay);
    };
    // 已加载完就直接跑探针（避免 once 挂晚了永远不触发）
    if (loaded) runProbe();
    else win.webContents.once('did-finish-load', runProbe);
  }
});

app.on('window-all-closed', () => app.quit());

// 看门狗：工装跑挂时（例如页面一直没 did-finish-load）别把进程和窗口留在屏幕上。
// 默认 120s，可用 HARNESS_MAX_MS 覆盖。
if (process.env.HARNESS_PROBE_JS) {
  const maxMs = Number(process.env.HARNESS_MAX_MS || 120000);
  setTimeout(() => {
    console.log(`[harness] watchdog: ${maxMs}ms 未完成，强制退出`);
    app.exit(0);
  }, maxMs).unref?.();
}
