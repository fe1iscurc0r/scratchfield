# WO-278 运行时验证记录（真 Electron）

> 2026-10-25 · 补齐交接文档 §7 的空缺：桥工厂与页面适配器**第一次在真 Electron 里运行**。
>
> 结论：发现并修掉一个**纯 node 单测在结构上抓不到**的跨 `contextBridge` 缺陷；修后桥场景
> **32 项**端到端检查全绿（16 → 18 → 32：补 `close` 非 ASCII reason、`CloseEvent` 实例性、
> 200 字节 reason、异常码 1006、以及强制构造器抛错时的回退分支），并用「复刻旧行为」的对照
> 证明工装确实能抓住它。另新增**同源子窗口控制工装**（16 项 + 主进程状态核对），
> 把交接 §2.4 的「四方法未实测」补上。
> **装配（交接 §4.2 四步）本文未做**，真实应用里三扇 chat 窗仍在旧路径上。

---

## 0. 与交接文档的关系

交接 §7 的原话：

> 桥工厂 / 适配器 | ✅ 纯 node 单测覆盖（12 + 9），但**没在真 Electron 里跑过**

现在这条改为：

> 桥工厂 / 适配器 | ✅ 13 + 10 条纯 node 单测 **+ 真 Electron 端到端 4 场景**（含 A/B 与变异对照）
> 同源子窗口四方法 | ✅ 真 `preload-child.js` + 真 `createStorageGate()` 处理器，16 项 + 主进程状态核对

本文只补验证，不改设计决策、不改装配范围。§4.2 的装配仍然是下一步。

---

## 1. 结果总览

| 项 | 结果 | 证据 |
|---|---|---|
| 真 Electron 桥链路 | **32/32 通过** | 2026-10-25 补测后复跑，退出码 0 |
| 无 bridge 回退原生 | **5/5 通过** | 同上，退出码 0 |
| chat 窗隔离 A/B | 两臂均按预期 | 同一次运行的四个场景 |
| 同源子窗口四方法 | **16/16 + 主进程状态核对通过** | `child-window-control.main.js`，退出码 0 |
| 运输方式断言 | 4 场景全对 | `transportCheck`：1 / 0 / 0 / 1 次 `RAW_SEND` |
| 变异对照 | 三组全按预期红 | 旧行为 payload 装箱 9 项失败；删适配器 try/catch 3 项失败；改错 IPC 频道名 1 项失败 + 状态核对失败 |
| 单测 | 21 pass（8 契约 + 13 桥）、适配器 10 pass | 命令见 §8 |
| 真实应用 CDP 基线 | 3 扇窗，装配尚未接 | 见 §5 |

---

## 2. 找到并修掉的真实缺陷

### 2.1 现象

修复前，页面通过桥收到的 `message` / `close` 事件只有 `{ isTrusted }`：
`event.data`、`event.code`、`event.reason` 全是 `undefined`。而当时 **21 条单测全绿**。

### 2.2 根因

`contextBridge` 只做结构化克隆。preload 世界里的 `MessageEvent` / `CloseEvent` 是 DOM 对象，
`data` / `code` / `reason` 是**原型上的 getter**，克隆只保留自有可枚举属性 ⇒ 页面拿到空壳。

单测抓不到，是因为假 `ipc` 与桥在**同一个 JS 世界**里跑，事件对象从未跨过隔离边界。
这不是测试写得不好，是**测试位置决定了它看不见**。

### 2.3 修法

| 文件 | 改动 |
|---|---|
| `neko-electron-shell/src/websocket-bridge.js` | 桥**只发纯数据**：`fire('message', data)`（字符串）、`fire('close', { code, reason })`；不再构造 `Event`（[websocket-bridge.js:76](../neko-electron-shell/src/websocket-bridge.js#L76)、`:101`、`:110`） |
| `NEKO/N.E.K.O/static/app/ws-adapter.js` | 适配器在**页面世界**重建事件：`makePageEvent()` 用页面的 `MessageEvent` / `CloseEvent` 构造（[ws-adapter.js:117](../NEKO/N.E.K.O/static/app/ws-adapter.js#L117)、`:154`） |
| `neko-electron-shell/tests/websocket-bridge.test.js` | 新增「回调参数是纯数据」断言类型与键集合（`:112`） |
| `NEKO/N.E.K.O/tests/frontend/ws-adapter.test.js` | 新增「事件对象由适配器在页面世界重建」（`:186`） |

事件对象的 `code` / `reason` 在页面侧由 `CloseEvent` 构造器生成；浏览器不支持构造器时
回退成带 `type` / `code` / `reason` 的普通对象（同一函数内），所以不依赖实现细节。

### 2.4 变异对照（两条，都可复现）

**A. 复刻旧行为（不改源码，已入库）**

`tests/runtime/bridge-e2e.preload-legacy-event.js` 在真 bridge 外面包一层，
把 payload 重新包成 preload 世界的 `Event` 再交给页面——正是修复前的形态。

```
退出码 1，页面自报 23/32（9 项失败，全是 payload 内容，运输不受影响）：
  回显内容正确                                  detail "[object Object]"
  close 事件带 code/reason                      detail {"code":0,"reason":"","keys":["isTrusted"]}
  close 的 reason 原样保留（非 ASCII 两次过桥）  detail {"code":0,"reason":"","keys":["isTrusted"]}
  200 字节 reason 原样保留                      detail {"code":0,"reasonLength":0,...}
  第二条连接的 code 正确（4002）                 detail {...}
  code 1006 原样交付给页面                      detail {"code":0,"reason":""}
  异常断线的 reason 保留                        detail {"code":0,"reason":""}
  回退对象 code = 4003 / reason = forced        detail {"type":"close"}（payload 被装箱后无字段）
运输断言仍通过（rawSendCount=1）
```

**B. 直接改源码再还原（手工，留作对照）**

把 `fire('message', data);` 改成 `fire('message', new MessageEvent('message', { data }));`
⇒ 退出码 1，唯一失败项 `回显内容正确`（`[object Object]`）；还原后
sha256 `69412c79…62ffd7` 前后一致。

两条对照说明：**失败只落在 payload 内容上，运输链路不受影响**——工装定位准确，不是碰巧红。

### 2.5 2026-10-25 补测：close 边界与子窗口控制（两条新发现）

#### 2.5.1 更正：Chromium 148 的 `CloseEvent` 构造器**不设** 123 字节上限

此前文档（含本文 §9 旧表述）写着「>123 字节 reason 会让 `CloseEvent` 构造器抛错，走普通对象回退」。
真 Electron 实测**不成立**：

| 输入 | 实测结果 |
|---|---|
| `close(4002, 200 个 'x')` | 页面收到 `CloseEvent` 实例，`reason.length = 200`、内容逐字相同 |
| 主进程广播 `CLOSED {code: 1006}`（保留码） | 页面同样收到 `CloseEvent` 实例，`code = 1006` |

⇒ 123 字节限制只作用在 `WebSocket.close()` 的**网络路径**上，不在 `CloseEvent` 构造器。
适配器的 `catch` 回退分支在这个运行时里**自然不可达**；它仍是必要的防御（规范允许构造器抛错，
旧版/其它运行时可能收紧），但不能靠长 reason 或 1006 触发。

#### 2.5.2 回退分支改为「强制构造器抛错」来验

页面在世界侧把 `window.CloseEvent` 换成必抛版本，再让主进程广播 `CLOSED {code:4003, reason:'forced'}`：

```
CloseEvent 构造器抛错时回退成普通对象   PASS  {"type":"close","code":4003,"reason":"forced","isCloseEventInstance":false}
回退对象 code = 4003                    PASS
回退对象 reason = forced                PASS
回退后 readyState = 3                   PASS
```

**变异对照**：删掉 `ws-adapter.js` 里 `makePageEvent()` 的 `try/catch`（异常冒到桥的 `fire()` 被吞）
⇒ 页面**收不到 close 事件**，32 项里恰好 3 项失败、退出码 1；还原后 sha256
`e97e0f32…6e325b` 一致，单测 10 pass。

#### 2.5.3 同源子窗口 `nekoWindowControl` 四方法（交接 §2.4 的遗留项）

新工装 `tests/runtime/child-window-control.*`：真 `src/preload-child.js`（`contextIsolation: true`）
→ contextBridge → 页面调用 → 真 `createStorageGate()` 注册的四条 IPC 处理器 → 真 `BrowserWindow`。

判据是两份：页面自报 16 项，**加上**主进程按 100 ms 采样的窗口状态（必须真的最大化过、
最小化过，收尾两者均为 false）。结果全绿，两个值得记住的实际语义：

| 行为 | 实测 |
|---|---|
| `maximize()` | 返回 `{ok:true, isMaximized:true}`，再次调用切换为 `false` |
| `restore()` | 只在**最小化**时 `restore()`，其余情况 `show()+focus()` ⇒ **不解除最大化**（页面断言里钉住了这条） |
| 隔离生效旁证 | 页面世界 `require` / `ipcRenderer` 均为 `undefined` |

**变异对照**：把 `preload-child.js` 里 `maximize` 的频道名改成 `…-typo` ⇒
页面探针收到 `No handler registered for ...`，页面自报失败 + 主进程「窗口最大化过」核对失败，
退出码 1；还原后 sha256 `9a0b4d7b…734cd` 一致。

---

## 3. 端到端工装（不依赖后端）

### 3.1 组成

| 文件 | 作用 |
|---|---|
| `tests/runtime/bridge-e2e.main.js` | Electron 主进程：起静态服务器、按参数建窗、当「Pet」持真 WS、汇总结果、决定退出码 |
| `tests/runtime/bridge-e2e.preload.js` | 真 preload：`createWebSocketBridge` + `contextBridge.exposeInMainWorld` |
| `tests/runtime/bridge-e2e.preload-empty.js` | 空 preload（回退场景） |
| `tests/runtime/bridge-e2e.preload-legacy-event.js` | 变异对照（§2.4 A） |
| `tests/runtime/bridge-e2e.page.html` / `.page.js` | 页面侧探针：加载**仓库里真实的** `ws-adapter.js`，结果用 `HARNESS_RESULT <json>` 回传 |
| `tests/runtime/child-window-control.main.js` / `.page.html` / `.page.js` | 同源子窗口工装：真 `preload-child.js` + 真 `createStorageGate()` 处理器 + 主进程窗口状态采样（§2.5.3） |
| `tests/runtime/ws-echo-server.py` | 本地 WS 回显服务（`echo:` + 原文），端口 18765 |

页面不通过任何调试通道上报，所以同一份探针能跑所有场景。

### 3.2 四个场景与判据

| 场景 | 参数 | 页面应看到 | `RAW_SEND` 应为 | 实测 |
|---|---|---|---|---|
| 桥全链路 | `--mode bridge --isolation true` | 原生 `WebSocket` + `nekoWebSocket` + 适配器 | 1 | 32/32，1 次 |
| 无桥回退 | `--mode fallback --isolation false` + 空 preload | 原生 `WebSocket`，无 `nekoWebSocket` | 0 | 5/5，0 次 |
| chat 隔离态 | `--mode chat-proxy --isolation true` + 真 `src/preload-chat.js` | **原生**（构造器替换失效） | 0 | 5/5，0 次 |
| chat 非隔离 | `--mode chat-proxy --isolation false` + 真 `src/preload-chat.js` | **WSProxy** | 1 | 5/5，1 次 |

**退出码 = 页面自报通过 && 主进程观测到的运输方式符合预期**（`expectedRawSendCount()`）。
只信页面自报是不够的：页面可能拿到正确的数据却走了错误的路径。运输次数才是「直连还是 IPC 代理」的证据。

桥场景逐项覆盖：适配器存在、bridge 暴露、页面全局未被替换、返回对象而非裸句柄、
初始 `readyState=0`、`onopen` 赋值生效、两种监听并存、`readyState` 活值变 1、
**CONNECTING 不吃 stale CLOSED**、**重复 READY 只派一次 open**、send→IPC→主进程真 WS→回显、
`readyState` 变 3、close 带 code/reason、**close 的 reason 原样保留（`连接已断开`，两次过桥）**、
**close 事件是页面世界 `CloseEvent` 实例**、close 后 send 静默丢弃；以及三条 close 边界
（200 字节 reason、异常码 1006、强制构造器抛错回退，见 §2.5.1–2.5.2）。

> 桥场景用 **4 条连接**跑完 32 项：第 1 条验状态机与往返，其余三条分别验三种 close 边界
> （每条新建时由主进程在页面握手后补发一次 `READY`，因为桥只认广播）。

### 3.3 为什么不需要后端

主进程代持一条到本地回显服务的真 `WebSocket`，渲染进程的 `RAW_SEND` 由主进程转发。
验的是**运输链路与状态机**，不是模型或业务逻辑，所以不依赖 8000/48911。

### 3.4 时序是刻意安排的

页面先建 socket，主进程 **1.2 s 后广播一条上一轮遗留的 `CLOSED`**，**2.5 s 后才连真 WS**：
这正是生产里「页面加载时 Pet WS 还没 ready」的顺序。僵尸代理守卫与重复 READY 去重
都是在这个时序下断言的，而不是人为构造的瞬间。

### 3.5 边界

工装里的「Pet」是**主进程代持的 WS**，不是真的 `preload-pet` 窗口；真 Pet 的转发实现与
窗口生命周期没有走到。这层覆盖要等装配后的真机冒烟（§5）。

---

## 4. A/B 证据：隔离态下构造器替换失效

| 维度 | `contextIsolation: true` | `contextIsolation: false` |
|---|---|---|
| 页面 `WebSocket` | 原生（`[native code]`） | `WSProxy` |
| `nekoWebSocket` | 不存在（preload 没 expose） | 不存在 |
| open 耗时 | 26 ms（直连） | 2555 ms（等 READY） |
| 主进程 `RAW_SEND` | **0** | **1** |

结论：把 chat 窗的 `contextIsolation` 翻成 `true` 而**不装配**，页面会直连目标 `ws://` 地址，
不再经 Pet 转发——这正是交接 §4.2 说的阻塞，也是 `#406` 契约测试禁止的组合
（「替换页面全局构造器的 preload ⇒ 该窗不许开隔离」）。
本工装把这条从静态契约变成了**可执行的运输方式证据**。

---

## 5. 真实应用基线（CDP 冒烟）

### 5.1 工具修复

`scripts/smoke-ws-isolation.py` 原来会抓到加载窗的瞬时 target，并在 React 窗出现前就返回。
现在：

- `_is_app_page()` 只认 `localhost:48911` / `127.0.0.1:48911` 的页面（`:72`）
- `--settle`（默认 6 s）后再列一次 target，等 Chat/Toast 挂载（`:159`、`:220-222`）
- 每个 target 先做存活检查，`cdp_eval` 失败只记一条 skipped，不中断整轮（`:103` 起调用处）

### 5.2 基线结果（3 扇窗）

| 窗口 | `WebSocket` 原生 | `nekoWebSocket` | `__nekoCreateWebSocket` |
|---|---|---|---|
| Toast 窗（`/toast`） | **True** | undefined | undefined |
| Chat 窗（`/chat`） | **False** | undefined | undefined |
| Pet 窗（`/`） | **False** | undefined | undefined |

pet 窗一条 console warning 是 Live2D 头像抓取失败（无模型），与本议题无关。

### 5.3 读法

真实应用里**适配器还没被任何页面引入**（`__nekoCreateWebSocket` 全 undefined），
chat/pet 仍靠 preload 构造器替换。所以 §4.2 的装配仍是必要工作；基线正是装配后的对照起点。

---

## 6. 对交接 §5.1 / §6.3 的更正

| 交接原文 | 实测 |
|---|---|
| 源码后端「活不过一分钟」，约 20 s 自行退出 | **未复现**。从 `NEKO/N.E.K.O` 用**项目 venv 的 python 直接跑** `launcher.py`，48911 / 48915 持续监听、`/health` 200。日志末尾 `EmbeddingWorker ... model_file_missing` 是嵌入模型缺失导致该 worker 退出，**主服务没有跟着退** |
| 用 `python launcher.py`（系统解释器）启动 | 会触发 launcher 的 re-exec：`launcher_core/bootstrap.py` 里 `os.execv(target_executable, [target_executable] + sys.argv)`；项目路径含空格（`D:\my git …`）时 argv 被拼坏，表现为立刻失败。**绕法：直接用项目 venv 的解释器启动** |
| 「必须先有一个能长期活着的后端」 | 对**基线冒烟**不成立：只要 48911 能 200 就能起壳并探针（本次 8000 是 down 的，冒烟照常完成）。只有**聊天往返**才需要 8000 + 模型 |

仍然成立的问题：`launcher_core/lifecycle.py` 的 4 处 lumo 补丁被上游覆盖（`0/4 expected`），
`scripts/neko_launcher_wrapper.py` 仍 fail-fast——这条是代码问题，不是环境问题。

---

## 7. 环境自检（新增，省排查时间）

| 检查 | 含义 |
|---|---|
| `electron.exe --version` 打印 `v24.x` | `ELECTRON_RUN_AS_NODE` 还在环境里（Electron 会按 Node 跑）；正常应打印 Electron 版本 |
| 本地端口探测出现 `502` | 走了 `HTTP_PROXY`；加 `NO_PROXY=127.0.0.1,localhost,::1` 或 `ProxyHandler({})` |
| 起壳连崩、`GPU process isn't usable` | 加 `--no-sandbox --disable-gpu --disable-gpu-compositing` |
| 回显服务 `WinError 10048` | 18765 已有实例在跑（先探测再决定是否起） |

---

## 8. 复现命令

`python` 指装有 `websockets` + `websocket-client` 的解释器（本机为
`C:\Users\ASUS\python-sdk\python3.13.2\python.exe`）。

```bash
# 0) 回显服务（已存在则跳过）
python neko-electron-shell/tests/runtime/ws-echo-server.py

# 1) 单测
cd neko-electron-shell && node --test "tests/*.test.js"      # 21 pass
cd NEKO/N.E.K.O && node tests/frontend/ws-adapter.test.js    # 10 pass

# 2) 端到端四场景（cwd = neko-electron-shell）
E=node_modules/electron/dist/electron.exe
FLAGS="--no-sandbox --disable-gpu --disable-gpu-compositing"
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS NO_PROXY=127.0.0.1,localhost,::1 \
  $E tests/runtime/bridge-e2e.main.js --mode bridge --isolation true $FLAGS
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS NO_PROXY=127.0.0.1,localhost,::1 \
  $E tests/runtime/bridge-e2e.main.js --mode fallback --isolation false \
     --preload tests/runtime/bridge-e2e.preload-empty.js $FLAGS
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS NO_PROXY=127.0.0.1,localhost,::1 \
  $E tests/runtime/bridge-e2e.main.js --mode chat-proxy --isolation true \
     --preload src/preload-chat.js $FLAGS
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS NO_PROXY=127.0.0.1,localhost,::1 \
  $E tests/runtime/bridge-e2e.main.js --mode chat-proxy --isolation false \
     --preload src/preload-chat.js $FLAGS

# 3) 变异对照（预期退出码 1，9 处 payload 检查失败）
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS NO_PROXY=127.0.0.1,localhost,::1 \
  $E tests/runtime/bridge-e2e.main.js --mode bridge --isolation true \
     --preload tests/runtime/bridge-e2e.preload-legacy-event.js $FLAGS

# 4) 同源子窗口四方法（不需要回显服务与后端）
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS NO_PROXY=127.0.0.1,localhost,::1 \
  $E tests/runtime/child-window-control.main.js $FLAGS

# 5) 真实应用 CDP 冒烟（需要 48911 活着）
python scripts/smoke-ws-isolation.py --wait 90 --json ../_smoke.json
```

`--out <file>` 可把主进程观测写成 JSON（`rawSendCount`、`readyBroadcasts`、
`mainWsEvents`、`pageReport`、`transportCheck`）。

---

## 9. 本文**没**验证的

| 项 | 状态 |
|---|---|
| 真 `preload-pet` 窗口的转发实现与生命周期 | ❌ 工装用主进程代持 WS |
| 三扇 chat 窗装配（交接 §4.2） | ❌ 未做，真实应用仍是旧路径 |
| 端到端聊天往返（要 8000 + 模型） | ❌ 未做 |
| `close` 的 `reason` 边界 | ✅ 短非 ASCII、200 字节、异常码 1006、构造器抛错回退均已验（§2.5） |
| 同源子窗口四方法 | ✅ 16/16 + 主进程状态核对（§2.5.3） |
| `webSecurity: false` ×5 | ❌ 未验 |
| `skipAppear` **动画效果** | ❌ 仍需真机人眼（argv 通道与 preload 读取已有静态契约） |

---

## 10. 下一步

1. 抽 `preload-common.js`，按交接 §4.2 装配三扇 chat 窗，每步跑 §8 的 1）与 2）。
2. 装配后重跑 §8 的 5），预期 chat 窗出现 `nekoWebSocket: object`、
   `__nekoCreateWebSocket: function`、`probeReadyState: 0 → close 后 3`。
3. 补聊天往返与断线重连的人工点验。
