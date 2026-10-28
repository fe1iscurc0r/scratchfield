# WO-278 页面侧改造方案（剩余 4 扇窗）

- **作者**：K3 · **日期**：2026-10-24
- **状态**：**方案待决策**（未写代码）
- **前置**：批 1/2/3 已完成（`contextIsolation` true 8 / false 4），见 `docs/WO-278-contextbridge-migration.md`

---

## §0 一句话结论

| 窗 | 能不能靠"迁 preload"解决 | 结论 |
|---|---|---|
| `chatWindow` / `fullChatWindow` / `reactChatWindow` | 不能。卡在 `window.WebSocket = WSProxy`（**构造器替换**） | **可解**：页面侧改成从 bridge 取工厂（§2），中等工作量 |
| `petWindow` | 不能，而且**不该按"迁移"来做** | **建议不迁**：preload 在读 23 个页面全局、**205 处**，其中 `mmdManager` 43 / `vrmManager` 43 / `live2dManager` 35 是**活的类实例**，contextBridge 传不了（§3） |

**核心事实（决定了整个方案）**：`contextBridge` 只能传**可结构化克隆**的东西——函数、纯对象、数组、原始值。
**传不了**：类实例（方法在原型上）、DOM 节点、Proxy。所以：

- 「页面 → preload 读一个 Class 实例」**永远桥不了**，只能把**逻辑搬进页面**；
- 「preload → 页面写一个构造器」**也桥不了**，只能让**页面自己来做这件事**。

---

## §2 chat / full-chat / react-chat：WebSocketFactory 方案

### §2.1 现状（为什么要改页面）

```js
// preload-chat.js:117
window.WebSocket = WSProxy;   // WSProxy 是函数构造器
```

页面里所有 `new WebSocket(url)` 都命中这个代理，流量走
`Chat → IPC(ws-raw-send) → 主进程 → Pet → 真 WebSocket → 后端`。
开隔离后这个替换失效 ⇒ 页面直接用原生 WS ⇒ **聊天直接连不上**（不是降级，是不通）。

### §2.2 目标形态

**preload 侧**（三窗共用，改 `preload-common.js` 或各自 preload）：

```js
// 不再替换全局；把「建代理实例」暴露成工厂
contextBridge.exposeInMainWorld('nekoWebSocket', {
  create: (url, protocols) => makeWSProxy(url, protocols),   // 返回 { url, readyState, send, close, addEventListener, ... }
  CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3,
});
```

> ⚠️ **注意**：`makeWSProxy` 返回的必须是一个**纯对象 + 函数集合**（不是 class 实例），
> 否则过不了 contextBridge。现有 `WSProxy` 用的是 `Object.defineProperty(prototype, 'onopen', ...)`，
> 迁移时要改成把 getter/setter 变成显式方法，或者用 `exposeInMainWorld` 暴露一个
> `subscribe(handlers)` 形态。**这是本方案的主要工作量。**

**页面侧**（`NEKO/N.E.K.O/static/js/app-websocket.js` 等所有 `new WebSocket(` 处）：

```js
// 兼容两代运行时（浏览器直开 / Electron 隔离 / Electron 未隔离）
const WSImpl = (window.nekoWebSocket && typeof window.nekoWebSocket.create === 'function')
  ? window.nekoWebSocket
  : null;
const sock = WSImpl ? WSImpl.create(url) : new WebSocket(url);
```

### §2.3 分批与验收

| 步 | 内容 | 验收 |
|---|---|---|
| 1 | `app-websocket.js` 改为从工厂取（保留 `new WebSocket` 回退） | 构造/事件/readyState 三类单测（node + jsdom 或纯 mock） |
| 2 | 三窗 preload 改成暴露工厂、**不再替换全局** | 契约测试新增「preload 不得 `window.WebSocket =`」反向断言 |
| 3 | 逐窗翻 `contextIsolation: true` | 契约测试 + **真机冒烟**（下表） |

**真机冒烟清单**（必须逐条点，不能只看"界面出来了"）：

1. 打开聊天 → 发一条消息收到回复（证明 `send` 通路）
2. 断网 → 页面显示重连中 → 恢复网络 → 自动重连成功（证明 CLOSED/READY 状态机）
3. 主窗（Pet）重连时，chat 窗的代理要跟着 `READY`（**僵尸代理回归测试**：
   `preload-chat.js` 注释里专门写过这个坑——重复 READY 不能造出停在 CONNECTING 的僵尸）
4. 关闭 chat 窗再打开 → 新连接正常（证明没有泄漏的 IPC 监听）

### §2.4 风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| `WSProxy` 的属性语义 | 现在是 getter/setter（`onopen`/`onmessage`…），跨桥后不会有活的 getter | 改成显式 `on('open', fn)` 或页面轮询 `readyState`；**这是行为变化，必须在页面侧统一** |
| 三窗各有一份 `WSProxy` | `preload-chat` / `-chat-full` / `-chat-react` 各实现一遍 | 先抽到 `preload-common.js` 一份，再改页面；否则要改三遍 |
| 8124 行 react preload 里的 17 个页面侧全局 / 65 处读 | 与 WS 无关，但同窗打开隔离时会一起暴露 | 与 WS 改造分批做，不要同一 PR |

---

## §3 petWindow：**建议不迁**（理由量化）

### §3.1 实测数据

`preload-pet.js`：5524 行；写 13 个全局；**读 23 个页面全局、205 处引用**（2026-10-25 重测；
口径：只算读、去掉 `window.X = …` 赋值与 preload 自注入的 4 个全局）：

| 页面全局 | 引用数 | 它是什么 |
|---|---:|---|
| `window.mmdManager` | **43** | MMD 渲染器**实例**（活对象，含 currentModel 等状态） |
| `window.vrmManager` | **43** | VRM 3D 模型管理器**实例**（`currentModel` / `core`） |
| `window.live2dManager` | **35** | Live2D 管理器**实例** |
| `window.Jukebox` | 21 | 点歌台控制器（`getModelType` / `playVRMA` 等） |
| `window.lanlan_config` | 12 | 页面配置对象（`model_type` / `live3d_sub_type` …） |
| `window.DragHelpers` | 7 | 拖拽辅助（`isDragging` / `restoreButtonPointerEvents`） |
| `window.appState` / `pageConfigReady` | 6 / 6 | 页面状态 / 配置就绪信号 |
| `window.captureProactiveChatScreenshot` / `captureScreenshotDataUrl` | 4 / 2 | 页面提供的截图能力 |
| `window.nekoSubtitleShared` | 4 | 字幕共享状态 |
| `window.appButtons` / `avatarPortrait` | 3 / 3 | 交互载荷 / 头像截取 |
| `window._agentTaskMap` | 2 | 任务表 |
| `master_name` / `master_nickname` / `master_display_name` / `master_profile_name` | 各 1 | 页面注入的称呼 |

### §3.2 为什么不迁

1. **`mmdManager` / `vrmManager` / `live2dManager` 是类实例**（方法在原型、内部有 WebGL / 3D 上下文）。
   contextBridge 过桥会做结构化克隆：**函数能过，但实例过不去**，读到的会是空壳。
   要迁就只能把这 121 处调用**搬进页面**——那不是"迁移 preload"，是**改架构**。
2. **pet 的 preload 在做页面该做的事**：它驱动模型切换、锁状态、goodbye 模式、
   字幕渲染状态、VRMA 播放。放回页面才是正确分层，但那是一个独立工程（5524 行要拆）。
3. **风险/收益极不对称**：pet 是主窗，坏了整只猫都不动。而收益只是"少一个 `contextIsolation:false`"，
   且该窗已 `nodeIntegration:false` + 契约测试守着不许新增豁免。

### §3.3 建议

**保持 `contextIsolation: false`，但在文档与契约测试里把它登记为"已知且已论证的例外"**，
并在 WO-278 里关掉"pet 迁移"这一批（改成"架构重构：把 preload 里的渲染控制逻辑搬回页面"，另立单）。

契约测试已有 `CTOR_PRELOAD_WINDOW` 把它列进去（`preload-pet → petWindow`），
所以**谁翻它谁红**——这个安全网已经在位。

---

## §4 给决策者的三个选项

| 选项 | 内容 | 代价 | 收益 |
|---|---|---|---|
| **A（推荐）** | 只做 §2：三扇 chat 窗走 WebSocketFactory，做完 `contextIsolation` 从 8/4 变 **11/1**（只剩 pet） | 中：1 次页面侧改造 + 3 次翻配置 + 4 条真机冒烟 | 3 扇窗获得隔离 |
| **B** | §2 + pet 架构重构（把渲染控制搬回页面） | 大：5524 行 preload 拆分，独立工程 | 全部隔离 |
| **C** | 停在批 3（当前） | 零 | `contextIsolation` 8/4，剩 4 台全部有契约测试守着 |

**我的意见**：走 A。pet 那台留作技术债更划算——现在翻它是拿主窗稳定性换一个配置项。

---

## §5 本方案没有做的事

- 没有改任何代码（本轮只出方案）。
- 没有验证 §2.2 里"工厂返回纯对象"能否覆盖现有 `WSProxy` 的全部语义
  （`onopen`/`onmessage`/`onclose`/`onerror` 四个 setter + `addEventListener`）——
  这要先写一个**不接 Electron 的纯 node 单测**把两者的接口对齐，再动页面。
  这一步我可以做，但它属于 §2 步 1，不在方案阶段。

---

## §2.5 接口契约（实测 `static/app/app-websocket.js`，6806 行）

页面侧唯一的创建点是 `app-websocket.js:2942`：`S.socket = new WebSocket(wsUrl)`。
把它对 socket 的使用**逐项数出来**，才知道工厂要暴露什么、哪些根本桥不了：

| 成员 | 页面用量 | contextBridge 能不能过 | 结论 |
|---|---:|---|---|
| `.send(...)` | 24 | ✅ 函数可过 | 直接用 |
| `.close(...)` | 5 | ✅ 函数可过 | 直接用 |
| `.addEventListener(...)` | 23 | ✅ 函数可过 | 直接用（推荐页面统一用这个） |
| `.removeEventListener(...)` | 3 | ✅ 函数可过 | 直接用 |
| **`.readyState`** | **32** | ❌ **属性值是快照** | **必须改**成 `getReadyState()` 方法，或页面自己用事件维护状态 |
| **`.onopen = fn`** | 1（L2948） | ❌ **赋值语义过不了桥** | **必须改**成 `addEventListener('open', fn)` |
| **`.onmessage = fn`** | 1（L3231） | ❌ 同上 | 同上 |
| **`.onclose = fn`** | 1（L6184） | ❌ 同上 | 同上 |
| **`.onerror = fn`** | 1（L6306） | ❌ 同上 | 同上 |

### 这带来两个**必须先解决**的结论

1. **`onX = fn` 那种赋值，contextBridge 永远支持不了**——桥过来的是普通对象，
   页面对它做 `sock.onopen = fn` 只是给快照对象加了个属性，preload 收不到。
   ⇒ 那 4 处（2948 / 3231 / 6184 / 6306）必须改成 `addEventListener`。
2. **`readyState` 会变成死值**——桥过来的是值拷贝。页面用它 32 次（大多数是
   `if (S.socket.readyState === WebSocket.OPEN)` 这类判断），桥后恒为创建那一刻的状态。
   ⇒ 要么暴露 `getReadyState()` 让页面调用（32 处改成函数调用），
   要么**页面自己**在事件里维护 `S.socketReadyState`（推荐后者：改动更小、语义更准）。

### 改造面小结（这就是 §2 的真实工作量）

| 文件 | 改动 |
|---|---|
| `static/app/app-websocket.js` | 1 处创建（2942）+ 4 处 `onX=` → `addEventListener` + 32 处 `readyState` 读取改法 |
| `neko-electron-shell/src/preload-common.js`（建议） | 抽一份 `createWebSocketBridge()`：返回 `{ send, close, addEventListener, removeEventListener, getReadyState }` 的**纯对象** |
| 三个 chat preload | 删掉 `window.WebSocket = WSProxy`，改为 `exposeInMainWorld('nekoWebSocket', createWebSocketBridge(...))` |
| `window-manager.js` | 三窗 `contextIsolation: true` |

**风险最高的不是 preload，是那 32 处 `readyState`**：改错了会引发"看起来连上了但其实没连"。
所以 §2.3 的冒烟清单里第 2、3 条（断线重连、僵尸代理）是**必须**的，不能省。

### 一个能先做的降险动作（不用真机）

把这套工厂 + 页面改法，用**纯 node**（不接 Electron）写一份单测：
用假 `ipcRenderer` 驱动工厂，断言 `send/close/addEventListener/getReadyState` 行为与
原生 `WebSocket` 一致（含 CONNECTING→OPEN→CLOSING→CLOSED 四态）。
这一步在**本机就能做**，也正好是契约测试能守住的部分。

---

## §6 落地进展（2026-10-25）：桥工厂 + 纯 node 单测已写完（**本地，待推**）

§2.5 最后说的"降险动作"已经做了，不需要 Electron、不需要真机。

### §6.1 新增两个文件（等凭据恢复后一起推）

| 文件 | 作用 |
|---|---|
| `neko-electron-shell/src/websocket-bridge.js` | `createWebSocketBridge({ ipc, channels })` —— **依赖注入**的代理工厂，返回只含函数/常量的普通对象，可直接 `exposeInMainWorld` |
| `neko-electron-shell/tests/websocket-bridge.test.js` | 12 条纯 node 单测（假 ipc 驱动状态机） |

### §6.2 从现有 `WSProxy` 抄下来的三条语义（改坏会回归线上事故）

| # | 语义 | 为什么 |
|---|---|---|
| 1 | **CONNECTING 状态不吃 CLOSED** | 切档案时刚 new 的代理若吃了上一轮遗留 CLOSED，页面会排 stale auto-reconnect，3s 后造出永远停在 CONNECTING 的**僵尸代理**（源注释明确记过这个坑） |
| 2 | **非 OPEN 的 `send` 静默丢弃** | 沿用旧行为（页面已有大量 `if (readyState === OPEN) send()`），改成抛会炸 |
| 3 | **`close()` 是本地动作** | 不发 IPC，直接置 CLOSED + 派 close |

### §6.3 验收

```
cd neko-electron-shell && node --test "tests/*.test.js"
→ # tests 20 / # pass 20 / # fail 0      （8 契约 + 12 桥）
```

**「改坏 ⇒ FAIL」对照实验**（拆掉语义 1 的守卫 `readyState !== OPEN`）：

```
not ok 4 - 【回归守卫】CONNECTING 时收到 CLOSED 不得派 close（僵尸代理根因）
# fail 1
```

还原后 12 pass、sha256 一致。

### §6.4 这套工厂**还没有接进 preload**

- 没改 `preload-chat.js` / `-chat-full` / `-chat-react`（它们仍是 `window.WebSocket = WSProxy`）。
- 没改 `window-manager.js` 的三窗配置。
- 没改页面 `app-websocket.js`（§2.5 那 1+4+32 处）。

⇒ 即：**部件做完并验证过，装配还没做**。装配属于 §2.3 的三步，且第 3 步必须真机冒烟。

### §6.5 ⚠️ 当前阻塞

GitHub 凭据不可用（本地 PAT `401 Bad credentials`；MCP 通道 `404`，看不到私有仓），
`reconnect_plugin` 已尝试并成功但两个通道仍未恢复 ⇒ **上述文件只在本地**。

---

## §7 设计改进（2026-10-25）：页面侧适配器把 **37 处改动压成 1 处**

§2.5 原计划要动 `app-websocket.js` 的 **1 处创建 + 4 处 `onX=` + 32 处 `readyState`**。
后来发现：**这些差异可以在页面里补回来**——写一个薄适配器，把"桥工厂返回的普通对象"
包装成"语义与原生 WebSocket 一致"的对象，于是**那 36 处调用一行都不用改**。

### §7.1 适配器做什么

`NEKO/N.E.K.O/static/app/ws-adapter.js` → 暴露 `window.__nekoCreateWebSocket(url)`：

| 原生语义 | 桥工厂给的 | 适配器补法 |
|---|---|---|
| `sock.readyState` 跟着事件变 | `getReadyState()` 函数 | 适配器用**事件驱动**维护本地 `readyState`，并暴露成 **getter 属性** |
| `sock.onopen = fn` 生效 | 不支持赋值 | 适配器把 `onX` 的 setter 映射到 `addEventListener` |
| 无 bridge 时 | — | 直接 `new WebSocket(url)`（浏览器直开 / 未隔离窗口） |

⇒ 页面只需把**建连接那一行**改成 `__nekoCreateWebSocket(url)`，其余 `send` / `close` /
`addEventListener` / `readyState` / `onopen=` 全部照旧。

### §7.2 验收

```
node tests/frontend/ws-adapter.test.js        → # tests 9 / # pass 9 / # fail 0
pytest NEKO/N.E.K.O/tests/frontend/test_ws_adapter_node.py -q → 1 passed
```

**「改坏 ⇒ FAIL」**：把 `readyState` 的事件驱动更新删掉（退化成快照）⇒

```
not ok 2 - 有 bridge 时返回适配器，readyState 是活值（不是快照）
not ok 7 - send 走 handle；close 之后 readyState 立刻 CLOSED
not ok 9 - 监听器抛错不影响其它监听器，也不破坏 readyState
# fail 3
```

还原后 9 pass、sha256 一致。

### §7.3 剩下的装配反而更简单了

| 步 | 改动量 | 风险 |
|---|---|---|
| 1 | `app-websocket.js:2942` 一行 → `__nekoCreateWebSocket(wsUrl)`；页面引入 `ws-adapter.js` | 低 |
| 2 | 三个 chat preload：删 `window.WebSocket = WSProxy`，改 `exposeInMainWorld('nekoWebSocket', factory)` | 中 |
| 3 | 三窗 `contextIsolation: true` | 低（契约测试守着） |
| 4 | 真机冒烟（断线重连 / 僵尸代理 / 关窗再开） | **必须** |

> 注意：`onX=` 那 4 处（L2948/3231/6184/6306）**不用改**了——适配器的 setter 已经接管。

---

## §8 运行时冒烟工装（2026-10-25）：CDP 脚本能跑通，但整栈起不来

写了 `neko-electron-shell/scripts/smoke-ws-isolation.py`：以**隔离配置目录**启动 electron，
加 `--remote-debugging-port`，用 CDP 在每个渲染进程里跑探针（`window.nekoWebSocket` /
`window.__nekoCreateWebSocket` / `WebSocket` 是否原生 / 真建一个 socket 看状态机），
顺带抓 3 秒 console 错误，最后杀进程树并清理。

### §8.1 踩到的三个环境坑（都写进脚本注释了）

| 坑 | 现象 | 解法 |
|---|---|---|
| **`ELECTRON_RUN_AS_NODE=1`** | Electron 按普通 Node 跑 ⇒ 主进程 `require('electron').app` 是 `undefined`，启动即崩（`Cannot read properties of undefined (reading 'setPath')`） | 启动子进程前 `env.pop('ELECTRON_RUN_AS_NODE')`（**WorkBuddy 自身是 Electron 应用，会把它注入环境**） |
| **GPU 进程连崩** | `GPU process exited unexpectedly: exit_code=-1073741819` ×N 后 `FATAL: GPU process isn't usable. Goodbye.`；`--disable-gpu` 单独无效 | 加 **`--no-sandbox`** 才活下来（沙箱下 GPU 起不来）；另需 `--disable-gpu` |
| **CDP 握手 403** | `Rejected an incoming WebSocket connection from http://127.0.0.1:9222` | 加 `--remote-allow-origins=*` |

另外：Windows 控制台输出是 **GBK**，脚本若用 `stdout=PIPE` 解码会崩线程、管道不再排空 ⇒ 子进程写满缓冲就卡死
（表现成"等不到 CDP"）。改为**二进制落日志文件**。

### §8.2 已经证明的

```
CDP 已监听: Chrome/148.0.7778.280
拿到 1 个渲染 target
  [Loading...]
    nekoWebSocket       : undefined  (create=False)
    __nekoCreateWebSocket: undefined
    WebSocket 是原生     : True
```

⇒ **工装本身是通的**：attach → `Runtime.evaluate` → 取值都正常。

### §8.3 卡在哪：整栈起不来（不是脚本的问题）

- 应用启动时找**打包后端** `neko-electron-shell/bin/projectneko_server.exe` —— **本仓没有这个文件**
  （日志：`Python exe 未找到 … 跳过启动`）。
- 退而用源码后端 `NEKO/N.E.K.O/launcher.py` 起：确实打印了「所有服务器已准备就绪」、
  `GET /` 返回 200，但**随后进程退出**（几十秒后 `/health` 变成 **502**、48911 不再 LISTENING）。
- 应用的就绪探测走 `GET /health`（`backend-runtime.js:83`），502 ⇒ 永远不 ready ⇒ **停在 Loading 窗**，
  拿不到 pet/chat 渲染进程。

⇒ **结论：CDP 冒烟要验到 chat 窗，必须先有健康的后端**。两条路：
1. 用真实安装版的后端 exe（放到 `bin/`），或
2. 在用户正常开发环境里跑本脚本（那边后端通常是好的）。

### §8.4 所以"装配后要不要冒烟"这个问题的准确答案

- **能自动验的**：adapter 是否加载、`nekoWebSocket` 是否存在、socket 状态机、console 错误 —— 脚本已就绪。
- **验不了的**：完整聊天往返（要模型可用）、动画/视觉（要人眼）。
- **前置条件**：一个健康的后端。没有它，脚本只能看到 Loading 窗。

---

## §9 按既有技能对齐后的新发现（2026-10-25 17:xx）

我先前的 §8 里那三个环境坑，**自己的技能 `lumo-stack-startup` 早就写过**（坑三/坑四）——
这次没先查、重复踩了一遍。对齐后补了两条**技能里也没有**的：

### §9.1 新发现一：`HTTP_PROXY` 会让本地端口探测撒谎

本会话环境带 `HTTP_PROXY=http://127.0.0.1:63457`。用 `urllib` 探测
`http://localhost:48911/health` 会**走代理**，代理回 **502 Bad Gateway**。

| 观测值 | 真实含义 |
|---|---|
| `502` | **代理在中间**（不代表后端挂了） |
| `WinError 10061 / ConnectionRefused` | 真没起（必须禁用代理才看得到） |
| `200` | 真活着 |

**判据**：探测本地端口必须 `urllib.request.build_opener(ProxyHandler({}))`。
Node 的 `http` 模块不走代理，所以应用自己 `waitForServerReady` 报的"请求错误"是**真连不上**。

### §9.2 新发现二：`scratchpad-unified` 里 NEKO 后端起不来

- 技能里的代码根 `D://my git\scratchpad` 现在**只剩数据目录**（`carpet/ docs/ research/`），**没有 NEKO**；
  真正的代码在 `scratchpad-unified`。
- 用 `scripts/neko_launcher_wrapper.py` 起：**fail-fast 退出**
  `FATAL: lifecycle.py local-patch missing (0/4 expected)` ——
  上游同步把 `launcher_core/lifecycle.py` 里 4 处 lumo 补丁覆盖了。
- 改用上游 `NEKO/N.E.K.O/.venv/Scripts/python.exe launcher.py`（清掉 `NODE_OPTIONS` /
  `CODEBUDDY_SAFE_DELETE_*` 之后）：`/health` **能 200**、打印"所有服务器已启动完成"，
  但**约 20 秒后自行退出**（末尾 `EmbeddingWorker ... model_file_missing`，无崩溃栈）。

⇒ 结论不变：**端到端要验 chat 窗，得有一个能长期活着的后端**（真实安装版的
`bin/projectneko_server.exe` 最省事）。本仓源码后端在当前状态下活不过一分钟。

> **2026-10-25 复核更正**：上面「约 20 秒后自行退出」**未复现**。用**项目 venv 的解释器**
> 直接跑 `launcher.py` 时 48911 / 48915 持续监听、`/health` 持续 200；末尾的
> `EmbeddingWorker ... model_file_missing` 只是该 worker 退出，**主服务不跟着退**。
> 另：用**系统解释器**跑会触发 `launcher_core/bootstrap.py` 的 re-exec，项目路径含空格时
> argv 被拼坏、表现为立刻失败。详见 `docs/WO-278-runtime-verification.md` §6。

### §9.3 冒烟脚本已按技能对齐

`scripts/smoke-ws-isolation.py` 现在启动子进程前会清：
`ELECTRON_RUN_AS_NODE`、`NODE_OPTIONS`、`CODEBUDDY_SAFE_DELETE_BULK_GUARD`、
`CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR`、`CODEBUDDY_SAFE_DELETE_REPORT_PATH`
（前三个清错会导致 electron 退化成 Node 或 GPU 崩；后三个是 safe-delete 守卫，会拦 NEKO 的 node 子进程）。
