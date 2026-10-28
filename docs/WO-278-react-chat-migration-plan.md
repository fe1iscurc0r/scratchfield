# WO-278 续：React Chat 窗隔离迁移清单（2026-10-26）

## 0. 结论

`createReactChatWindow`（`window-manager.js:1909`，`contextIsolation:false`）是**运行时唯一有意义的
聊天窗**。它的 preload `preload-chat-react.js`（8124 行）跨世界耦合面可归成 5 组：

| 组 | 内容 | 处数 | 迁移难度 |
|---|---|---|---|
| A 只读 API 对象 | 页面调 preload 的方法集合 | 9 个对象 / 33 个方法 | 低（`exposeInMainWorld` 直接可用） |
| B 状态镜像 | preload 写、页面读的全局 | 9 个名字 | 中（`contextBridge` 属性是快照，需 getter 门面） |
| C 反向钩子 | preload 读/调页面函数 | 4 处 | 中（需要页面→preload 的反向通道） |
| D 页面状态被 preload 改 | realistic 队列 + 气泡 | 1 处 4 个全局 | 高（逻辑要搬到页面侧） |
| E 跨世界事件 | preload `dispatchEvent` 10 处；页面回传 2 个 CustomEvent | 12 | 低（沿用 `makePageEvent` 重建） |

页面就是 `templates/chat.html`（`pages_router.py:489`），已经加载 `ws-adapter.js` +
`electron-page-bridge.js` + `app-websocket.js`（WO-278 装配已做），所以 WS 运输那一步是现成的。

## 1. 分组明细

### A. preload → 页面的 API 对象（`exposeInMainWorld` 可直传）

| 页面全局 | 定义处 | 页面侧引用 |
|---|---|---|
| `nekoChatWindow`（15 方法，另有 `isCollapsed`/`idleDock*` 运行时补挂） | `:375`，补挂 `:6613/:6617/:6712/:6762` | 10 文件 / 20 次 |
| `electronDesktopCapturer`（7 方法） | `:406` | 2 文件 / 4 次 |
| `nekoScreenshotProxy`（1 方法 + `neko:screenshot-result`） | `:416` | 1 文件 / 2 次 |
| `nekoSubtitleWindow`（3 方法） | `:423` | 3 文件 / 13 次 |
| `__nekoJukeboxToggle` | `:451` | 3 文件 / 12 次 |
| `__nekoRequestConfigInjection` | `:937` | 1 文件 / 3 次 |
| `__nekoRequestAvatarPreview` | `:954` | 2 文件 / 6 次 |
| `__nekoFocusReactChatInputFromHotkey` | `:6822` | 主进程注入调用（`hotkey-manager.js:830`） |
| `__nekoGetAvatarToolClientScreenPoint` / `…ScreenClientPoint` | `:2136` / `:2149` | 仅 preload 内部 + 主进程可注入 |

注意 `nekoChatWindow` 上的 `idleDock*` 是后补挂的方法，`exposeInMainWorld` 传的对象在页面侧被
冻结属性形状；补挂要么在暴露前完成，要么走 B 组 getter 门面。

### B. preload 写、页面读的状态（不能直接 `exposeInMainWorld` 静态值）

| 页面全局 | preload 写入处 | 页面读 |
|---|---|---|
| `__nekoDesktopCompactLayout` | 27 处（`:3738/:3779/:7066` …） | 8 文件 |
| `__nekoDesktopAvatarBounds` | `:1918/:3739/:3778` | 4 文件（`app-react-chat-window/*`） |
| `__nekoDesktopCompactBallScreenRect` | `:1633/:1645/:3742` | 1 文件 |
| `__nekoDesktopCompactExternalBall` | `:3741` | 1 文件 |
| `__nekoDesktopCompactHistoryDragState` | `:1239/:2422/:2943/:3033/:3041` | 0（仅 preload 自用） |
| `__nekoDesktopCompactHistoryPointerPassthrough` | `:1238/:4239` | 0 |
| `__nekoDesktopCompactToolWheelDragActive` / `…ToolFanOpenSolid` | `:4303/:4319/:4506/:4508` | 0 |
| `__NEKO_DESKTOP_RUNTIME__`（`Object.freeze`） | `:970` | 12 文件 / 20 次 |
| `__nekoInjectedConfig` | `:934` | 1 文件 / 3 次 |

`__NEKO_DESKTOP_RUNTIME__` 与 `__nekoInjectedConfig` 是一次性写入，可在暴露时直接给值；
`*Layout` / `*Bounds` / `*BallScreenRect` / `*ExternalBall` 是持续变化，页面要活值 →
页面 shim 用 `Object.defineProperty` 定义 getter，内部读桥的 `getState()`。
其余 5 个页面侧零引用，只需保证 preload 内部自洽，可在 shim 中不提供。

### C. 反向钩子（preload 需要页面的东西）

| preload 处 | 读什么 | 用途 |
|---|---|---|
| `:944-945` | `window.appChatAvatar.setExternalAvatar(dataUrl, modelType)` | 外部头像预览落图 |
| `:5708` | `window.reactChatWindowHost` | 紧凑态宿主读取 |
| `:8111-8112` | `window.reactChatWindowHost.openWindow()` | 热键/工具触发打开对话框 |

（`window.reactChatWindowHost` 由页面 `app-buttons.js` 定义；`setComposerAttachments`、
`prepareCompactHistoryDropSubmit`、`setHomeTutorialInteractionLocked` 等方法也是页面自己互调，不涉桥。）

做法：preload 暴露 `nekoPageHooks.register({ getAppChatAvatar, getReactChatWindowHost })`，
页面 shim 在 DOM ready 后注册；preload 端改为 `hooks.getReactChatWindowHost()`。

### D. 页面状态被 preload 直接改（最硬的一处）

`setupWSProxy` 里的 `_flushRealisticQueue()`（`:40-54`）在 preload 世界直接操作页面状态：

- 读 `window._realisticGeminiQueue`，逐个调 `window.createGeminiBubble(...)`；
- 重置 `window._realisticGeminiQueue`、`_realisticGeminiVersion`、`_isProcessingRealisticQueue`。

隔离后这三个全局在页面世界，preload 完全碰不到。做法：把 `_flushRealisticQueue` 整体搬到页面
side（`electron-page-bridge.js` 或 `app-websocket.js`），通过 `nekoPageHooks` 注册成
`flushRealisticQueue`，preload 在需要时经反向通道调用。**这是唯一需要动页面业务逻辑的点**，
也是本期最大回归风险（气泡乱序/重复）。

### E. 事件

- preload `dispatchEvent` 10 处：`neko:screenshot-result`、`neko:config-injected`、
  `neko:avatar-preview-ipc-result`、`neko:desktop-avatar-bounds-change`（4）、
  `neko:compact-history-drag-*`（2）、`neko:desktop-compact-layout-change`（2）。
  隔离后 `detail` 是跨世界对象，页面读属性不可靠 → 由页面 shim 订阅桥数据后重建事件
  （WO-278 已验证的 `makePageEvent` 手法）。
- 页面 `dispatchEvent` 被 preload 监听 2 处：`react-chat-window:avatar-tool-state`（`:901`）、
  `neko:tutorial-overlay-relay`（`:4869`）。这两条是 DOM `CustomEvent`，DOM 事件跨世界共享，
  预期不用改；**但 `detail` 跨世界读取要在真 Electron 里验一次**，不能想当然。
- 30 处 `window.addEventListener` 里绝大多数是 `pointer*` 事件，DOM 共享，不受影响。

## 2. 分期与顺序

| 期 | 内容 | 可独立验收 |
|---|---|---|
| P1 ✅ | WS 运输：`window.WebSocket = WSProxy` 换成 `exposeToPage('nekoWebSocket', bridge)` | 页面 `__nekoCreateWebSocket()` 返回桥实例，真回显往返（施工记录 §6） |
| P2 ✅ | A 组对象暴露（先 `nekoChatWindow` / `electronDesktopCapturer` / `nekoSubtitleWindow` / jukebox，再其余） | 各 API 在隔离态下可调，返回类型不变（施工记录 §7） |
| P3 | B 组状态门面（`getState()` + 页面 getter） | 页面读到的 `*Layout`/`*Bounds` 与 preload 内部值同源 |
| P4 | C 组反向钩子 + D 组队列搬迁 | 外部头像、热键打开对话框、气泡排空三条链路 |
| P5 | E 组事件重建 | 10 条事件的页面监听方都能收到等价 detail |
| P6 | 翻 `contextIsolation:true` + 真应用 CDP 冒烟 | `/chat` 上 `nekoWebSocket` 存在、`window.WebSocket` 为原生、整窗可用 |

P1–P5 都在 `contextIsolation:false` 下可先落地并测（桥暴露函数双分支都要覆盖，
与 WO-278 的 `exposeToPage` 一致），P6 才翻面——这样任一期出问题都能单独回退。

## 3. 验收方式（每期都要真跑）

- 单测：`neko-electron-shell/tests/websocket-bridge.test.js` 扩桥工厂契约；
  新增 `tests/react-chat-bridge.contract.test.js` 断言 A 组方法名与返回形状。
- 两臂 harness：复用 `tests/runtime/bridge-e2e.main.js`（`--isolation true/false`），
  preload 换成 `preload-chat-react.js`，页面用 `chat.html` 的最小替身。
- 真应用 CDP：`scripts/smoke-ws-isolation.py` 已能拿到 `/chat` target；P6 前把探针扩成
  断言 `nekoWebSocket.getBounds()` 返回数字、`__NEKO_DESKTOP_RUNTIME__` 键集一致、
  `__nekoCreateWebSocket()` 实例走 IPC（回显服务）。
- 破坏对照（每期至少一条）：例如 P1 抽掉 `exposeToPage` 暴露 → 桥场景必红；P3 把 getter
  改成静态快照 → 布局变化后页面读到旧值，必须能测出来。

## 4. 风险与未验

1. **D 组是最大风险**：realistic 队列排空是时序敏感逻辑，搬到页面侧后要专门构造
   「queue 未排空时切 merge 模式」的复现，否则测不出乱序。
2. `nekoChatWindow` 的动态补挂方法（`idleDock*`）在冻结形状下的行为未验 —— **P2 已验**：
   静态快照会丢 5 个方法，改用 `exposeLiveFacade` 活门面后隔离臂可调到（§7）。
3. `detail` 跨世界读取只做了推理，未在真 Electron 隔离态实测（P5 必测）。
4. `preload-chat-full.js`（`fullChatWindow`）与 `preload-pet.js` 是同类问题，
   本计划只覆盖 React Chat；full chat 若上线同样要迁。
5. `webSecurity:false`（`:1921`）仍留着，与隔离正交，不在本期范围。

## 5. 不做

- 不重写 `preload-chat-react.js` 的 8124 行结构，只做「暴露点替换 + 状态门面 + 反向通道」。
- 不顺手迁 `fullChatWindow` / `petWindow`（不同 preload，不同页面全局集合）。
- 不动 `webSecurity`，不动 `nodeIntegration`。

## 6. P1 施工记录（2026-10-27）

**范围**：只换 WS 运输层。不翻 `contextIsolation`（`window-manager.js:1915` 仍为 `false`），
不动 `webSecurity`，不碰 A/B/C/D/E 组。P1 在两个运行态下都安全：当前非隔离生产窗照常工作，
将来 P6 翻面时同一段代码走 `contextBridge` 分支。

### 6.1 改动

`neko-electron-shell/src/preload-chat-react.js`

| 位置 | 改动 |
|---|---|
| `:21` | 新增 `exposeToPage(name, value)`：`process.contextIsolated` 时走 `contextBridge.exposeInMainWorld`，否则 `window[name] = value`（与 WO-278 已验证的 `exposeToPage` 同形） |
| `:42-424` | WSProxy **整段保留**作为引擎，只在其上加一层页面侧句柄 |
| `:381` | 新增 `createPageSocket(url, protocols)`：把 WSProxy 的 `open/message/close/error` 转成**纯 payload**（`message → event.data`，`close → {code, reason}`），带 `getReadyState()`、`addEventListener/removeEventListener`、`url`、`readyState` 常量 |
| `:426` | `exposeToPage('nekoWebSocket', { create, CONNECTING, OPEN, CLOSING, CLOSED })` |
| 原 `window.WebSocket = WSProxy` | **删除**（页面不再需要构造器顶替） |

**为什么不用 `websocket-bridge.js` 的 `createWebSocketBridge`**：那是简化版，没有 WSProxy 在生产上
踩出来的三件事——构造前 IPC 缓冲（页面建连早于 Pet READY 时首条 greeting 会丢）、
`sessionEpoch`/`generation` 代际过滤（切档案时旧代 CLOSED 不能砸新连接）、`_flushRealisticQueue`
（P4 搬迁前仍留在 preload）。换成简化版会把这三条静默丢掉。

**页面侧未改**。`chat.html` 已加载 `ws-adapter.js`（WO-278 装配），
`app-websocket.js:2944` 的建连点会优先用 `__nekoCreateWebSocket()`。

**构造器移除的安全性审计**：解析 `chat.html` 的 88 个 `<script src>` 与全部内联脚本，
`new WebSocket(` 只出现在 `static/app/app-websocket.js:2946` 的 ternary 回退支路（加载适配器后不会走到）；
仓库里另一处非 vendor 用法 `static/visit/transport/backend-ws.js` 不在 chat 页脚本集合内。

### 6.2 工装

`neko-electron-shell/tests/runtime/bridge-e2e.main.js`

- `--page <url path>` 覆盖页面（默认仍是 `bridge-e2e.page.html`），artifacts 里记录 `pageUrl`；
- `--mode react-chat`：400ms 时广播 CONNECTING+READY+`RAW_MESSAGE:greeting-preconstruct`（**早于页面建连**），
  1500ms 广播旧代际 `CLOSED{sessionEpoch:0,generation:0}`（页面此时已 OPEN，必须按 stale 丢弃），
  1800ms 才让主进程真 WS 连上回声服务；
- 崩溃可视化：`preload-error` / `render-process-gone` 写入 `observations` 并立即结束；
- **sync IPC stub**：补 `neko:input-region-backend`、`neko:has-set-shape`、`neko:x11-input-shape-active`、
  `TUTORIAL_OVERLAY_CHANNELS.GET_WINDOW_METRICS_SYNC` 的 `ipcMain.on` 应答（见 6.5）。

`neko-electron-shell/tests/runtime/bridge-e2e.page.js`：新增 `testReactChat()` 18 项断言
（桥暴露、`window.WebSocket` 仍为原生、建连瞬间 `readyState=0`、缓冲 greeting 不丢、
活值 `readyState`、stale CLOSED 忽略、重复 READY 只派一次 open、回显往返、
`removeEventListener` 跨世界同引用生效、CloseEvent 带 code/reason、close 后 send 静默）。

### 6.3 真跑结果（Electron 42.11.18）

回声服务：`./.venv/Scripts/python.exe neko-electron-shell/tests/runtime/ws-echo-server.py --port 18765`。

```
cd neko-electron-shell
export TMPDIR=/c/Users/ASUS/AppData/Local/Temp
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS ./node_modules/electron/dist/electron.exe \
  tests/runtime/bridge-e2e.main.js --mode react-chat --isolation <true|false> \
  --preload src/preload-chat-react.js --out "$TMPDIR/wo278-react-<arm>.json" \
  --no-sandbox --disable-gpu --disable-gpu-compositing
```

| 场景 | EXIT | 页面断言 | transportCheck | 关键观测 |
|---|---|---|---|---|
| `react-chat --isolation true` | 0 | 18/18 | 1 / 1 pass | `nativeWebSocket=true, openCount=1, greeting=greeting-preconstruct, handlerMessages=[greeting-preconstruct, echo:ping-1]`，`preconstructBroadcast=true, staleClosedBroadcast=true` |
| `react-chat --isolation false` | 0 | 18/18 | 1 / 1 pass | 同上（artifacts 内 `isolation:false`） |

回归（harness 改动未伤旧基线，均两臂）：

| 场景 | EXIT | 断言 | transportCheck |
|---|---|---|---|
| `bridge`（默认桥工厂） | 0 / 0 | 32/32、32/32 | 1/1、1/1 |
| `chat-proxy --preload src/preload-chat.js` | 0 / 0 | 15/15、15/15 | 1/1、1/1 |

单测：`node --test tests/websocket-bridge.test.js` 13/13；`node --test tests/window-hardening.contract.test.js` 9/9。

### 6.4 破坏对照

把 `preload-chat-react.js:426` 的暴露改成 `false && exposeToPage('nekoWebSocket', …)` 后重跑隔离臂：

- `EXIT=1`；
- `transportCheck = {expectedRawSendCount:1, actualRawSendCount:0, pass:false}`（页面建不出连接，主进程零 RAW_SEND）；
- 页面 3 项断言：`bridge 已暴露` **FAIL**，其余两项（适配器加载、`window.WebSocket` 原生）仍 PASS——
  失败点精确落在被抽掉的那一处。

还原后 `diff -q` 与绿场快照一致，重跑隔离臂 `EXIT=0`、18/18、transport 1/1。

### 6.5 新发现：Electron 42 `sendSync` 无监听者会永久阻塞 renderer

首次用 `preload-chat-react.js` 跑 harness 时，页面无任何 console、`dom-ready` 不触发、
6s 的 `executeJavaScript` 永不 resolve。逐段打点定位到：preload 的 DOMContentLoaded 里
`ipcRenderer.sendSync('neko:input-region-backend')`（以及 `neko:has-set-shape`）**没有 `ipcMain.on` 应答**，
Electron 42 下 renderer 主线程就此挂死（只打一条 warning，不抛错）。

生产侧这两个通道由 `src/main/window-host-ipc.js:1557/1566` 同步应答，`GET_WINDOW_METRICS_SYNC`
由 `tutorial-global-overlay-service.js:905` 应答，所以真应用不受影响；**任何脱离主进程全套 IPC 的
harness 都必须给这些 sync 通道补应答**，否则会误判成「preload 语法错误 / contextBridge 炸了」。

### 6.6 P1 明确未覆盖

- A/B/C/E 组暴露与事件重建（P2/P3/P5）；`_flushRealisticQueue` 仍在 preload（P4）。
- 未翻 `contextIsolation`（P6），`webSecurity:false` 原样保留。
- 真应用 CDP 冒烟仍是 P6 的门，P1 只证明运输层在真 Electron 两臂可用。

### 6.7 回滚

P1 是单文件改动：还原 `preload-chat-react.js` 中 `exposeToPage` 暴露段并恢复
`window.WebSocket = WSProxy`（原行位于 WSProxy 定义之后）即可完全回到迁移前。
harness 的 react-chat 模式与 sync stub 是纯增量，可一并保留或删除，不影响生产。

## 7. P2 施工记录：A 组 API 暴露（2026-10-27）

### 7.1 结论

A 组 8 个页面全局 + `__NEKO_MULTI_WINDOW__` 全部改成 `exposeToPage` 暴露，页面侧零改动。
`nekoChatWindow` 额外加一层 **活门面**：`exposeInMainWorld` 的对象形状在暴露那一刻固定，
而它有 5 个方法要等 DOMContentLoaded 才补挂，静态暴露在隔离态必丢（已用破坏对照证明）。
真 Electron 两臂（`contextIsolation` true/false）均 30/30，主进程侧的 IPC 对账 18 条 send
+ 11 条 invoke 全部对上，页面零 RAW_SEND（运输层没被动过）。

### 7.2 改动

`neko-electron-shell/src/preload-chat-react.js`：

| 位置 | 改动 |
|---|---|
| `:32` | 新增 `exposeLiveFacade(name, methodNames, getImpl)`：先把方法名全部预留成转发函数，调用时再从 preload 世界的实现对象取 |
| `:460` | `window.nekoChatWindow = {…}` → `var nekoChatWindowImpl = {…}`（实现留在 preload 世界） |
| `:485` | `exposeLiveFacade('nekoChatWindow', [21 个名字], () => nekoChatWindowImpl)`；16 个是立即方法，5 个是晚挂 |
| `:496` | `__NEKO_MULTI_WINDOW__` → `exposeToPage` |
| `:501`/`:502` | `__nekoFocusReactChatInputFromHotkey` 改为转发壳 + `*Impl` 变量；impl 未挂上时按 hotkey-manager 的同段兜底直接聚焦输入框 |
| `:520`–`:566` | `electronDesktopCapturer`（6 方法）、`nekoScreenshotProxy`、`nekoSubtitleWindow`（3 方法）、`__nekoJukeboxToggle` 改 `exposeToPage` |
| `:1055`/`:1070` | `__nekoRequestConfigInjection`（保留加载时自触发）、`__nekoRequestAvatarPreview` 改 `exposeToPage` |
| `:777`/`:1103` | preload 内部读取 `window.nekoChatWindow` → `nekoChatWindowImpl`（隔离后 window 上是页面那份门面） |
| `:6729`–`:6988` | 5 个晚挂方法改为写 `nekoChatWindowImpl.X`；`__nekoFocusReactChatInputFromHotkey` 写 `*Impl` |

未动：`__nekoGetAvatarToolClientScreenPoint` / `…ScreenClientPoint`（`:2252`/`:2265`）保持
preload 内部——页面从未引用，P3 若要暴露再走门面。E 组的 `window.dispatchEvent`（含
`neko:screenshot-result`、`neko:config-injected`、`neko:avatar-preview-ipc-result`）原样保留，P5 处理。

### 7.3 工装

`tests/runtime/bridge-e2e.main.js` 新增 `--mode react-chat-api`：

- main 侧把 A 组背后的 IPC 全接住：5 条 `ipcMain.handle`（get-bounds / get-workarea /
  drag-stop-and-get-bounds / collapse / expand）+ 6 条 capturer handle + 18 条 `ipcMain.on`，
  逐条记 `{kind, channel, payload}` 到 `observations.apiLog`；
- `evaluateApiCheck()` 按**载荷**对账（不是只看次数）：`setPosition(11,22)`、`setSize(555,444)`、
  `setResizable(false,{reason:'p2'})`、`resizeStart('se',{minWidth:300,…})`、
  `collapse({x:7,…})`、`getSources({types:['window']})`、`restoreNekoWindows([101])` 等；
  `CONFIG_REQUEST`/`AVATAR_PREVIEW` 各要求 ≥2（加载自触发 + 页面再调）；
- `expectedRawSendCount()` 对该模式返回 **0**：没建 WS 才是「没动运输层」的证据；
- `did-finish-load` 里该模式直接返回，不广播、不连回声服务。

`tests/runtime/bridge-e2e.page.js` 新增 `testReactChatApi()`，30 项断言，含三条只有隔离态才
有意义的：

1. **解析期**（DOMContentLoaded 之前）`nekoChatWindow.isCollapsed` 已是函数，但调用返回
   `undefined` —— 证明名字预留了、实现还没挂；
2. DOMContentLoaded 之后同一调用返回 `false` —— 证明转发壳确实接到晚挂实现；
3. `Object.keys(window.nekoChatWindow)` 恰为 21 个方法名（两臂一致，门面形状不随隔离变）。

其余断言：`electronDesktopCapturer` 6 方法逐个往返（桩值 `data:image/png;base64,AAAA/BBBB`、
`[101,102]`、`true`）、`collapse/expand` 参数过桥后原样回显、`nekoSubtitleWindow` 三方法、
`__nekoJukeboxToggle`、`__nekoRequestConfigInjection/AvatarPreview`、
`__nekoFocusReactChatInputFromHotkey()` 走 impl 返回 true（裸页面无输入框 → 排一次重试）、
P1 的 `nekoWebSocket` 与原生 `window.WebSocket` 未回退。

`tests/react-chat-p2-api.contract.test.js`（新增，5 项）静态钉住暴露方式：A 组不许
`window.X =`、门面名单必须覆盖实现对象上的**所有**方法（含晚挂）、preload 内部不许读
`window.nekoChatWindow.*`、屏幕点换算函数不暴露。**这条是必要的**：非隔离臂里静态快照与
活门面表现相同，运行期测不出差异（见 7.5）。

### 7.4 真跑结果（Electron 42.11.18）

```
cd neko-electron-shell
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS ./node_modules/electron/dist/electron.exe \
  tests/runtime/bridge-e2e.main.js --mode react-chat-api --isolation <true|false> \
  --preload src/preload-chat-react.js --out "$TMPDIR/wo278p2/api-<arm>.json" \
  --no-sandbox --disable-gpu --disable-gpu-compositing
```

| 场景 | EXIT | 页面断言 | transportCheck | apiCheck |
|---|---|---|---|---|
| `react-chat-api --isolation true` | 0 | 30/30 | 0 / 0 pass | pass，`configRequests=2, avatarPreviews=2`，18 send / 11 invoke 全对上 |
| `react-chat-api --isolation false` | 0 | 30/30 | 0 / 0 pass | 同上 |

回归（均两臂，echo 服务 `:18765`）：

| 场景 | EXIT | 断言 | transportCheck |
|---|---|---|---|
| `react-chat --preload src/preload-chat-react.js` | 0 / 0 | 18/18、18/18 | 1/1、1/1 |
| `bridge` | 0 / 0 | 32/32、32/32 | 1/1、1/1 |
| `chat-proxy --preload src/preload-chat.js` | 0 / 0 | 15/15、15/15 | 1/1、1/1 |

单测：`npm test` **27/27**（websocket-bridge 13 + window-hardening 9 + 新增契约 5）。

### 7.5 破坏对照

把 `nekoChatWindow` 的暴露换成静态快照 `exposeToPage('nekoChatWindow', nekoChatWindowImpl)`
（即「不管晚挂」的写法），重跑**隔离臂**：

- `EXIT=1`，`page.pass=false`，6 项 FAIL，且全部落在门面相关断言：
  - `门面暴露时就预留了晚挂方法名（isCollapsed）`（`typeof` = `string`，即不存在）
  - `晚挂方法此刻还没落地…`（`not-a-function`）
  - `门面方法名齐全（21 个）`（`missing=isCollapsed,idleDockCollapse,idleDockExpand,idleDockCommitCollapsedBounds,ensureExpandedForTutorial`）
  - `门面上每个名字都是函数`
  - `晚挂的 isCollapsed 已接通…`、`晚挂的 ensureExpandedForTutorial 已接通…`
- `apiCheck` 与 `transportCheck` 仍 pass —— 失败点精确落在被改坏的那一处，没有连带噪声。

还原后 `diff -q` 与备份一致，重跑隔离臂 `EXIT=0`、30/30、`apiCheck.pass=true`。

补充：同一补丁在**非隔离臂**仍全绿（`window` 就是 preload 世界，静态快照也能看见晚挂），
所以 `tests/react-chat-p2-api.contract.test.js` 是这道回归的唯一静态闸门。

### 7.6 P2 明确未覆盖

- B 组状态门面（`__NEKO_DESKTOP_RUNTIME__`、`__nekoInjectedConfig`、`*Layout`/`*Bounds`
  仍是 preload 直写，隔离后页面读不到）→ P3。
- C 组反向钩子（`appChatAvatar.setExternalAvatar`、`reactChatWindowHost`）→ P4。
- E 组 12 条事件（preload `dispatchEvent` ×10、页面回传 ×2）→ P5；`neko:screenshot-result`
  在本期只验了「页面发起 request 到主进程」，没验 detail 跨世界可读。
- 未翻 `contextIsolation`（P6）；`webSecurity:false` 原样保留。
- 未跑真应用 CDP：`chat.html` 上的 `nekoChatWindow` 仍是 preload 直写（非隔离），P6 前页面上
  看到的依然不是门面，本期结论只覆盖「隔离后可达」这一层。

### 7.7 回滚

单文件改动：把 `preload-chat-react.js` 的 A 组暴露段还原成 `window.X = …`（`nekoChatWindow`
还原成实现对象本身），并删掉 `exposeLiveFacade` 与 `*Impl` 转发。harness 的
`react-chat-api` 模式与新增契约测试是纯增量，可一并保留或删除，不影响生产。
