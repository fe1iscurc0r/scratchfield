'use strict';

/**
 * WO-278 运行时工装：同源子窗口的 `nekoWindowControl` 四方法（批 2 遗留项）。
 *
 * 交接 §2.4 写着「minimize/restore/maximize/isMaximized 四个方法的行为未实测」。
 * 这份工装把整条链跑起来：真 `src/preload-child.js`（contextIsolation: true）
 * → contextBridge → 页面调用 → 真 `createStorageGate()` 注册的 IPC 处理器
 * → 真 BrowserWindow 状态变化。
 *
 * 判据有两份，缺一不可：
 *   1. 页面自报：四个方法的返回值与 isMaximized() 的读数符合预期；
 *   2. 主进程观测：窗口状态真的变过（最大化过、最小化过，最后两个状态都是 false）。
 * 只看页面自报不够 —— 处理器返回 {ok:true} 但窗口没动，页面是看不出来的。
 */

const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const https = require('https');

const { createStorageGate } = require('../../src/main/storage-gate');

const argv = process.argv.slice(2);
function arg(name, fallback) {
  const i = argv.indexOf(name);
  return i >= 0 && i + 1 < argv.length ? argv[i + 1] : fallback;
}

const OUT = arg('--out', '');
const ROOT = path.resolve(__dirname, '..', '..', '..');

const observations = {
  mode: 'child-window-control',
  isolation: true,
  pageReport: null,
  pageConsole: [],
  mainLog: [],
  windowStates: [],
  finalState: null,
  stateCheck: null,
  error: null,
};

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
};

function startStaticServer() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      let rel;
      try {
        rel = decodeURIComponent((req.url || '/').split('?')[0]);
      } catch (_) {
        res.writeHead(400);
        res.end('bad url');
        return;
      }
      const abs = path.resolve(ROOT, '.' + rel);
      if (!abs.startsWith(ROOT + path.sep) && abs !== ROOT) {
        res.writeHead(403);
        res.end('forbidden');
        return;
      }
      fs.readFile(abs, (err, data) => {
        if (err) {
          res.writeHead(404);
          res.end('not found');
          return;
        }
        res.writeHead(200, { 'Content-Type': MIME[path.extname(abs)] || 'application/octet-stream' });
        res.end(data);
      });
    });
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

function finish(code, extra) {
  if (finish.done) return;
  finish.done = true;
  Object.assign(observations, extra || {});
  const payload = JSON.stringify(observations, null, 2);
  if (OUT) {
    try {
      fs.writeFileSync(OUT, payload, 'utf8');
    } catch (err) {
      console.error('write out failed:', err && err.message);
    }
  }
  console.log('=== HARNESS_JSON_BEGIN ===');
  console.log(payload);
  console.log('=== HARNESS_JSON_END ===');
  if (app.isReady()) app.exit(code);
  else process.exit(code);
}

async function main() {
  const server = await startStaticServer();
  const port = server.address().port;

  // 真处理器：只有 createStorageGate 注册的那四条会被调到，其余上下文是占位。
  createStorageGate({
    BrowserWindow,
    app,
    dialog,
    http,
    https,
    ipcMain,
    log: (...args) => {
      observations.mainLog.push(args.map(String).join(' ').slice(0, 300));
    },
    requestAppQuit: () => {
      observations.quitRequested = true;
    },
    resolveServerUrl: () => 'http://127.0.0.1:' + port,
    getOriginalUrl: () => 'http://127.0.0.1:' + port + '/',
    windowManager: {},
    getMainWindow: () => null,
    getInitialChatSurfaceMode: () => 'compact',
    restoreReactChatFromBall: () => {},
    isReactChatSelfMinimizedBallActive: () => false,
  });

  const win = new BrowserWindow({
    // 同 isolation-harness：默认不显示，避免在用户屏幕上留一个空白 Electron 窗。
    show: process.env.HARNESS_SHOW === '1',
    width: 640,
    height: 480,
    webPreferences: {
      preload: path.join(__dirname, '..', '..', 'src', 'preload-child.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  const t0 = Date.now();
  const sampler = setInterval(() => {
    if (win.isDestroyed()) return;
    observations.windowStates.push({
      t: Date.now() - t0,
      maximized: win.isMaximized(),
      minimized: win.isMinimized(),
      visible: win.isVisible(),
    });
  }, 100);

  win.webContents.on('console-message', (...params) => {
    const message = params[1] && typeof params[1] === 'object' && 'message' in params[1]
      ? String(params[1].message)
      : String(params[2]);
    observations.pageConsole.push(message.slice(0, 500));
    const at = message.indexOf('HARNESS_RESULT ');
    if (at < 0) return;
    try {
      observations.pageReport = JSON.parse(message.slice(at + 'HARNESS_RESULT '.length));
    } catch (err) {
      observations.error = 'page report parse failed: ' + (err && err.message);
    }
    clearInterval(sampler);
    setTimeout(() => {
      const finalState = {
        maximized: win.isDestroyed() ? null : win.isMaximized(),
        minimized: win.isDestroyed() ? null : win.isMinimized(),
      };
      // 主进程侧硬证据：窗口必须真的最大化过、最小化过，且收尾时两者都为 false。
      const stateCheck = {
        sawMaximized: observations.windowStates.some((s) => s.maximized === true),
        sawMinimized: observations.windowStates.some((s) => s.minimized === true),
        finalMaximized: finalState.maximized,
        finalMinimized: finalState.minimized,
      };
      stateCheck.pass =
        stateCheck.sawMaximized === true &&
        stateCheck.sawMinimized === true &&
        stateCheck.finalMaximized === false &&
        stateCheck.finalMinimized === false;
      const pass = !!(observations.pageReport && observations.pageReport.pass) &&
        stateCheck.pass &&
        !observations.error;
      finish(pass ? 0 : 1, { finalState, stateCheck });
    }, 300);
  });

  win.webContents.once('did-fail-load', (_e, code, desc) => {
    observations.error = 'did-fail-load ' + code + ' ' + desc;
    finish(1);
  });

  const pageUrl =
    'http://127.0.0.1:' + port +
    '/neko-electron-shell/tests/runtime/child-window-control.page.html';

  win.loadURL(pageUrl).catch((err) => {
    observations.error = 'loadURL failed: ' + (err && err.message);
    finish(1);
  });

  setTimeout(() => {
    if (!observations.pageReport) {
      observations.error = observations.error || 'timeout waiting for page report';
      finish(1);
    }
  }, 30000);
}

app.whenReady().then(main).catch((err) => {
  observations.error = String(err && err.stack ? err.stack : err);
  finish(1);
});

app.on('window-all-closed', () => {
  if (!finish.done) finish(1);
});
