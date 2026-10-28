'use strict';

/**
 * 页面侧探针。结果用 `HARNESS_RESULT <json>` 打到 console，由主进程收集。
 * 不依赖任何 bridge / preload 暴露的调试通道，所以同一个文件能跑三种场景。
 */

(function () {
  var params = new URLSearchParams(location.search);
  var MODE = params.get('mode') || 'bridge';
  var WS_URL = params.get('ws');
  var checks = [];

  function check(name, pass, detail) {
    checks.push({ name: name, pass: !!pass, detail: detail });
  }

  function waitFor(describe, predicate, timeoutMs) {
    return new Promise(function (resolve) {
      var started = Date.now();
      (function tick() {
        var value;
        try {
          value = predicate();
        } catch (err) {
          resolve({ ok: false, elapsed: Date.now() - started, error: String(err && err.message) });
          return;
        }
        if (value) {
          resolve({ ok: true, elapsed: Date.now() - started, value: value });
          return;
        }
        if (Date.now() - started >= timeoutMs) {
          resolve({ ok: false, elapsed: Date.now() - started, error: 'timeout: ' + describe });
          return;
        }
        setTimeout(tick, 25);
      })();
    });
  }

  function isNativeWebSocket() {
    try {
      return String(window.WebSocket).indexOf('[native code]') >= 0;
    } catch (err) {
      return 'err';
    }
  }

  function report(extra) {
    var payload = {
      mode: MODE,
      isolation: window.process && typeof window.process.contextIsolated === 'boolean'
        ? window.process.contextIsolated
        : null,
      userAgentIsElectron: /Electron\//.test(navigator.userAgent),
      checks: checks,
      pass: checks.every(function (c) { return c.pass; }),
    };
    Object.keys(extra || {}).forEach(function (k) { payload[k] = extra[k]; });
    console.log('HARNESS_RESULT ' + JSON.stringify(payload));
  }

  async function testFallback() {
    check('adapter 已加载（window.__nekoCreateWebSocket）',
      typeof window.__nekoCreateWebSocket === 'function');
    check('没有 bridge（浏览器直开 / 未隔离窗口）',
      typeof window.nekoWebSocket === 'undefined', typeof window.nekoWebSocket);

    var opened = false;
    var received = [];
    var sock = window.__nekoCreateWebSocket(WS_URL);
    check('无 bridge 时回退原生 WebSocket', sock instanceof window.WebSocket);
    sock.onopen = function () { opened = true; };
    sock.onmessage = function (event) { received.push(String(event.data)); };
    var openWait = await waitFor('open', function () { return opened; }, 6000);
    check('原生回退能连上', openWait.ok, openWait.ok ? openWait.elapsed + 'ms' : openWait.error);
    if (openWait.ok) {
      sock.send('fallback-1');
      var msg = await waitFor('message', function () { return received.length > 0; }, 5000);
      check('原生回退消息往返（事件是页面世界原生对象）', msg.ok && received[0] === 'echo:fallback-1',
        received[0] || msg.error);
      sock.close(1000, 'done');
    }
    report({});
  }

  async function testBridge() {
    check('adapter 已加载（window.__nekoCreateWebSocket）',
      typeof window.__nekoCreateWebSocket === 'function');
    check('bridge 已暴露（window.nekoWebSocket.create）',
      !!(window.nekoWebSocket && typeof window.nekoWebSocket.create === 'function'),
      typeof window.nekoWebSocket);
    check('页面全局 WebSocket 未被替换（本场景 preload 不碰它）',
      isNativeWebSocket() === true, String(window.WebSocket).slice(0, 60));

    if (typeof window.__nekoCreateWebSocket !== 'function') {
      report({ fatal: 'adapter missing' });
      return;
    }

    var openFromOnOpen = false;
    var openFromListener = false;
    var openCount = 0;
    var openEventShape = null;
    var messagesOnHandler = [];
    var messagesFromListener = [];
    var messageEventShape = null;
    var closeEvent = null;
    // 非 ASCII + 多字节 reason：既验结构化克隆（页面→preload→页面 两次过桥），
    // 也验页面世界 CloseEvent 构造器接受非 ASCII（< 123 字节，不触发上限回退）。
    var CLOSE_REASON = '连接已断开';

    var sock = window.__nekoCreateWebSocket(WS_URL);
    check('适配器返回对象（不是桥的裸句柄）', !!sock && typeof sock.send === 'function');
    check('建连瞬间 readyState = 0（CONNECTING）', sock.readyState === 0, sock.readyState);

    sock.onopen = function (event) {
      openFromOnOpen = true;
      openCount += 1;
      openEventShape = { kind: typeof event, type: event && event.type, keys: event ? Object.keys(event) : null };
    };
    sock.addEventListener('open', function () { openFromListener = true; });
    sock.onmessage = function (event) {
      messageEventShape = {
        kind: typeof event,
        type: event && event.type,
        dataType: event && typeof event.data,
        keys: event ? Object.keys(event) : null,
      };
      messagesOnHandler.push(String(event && event.data));
    };
    sock.addEventListener('message', function (event) {
      messagesFromListener.push(String(event && event.data));
    });
    sock.onclose = function (event) {
      closeEvent = {
        kind: typeof event,
        type: event && event.type,
        code: event && event.code,
        reason: event && event.reason,
        isCloseEventInstance: typeof window.CloseEvent === 'function'
          ? event instanceof window.CloseEvent
          : null,
        keys: event ? Object.keys(event) : null,
      };
    };

    var opened = await waitFor('readyState → 1', function () {
      return sock.readyState === 1;
    }, 15000);
    check('onopen 赋值生效（桥不支持赋值，适配器必须补）', openFromOnOpen === true);
    check('addEventListener("open") 也收到', openFromListener === true);
    check('readyState 在 open 后为活值 1', opened.ok, opened.ok ? opened.elapsed + 'ms' : opened.error);
    check('关闭前没有误触发 close（CONNECTING 吃掉 stale CLOSED 会在这里露馅）',
      closeEvent === null, JSON.stringify(closeEvent));
    check('重复 READY 只派一次 open', openCount === 1, 'openCount=' + openCount);

    if (opened.ok) {
      sock.send('ping-1');
      var got = await waitFor('message', function () {
        return messagesOnHandler.length > 0;
      }, 5000);
      check('send → 主进程真 WS → 回显', got.ok, messagesOnHandler[0] || got.error);
      check('回显内容正确', messagesOnHandler[0] === 'echo:ping-1', messagesOnHandler[0]);
      var got2 = await waitFor('listener message', function () {
        return messagesFromListener.length > 0;
      }, 2000);
      check('addEventListener("message") 也收到', got2.ok, messagesFromListener[0] || got2.error);

      sock.close(4001, CLOSE_REASON);
      var closed = await waitFor('readyState → 3', function () {
        return sock.readyState === 3;
      }, 5000);
      check('close 后 readyState = 3', closed.ok, closed.ok ? closed.elapsed + 'ms' : closed.error);
      check('close 事件带 code/reason', !!closeEvent && closeEvent.code === 4001,
        JSON.stringify(closeEvent));
      check('close 的 reason 原样保留（非 ASCII 两次过桥）',
        !!closeEvent && closeEvent.reason === CLOSE_REASON, JSON.stringify(closeEvent));
      check('close 事件是页面世界 CloseEvent 实例（不是裸对象）',
        !!closeEvent && closeEvent.isCloseEventInstance === true, JSON.stringify(closeEvent));
      var threw = false;
      try { sock.send('after-close'); } catch (err) { threw = true; }
      check('close 后 send 静默丢弃（不抛）', threw === false);

      // —— 两条 close 边界：
      // ① 200 字节 reason：实测 Chromium 148 的 CloseEvent 构造器**不吃** 123 字节上限，
      //    所以这里断言的是「原样保留」，不是回退（123 限制只管 WebSocket.close 的网络路径）。
      // ② code 1006（异常断线）：实测 Chromium 148 连保留码也不拒（见 docs §2.5），
      //    所以这条只钉「异常码原样交付」；回退分支另用强制抛错验证（③）。
      console.log('HARNESS_PHASE long-close');
      var LONG_REASON = new Array(201).join('x'); // 200 字节 ASCII，稳定超过 123
      var longClosed = null;
      var sock2 = window.__nekoCreateWebSocket(WS_URL);
      sock2.onclose = function (event) {
        longClosed = {
          type: event && event.type,
          code: event && event.code,
          reasonLength: event && event.reason ? event.reason.length : 0,
          reasonMatches: event && event.reason === LONG_REASON,
          isCloseEventInstance: typeof window.CloseEvent === 'function'
            ? event instanceof window.CloseEvent
            : null,
        };
      };
      var opened2 = await waitFor('second readyState → 1', function () {
        return sock2.readyState === 1;
      }, 8000);
      check('第二条连接能 open（主进程收到 HARNESS_PHASE 后补发 READY）', opened2.ok,
        opened2.ok ? opened2.elapsed + 'ms' : opened2.error);
      if (opened2.ok) {
        sock2.close(4002, LONG_REASON);
        var closed2 = await waitFor('second close', function () { return longClosed !== null; }, 5000);
        check('200 字节 reason 原样保留（Chromium CloseEvent 构造器不设 123 上限）',
          closed2.ok && longClosed.reasonMatches && longClosed.reasonLength === 200,
          JSON.stringify(longClosed));
        check('200 字节 reason 走的是真实 CloseEvent 实例', closed2.ok && longClosed.isCloseEventInstance === true,
          JSON.stringify(longClosed));
        check('第二条连接的 code 正确', closed2.ok && longClosed.code === 4002, JSON.stringify(longClosed));
        check('第二条连接 close 后 readyState = 3', sock2.readyState === 3, sock2.readyState);

        // ② 异常断线 code 1006 —— 主进程代持的「Pet WS」异常关闭时就是这个码
        console.log('HARNESS_PHASE abnormal-close');
        var abnormal = null;
        var sock3 = window.__nekoCreateWebSocket(WS_URL);
        sock3.onclose = function (event) {
          abnormal = {
            type: event && event.type,
            code: event && event.code,
            reason: event && event.reason,
            isCloseEventInstance: typeof window.CloseEvent === 'function'
              ? event instanceof window.CloseEvent
              : null,
          };
        };
        var opened3 = await waitFor('third readyState → 1', function () {
          return sock3.readyState === 1;
        }, 8000);
        check('第三条连接能 open', opened3.ok, opened3.ok ? opened3.elapsed + 'ms' : opened3.error);
        if (opened3.ok) {
          var closed3 = await waitFor('third close', function () { return abnormal !== null; }, 5000);
          // 实测：Chromium 148 的 CloseEvent 构造器连 1006 都不拒（见 docs 运行时记录 §2.5），
          // 所以这里只钉「异常码原样交付」，不断言回退。
          check('code 1006 原样交付给页面', closed3.ok && abnormal.code === 1006, JSON.stringify(abnormal));
          check('异常断线的 reason 保留', closed3.ok && abnormal.reason === 'abnormal', JSON.stringify(abnormal));
          check('第三条连接收到 CLOSED 后 readyState = 3', sock3.readyState === 3, sock3.readyState);

          // ③ 回退分支：若运行时 CloseEvent 构造器抛错（旧 Chromium / 未来收紧校验），
          // 适配器的 catch 必须兜住，否则异常会冒到桥的 fire() 里被吞掉 ⇒ 页面永远收不到 close。
          // 这里在页面世界把构造器换成必抛版本，验证兜底路径本身。
          var RealCloseEvent = window.CloseEvent;
          window.CloseEvent = function CloseEvent() { throw new TypeError('forced for fallback test'); };
          console.log('HARNESS_PHASE forced-ctor-throw');
          var forced = null;
          var sock4 = window.__nekoCreateWebSocket(WS_URL);
          sock4.onclose = function (event) {
            forced = {
              type: event && event.type,
              code: event && event.code,
              reason: event && event.reason,
              isCloseEventInstance: event instanceof RealCloseEvent,
            };
          };
          var opened4 = await waitFor('fourth readyState → 1', function () {
            return sock4.readyState === 1;
          }, 8000);
          check('第四条连接能 open', opened4.ok, opened4.ok ? opened4.elapsed + 'ms' : opened4.error);
          if (opened4.ok) {
            var closed4 = await waitFor('fourth close', function () { return forced !== null; }, 5000);
            check('CloseEvent 构造器抛错时回退成普通对象', closed4.ok && forced.isCloseEventInstance === false,
              JSON.stringify(forced));
            check('回退对象 code = 4003', closed4.ok && forced.code === 4003, JSON.stringify(forced));
            check('回退对象 reason = forced', closed4.ok && forced.reason === 'forced', JSON.stringify(forced));
            check('回退后 readyState = 3', sock4.readyState === 3, sock4.readyState);
          }
          window.CloseEvent = RealCloseEvent;
        }
      }
    }

    report({
      eventShapes: {
        open: openEventShape,
        message: messageEventShape,
        close: closeEvent,
      },
    });
  }

  async function testChatProxy() {
    // 装配后两臂都是「preload 暴露桥 + 页面适配器」，页面全局必须保持原生。
    check('页面全局 WebSocket 是原生（preload 不再替换构造器）',
      isNativeWebSocket() === true, String(window.WebSocket).slice(0, 60));
    check('bridge 已暴露（window.nekoWebSocket.create）',
      !!(window.nekoWebSocket && typeof window.nekoWebSocket.create === 'function'),
      typeof window.nekoWebSocket);
    check('适配器已加载（window.__nekoCreateWebSocket）',
      typeof window.__nekoCreateWebSocket === 'function');
    // chat.html 的布局门禁读这两个全局；隔离后它们也必须过桥，否则 full/compact 版式会退回浏览器分支。
    check('window.nekoChatWindow 已过桥（含 getBounds/setBounds）',
      !!(window.nekoChatWindow
        && typeof window.nekoChatWindow.getBounds === 'function'
        && typeof window.nekoChatWindow.setBounds === 'function'),
      typeof window.nekoChatWindow);
    check('window.__NEKO_STANDALONE_CHAT__ 已过桥且为 true',
      window.__NEKO_STANDALONE_CHAT__ === true, String(window.__NEKO_STANDALONE_CHAT__));

    // ---- 页面桥：toast 必须由页面 shim 接到宿主（隔离态 preload 写不到页面 window）----
    check('showStatusToast 已由页面 shim 接到宿主', typeof window.showStatusToast === 'function',
      typeof window.showStatusToast);
    try { window.showStatusToast('wo278-toast', 1200, { important: false }); } catch (_) {}

    // ---- 页面桥：设置同步两个方向 ----
    window.appState = { proactiveChatEnabled: false, textGuardMaxLength: 100 };
    var originalSave = function () {};
    window.saveNEKOSettings = originalSave;
    var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
    await sleep(800);
    check('saveNEKOSettings 已被页面 shim hook', window.saveNEKOSettings !== originalSave,
      String(window.saveNEKOSettings).slice(0, 40));

    var receivedSettings = false;
    if (window.saveNEKOSettings !== originalSave) {
      try { window.saveNEKOSettings(); } catch (_) {}
      // 主进程收到 SYNC 后回发一个可识别值，验证「接收 → 页面世界生效」这一半。
      console.log('HARNESS_PHASE settings-echo');
      var applied = await waitFor('settings echo', function () {
        return window.textGuardMaxLength === 4242;
      }, 5000);
      receivedSettings = applied.ok;
      check('主进程下发的设置已应用到页面 world（window.textGuardMaxLength=4242）',
        applied.ok, applied.ok ? 'ok' : applied.error);
      check('同一份设置也写进了页面 appState',
        !!(window.appState && window.appState.textGuardMaxLength === 4242),
        window.appState && window.appState.textGuardMaxLength);
    }

    var events = [];
    var opened = false;
    var received = [];
    var sock = window.__nekoCreateWebSocket(WS_URL);
    check('适配器返回对象（不是桥的裸句柄）', !!sock && typeof sock.send === 'function');
    check('socket.url 保留（app-websocket 的幂等守卫要用）', sock.url === WS_URL, sock.url);
    sock.onopen = function () { opened = true; events.push('open'); };
    sock.onmessage = function (event) { received.push(String(event.data)); };
    sock.onclose = function () { events.push('close'); };

    var openWait = await waitFor('socket open', function () { return opened; }, 12000);
    check('socket 能 open（桥 → IPC → 主进程真 WS）', openWait.ok,
      openWait.ok ? openWait.elapsed + 'ms' : openWait.error);

    if (openWait.ok) {
      sock.send('msg-1');
      var msg = await waitFor('message', function () { return received.length > 0; }, 6000);
      check('send 有结果回来', msg.ok, received[0] || msg.error);
      check('回显内容正确', received[0] === 'echo:msg-1', received[0]);
      check('readyState 是活值（open 后 = 1）', sock.readyState === 1, sock.readyState);
    }

    try { sock.close(4000, 'done'); } catch (_) {}

    report({
      // 运输方式的判据在主进程：装配后两臂 rawSendCount 都应为 1。
      observed: {
        nativeWebSocket: isNativeWebSocket(),
        receivedSettings: receivedSettings,
        openMs: openWait.ok ? openWait.elapsed : null,
        events: events,
      },
    });
  }

  async function testReactChat() {
    // P1：preload-chat-react.js 不再替换 window.WebSocket，只暴露 nekoWebSocket。
    // 这一场景还额外钉住 WSProxy 引擎（而非简化桥）带来的两条生产语义：
    // 构造前 READY/greeting 缓冲、旧 sessionEpoch 的 CLOSED 丢弃。
    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

    check('adapter 已加载（window.__nekoCreateWebSocket）',
      typeof window.__nekoCreateWebSocket === 'function');
    check('bridge 已暴露（window.nekoWebSocket.create）',
      !!(window.nekoWebSocket && typeof window.nekoWebSocket.create === 'function'),
      typeof window.nekoWebSocket);
    check('页面全局 WebSocket 未被替换（preload 不再写构造器）',
      isNativeWebSocket() === true, String(window.WebSocket).slice(0, 60));

    if (typeof window.__nekoCreateWebSocket !== 'function'
      || !(window.nekoWebSocket && typeof window.nekoWebSocket.create === 'function')) {
      report({ fatal: 'react-chat bridge missing' });
      return;
    }

    // 主进程在 400ms 就广播 CONNECTING + READY + greeting；这里推迟到 1200ms 才建连，
    // 让 READY/greeting 落在「页面构造之前」。
    await sleep(1200);
    var sock = window.__nekoCreateWebSocket(WS_URL);
    check('适配器返回对象（不是桥的裸句柄）', !!sock && typeof sock.send === 'function');
    check('建连瞬间 readyState = 0（CONNECTING，即使 READY 已缓冲）', sock.readyState === 0, sock.readyState);
    check('socket.url 保留（app-websocket 的幂等守卫要用）', sock.url === WS_URL, sock.url);

    var opened = false;
    var openCount = 0;
    var fromHandler = [];
    var fromListener = [];
    var removedHits = 0;
    var closeEvent = null;

    sock.onopen = function () { opened = true; openCount += 1; };
    sock.addEventListener('open', function () {});
    sock.onmessage = function (event) { fromHandler.push(String(event && event.data)); };
    function removedListener() { removedHits += 1; }
    sock.addEventListener('message', removedListener);
    sock.removeEventListener('message', removedListener);
    sock.addEventListener('message', function (event) { fromListener.push(String(event && event.data)); });
    sock.onclose = function (event) {
      closeEvent = {
        type: event && event.type,
        code: event && event.code,
        reason: event && event.reason,
        isCloseEventInstance: typeof window.CloseEvent === 'function'
          ? event instanceof window.CloseEvent
          : null,
      };
    };

    var openWait = await waitFor('constructor-buffered open', function () { return opened; }, 8000);
    check('构造前缓冲的 READY 生效（Pet WS 早于页面建连）', openWait.ok,
      openWait.ok ? openWait.elapsed + 'ms' : openWait.error);
    check('构造前到达的 greeting 没丢', fromHandler[0] === 'greeting-preconstruct', fromHandler[0]);
    check('readyState 在 open 后为活值 1', sock.readyState === 1, sock.readyState);

    // 等真 WS（1800ms）就绪并吃掉它补发的 READY（+300ms）与旧代际 CLOSED（1500ms）。
    await sleep(1400);
    check('旧 sessionEpoch 的 CLOSED 未触发 close', closeEvent === null, JSON.stringify(closeEvent));
    check('重复 READY 只派一次 open', openCount === 1, 'openCount=' + openCount);

    if (openWait.ok) {
      sock.send('ping-1');
      var got = await waitFor('echo', function () { return fromHandler.length > 1; }, 6000);
      check('send → IPC → 主进程真 WS → 回显', got.ok,
        got.ok ? fromHandler[fromHandler.length - 1] : got.error);
      check('回显内容正确', fromHandler.indexOf('echo:ping-1') >= 0, fromHandler.join(','));
      var got2 = await waitFor('listener echo', function () {
        return fromListener.indexOf('echo:ping-1') >= 0;
      }, 2000);
      check('addEventListener("message") 也收到', got2.ok, fromListener.join(','));
      check('removeEventListener 跨世界仍按同一引用生效', removedHits === 0, 'removedHits=' + removedHits);

      sock.close(4001, 'react-done');
      var closed = await waitFor('close', function () { return sock.readyState === 3; }, 5000);
      check('close 后 readyState = 3', closed.ok, closed.ok ? closed.elapsed + 'ms' : closed.error);
      check('close 事件带 code/reason（页面世界 CloseEvent 实例）',
        !!closeEvent && closeEvent.code === 4001 && closeEvent.reason === 'react-done'
        && closeEvent.isCloseEventInstance === true, JSON.stringify(closeEvent));
      var threw = false;
      try { sock.send('after-close'); } catch (_) { threw = true; }
      check('close 后 send 静默丢弃（不抛）', threw === false);
    }

    report({
      observed: {
        nativeWebSocket: isNativeWebSocket(),
        openCount: openCount,
        greeting: fromHandler[0] || null,
        handlerMessages: fromHandler,
      },
    });
  }

  async function testReactChatApi() {
    // P2：A 组 API 对象暴露。重点不是「窗口控制能不能用」（非隔离时一直能用），
    // 而是隔离态下页面拿到的是 exposeLiveFacade 门面：晚挂方法名先预留、实现晚到也能命中。
    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
    var FACADE_METHODS = [
      'getBounds', 'getWorkArea', 'setPosition', 'setSize', 'setBounds', 'setResizable',
      'bringToFront', 'dragStart', 'dragStop', 'dragStopAndGetBounds',
      'resizeStart', 'resizeStop', 'collapse', 'expand', 'enableInteraction',
      'setCompactChatBallTemporarilyHidden',
      // setupReactChatDomInterceptors 里才补挂的 5 个：
      'isCollapsed', 'idleDockCollapse', 'idleDockExpand',
      'idleDockCommitCollapsedBounds', 'ensureExpandedForTutorial',
    ];

    // 页面脚本在解析期执行：preload 的门面已暴露，但 impl 上的晚挂方法还没有。
    var earlyCallable = typeof (window.nekoChatWindow && window.nekoChatWindow.isCollapsed) === 'function';
    var earlyValue;
    try {
      earlyValue = earlyCallable ? window.nekoChatWindow.isCollapsed() : 'not-a-function';
    } catch (err) {
      earlyValue = 'threw: ' + (err && err.message);
    }
    check('nekoChatWindow 在页面脚本执行时已暴露', !!window.nekoChatWindow, typeof window.nekoChatWindow);
    check('门面暴露时就预留了晚挂方法名（isCollapsed）', earlyCallable === true, typeof earlyValue);
    check('晚挂方法此刻还没落地（返回 undefined ⇒ 门面是活的，不是静态快照）',
      earlyValue === undefined, String(earlyValue));

    if (!window.nekoChatWindow) {
      report({ fatal: 'nekoChatWindow missing' });
      return;
    }

    if (document.readyState === 'loading') {
      await new Promise(function (resolve) {
        document.addEventListener('DOMContentLoaded', function () { resolve(); }, { once: true });
      });
    }
    await sleep(300);

    var keys = window.nekoChatWindow ? Object.keys(window.nekoChatWindow) : [];
    var missing = FACADE_METHODS.filter(function (name) { return keys.indexOf(name) < 0; });
    check('门面方法名齐全（21 个）', missing.length === 0, 'missing=' + missing.join(','));
    check('门面上每个名字都是函数', FACADE_METHODS.every(function (name) {
      return window.nekoChatWindow && typeof window.nekoChatWindow[name] === 'function';
    }));

    var lateCollapsed = typeof window.nekoChatWindow.isCollapsed === 'function'
      ? window.nekoChatWindow.isCollapsed()
      : 'not-a-function';
    check('晚挂的 isCollapsed 已接通（false 布尔，不再是 undefined）',
      lateCollapsed === false, String(lateCollapsed));
    var lateTutorial = typeof window.nekoChatWindow.ensureExpandedForTutorial === 'function'
      ? window.nekoChatWindow.ensureExpandedForTutorial()
      : 'not-a-function';
    check('晚挂的 ensureExpandedForTutorial 已接通（未折叠/不忙 → false）',
      lateTutorial === false, String(lateTutorial));

    check('__NEKO_MULTI_WINDOW__ 为 true', window.__NEKO_MULTI_WINDOW__ === true,
      String(window.__NEKO_MULTI_WINDOW__));
    check('nekoWebSocket 仍在（P1 未回退）',
      !!(window.nekoWebSocket && typeof window.nekoWebSocket.create === 'function'));
    check('页面全局 WebSocket 仍是原生（P1 未回退）', isNativeWebSocket() === true,
      String(window.WebSocket).slice(0, 60));

    var capturerMethods = ['getSources', 'setSelectedSource', 'captureSourceAsDataUrl',
      'captureSourceWithoutNeko', 'hideNekoWindows', 'restoreNekoWindows'];
    check('electronDesktopCapturer 6 个方法齐全', !!window.electronDesktopCapturer
      && capturerMethods.every(function (name) {
        return typeof window.electronDesktopCapturer[name] === 'function';
      }), typeof window.electronDesktopCapturer);
    check('nekoScreenshotProxy.request 可调',
      !!(window.nekoScreenshotProxy && typeof window.nekoScreenshotProxy.request === 'function'));
    check('nekoSubtitleWindow 3 个方法齐全', !!window.nekoSubtitleWindow
      && ['setEnabled', 'show', 'hide'].every(function (name) {
        return typeof window.nekoSubtitleWindow[name] === 'function';
      }), typeof window.nekoSubtitleWindow);
    check('__nekoJukeboxToggle 可调', typeof window.__nekoJukeboxToggle === 'function');
    check('__nekoRequestConfigInjection 可调', typeof window.__nekoRequestConfigInjection === 'function');
    check('__nekoRequestAvatarPreview 可调', typeof window.__nekoRequestAvatarPreview === 'function');
    check('__nekoFocusReactChatInputFromHotkey 可调（热键走 executeJavaScript 读页面世界）',
      typeof window.__nekoFocusReactChatInputFromHotkey === 'function');

    // ---- invoke 往返：页面拿到的值必须是主进程桩值，否则调用被某个世界短路了 ----
    var bounds = await window.nekoChatWindow.getBounds();
    check('getBounds() 过 IPC 返回主进程桩值', !!bounds
      && bounds.x === 120 && bounds.y === 80 && bounds.width === 520 && bounds.height === 680,
      JSON.stringify(bounds));
    var workArea = await window.nekoChatWindow.getWorkArea();
    check('getWorkArea() 过 IPC', !!workArea && workArea.width === 1920, JSON.stringify(workArea));
    var dragStop = await window.nekoChatWindow.dragStopAndGetBounds({ reason: 'p2' });
    check('dragStopAndGetBounds() 过 IPC', !!dragStop && dragStop.x === 130, JSON.stringify(dragStop));

    var collapseTarget = { x: 7, y: 7, width: 88, height: 88 };
    var collapsedRet = await window.nekoChatWindow.collapse(collapseTarget);
    check('collapse() 参数过桥后原样回显', !!collapsedRet
      && collapsedRet.x === 7 && collapsedRet.width === 88, JSON.stringify(collapsedRet));
    var expandTarget = { x: 120, y: 80, width: 520, height: 680 };
    var expandedRet = await window.nekoChatWindow.expand(expandTarget);
    check('expand() 参数过桥后原样回显', !!expandedRet
      && expandedRet.x === 120 && expandedRet.width === 520, JSON.stringify(expandedRet));

    var sources = await window.electronDesktopCapturer.getSources({ types: ['window'] });
    check('getSources() 过 IPC 且 options 随行', Array.isArray(sources) && sources.length === 1
      && sources[0].id === 'screen:0:0' && sources[0].types
      && sources[0].types[0] === 'window', JSON.stringify(sources));
    var selected = await window.electronDesktopCapturer.setSelectedSource('screen:0:0');
    check('setSelectedSource() 回显 id', selected === 'screen:0:0', String(selected));
    var dataUrl = await window.electronDesktopCapturer.captureSourceAsDataUrl('screen:0:0');
    check('captureSourceAsDataUrl() 返回主进程桩',
      dataUrl === 'data:image/png;base64,AAAA', String(dataUrl));
    var withoutNeko = await window.electronDesktopCapturer.captureSourceWithoutNeko('screen:0:0');
    check('captureSourceWithoutNeko() 返回主进程桩',
      withoutNeko === 'data:image/png;base64,BBBB', String(withoutNeko));
    var hiddenIds = await window.electronDesktopCapturer.hideNekoWindows();
    check('hideNekoWindows() 返回 id 列表',
      Array.isArray(hiddenIds) && hiddenIds[0] === 101, JSON.stringify(hiddenIds));
    var restored = await window.electronDesktopCapturer.restoreNekoWindows([101]);
    check('restoreNekoWindows() 过 IPC', restored === true, String(restored));

    // ---- send 系列：页面不抛，参数由主进程逐条对账（apiCheck）----
    var sendThrew = null;
    try {
      window.nekoChatWindow.setPosition(11, 22);
      window.nekoChatWindow.setSize(555, 444);
      window.nekoChatWindow.setBounds(11, 22, 555, 444);
      window.nekoChatWindow.setResizable(false, { reason: 'p2' });
      window.nekoChatWindow.bringToFront();
      window.nekoChatWindow.dragStart({ reason: 'p2' });
      window.nekoChatWindow.dragStop({ reason: 'p2' });
      window.nekoChatWindow.resizeStart('se', { minWidth: 300, minHeight: 200 });
      window.nekoChatWindow.resizeStop();
      window.nekoChatWindow.enableInteraction();
      window.nekoChatWindow.setCompactChatBallTemporarilyHidden(true);
      window.nekoScreenshotProxy.request();
      window.nekoSubtitleWindow.setEnabled(true);
      window.nekoSubtitleWindow.show();
      window.nekoSubtitleWindow.hide();
      window.__nekoJukeboxToggle();
      window.__nekoRequestConfigInjection();
      window.__nekoRequestAvatarPreview();
    } catch (err) {
      sendThrew = String(err && err.message);
    }
    check('17 个 send 型调用在页面世界都不抛', sendThrew === null, sendThrew);

    var hotkeyResult = window.__nekoFocusReactChatInputFromHotkey();
    check('__nekoFocusReactChatInputFromHotkey() 走 impl（裸页面无输入框 → 排一次重试，返回 true）',
      hotkeyResult === true, String(hotkeyResult));

    await sleep(300);
    report({
      observed: {
        facadeKeys: keys,
        earlyValue: String(earlyValue),
        lateCollapsed: lateCollapsed,
        lateTutorial: lateTutorial,
        hotkeyResult: hotkeyResult,
      },
    });
  }

  var runner = MODE === 'bridge'
    ? testBridge
    : (MODE === 'fallback'
      ? testFallback
      : (MODE === 'react-chat'
        ? testReactChat
        : (MODE === 'react-chat-api' ? testReactChatApi : testChatProxy)));
  runner().catch(function (err) {
    check('探针自身未抛异常', false, String(err && err.stack ? err.stack : err).slice(0, 300));
    report({ fatal: String(err && err.message) });
  });
})();
