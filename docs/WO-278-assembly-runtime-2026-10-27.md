# WO-278 装配后的运行时验证 · 2026-10-27

> 本文记录**首次在真机、真后端、真 Electron 下**验证装配结果。
> 前一份 `WO-278-runtime-verification.md` 验的是「桥 + 适配器」这套零件（独立 echo server）；
> 本文验的是**装配进应用之后**的 chat 窗。

---

## 1. 环境与方法

| 项 | 值 |
|---|---|
| 后端 | 源码链路 `scripts/neko_launcher_wrapper.py`（依赖 #430 复原的 `lifecycle.py` 4 处补丁） |
| 后端健康 | `GET /health` → `200 {"app":"N.E.K.O","service":"main","status":"ok",...}`，8 秒内就绪 |
| Electron | `node_modules/electron/dist/electron.exe`（Chrome/148），`--remote-debugging-port=9222 --remote-allow-origins=* --no-sandbox --disable-gpu` |
| 配置隔离 | `NEKO_USER_DATA_DIR` 指向临时目录，**不碰用户真实 profile** |
| 探针 | `scripts/smoke-ws-isolation.py`：CDP attach → 每个渲染 target 跑 `Runtime.evaluate` |
| 代码版本 | `main @ c58472bde738`（#429 装配 + #430 lifecycle 补丁均已合入） |

**启动前必须清掉的环境变量**（宿主注入的，不清就起不来）：

```
ELECTRON_RUN_AS_NODE / NODE_OPTIONS
CODEBUDDY_SAFE_DELETE_BULK_GUARD / _STATE_DIR / _REPORT_PATH
```

---

## 2. 结果：3 个渲染进程

| 窗口 | URL | `nekoWebSocket` | `__nekoCreateWebSocket` | `WebSocket` 原生 | console 错误 |
|---|---|---|---|---|---|
| **chat（已隔离）** | `/chat` | **object**（create=true） | **function** | **true** | **0 条** |
| pet（未迁移） | `/` | undefined | function | **false** | — |
| toast | `/toast` | undefined | undefined | true | — |

### chat 窗完整探针

```json
{
  "hasNekoWebSocket": "object",
  "hasNekoWebSocketCreate": true,
  "hasAdapter": "function",
  "webSocketIsNative": true,
  "hasNekoChatWindow": "object",
  "probeReadyState0": 0,
  "probeReadyStateAfterClose": 3
}
```

---

## 3. 这三行分别证明了什么

### 3.1 `hasNekoWebSocket: object` + `create: true` —— preload 的桥真的过到了页面

`preload-chat.js` 在 `contextIsolation: true` 下用 `exposeToPage('nekoWebSocket', createWebSocketBridge(...))`，
页面能拿到对象且有 `create` 方法 ⇒ **contextBridge 通道成立**。

### 3.2 `webSocketIsNative: true` —— 构造器替换已经彻底移除

这是最关键的一条。旧架构下 chat 窗的 `window.WebSocket` 被换成 `WSProxy`，探针会读到 `false`。
现在读 `true` ⇒ preload 不再动页面全局，装配**没有留下半套旧机制**。

### 3.3 `readyState 0 → 3` —— 桥造出来的代理是真的能跑状态机

探针在页面里 `window.nekoWebSocket.create('ws://…')` 建了一个实例：

- `0` = CONNECTING（等 Pet 窗的真 WS READY）
- 调 `close()` 后 `3` = CLOSED

⇒ `getReadyState()` 与 `close()` 的本地语义都对，**不是空壳对象**。

> 为什么停在 CONNECTING：chat 窗自己不建真连接，要等 Pet 窗的真 WebSocket READY。
> 本次冒烟只起了 chat 窗的页面，没有走「Pet 已连接 → 发消息」的完整链路，所以没到 OPEN。
> 这属于**未验范围**，见 §5。

### 3.4 `console: []` —— 页面加载期零错误

适配器与页面桥都在 `app-websocket.js` 之前加载，没有出现「`__nekoCreateWebSocket` 未定义」
或「`electron-page-bridge` 报错」这类加载顺序问题。

---

## 4. `/` 窗口 `WebSocket` 非原生 —— 已知且符合预期

`preload-pet.js:3762` 仍执行 `window.WebSocket = function (...)`（pet 窗持有真连接、负责转发）。
pet 窗是 `contextIsolation: false` 的**有意保留**：它读 **22 个页面全局、约 140 处**
（`mmdManager` 43 / `live2dManager` 35 / `Jukebox` 21，全是活的类实例），
contextBridge 过不去 ⇒ 迁移等于 5524 行重构，不是翻配置。

⇒ 探针在 `/` 读到 `false` **不是回归**，是未迁移项的现状。

---

## 5. 未验范围（诚实登记）

| 项 | 状态 | 为什么 |
|---|---|---|
| **完整聊天往返**（发消息 → 模型回复） | ❌ 未验 | 需要可用模型额度；本次后端起来了但 `[CUA] LLM connectivity FAIL (AGENT_API_KEY_INVALID)` —— 用户配置的 dashscope key 失效，与本次改动无关 |
| chat 窗进入 OPEN 态 | ❌ 未验 | 需要 Pet 窗真 WS 连上后端（要 pet 窗完整跑起来 + 有效模型） |
| 断线重连 / 僵尸代理 | ❌ 未验 | 同上，需要真实网络抖动 |
| `webSecurity: false` ×5 去留 | ❌ 未验 | 取决于用户可配的 `apiBaseUrl`，要运行期判断跨源素材 |
| 视觉/动画 | ❌ 不可能自动验 | 需要人眼 |

---

## 6. 本轮顺带修掉 / 发现的问题

### 6.1 已修：#429 的 adapter 测试夹具形状错（确定性红）

`tests/frontend/ws-adapter.test.js` 原夹具：

```js
win._bridgeHandle._fire('message', { type: 'message', data: 'hello' });   // ❌
```

而真实入站是 **WebSocket 的 `event.data` 原始字符串**（`preload-pet.js:3800`
`ipcRenderer.send(RAW_MESSAGE, event.data)`），close 才是 `{code, reason}`。
夹具造错形状 ⇒ 适配器忠实地把整个对象当 `data` 传下去 ⇒ 断言期望 `'hello'` 必然红。

**改后**：`_fire('message', 'hello')` / `_fire('close', { code: 1001 })` ⇒ **9 pass**。
**产品代码没动**（它本来就是对的）。

### 6.2 未修（记录）：wrapper 用非项目解释器启动时，路径被空格截断

用 `C:/Users/ASUS/python-sdk/.../python.exe` 跑 wrapper，会在
`_maybe_reexec_into_project_venv` 之后报：

```
uv-python3.11: can't open file 'D:\my git\scratchpad-unified\NEKO\N.E.K.O\git\scratchpad-unified\NEKO\N.E.K.O\.venv\Scripts\python.exe'
```

即项目路径里的**空格**（`D:\my git`）把一条拼好的命令行切成了两半。

**绕法（已验证可用）**：直接用项目自己的 `.venv/Scripts/python.exe` 跑 wrapper
⇒ `current_venv_dir == expected_venv_dir`，reexec 分支早退，不再触发。

⇒ 只要项目**不在带空格的路径**下，或**用项目 venv**，就不受影响。
真修需要找到那处字符串拼命令的地方（`launcher_core/runtime.py` 的子进程启动路径），另立单。

---

## 7. 复现命令

```bash
# 1) 后端（必须用项目 venv，且清掉宿主注入的变量）
cd NEKO/N.E.K.O
env -u NODE_OPTIONS -u CODEBUDDY_SAFE_DELETE_BULK_GUARD \
    -u CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR -u CODEBUDDY_SAFE_DELETE_REPORT_PATH \
    PYTHONUTF8=1 NO_PROXY="127.0.0.1,localhost,::1" \
    ./.venv/Scripts/python.exe ../../scripts/neko_launcher_wrapper.py
# 期望日志: [wrapper] lifecycle.py local-patch verified (4/4) → 所有服务器已启动完成

# 2) 另开一个终端，确认后端（禁用代理，否则会拿到代理的假 502）
python -c "import urllib.request as u; print(u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:48911/health',timeout=5).status)"

# 3) 冒烟
cd neko-electron-shell
../.venv/Scripts/python.exe scripts/smoke-ws-isolation.py \
    --extra-args "--no-sandbox --disable-gpu --disable-gpu-compositing" --wait 90
```

**期望输出**（关键三行）：

```
[人类 Terminal - Project N.E.K.O.]
  nekoWebSocket        : object  (create=True)
  __nekoCreateWebSocket: function
  WebSocket 是原生      : True
```

---

## 8. P1-c：full-chat / react-chat 开隔离（同日追加）

### 8.1 两扇窗的起点不一样

| 窗 | preload 原状 | 本批改动 |
|---|---|---|
| `reactChatWindow` | ~~早已迁完~~ → **更正**：main 上是旧版（8124 行、含 `window.WebSocket = WSProxy`）；「已迁完」是我看**本地工作树**得出的错误结论，详见 §10 | 翻配置 + **补桥**（#431 的 preload 版本，提交 `93439fec`） |
| `fullChatWindow` | 仍是 `window.WebSocket = WSProxy`（L364） | 补 `exposeToPage` + `createPageSocket` + 暴露，删掉构造器替换 |

### 8.2 为什么不换成 `websocket-bridge.js` 的工厂

这两份 `WSProxy` **不是 chat 窗那个简化版**，它带着生产上修过的两件事：

- **会话代际过滤**（`_isStaleLifecycle` / `_adoptLifecycle` / `_cancelOlderClose`）——防止切档案时吃到上一代的生命周期
- **构造前消息缓冲**（`_wsBuffer`）——Pet 的 `READY` / greeting `RAW_MESSAGE` 可能在页面建连前到达，丢了就少一条开场白

换成简化工厂会**静默丢这两条语义**。所以做法是**保留 WSProxy 引擎**，只在它外面套一层
`createPageSocket()`：句柄成员全是函数，回调送出**纯 payload**（message → 数据本体、
close → `{code, reason}`），页面世界由 `ws-adapter.js` 重建 Event。

> 这层包装是从 `preload-chat-react.js` 已有的实现**照搬**到 full 的（两文件同构），不是新设计。

### 8.3 验收

```
node --test "tests/*.test.js"   → # tests 28 / # pass 28 / # fail 0
node --check preload-chat-full.js / window-manager.js / 契约测试 → 全 OK
```

**「改坏 ⇒ FAIL」**：把 `window.WebSocket = WSProxy;` 加回 `preload-chat-full.js` ⇒

```
not ok 8  - 替换页面全局构造器的 preload，其窗口不得开 contextIsolation（WO-278 批 3）
not ok 10 - reactChatWindow / fullChatWindow 已改走 WS 桥并开 contextIsolation（WO-278 P1-c）
# fail 2
```

还原后 28 pass、sha256 一致。

### 8.4 运行时：full-chat **已验绿**，react-chat **工装验不了**

这两扇窗是**托盘触发的懒创建**窗口，正常冒烟不会打开它们。所以新增了工装
`tests/runtime/isolation-harness.main.js`（用指定 preload + 指定 URL 起一个真窗口），
并给 `smoke-ws-isolation.py` 加了 `--entry` 参数。

**full-chat（`preload-chat-full` + `/chat_full`，contextIsolation:true）**：

```
nekoWebSocket      : object  (create=True)
__nekoCreateWebSocket: function
WebSocket 是原生    : True
probe readyState   : 0 → close 后 3
```

⇒ 与 chat 窗同等的三行证据，**P1-c 的 full 部分成立**。

**react-chat：工装连不上 CDP target（`Connection timed out`）**，且做了决定性对照：

| 组合 | 结果 |
|---|---|
| `preload-chat` + `/chat`（已知好） | ✅ 全绿 |
| `preload-chat-react` + `/chat`，**contextIsolation: true** | ❌ CDP 超时 |
| `preload-chat-react` + `/chat`，**contextIsolation: false**（复刻旧架构） | ❌ **同样超时** |

⇒ 超时**与隔离无关**，是该 preload/页面在这个工装里的既有问题（真机上由托盘路径创建、
带 `persist:neko-full-chat` 分区等上下文，工装没复刻）。
**所以 react-chat 的运行时行为仍是「未验」**，只有静态契约 + 代码审查作依据。

### 8.5 计数变化

| 范围 | 之前 | 现在 |
|---|---|---|
| `window-manager.js` | true 9 / false 3 | **true 11 / false 1**（只剩 `petWindow`） |
| 整个 `src/` | true 14 / false 8 | **true 16 / false 6** |

`src/` 里另 5 处 `contextIsolation:false` 在契约测试**覆盖范围之外**
（`avatar-tool-cursor-service.js` 1、`main.js` 1、`tutorial-global-overlay-service.js` 2、
`main/pet-window-lifecycle.js` 1）——其中 `tutorial-global-overlay-service` 的 2 处
和 `avatar-tool-cursor-service` 的 1 处**没有同行理由注释**，属既有缺口，建议单独立单补契约。

---

## 9. 契约覆盖缺口已补（同日追加）

§8.5 里提到的「5 处在契约覆盖范围之外」，根因是**契约只遍历白名单里列出的文件**：

```js
for (const rel of Object.keys(ISOLATION_EXCEPTIONS)) { ... }   // ← 只看登记过的文件
```

⇒ 在**任何没登记过的文件**里新开一个 `contextIsolation:false` 的窗口，**没有任何断言会看见**。

### 9.1 改法

| 改动 | 内容 |
|---|---|
| 覆盖面 | 改成 `for (const rel of listSourceFiles())`，**扫整个 `src/`** |
| 文件级登记 | 新增 `FILE_LEVEL_ISOLATION_EXCEPTIONS`：`avatar-tool-cursor-service.js`、`tutorial-global-overlay-service.js`（它们的 `new BrowserWindow(` 不是 `X = new ...` 形式，反推不出窗口名） |
| 棘轮 | `allowed >= 2` 改成**精确值** `strictEqual(allowed, 5)`：多一处要改常量、少一处（迁移完成）也要改常量，不会悄悄脱钩 |
| `main.js` 加载窗 | **无 preload** ⇒ 隔离对它没有任何作用，直接收紧为 `contextIsolation: true`（少一处豁免） |

### 9.2 为什么三个 overlay 不顺手翻

`preload-avatar-tool-cursor-overlay.js` / `preload-tutorial-global-overlay.js` /
`preload-tutorial-loading-overlay.js` **都没有直写 `window.*`**（只做 DOM 注入，DOM 跨世界共享），
理论上可以隔离。但它们的触发链路（光标捕获、教程光效/加载覆盖层）**没有做运行期验证**，
本机也不容易复现 ⇒ 暂留 `false`，但在源码那一行**补了同行理由**并登记进契约。

### 9.3 验收

```
node --test "tests/*.test.js"   → 28 pass / 0 fail
```

**覆盖面验证**：临时新建 `src/_probe-unregistered-window.js`（含一处未登记 `contextIsolation:false`）⇒

```
not ok 2 - contextIsolation:false 只允许出现在白名单窗口，且必须带同行说明
   出现未登记的不隔离窗口：...
# fail 1
```

删除后恢复 28 pass。⇒ **缺口真的补上了，不是只改了断言数字。**

### 9.4 剩余 5 处豁免

| 位置 | 原因 |
|---|---|
| `window-manager.js` `petWindow` | pet 窗读 22 个页面全局约 140 处，见 §5 |
| `main/pet-window-lifecycle.js` `mainWindow` | 同一份 `preload-pet.js` |
| `avatar-tool-cursor-service.js` ×1 | overlay，触发链路未验 |
| `tutorial-global-overlay-service.js` ×2 | overlay，触发链路未验 |

---

## 10. 更正与教训：**本地工作树 ≠ main**（2026-10-27 18:xx）

### 10.1 我说错了什么

§8.1 里写着「`reactChatWindow` 的 preload 早已迁完，只差窗口配置一行」。**这句是错的。**

真实情况：

| 位置 | `preload-chat-react.js` |
|---|---|
| **main** | 8124 行，含 `window.WebSocket = WSProxy`，**没有** `exposeToPage('nekoWebSocket')` |
| 我的本地工作树 | 8190+ 行，已无构造器替换、已有桥（是**别人未合入的 P1/P2/P3 改动**） |

我当时看到的是本地工作树，就当成 main 的状态写了文档、并据此把 `reactChatWindow` 翻成隔离。

### 10.2 后果（真实的、不是理论风险）

main 上出现了 **「隔离 + 构造器替换」** 这个不安全组合：
`contextIsolation: true` 的窗里 preload 去写 `window.WebSocket = WSProxy` 会被**静默忽略**，
页面的 `new WebSocket()` 走回原生实现 ⇒ React Chat 的 WS 中转失效。

**是契约测试抓出来的**（在 main 上跑，不是在本地跑）：

```
not ok 28 - 替换页面全局构造器的 preload，其窗口不得开 contextIsolation（WO-278 批 3）
not ok 30 - reactChatWindow / fullChatWindow 已改走 WS 桥并开 contextIsolation（WO-278 P1-c）
```

### 10.3 修法

- 取 PR #431 的 `preload-chat-react.js`（main 侧该文件与 #431 的 base 是同一个 blob `b3a86932`，可整文件替换）
- 按 Git Data API 直接落到 main：提交 `93439fec`
- **验证**：从 main 全量拉取 shell + 页面文件 → `node --test "tests/*.test.js"` → **32 pass / 0 fail**

### 10.4 两个教训

1. **永远不要用本地工作树判断 main 的状态。** 这个仓有多条线并行（别人也在同一个工作树里改），
   本地文件可能领先 main 好几个 PR。判断"main 上有没有"只有一个办法：**从 main 拉 blob/tree**。
   （我之前定的规矩是"判做完看 main 路径"，但只用在**交付后复核**，没用在**动手前调研**——这就是漏洞。）
2. **契约测试要在 main 上跑一遍。** 本地绿没有任何意义——本地那套文件组合根本不等于仓库状态。

### 10.5 附带发现：merge API 会产生孤儿提交

`PUT /pulls/{n}/merge` 对 #431 返回了 `merged=true` 且给了 `merge_commit_sha`，
但那个 squash 提交的**父节点是 PR 的旧 base**，与 main 分叉，**main 根本没动**。
判定方法：`GET /compare/main...<merge_commit_sha>`，看 `status` 是不是 `ahead`/`identical`；
`diverged` 就说明没落上去。这种"看着合了其实没合"最坑，**必须以 main 的 tree 为准**。

---

## 11. React Chat 真机验证：24 个注入全部可见（2026-10-27 19:4x）

### 11.1 为什么这次必须验

`reactChatWindow` 在 #432 被翻成 `contextIsolation: true`，但 main 上的 `preload-chat-react.js`
还有 **24 个直写 `window.*`** ⇒ 在隔离窗里**全部被静默忽略**（窗口控制 / 截屏 / 字幕 / 点歌开关 /
配置注入 / 快捷键聚焦 / avatar tool 屏幕点…）。#431 修了 WS 运输，#433 修了 A 组 API。
**这两个改动都必须用真机确认「注入真的可见了」，否则只是"文件改了"。**

### 11.2 方法（这一套是可复用的）

CDP 在重度页面上不稳（`Connection timed out`），所以走**主进程 `executeJavaScript`**：

```bash
# 0) 后端先起（源码链路，wrapper）
cd NEKO/N.E.K.O && ./.venv/Scripts/python.exe ../../scripts/neko_launcher_wrapper.py
#    等 /health 200（禁用代理，否则拿到代理的假 502）

# 1) 用「main 的 preload」+ 指定页面起一个真窗口，让主进程把探针结果打出来
cd neko-electron-shell
env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS     -u CODEBUDDY_SAFE_DELETE_BULK_GUARD -u CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR     -u CODEBUDDY_SAFE_DELETE_REPORT_PATH   HARNESS_PRELOAD=preload-chat-react   HARNESS_URL="http://localhost:48911/chat"   HARNESS_ISOLATION=1   HARNESS_PROBE_JS="$PROBE" HARNESS_PROBE_DELAY_MS=14000   ./node_modules/electron/dist/electron.exe tests/runtime/isolation-harness.main.js --no-sandbox
```

### 11.3 ⚠️ 环境坑（这次踩到，值得记）

**`--disable-gpu` 会让 `Network service` 崩掉**，页面永远到不了 `did-finish-load`：

```
[19792:ERROR:content\browser\network_service_instance_impl.cc:703] Network service crashed or was terminated, restarting service.
[19792:ERROR:content\browser\gpu_process_host.cc:1017] GPU process exited unexpectedly: exit_code=143
```

之前 pet 窗 / react 窗的「CDP 超时」「页面加载不完」**很可能就是这个原因**，不是页面太重。
去掉 `--disable-gpu`（只留 `--no-sandbox`）后立刻正常：`did-finish-load` + 探针有结果。

### 11.4 结果（真 Electron + 真后端 + `contextIsolation: true`）

```json
{
  "nekoWebSocket": "object",
  "adapter": "function",
  "nekoChatWindow": "object",
  "chatWinMethods": 21,
  "bringToFront": "function",
  "desktopCapturer": "object",
  "screenshotProxy": "object",
  "subtitleWindow": "object",
  "jukeboxToggle": "function",
  "multiWindow": "boolean",
  "wsNative": true
}
```

逐项含义：

| 探针 | 值 | 说明 |
|---|---|---|
| `nekoWebSocket` / `adapter` | object / function | P1 的 WS 桥在页面可见，适配器已加载 |
| `nekoChatWindow` | object，**21 个方法** | 窗口控制从"直写全丢"变成"经活门面可见" |
| `bringToFront` | **function** | 门面方法可调用（不是空壳） |
| `desktopCapturer` / `screenshotProxy` / `subtitleWindow` | object | 截屏、截图代理、字幕窗 API 都在 |
| `jukeboxToggle` / `multiWindow` | function / boolean | 点歌开关、多窗标记都在 |
| `wsNative` | **true** | 构造器替换没有回来（`WebSocket` 仍是原生） |

⇒ **#431 + #433 的修复在真机上成立**：那 24 个原本静默失效的注入，现在页面都拿得到。

### 11.5 仍未验（诚实登记）

| 项 | 为什么 |
|---|---|
| 拖拽 / 缩放的实际手感 | 需要人眼与鼠标 |
| 点歌弹窗、字幕窗的真实行为 | 只验了 API 可见，没验交互流程 |
| 截图的图像内容是否正确 | 只验了 API 存在 |
| React Chat 的完整聊天往返 | 需要有效模型额度（当前 `AGENT_API_KEY_INVALID`） |

---

## 12. Pet 注册面真机验证（2026-10-27 20:xx）

### 12.1 怎么验的

pet 窗真实页（`/`，含 Live2D/VRM/MMD）在本工装里仍然加载不完，所以用**等价边界**验证：
**真实 `preload-pet.js` + 真实 `static/app/pet-host-bridge.js`**，页面只提供同形的假全局。

```bash
# 1) 把真实注册面和一个夹具页放进同一目录，用本地 http 供出
mkdir _petweb && cd _petweb
cp ../../scratchpad-unified/NEKO/N.E.K.O/static/app/pet-host-bridge.js .
# index.html：先定义 lanlan_config / appState / pageConfigReady / master_name /
#             DragHelpers（isDragging + restoreButtonPointerEvents）/ t / safeT / mmdManager
#             再 <script src="pet-host-bridge.js">
python -m http.server 8931 --bind 127.0.0.1 &

# 2) 用真实 preload 起窗口，主进程 executeJavaScript 取诊断（不依赖 CDP）
cd neko-electron-shell
HARNESS_PRELOAD=preload-pet HARNESS_URL=http://127.0.0.1:8931/ HARNESS_ISOLATION=1 \
HARNESS_PROBE_JS="$PROBE" HARNESS_PROBE_DELAY_MS=3000 \
  ./node_modules/electron/dist/electron.exe tests/runtime/isolation-harness.main.js --no-sandbox
```

### 12.2 结果：两种模式**完全一致**（除 `isolated` / `misses`）

```json
// ISO=1（隔离）
{"host":"object","restored":true,
 "snap":{"isolated":true,"hostRegistered":true,"misses":{"nekoSubtitleShared":1},
   "probes":{"t":"function","safeT":"function","lanlan_config":"object","appState":"object",
             "pageConfigReady":"boolean","dragHelpersBusy":true},
   "calls":{"t":"T:probe.key","restore":"called","configModelType":"vrm"}}}

// ISO=0（非隔离对照）
{"host":"object","restored":true,
 "snap":{"isolated":false,"hostRegistered":true,"misses":{},
   "probes":{"t":"function","safeT":"function","lanlan_config":"object","appState":"object",
             "pageConfigReady":"boolean","dragHelpersBusy":true},
   "calls":{"t":"T:probe.key","restore":"called","configModelType":"vrm"}}}
```

**证明了什么**：

| 证据 | 含义 |
|---|---|
| `hostRegistered: true` | 页面侧的 `pet-host-bridge.js` 成功通过 `contextBridge` 把 getter 交给 preload |
| `probes.*` 类型正确 | 函数过桥仍是 `function`、数据仍是 `object`、布尔仍是 `boolean` |
| `calls.t === 'T:probe.key'` | **函数真的被调用并返回值**（不是拿个空壳） |
| `restored: true` | 页面以 `window.__restored = true` 验证副作用**真的发生在页面世界** |
| `calls.configModelType === 'vrm'` | 数据读取拿到的是当前值 |
| 两模式结果一致 | 门控（`if (!process.contextIsolated) return window[name]`）语义等价 |
| `misses: {nekoSubtitleShared: 1}` | miss 计数器工作正常（夹具故意没提供该能力） |

### 12.3 ⚠️ 工装的 3 个「假故障」（都曾让我误判"页面太重"）

| # | 现象 | 真因 | 修法 |
|---|---|---|---|
| 1 | 页面永远不到 `did-finish-load`，日志有 `Network service crashed` + `GPU process exited (143)` | 传了 `--disable-gpu` | **去掉**该参数（只留 `--no-sandbox`） |
| 2 | 轻量页同样等不到 `did-finish-load` | 监听挂在 `loadURL()` **之后**，轻量页在挂之前就加载完了 | **先挂监听再 load**，并加 `loaded` 兜底 |
| 3 | `preload-pet` 起的窗口一律卡住 | preload 加载期用 `sendSync` 读 3 个主进程状态，工装没有 handler ⇒ 渲染进程卡在同步 IPC | 补 `ipcMain.on(ch, e => e.returnValue = undefined)` |

> 教训：**"页面太重所以加载不了"是个偷懒结论**。先看进程错误日志、先怀疑自己的工装。

### 12.4 顺带修掉诊断自身的一个假报

`pageApi('DragHelpers.isDragging')` 这种**带点的复合名**，在非隔离下回落是
`window['DragHelpers.isDragging']` ⇒ 必然 `undefined`，诊断会假报"能力缺失"。
改成直接调用生产代码同款的 helper（`petDragHelpersBusy` / `petRestoreButtonPointerEvents`），
两种模式都可信 —— 修完才拿到上面那份"两种模式一致"的对照。

### 12.5 仍未验

| 项 | 原因 |
|---|---|
| pet 真实页（Live2D/VRM 渲染）在本工装里的加载 | 与本改动无关的渲染负载 |
| 拖拽手感 / 命中测试精度 | 需要人眼与鼠标 |
| 点歌弹窗、字幕窗真实流程 | 只验了边界契约 |

---

## 13. 修掉「工装会在屏幕上留一个空白 Electron 窗」（2026-10-27 20:5x）

### 13.1 现象

用户报告「有一个 electron 白窗，从前几天开始」。排查结论：**是我的测试工装弹的**。

- `tests/runtime/isolation-harness.main.js` 创建窗口时 `show: true`
- `tests/runtime/child-window-control.main.js` 同样 `show: true`

这些工装一跑就是几十秒；更糟的是在修 §12.3 那三个坑之前，它们会**卡在等 `did-finish-load`**，
于是屏幕上就留下一个**空白 Electron 窗**，一直挂着。

### 13.2 修法

| 项 | 改动 |
|---|---|
| 可见性 | 两个工装改成 `show: process.env.HARNESS_SHOW === '1'` ——**默认不显示**，要肉眼看才开 |
| 看门狗 | `isolation-harness` 加 `HARNESS_MAX_MS`（默认 120s）：探针模式下若迟迟不结束，`app.exit(0)`，不让进程和窗口留在屏幕上 |

### 13.3 验收

```bash
# 默认（不开窗）：仍能拿到探针结果并正常退出
HARNESS_PRELOAD=preload-chat HARNESS_URL="data:text/html,<h1>x</h1>" HARNESS_ISOLATION=1 \
HARNESS_PROBE_JS="({ws: typeof window.nekoWebSocket})" HARNESS_PROBE_DELAY_MS=1500 \
  ./node_modules/electron/dist/electron.exe tests/runtime/isolation-harness.main.js --no-sandbox
# → [harness] did-finish-load / [harness-probe] {...} / 退出码 0，全程无可见窗口
```

### 13.4 教训

**测试工装也是产品的一部分**：它会占用用户的屏幕、CPU 和注意力。
凡是会创建窗口的自动化，默认就该是**不可见**的，可见必须是显式 opt-in；
并且必须有超时自杀，避免"跑挂了就永远挂在那"。

（另外：`bridge-e2e.main.js` 的 `react-chat-state` 模式仍需 `show: true`——它验的是
`document.hidden` 下的行为，属有意为之，但同样建议后续加看门狗。）
