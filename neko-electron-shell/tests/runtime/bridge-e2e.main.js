'use strict';

/**
 * WO-278 运行时工装（真 Electron，非单测）。
 *
 * 目的：补上「桥工厂 / 适配器 / 构造器替换」从没在真 Electron 里跑过的空白。
 * 三条场景共用一份 main：
 *
 *   --mode bridge        真 preload 用 contextBridge 暴露 websocket-bridge + 页面加载 ws-adapter
 *   --mode fallback      空 preload（无 bridge）：页面应退化成原生 WebSocket
 *   --mode chat-proxy    真 preload-chat.js + 页面适配器 + 页面桥（toast / 设置同步）；
 *                        装配后两臂都走桥，主进程应看到 1 次 RAW_SEND
 *
 * 退出码同时要求「页面自报通过」与「主进程观测到的 RAW_SEND 次数符合预期」。
 * 后者才是运输方式（直连 vs IPC 代理）的证据，见 expectedRawSendCount()。
 *
 * 主进程按生产语义当「Pet 窗口」：持一条到本地回显服务的真 WebSocket，
 * 收到渲染进程的 RAW_SEND 就往真 WS 发，真 WS 的 ready/message/close 再广播回渲染进程。
 * 页面结果通过 console 前缀回传（不依赖任何 bridge），主进程补上自己的观测后落盘。
 */

const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');

const {
  WS_PROXY_CHANNELS, SETTINGS_CHANNELS, TUTORIAL_OVERLAY_CHANNELS,
  WINDOW_CONTROL_CHANNELS, CHAT_CHANNELS, JUKEBOX_CHANNELS, CHAT_ACTION_CHANNELS,
  COMPACT_CHAT_BALL_CHANNELS, SUBTITLE_CHANNELS,
} = require('../../src/ipc-channels');

const argv = process.argv.slice(2);
function arg(name, fallback) {
  const i = argv.indexOf(name);
  return i >= 0 && i + 1 < argv.length ? argv[i + 1] : fallback;
}

const MODE = arg('--mode', 'bridge');
const ISOLATED = arg('--isolation', 'true') === 'true';
const OUT = arg('--out', '');
const WS_URL = arg('--ws-url', 'ws://127.0.0.1:18765/echo');
const ROOT = path.resolve(__dirname, '..', '..', '..');
const PRELOAD = path.resolve(
  arg('--preload', path.join(__dirname, 'bridge-e2e.preload.js'))
);
const PAGE_OVERRIDE = arg('--page', '');

const observations = {
  mode: MODE,
  isolation: ISOLATED,
  preload: path.relative(ROOT, PRELOAD),
  wsUrl: WS_URL,
  rawSendCount: 0,
  rawSends: [],
  readyBroadcasts: 0,
  toastCount: 0,
  toastMessages: [],
  settingsRequestCount: 0,
  settingsSyncFromPage: [],
  settingsEchoSent: false,
  mainWsEvents: [],
  apiLog: [],
  pageReport: null,
  pageConsole: [],
  error: null,
};

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
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

/**
 * 渲染进程应发出多少次 RAW_SEND —— 把 A/B 的**差分**也钉成断言，而不只是「页面自己说通过」。
 * bridge：页面 → 桥 → IPC，恰好一次；fallback：页面直连，零次；
 * chat-proxy：装配后两臂都走桥（隔离与否都由 preload 暴露 nekoWebSocket），恰好一次。
 * react-chat：preload-chat-react.js 在 P1 后同样只暴露桥、不替换构造器，恰好一次。
 * react-chat-api（P2）：只验 A 组 API 暴露，页面不建连，零次。
 */
function expectedRawSendCount() {
  if (MODE === 'bridge') return 1;
  if (MODE === 'fallback') return 0;
  if (MODE === 'react-chat-api') return 0;
  return 1;
}

function recordApi(kind, channel, payload) {
  observations.apiLog.push({
    kind,
    channel,
    payload: payload === undefined ? null : payload,
  });
}

/**
 * P2：把 A 组 API 背后要打的 IPC 全部接住。
 * `handle` 的返回值同时是页面断言的证据：页面拿到的对象必须等于这里的桩值，
 * 说明调用真的过了 IPC，而不是在某个世界里被短路。
 */
function setupReactChatApiStubs() {
  const handle = (channel, result) => {
    ipcMain.handle(channel, (_event, payload) => {
      recordApi('invoke', channel, payload);
      return typeof result === 'function' ? result(payload) : result;
    });
  };
  const on = (channel) => {
    ipcMain.on(channel, (_event, payload) => recordApi('send', channel, payload));
  };

  handle(WINDOW_CONTROL_CHANNELS.GET_BOUNDS, { x: 120, y: 80, width: 520, height: 680 });
  handle(WINDOW_CONTROL_CHANNELS.GET_WORKAREA, { x: 0, y: 0, width: 1920, height: 1040 });
  handle(WINDOW_CONTROL_CHANNELS.DRAG_STOP_AND_GET_BOUNDS, { x: 130, y: 90, width: 520, height: 680 });
  // 折叠/展开的返回值回显实参：页面据此断言「过桥的参数没被改写」。
  handle(WINDOW_CONTROL_CHANNELS.COLLAPSE, (payload) => payload);
  handle(WINDOW_CONTROL_CHANNELS.EXPAND, (payload) => payload);
  handle('get-desktop-sources', (payload) => [{
    id: 'screen:0:0',
    name: 'Screen 1',
    types: (payload && payload.types) || null,
  }]);
  handle('set-selected-screen-source', (sourceId) => sourceId);
  handle('capture-source-as-dataurl', () => 'data:image/png;base64,AAAA');
  handle('capture-source-without-neko', () => 'data:image/png;base64,BBBB');
  handle('hide-neko-windows', [101, 102]);
  handle('restore-neko-windows', true);

  [
    WINDOW_CONTROL_CHANNELS.SET_POSITION,
    WINDOW_CONTROL_CHANNELS.SET_SIZE,
    WINDOW_CONTROL_CHANNELS.SET_BOUNDS,
    WINDOW_CONTROL_CHANNELS.SET_RESIZABLE,
    WINDOW_CONTROL_CHANNELS.BRING_TO_FRONT,
    WINDOW_CONTROL_CHANNELS.DRAG_START,
    WINDOW_CONTROL_CHANNELS.DRAG_STOP,
    WINDOW_CONTROL_CHANNELS.RESIZE_START,
    WINDOW_CONTROL_CHANNELS.RESIZE_STOP,
    'set-ignore-mouse-events',
    COMPACT_CHAT_BALL_CHANNELS.SET_TEMPORARY_HIDDEN,
    CHAT_CHANNELS.REQUEST_SCREENSHOT,
    SUBTITLE_CHANNELS.SETTINGS_CHANGE,
    'neko:show-subtitle',
    'neko:hide-subtitle',
    JUKEBOX_CHANNELS.TOGGLE,
    CHAT_ACTION_CHANNELS.CONFIG_REQUEST,
    CHAT_ACTION_CHANNELS.AVATAR_PREVIEW,
  ].forEach(on);
}

function evaluateApiCheck() {
  const has = (kind, channel, predicate) => observations.apiLog.some(
    (entry) => entry.kind === kind && entry.channel === channel && predicate(entry.payload),
  );
  const expectedSends = {
    [WINDOW_CONTROL_CHANNELS.SET_POSITION]: (p) => p && p.x === 11 && p.y === 22,
    [WINDOW_CONTROL_CHANNELS.SET_SIZE]: (p) => p && p.w === 555 && p.h === 444,
    [WINDOW_CONTROL_CHANNELS.SET_BOUNDS]: (p) => p && p.x === 11 && p.y === 22 && p.w === 555 && p.h === 444,
    [WINDOW_CONTROL_CHANNELS.SET_RESIZABLE]: (p) => p && p.resizable === false && p.reason === 'p2',
    [WINDOW_CONTROL_CHANNELS.BRING_TO_FRONT]: () => true,
    [WINDOW_CONTROL_CHANNELS.DRAG_START]: (p) => p && p.reason === 'p2',
    [WINDOW_CONTROL_CHANNELS.DRAG_STOP]: (p) => p && p.reason === 'p2',
    [WINDOW_CONTROL_CHANNELS.RESIZE_START]: (p) => p && p.direction === 'se' && p.minWidth === 300,
    [WINDOW_CONTROL_CHANNELS.RESIZE_STOP]: () => true,
    'set-ignore-mouse-events': (p) => p === false,
    [COMPACT_CHAT_BALL_CHANNELS.SET_TEMPORARY_HIDDEN]: (p) => p && p.hidden === true,
    [CHAT_CHANNELS.REQUEST_SCREENSHOT]: () => true,
    [SUBTITLE_CHANNELS.SETTINGS_CHANGE]: (p) => p && p.type === 'toggle' && p.value === true,
    'neko:show-subtitle': () => true,
    'neko:hide-subtitle': () => true,
    [JUKEBOX_CHANNELS.TOGGLE]: () => true,
  };
  const expectedInvokes = {
    [WINDOW_CONTROL_CHANNELS.GET_BOUNDS]: () => true,
    [WINDOW_CONTROL_CHANNELS.GET_WORKAREA]: () => true,
    [WINDOW_CONTROL_CHANNELS.DRAG_STOP_AND_GET_BOUNDS]: (p) => p && p.reason === 'p2',
    [WINDOW_CONTROL_CHANNELS.COLLAPSE]: (p) => p && p.x === 7 && p.width === 88,
    [WINDOW_CONTROL_CHANNELS.EXPAND]: (p) => p && p.x === 120 && p.width === 520,
    'get-desktop-sources': (p) => p && Array.isArray(p.types) && p.types[0] === 'window',
    'set-selected-screen-source': (p) => p === 'screen:0:0',
    'capture-source-as-dataurl': (p) => p === 'screen:0:0',
    'capture-source-without-neko': (p) => p === 'screen:0:0',
    'hide-neko-windows': () => true,
    'restore-neko-windows': (p) => Array.isArray(p) && p[0] === 101,
  };

  const failures = [];
  Object.keys(expectedSends).forEach((channel) => {
    if (!has('send', channel, expectedSends[channel])) failures.push('send ' + channel);
  });
  Object.keys(expectedInvokes).forEach((channel) => {
    if (!has('invoke', channel, expectedInvokes[channel])) failures.push('invoke ' + channel);
  });
  // __nekoRequestConfigInjection / __nekoRequestAvatarPreview：加载时自触发一次，页面各再调一次。
  const configRequests = observations.apiLog
    .filter((e) => e.channel === CHAT_ACTION_CHANNELS.CONFIG_REQUEST).length;
  const avatarPreviews = observations.apiLog
    .filter((e) => e.channel === CHAT_ACTION_CHANNELS.AVATAR_PREVIEW).length;
  if (configRequests < 2) failures.push('config-request count ' + configRequests);
  if (avatarPreviews < 2) failures.push('avatar-preview count ' + avatarPreviews);

  return {
    pass: failures.length === 0,
    failures,
    configRequests,
    avatarPreviews,
    sendChannels: [...new Set(observations.apiLog.filter((e) => e.kind === 'send').map((e) => e.channel))],
    invokeChannels: [...new Set(observations.apiLog.filter((e) => e.kind === 'invoke').map((e) => e.channel))],
  };
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

  if (MODE === 'react-chat-api') setupReactChatApiStubs();

  const win = new BrowserWindow({
    show: false,
    width: 800,
    height: 600,
    webPreferences: {
      preload: PRELOAD,
      contextIsolation: ISOLATED,
      nodeIntegration: false,
      // preload 用 require 相对模块；sandbox 必须关（与生产窗口一致）
      sandbox: false,
    },
  });

  const wc = win.webContents;

  wc.on('preload-error', (_event, preloadPath, error) => {
    observations.preloadError = path.relative(ROOT, preloadPath) + ': '
      + String(error && error.stack ? error.stack : error);
  });
  wc.on('render-process-gone', (_event, details) => {
    observations.error = 'render-process-gone: ' + JSON.stringify(details);
    finish(1);
  });

  wc.on('console-message', (...params) => {
    let message = '';
    if (params[1] && typeof params[1] === 'object' && 'message' in params[1]) {
      message = String(params[1].message);
    } else {
      message = String(params[2]);
    }
    observations.pageConsole.push(message.slice(0, 500));
    // 页面要建第二条连接来测「>123 字节 close reason」：桥只认 READY 广播，
    // 而这条连接建在主 WS 已就绪之后，所以主进程看到握手后再补发一次 READY。
    // 页面打印握手后立刻同步建 handle，因此 300ms 延迟足够避免「READY 早于监听器」。
    if (message.indexOf('HARNESS_PHASE long-close') >= 0 && !observations.longCloseReadySent) {
      observations.longCloseReadySent = true;
      setTimeout(() => {
        observations.readyBroadcasts += 1;
        broadcast(WS_PROXY_CHANNELS.READY);
      }, 300);
    }
    // 异常断线场景：先让新句柄 READY，再广播保留码 1006 + reason。
    // （Chromium 148 的 CloseEvent 构造器不校验保留码，这条断言的是「原样送达」。）
    if (message.indexOf('HARNESS_PHASE abnormal-close') >= 0 && !observations.abnormalCloseSent) {
      observations.abnormalCloseSent = true;
      setTimeout(() => {
        observations.readyBroadcasts += 1;
        broadcast(WS_PROXY_CHANNELS.READY);
      }, 200);
      setTimeout(() => {
        broadcast(WS_PROXY_CHANNELS.CLOSED, { code: 1006, reason: 'abnormal' });
      }, 700);
    }
    // 回退分支：页面把 CloseEvent 换成必抛版本后，仍要收到完整 close payload。
    if (message.indexOf('HARNESS_PHASE forced-ctor-throw') >= 0 && !observations.forcedCtorSent) {
      observations.forcedCtorSent = true;
      setTimeout(() => {
        observations.readyBroadcasts += 1;
        broadcast(WS_PROXY_CHANNELS.READY);
      }, 200);
      setTimeout(() => {
        broadcast(WS_PROXY_CHANNELS.CLOSED, { code: 4003, reason: 'forced' });
      }, 700);
    }
    // 设置同步的「接收」方向：页面已广播过一次快照，这里回发一个可识别值。
    if (message.indexOf('HARNESS_PHASE settings-echo') >= 0 && !observations.settingsEchoSent) {
      observations.settingsEchoSent = true;
      setTimeout(() => {
        broadcast(SETTINGS_CHANNELS.SYNC, { textGuardMaxLength: 4242 });
      }, 300);
    }
    const at = message.indexOf('HARNESS_RESULT ');
    if (at >= 0) {
      try {
        observations.pageReport = JSON.parse(message.slice(at + 'HARNESS_RESULT '.length));
      } catch (err) {
        observations.error = 'page report parse failed: ' + (err && err.message);
      }
      setTimeout(() => {
        const expected = expectedRawSendCount();
        const transportPass = observations.rawSendCount === expected;
        observations.transportCheck = {
          expectedRawSendCount: expected,
          actualRawSendCount: observations.rawSendCount,
          pass: transportPass,
        };
        // chat-proxy 装配后：preload 写不到页面 window 的 toast / 设置同步必须由页面 shim 接上。
        // 这些都是主进程侧观测，页面自报通过也可能漏（它看不到 IPC 是否真的发出去了）。
        if (MODE === 'chat-proxy') {
          const broadcastToMain = observations.settingsSyncFromPage.some(
            (snap) => snap && snap.textGuardMaxLength === 100,
          );
          observations.pageBridgeCheck = {
            toastDelivered: observations.toastCount >= 1,
            settingsRequested: observations.settingsRequestCount >= 1,
            settingsBroadcast: broadcastToMain,
            settingsEchoSent: observations.settingsEchoSent === true,
            pass: observations.toastCount >= 1
              && observations.settingsRequestCount >= 1
              && broadcastToMain
              && observations.settingsEchoSent === true,
          };
        }
        if (MODE === 'react-chat-api') {
          observations.apiCheck = evaluateApiCheck();
        }
        const pass =
          !!(observations.pageReport && observations.pageReport.pass) &&
          transportPass &&
          (!observations.pageBridgeCheck || observations.pageBridgeCheck.pass) &&
          (!observations.apiCheck || observations.apiCheck.pass) &&
          !observations.error;
        finish(pass ? 0 : 1);
      }, 300);
    }
  });

  // —— 主进程侧的「Pet 真 WS」：生产里由 preload-pet 持有一条真连接，这里由主进程代持 ——
  let mainWs = null;
  function broadcast(channel, payload) {
    for (const w of BrowserWindow.getAllWindows()) {
      if (!w.isDestroyed()) w.webContents.send(channel, payload);
    }
  }

  ipcMain.on(WS_PROXY_CHANNELS.RAW_SEND, (_event, data) => {
    observations.rawSendCount += 1;
    observations.rawSends.push(String(data).slice(0, 120));
    if (mainWs && mainWs.readyState === 1) {
      mainWs.send(String(data));
    } else {
      observations.mainWsEvents.push('RAW_SEND while main ws not open: ' + mainWs?.readyState);
    }
  });

  // 页面桥（隔离态 preload 写不到页面 window 的那部分）：
  // toast 必须真的到主进程，设置同步两个方向都必须通。
  ipcMain.on('neko:show-toast', (_event, payload) => {
    observations.toastCount += 1;
    observations.toastMessages.push(payload && payload.message);
  });
  ipcMain.on(SETTINGS_CHANNELS.REQUEST, () => {
    observations.settingsRequestCount += 1;
  });
  ipcMain.on(SETTINGS_CHANNELS.SYNC, (_event, snapshot) => {
    observations.settingsSyncFromPage.push(snapshot);
  });

  // preload-chat-react 在 DOMContentLoaded 里同步询问原生输入区后端。生产由
  // window-host-ipc.js 同步应答；工装不接这三条 sendSync 会把渲染进程主线程挂死
  // （表现为页面永远到不了 DOMContentLoaded，而 console 里只有一条 "without listeners" 警告）。
  ipcMain.on('neko:input-region-backend', (event) => {
    event.returnValue = { backend: 'none', canUseSetShape: false, hasSetShapeMethod: false, patch: {} };
  });
  ipcMain.on('neko:has-set-shape', (event) => { event.returnValue = false; });
  ipcMain.on('neko:x11-input-shape-active', (event) => { event.returnValue = false; });
  ipcMain.on(TUTORIAL_OVERLAY_CHANNELS.GET_WINDOW_METRICS_SYNC, (event) => { event.returnValue = null; });

  function connectMainWs() {
    observations.mainWsEvents.push('connecting');
    try {
      mainWs = new WebSocket(WS_URL);
    } catch (err) {
      observations.mainWsEvents.push('ctor failed: ' + (err && err.message));
      return;
    }
    mainWs.addEventListener('open', () => {
      observations.mainWsEvents.push('open');
      observations.readyBroadcasts += 1;
      broadcast(WS_PROXY_CHANNELS.READY);
      // 真 Electron 里复验「重复 READY 只派一次 open」：Pet 重连时会晚到一条
      setTimeout(() => {
        observations.readyBroadcasts += 1;
        broadcast(WS_PROXY_CHANNELS.READY);
      }, 300);
    });
    mainWs.addEventListener('message', (event) => {
      const data = typeof event.data === 'string' ? event.data : String(event.data);
      observations.mainWsEvents.push('message:' + data.slice(0, 80));
      broadcast(WS_PROXY_CHANNELS.RAW_MESSAGE, data);
    });
    mainWs.addEventListener('close', (event) => {
      observations.mainWsEvents.push('close:' + event.code);
      broadcast(WS_PROXY_CHANNELS.CLOSED, { code: event.code, reason: event.reason });
    });
    mainWs.addEventListener('error', () => {
      observations.mainWsEvents.push('error');
    });
  }

  // 页面先起 socket、再让真 WS 就绪：模拟「页面加载时 Pet WS 还没 ready」的真实时序
  wc.once('did-finish-load', () => {
    if (MODE === 'react-chat') {
      // React Chat 的 WSProxy 比桥工厂多两件事，必须单独验：
      // ① 页面建连前到达的 READY + greeting 要先缓冲、建连后补发（chat.html 首条 greeting 丢失的修复）；
      // ② 切档案时上一代真 WS 的 CLOSED 带旧 sessionEpoch，不能砸掉新一代代理。
      // 页面侧 testReactChat 会先等 1200ms 再建连，这 400ms 的广播就落在「构造前」。
      setTimeout(() => {
        observations.preconstructBroadcast = true;
        broadcast(WS_PROXY_CHANNELS.CONNECTING, { sessionEpoch: 1, generation: 1 });
        broadcast(WS_PROXY_CHANNELS.READY, { sessionEpoch: 1, generation: 1 });
        broadcast(WS_PROXY_CHANNELS.RAW_MESSAGE, 'greeting-preconstruct');
      }, 400);
      // 旧代际的 CLOSED：页面此时已 OPEN，必须按 stale 丢弃。
      setTimeout(() => {
        observations.staleClosedBroadcast = true;
        broadcast(WS_PROXY_CHANNELS.CLOSED, {
          code: 1006, reason: 'stale', sessionEpoch: 0, generation: 0,
        });
      }, 1500);
      // 真 WS 在页面建连之后才就绪：页面会收到重复 READY（应被忽略）。
      setTimeout(connectMainWs, 1800);
      return;
    }
    if (MODE === 'react-chat-api') {
      // P2 只验 A 组 API 暴露，页面不建连：保持零 RAW_SEND 才是「没动运输层」的证据。
      return;
    }
    setTimeout(() => {
      observations.staleClosedBroadcast = true;
      broadcast(WS_PROXY_CHANNELS.CLOSED, { code: 1006, reason: 'stale' });
    }, 1200);
    setTimeout(connectMainWs, 2500);
  });
  wc.once('did-fail-load', (_e, code, desc) => {
    observations.error = 'did-fail-load ' + code + ' ' + desc;
    finish(1);
  });

  const pageUrl =
    'http://127.0.0.1:' + port +
    (PAGE_OVERRIDE || '/neko-electron-shell/tests/runtime/bridge-e2e.page.html') +
    '?mode=' + encodeURIComponent(MODE) +
    '&ws=' + encodeURIComponent(WS_URL);
  observations.pageUrl = pageUrl;

  win.loadURL(pageUrl).catch((err) => {
    observations.error = 'loadURL failed: ' + (err && err.message);
    finish(1);
  });


  setTimeout(() => {
    if (!observations.pageReport) {
      observations.error = observations.error || 'timeout waiting for page report';
      finish(1);
    }
  }, 25000);
}

app.whenReady().then(main).catch((err) => {
  observations.error = String(err && err.stack ? err.stack : err);
  finish(1);
});

app.on('window-all-closed', () => {
  if (!finish.done) finish(1);
});
