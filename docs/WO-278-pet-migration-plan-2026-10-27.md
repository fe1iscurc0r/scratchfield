# WO-278 · pet 窗架构改造方案（2026-10-27）

> 现状：`contextIsolation` 全线只剩 **1 扇窗**（`petWindow`）还是 `false`。
> 本文不改代码，只给**可执行的分阶段路径 + 每阶段验收**，以及"值不值得做"的判断。

---

## 1. 精确量化（脚本统计，非估算）

`preload-pet.js` **5524 行**，对 `window.*` 的读取 **336 处 / 39 个名字**。分成两类：

### ① DOM / 浏览器标准 API：**13 个 / 126 处，不需要迁移**

| 名字 | 处数 | | 名字 | 处数 |
|---|---:|---|---|---:|
| `addEventListener` | 67 | | `devicePixelRatio` | 3 |
| `innerWidth` | 12 | | `requestAnimationFrame` | 2 |
| `innerHeight` | 11 | | `screenX` / `screenY` | 1 / 1 |
| `dispatchEvent` | 8 | | `cancelAnimationFrame` | 1 |
| `setTimeout` | 8 | | `getComputedStyle` | 5 |
| `location` | 4 | | `clearTimeout` | 3 |

> **为什么不用管**：`contextIsolation` 只分离 **JS 全局**，不分离 DOM。这些 API 在隔离世界里照常可用。
> 上一版方案里把它们也算进"待迁移"，是数字虚高的原因之一。

### ② 真正的页面全局：**22 个 / 197 处，需要处理**

| 类别 | 名字（处数） | 小计 |
|---|---|---:|
| **活实例** | `mmdManager` 43、`vrmManager` 43、`live2dManager` 35、`Jukebox` 21、`avatarPortrait` 3 | **145** |
| **数据/配置** | `lanlan_config` 12、`appState` 6、`pageConfigReady` 6、`nekoSubtitleShared` 4、`appButtons` 3、`_agentTaskMap` 2、`master_name`/`master_profile_name`/`master_nickname`/`master_display_name` 各 1 | **37** |
| **函数/工具** | `DragHelpers` 7、`captureProactiveChatScreenshot` 2、`resetToDefaultModel` 2、`captureScreenshotDataUrl` 1、`t` 1、`safeT` 1、`subtitleBridge` 1 | **15** |

> ⚠️ **更正**：我之前口头说的"约 140 处"是低估，准确是 **197 处**。名字数（22）对得上。

### 实例调用的真实构成（决定方案形态）

| 用法 | 处数 | 性质 |
|---|---:|---|
| `interaction`（读写 `.isDragging`） | 24 | 状态读写 |
| `getModelScreenBounds()` | 12 | **需要同步返回值** |
| `getCurrentModel()` | 8 | 同步返回实例 |
| `resumeRendering` / `pauseRendering` | 12 | 命令 |
| `resetModelPosition` | 6 | 命令 |
| `currentModel`（判空/判类型） | 6 | 状态读 |
| `cursorFollow._pointerMoveHandler(...)` | 3 | **回调页面函数** |

---

## 2. 为什么"翻配置"不可行（三条硬边界）

| 边界 | 说明 |
|---|---|
| **实例过不了桥** | `contextBridge` 传对象是**结构化克隆**，类实例的 `prototype` 方法全丢。`mmdManager.getModelScreenBounds()` 在隔离世界调不到 |
| **赋值语义过不了桥** | preload 侧 `window.live2dManager._isDraggingModel = false` 改的是**隔离世界**的一个新属性，页面世界看不到 |
| **读页面全局拿不到** | 隔离世界里 `window.mmdManager` 是 `undefined`（页面全局不跨世界） |

---

## 3. 核心洞察：`contextBridge` 是**双向**的 —— 反向依赖可以变成"页面主动注册"

这是整份方案的关键。桥不仅能「preload → 页面」，也能「页面 → preload」：

```js
// preload（隔离世界）
let host = null;
contextBridge.exposeInMainWorld('nekoPetHost', {
  register(hooks) { host = hooks; },   // ← 页面把对象传进来
});

// 之后所有 window.mmdManager 的用法改成：
const bounds = host && host.getModelBounds ? host.getModelBounds() : null;
```

**为什么这比"搬实例"好**：

1. **函数可以过桥，而且调用是同步的** —— `host.getModelBounds()` 能拿回返回值，
   `getModelScreenBounds` 那 12 处同步语义**原样保留**（这点很关键，换成 IPC 就没法同步了）。
2. **不需要搬 5 个类**，只需要页面导出**实际用到的 ~10 个成员**。
3. **写状态也能解决** —— 页面导出 `setDragging(false)`，preload 调它，
   写操作发生在页面世界，`interaction.isDragging` 真的被改到。

⇒ **145 处"活实例"依赖，本质上只需要页面导出 10 个函数。**

---

## 4. 分阶段路径

### P0 · 只加观测，不改行为（0 风险）

在 preload 里给每个 `window.X` 访问点套一个取值器，记录"命中/未命中"：

```js
function pageGlobal(name) {
  const v = window[name];
  if (v === undefined) __petBridgeMiss(name);   // 只计数，不改变行为
  return v;
}
```

**验收**：跑一组真实操作（拖拽、切模型、点歌、截图、字幕、教程），
日志里 **miss 计数 = 0**（说明统计到的 22 个名字是完整的，没有动态访问漏网）。
**回滚**：删掉计数即可，行为零变化。

### P1 · 页面注册面（先做 52 处：数据类 37 + 函数类 15）

页面（`pet.html` 的启动脚本）在 `DOMContentLoaded` 后调用：

```js
window.nekoPetHost.register({
  // 数据类
  getConfig: () => window.lanlan_config,
  getAppState: () => window.appState,
  isPageConfigReady: () => !!window.pageConfigReady,
  getButtons: () => window.appButtons,
  getSubtitleShared: () => window.nekoSubtitleShared,
  getAgentTask: (id) => window._agentTaskMap && window._agentTaskMap[id],
  getMaster: () => ({
    name: window.master_name, nickname: window.master_nickname,
    display: window.master_display_name, profile: window.master_profile_name,
  }),
  // 函数类
  t: (k, ...a) => window.t(k, ...a),
  safeT: (k, ...a) => (window.safeT || window.t)(k, ...a),
  drag: (op, arg) => window.DragHelpers && window.DragHelpers[op] && window.DragHelpers[op](arg),
  captureProactive: () => window.captureProactiveChatScreenshot(),
  captureDataUrl: () => window.captureScreenshotDataUrl(),
  resetToDefaultModel: () => window.resetToDefaultModel(),
  subtitleBridge: () => window.subtitleBridge,
});
```

**验收**：
- 静态：`grep -c "window\.\(lanlan_config\|appState\|DragHelpers\|…\)"` 在 preload 里降到 **0**
- 运行：P0 的 miss 计数仍为 0；这 52 处行为对照（点歌、字幕、拖拽、截图各点一次）
**回滚**：preload 里 `host` 为空时**回落到 `window.X`**（非隔离下这条路径仍然可用），一个开关切换。

### P2 · 实例调用改指令（145 处，分 5 个域）

按成员逐个注册，不要一次全上：

| 域 | 成员 | 处数 | 说明 |
|---|---|---:|---|
| A 拖拽/交互 | `isDragging()` / `setDragging(v)` / `isModelDragging()` | 24+2 | 读写分离，写走 setter |
| B 测量 | `getModelBounds()` / `getModelType()` | 12+6+6 | 同步返回，注意 DPR 换算仍在 preload 侧做 |
| C 渲染控制 | `pause()` / `resume()` / `resetPosition()` | 12+6 | 纯命令，可后续再优化成 IPC |
| D 视线跟随 | `onPointerMove(evt)` | 3 | 事件对象不能过桥 ⇒ 只传 `{clientX, clientY, timeStamp}` 三个数 |
| E 点歌台 | `Jukebox` 的 21 处 | 21 | 需单独看：可能是读状态 + 调方法混合 |

**每完成一个域就跑一次 P0 的 miss 计数 + 对应窗口手动点一遍。**
**验收**：该域 `window.<实例名>` 出现次数 = 0，且行为对照无差异。

### P3 · 双模对照 → 翻配置

1. 用 `isolation-harness.main.js` 的 `HARNESS_ISOLATION=0/1` 两组跑**同一套探针**，
   比对：`window.nekoPetHost` 存在、`host` 已注册、`getModelBounds()` 返回合理值。
2. 翻 `window-manager.js:383` 与 `main/pet-window-lifecycle.js:921` 两处为 `true`。
3. 契约测试的 `EXPECTED_FALSE_COUNT` 从 5 降到 2，`ISOLATION_EXCEPTIONS` 摘掉 pet 两项。

**必须人眼验的**（自动验不了）：模型位置、拖拽手感、点击响应延迟、点歌台弹窗、截图清晰度。

---

## 5. 我的判断：**值得做，但不该现在做**

### 成本

| 阶段 | 改动量 | 风险 |
|---|---|---|
| P0 观测 | ~50 行 | ≈0 |
| P1 注册面 | 页面 +60 行、preload 52 处替换 | 低（有回落开关） |
| P2 五个域 | preload 145 处 + 页面 ~120 行 | **中高**（拖拽/测量有手感与时序问题） |
| P3 翻配置 | 2 行 + 契约 | 低（但要人眼验） |

### 为什么先不做

- `petWindow` 是**主窗**，承载模型渲染、拖拽、点歌、截图、指令面板。
  一旦手感变差（拖拽延迟、模型位置飘），体验是**全局性**的，而收益只是"一个配置项变成 true"。
- P2 的 B/C/D 三个域都涉及**时序与手感**，必须真机反复点，不是自动化能兜住的。
- 相比之下，**同一份力气花在本文 P0+P1 上收益更高**：那 52 处（数据/函数类）改完，
  preload 里对页面全局的**耦合就少了一半**，而且不碰手感。

### 建议

1. **先做 P0 + P1**（收益明确、风险低、可回落），把它们当成独立的小单。
2. **P2 等有"必须全隔离"的硬理由时再做**（比如安全审计要求、或某个 Electron 升级强制）。
3. 把本文作为 P2 的设计依据存着，不要现在排期。

---

## 6. 立单建议

若要推进，建议拆成三张单而不是一张大单（颗粒度按域，便于并行与回滚）：

| 建议单 | 内容 | 前置 |
|---|---|---|
| P0 依赖观测 | 给 `preload-pet.js` 加 `pageGlobal()` 取值器 + miss 计数 | 无 |
| P1 页面注册面 | `nekoPetHost.register` + 52 处替换 + 回落开关 | P0 |
| P2-{A..E} | 五个域各一张，按 §4 表格 | P1 |

> 立单前按纪律要查 **main 全树 + 所有开放分支里的 `TRAE_WORKORDER_PROMPT_AGENT_*.md`** 再定号，
> 不要凭记忆里的最大号顺延（历史上因此撞过一次号）。

---

## 7. 附：为什么这次没有"顺手翻"

本文 §1 的 22 个名字是**脚本统计**出来的，不是估的。

而且做了一次完整性检查：`preload-pet.js` 里 **`window[...]` 动态访问 0 处**
（`const x = window.Y` 这种解构也是静态的，已计入统计）⇒ **这 22 个名字很可能就是完整集合**。

即便如此，第一步仍建议是 P0 的 miss 计数而不是直接翻配置，理由有两条：

1. 静态清单证明不了**时序**：某些全局可能在 preload 早期还不存在（页面脚本晚于 preload 执行），
   miss 计数能暴露"什么时候读不到"，而不只是"读不读得到"。
2. 翻配置是一次性动作，P0 是**可回滚的观测**——同样的成本，先拿证据再动手。

---

## 8. 实施记录（2026-10-27）：P1 已落地，但**没有翻配置**

### 8.1 做了什么

| 文件 | 改动 |
|---|---|
| `neko-electron-shell/src/preload-pet.js` | 新增 `exposeToPage` + `nekoPetHost.register` + `nekoPetDiagnostics.snapshot` + `pageApi(name)`；**17 个数据/函数名共 57 处读取**改走 `pageApi()`；`DragHelpers` 拆成 `isDragging`（值）与 `restoreButtonPointerEvents`（函数）两个入口 |
| `NEKO/N.E.K.O/static/app/pet-host-bridge.js`（新） | 页面侧注册面：17 个惰性 getter，`host.register(fn)` |
| `NEKO/N.E.K.O/templates/index.html` | 在 `ws-adapter.js` 之前引入 `pet-host-bridge.js` |
| `neko-electron-shell/tests/pet-host-bridge.test.js`（新） | **6 条纯 node 单测**（vm 造假 window，覆盖惰性取值/DragHelpers 拆分/未知名） |
| `neko-electron-shell/tests/window-hardening.contract.test.js` | 2 条新契约：17 名不得直接 `window.X`、实例 5 名**仍应直接读**（未做 P2 就不能假装做完）、注册面文件与引入顺序 |
| `scripts/smoke-ws-isolation.py` + `tests/runtime/isolation-harness.main.js` | 探针能读 `nekoPetDiagnostics`；工装支持 `--entry` / `HARNESS_PROBE_JS`（主进程 `executeJavaScript`，绕开 CDP） |

### 8.2 为什么**没有**翻 `contextIsolation`

`pageApi()` 的第一行是 `if (!process.contextIsolated) return window[name]`。
也就是说 **petWindow 仍是 `false` 时，所有调用点走的还是原来那条路径，行为零变化**。
翻配置留给 P2 完成（实例 145 处按成员拆完之后），这与 §5 的判断一致。

### 8.3 一个被自己纠正的设计错误（值得记）

第一版我用机械替换把**所有** 22 个名字（含 5 个实例）都改成 `pageApi('X')`，被自己拦下：

> 实例过桥会**丢原型方法**。`pageApi('mmdManager')` 返回的是克隆出来的普通对象，
> `getModelScreenBounds()` 在 preload 侧就没了。

同理 `DragHelpers`（命名空间对象，一个布尔 + 若干方法）也不能整体传——
对象里的 getter 在克隆时会丢。所以拆成「值」和「函数」两个入口。

⇒ **能过桥的只有：函数、纯数据。实例与带方法的命名空间必须按成员拆。**

### 8.4 验收

```
node --test "tests/*.test.js"        → # tests 36 / # pass 36 / # fail 0
   （含新增 6 条 pet-host-bridge 单测 + 2 条契约）
node --check preload-pet.js / pet-host-bridge.js / 契约测试 → 全 OK
```

**改坏 ⇒ FAIL**：把任意一处 `pageApi('appState')` 改回 `window.appState` ⇒
`not ok 11 - pet preload：数据/函数类全局必须走 pageApi…`，还原后 36 pass、sha256 一致。

### 8.5 运行时验证：**没做到**（诚实登记）

| 尝试 | 结果 |
|---|---|
| `HARNESS_PRELOAD=preload-pet` + `/` + 隔离，CDP 探针 | ❌ `Connection timed out` |
| 同上，`--settle 30` / `--wait 90` | ❌ 仍然超时 |
| 改用主进程 `executeJavaScript`（不依赖 CDP） | ❌ 页面始终没有 `did-finish-load`；日志里 `Network service crashed` + `GPU process exited (143)` |
| `file://` 轻量夹具页 | ❌ 同样不触发 `did-finish-load` |

结论：**这个沙箱环境加载不了重度页面**（pet 页有 Live2D/VRM/MMD）。
所以本阶段的证据只有 **单测 + 静态契约 + 改坏验证**，
**没有**在真机 pet 窗里跑过——这一点不能含糊。
⇒ 真机验证要等能跑起来的环境，或在 P2 一起做（届时反正要人眼验手感）。

### 8.6 下一步（P2）

| 域 | 待做 | 处数 |
|---|---|---:|
| A 拖拽/交互 | `isDragging()` / `setDragging(v)` | 26 |
| B 测量 | `getModelBounds()` / `getModelType()` | 24 |
| C 渲染控制 | `pause()` / `resume()` / `resetPosition()` | 18 |
| D 视线跟随 | `onPointerMove({clientX, clientY, timeStamp})`（事件对象不能过桥） | 3 |
| E 点歌台 | `Jukebox` 21 处需先摸清用法 | 21 |

### 8.7 域 A 第一批（同日追加）：模型态 8 处

在注册面上补了 4 个「模型态」能力，把 8 处简单读写收口（其余 18 处是把 `interaction`
对象传进 helper 的，需要改 helper 签名，属于下一批）：

| 能力 | 覆盖的原代码 | 性质 |
|---|---|---|
| `modelType` | `window.mmdManager.currentModel` / `window.vrmManager.currentModel` 探测 | 值 |
| `modelDragging:live2d` / `:vrm` / `:mmd` | `_isDraggingModel` / `interaction.isDragging` 读取 | 值（按模型类型分入口，保持原语义） |
| `clearModelDragging` | 三处 `isDragging = false` 写 + live2d 的 `model.dragging = false` | **动作型**（取值即执行） |

> 「动作型」这个语义要记：`pageApi('clearModelDragging')` 的**取值本身就是调用**，
> 返回值是执行结果。写单测时如果把返回值再当函数调，会得到 `is not a function`。

**验收**：`node --test "tests/*.test.js"` → **37 pass / 0 fail**（新增 1 条域 A 单测）。

⚠️ **别被计数骗了**：文件里 `window.<实例>` 的出现次数**没有下降**（仍 145 处）。
因为门控助手内部必须保留 `window.X` 作为**非隔离回落**，所以这 8 处只是从
「散落在业务代码里」变成「集中进 3 个助手」。**这一步的价值是结构，不是数量**：
翻配置的前提是"业务代码不再直接碰页面全局"，而这一点已经达成了。
**一个小坑**：单测里假 `getCurrentModel` 必须返回**同一个对象**，
否则每次调用都是新对象，「model.dragging 被清掉」会永远**假通过**。
