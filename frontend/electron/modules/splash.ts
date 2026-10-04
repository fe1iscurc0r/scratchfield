import { Buffer } from 'node:buffer'
/**
 * 早期启动 splash 窗口
 *
 * 作用：
 *   双击 lumo.bat 后，vite dev server 启动 + Electron 加载 + Vue 挂载需要 10~30 秒。
 *   在此期间用户原本只能看到 PowerShell 控制台滚动日志，无法判断程序是否在运行。
 *   本模块在 app.whenReady() 最早阶段同步创建一个轻量 splash 窗口，
 *   用 data URL 内联 HTML（不依赖 vite dev server），立即显示"陆墨正在启动..."进度条。
 *
 * 生命周期：
 *   1. app.whenReady() → createSplashWindow() 立即显示 splash
 *   2. splash 内部 JS 用 setInterval 模拟进度推进（0→90%，约 12 秒走到 90% 后等待）
 *   3. 主窗口 ready-to-show → closeSplashWindow()，splash 淡出关闭
 *   4. 主窗口内的 SplashScreen.vue 组件接管，显示真实后端进度
 *
 * 设计要点：
 *   - 进度条只做"视觉反馈"，不绑定后端真实进度（因为后端可能由 lumo.ps1 启动，
 *     Electron 收不到 stdout）。真实进度由主窗口 SplashScreen.vue 接管。
 *   - HTML/CSS/JS 全部内联到 data URL，避免文件路径和 vite 打包问题。
 *   - 风格与 SplashScreen.vue 金色主题一致，保持视觉连贯。
 */
import { BrowserWindow } from 'electron'

let splashWindow: BrowserWindow | null = null
// closeSplashWindow 淡出动画定时器引用，便于窗口提前销毁时清理，避免访问已销毁窗口
let closeTimer: NodeJS.Timeout | null = null

/** 内联 splash HTML（金色主题，与 SplashScreen.vue 风格一致） */
const SPLASH_HTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>陆墨</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 100%; height: 100%;
    background: #0a0a0a;
    overflow: hidden;
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    color: rgba(212, 175, 55, 0.9);
    user-select: none;
  }
  .container {
    width: 100%; height: 100%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 28px;
  }
  .title {
    font-size: 38px; font-weight: 300;
    letter-spacing: 0.4em;
    color: rgba(212, 175, 55, 0.95);
    text-shadow: 0 0 24px rgba(212, 175, 55, 0.35);
    animation: breathe 2.4s ease-in-out infinite;
  }
  @keyframes breathe {
    0%, 100% { opacity: 0.75; text-shadow: 0 0 18px rgba(212, 175, 55, 0.25); }
    50%      { opacity: 1;    text-shadow: 0 0 32px rgba(212, 175, 55, 0.5); }
  }
  .subtitle {
    font-size: 12px; letter-spacing: 0.3em;
    color: rgba(212, 175, 55, 0.5);
  }
  .progress-wrap {
    width: 320px;
    display: flex; flex-direction: column; gap: 8px;
  }
  .progress-meta {
    display: flex; justify-content: space-between;
    font-size: 11px; letter-spacing: 0.15em;
    color: rgba(212, 175, 55, 0.65);
  }
  .progress-track {
    width: 100%; height: 2px;
    background: rgba(212, 175, 55, 0.15);
    border-radius: 1px;
    overflow: hidden;
  }
  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, rgba(212, 175, 55, 0.4), rgba(212, 175, 55, 0.95));
    border-radius: 1px;
    transition: width 0.4s ease-out;
    box-shadow: 0 0 8px rgba(212, 175, 55, 0.4);
  }
  .hint {
    font-size: 10px; letter-spacing: 0.1em;
    color: rgba(212, 175, 55, 0.35);
    margin-top: 4px;
  }
  .fade-out { animation: fadeOut 0.4s ease forwards; }
  @keyframes fadeOut { to { opacity: 0; } }
</style>
</head>
<body>
<div class="container" id="root">
  <div class="title">陆 墨</div>
  <div class="subtitle">材 料 科 研 助 手</div>
  <div class="progress-wrap">
    <div class="progress-meta">
      <span id="phase">正在启动...</span>
      <span id="percent">0%</span>
    </div>
    <div class="progress-track">
      <div class="progress-bar" id="bar" style="width: 0%"></div>
    </div>
    <div class="hint">首次启动需加载依赖，请耐心等待</div>
  </div>
</div>
<script>
  (function () {
    var phaseEl = document.getElementById('phase');
    var percentEl = document.getElementById('percent');
    var barEl = document.getElementById('bar');
    var progress = 0;
    var phases = [
      { at: 0,  text: '正在启动...' },
      { at: 15, text: '加载前端资源...' },
      { at: 40, text: '初始化 Electron...' },
      { at: 65, text: '挂载主窗口...' },
      { at: 85, text: '即将就绪...' }
    ];
    function currentPhase(p) {
      var text = phases[0].text;
      for (var i = 0; i < phases.length; i++) {
        if (p >= phases[i].at) text = phases[i].text;
      }
      return text;
    }
    function render() {
      var display = Math.min(100, Math.round(progress));
      phaseEl.textContent = currentPhase(progress);
      percentEl.textContent = display + '%';
      barEl.style.width = display + '%';
    }
    // 缓慢推进到 90%，等主窗口接管
    var timer = setInterval(function () {
      if (progress >= 90) { clearInterval(timer); return; }
      // 比例衰减：越接近 90 越慢
      var step = Math.max(0.4, (90 - progress) * 0.04);
      progress = Math.min(90, progress + step);
      render();
    }, 180);
    render();
    // 暴露给主进程：主窗口 ready 后调用 jumpTo(100) 然后淡出
    window.__jumpComplete = function () {
      clearInterval(timer);
      progress = 100;
      render();
      phaseEl.textContent = '准备就绪';
      document.getElementById('root').classList.add('fade-out');
    };
  })();
</script>
</body>
</html>`

/**
 * 创建并显示早期 splash 窗口。
 * 必须在 app.whenReady() 之后调用。
 */
export function createSplashWindow(): BrowserWindow {
  if (splashWindow && !splashWindow.isDestroyed()) {
    return splashWindow
  }

  splashWindow = new BrowserWindow({
    width: 480,
    height: 320,
    frame: false,
    transparent: false,
    resizable: false,
    minimizable: false,
    maximizable: false,
    center: true,
    show: true, // 立即显示，不等 ready-to-show
    alwaysOnTop: true, // 启动期间置顶，避免被 IDE/浏览器遮挡导致用户看不到进度
    skipTaskbar: true, // 不在任务栏显示，避免与主窗口任务栏图标重叠闪现
    backgroundColor: '#0a0a0a',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      // 不开 sandbox：splash 加载的是内联可信 HTML，sandbox 会阻止内联 <script> 执行
      sandbox: false,
    },
  })

  // 用 base64 编码的 data URL 加载内联 HTML，比 encodeURIComponent 更可靠
  // base64 不会引入特殊字符，避免 Chromium 解析 data URL 时的编码问题
  const dataUrl = `data:text/html;base64,${Buffer.from(SPLASH_HTML, 'utf-8').toString('base64')}`
  splashWindow.loadURL(dataUrl).catch((err) => {
    // data URL 极少失败；失败时直接销毁 splash，避免 480x320 黑色空窗残留
    console.warn('[Splash] loadURL failed:', err)
    try {
      splashWindow?.destroy()
    }
    catch {}
    splashWindow = null
  })

  return splashWindow
}

/**
 * 关闭 splash 窗口。
 * 会先调用渲染层的淡出动画，然后延迟销毁，避免突兀消失。
 * 直接调用 destroy() 而非 close()+destroy()，避免 close 事件被跳过。
 */
export function closeSplashWindow(): void {
  if (!splashWindow || splashWindow.isDestroyed()) {
    return
  }
  // 清理上一次未触发的关闭定时器，避免重复销毁或访问已销毁窗口
  if (closeTimer) {
    clearTimeout(closeTimer)
    closeTimer = null
  }
  try {
    // 通知渲染层跳到 100% 并淡出
    splashWindow.webContents.executeJavaScript('window.__jumpComplete && window.__jumpComplete()')
      .catch(() => {})
    // 延迟 450ms 等淡出动画完成后再销毁
    closeTimer = setTimeout(() => {
      closeTimer = null
      try {
        splashWindow?.destroy()
      }
      catch {}
      splashWindow = null
    }, 450)
  }
  catch {
    try {
      splashWindow.destroy()
    }
    catch {}
    splashWindow = null
  }
}

export function getSplashWindow(): BrowserWindow | null {
  return splashWindow
}
