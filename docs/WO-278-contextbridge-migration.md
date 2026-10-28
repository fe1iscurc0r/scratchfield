# WO-278 施工记录 · Electron 窗口隔离完整化（contextBridge 迁移）

- **执行方**：K3（WorkBuddy agent）
- **开工**：2026-10-23 22:3x
- **基线**：`main@91fc9669e5ad`
- **本文件按批记录**；每批一节，写完即更新 §进度表。

---

## §0 进度表（**已按实测重排**）

### §0.1 为什么重排

1. **原工单的批次序过期**：原写"批 1 = jukebox"，实测 jukebox 早已迁完
   （`preload-jukebox.js` 已用 `contextBridge`、窗口已 `contextIsolation: true`）。
2. **"直写数"这个指标有坑**：用 `window\.\w+\s*=` 统计会把 `typeof window.X === 'function'` 也算成写，
   还会漏掉**反方向**的耦合 —— preload **读页面定义的全局**（`window.captureProactiveChatScreenshot`、
   `window.t`、`window.safeT`）。后者 contextBridge **根本桥不了**，必须改调用方。

### §0.2 真实耦合矩阵（脚本统计，双向）

| preload | 行数 | 写（→页面） | **读（←页面，桥不了）** | 可迁性 |
|---|---:|---:|---:|---|
| compact-chat-ball | 278 | 0 | 0 | ✅ **批 1 已完成** |
| **child** | 50 | 1 | 0 | 🟢 最容易 |
| **chat** | 160 | 3 | 0 | 🟢 容易（含 WebSocket 替换） |
| toast | 34 | 0 | 0 | 🟢 已就绪（窗已 `contextIsolation: true`，只差 `webSecurity`） |
| agenthud | 37 | 1 | 1 | 🟡 有 1 处反向读 |
| subtitle | 87 | 4 | 1 | 🟡 |
| chat-full | 1613 | 14 | 5 | 🟠 中等 |
| chat-react | 8124 | 25 | 17 | 🔴 难 |
| **pet** | 5524 | 13 | **23** | 🔴 **最难**（原排批 2，实为最重） |

> **2026-10-25 复核口径**：这里「读」= preload 读到的 `window.*` 全局个数（只算读，不算
> `window.X = …`），按最新脚本重测：chat-react **17 个 / 65 处读**（其中 6 个布局/几何标志由
> preload 或主进程注入）、pet **23 个 / 205 处读**（`mmdManager` 43 / `vrmManager` 43 /
> `live2dManager` 35 三个活实例占 121 处；早前版本漏计了 `vrmManager`）。明细见
> `docs/WO-278-page-side-refactor-plan.md` §3.1。
> `preload-common.js`（679 行 / 写 12 / 读 6）是共享库，不是某扇窗的 preload，单独评估。

### §0.3 重排后的批次

| 批 | 对象 | 现状 |
|---|---|---|
| 1 | compact chat ball | ✅ 完成 |
| **2** | **child**（50 行 / 1 写 / 0 读） | ✅ 完成（见 §2） |
| **3** | chat / full-chat / react-chat —— **构造器替换阻塞**，改交付「边界契约测试」 | ✅ 见 §3 |
| 4 | agenthud / subtitle（各 1 处反向读） | ⏳ |
| 5 | chat-full（14 写 / 5 读） | ⏳ |
| 6 | chat-react（25 写 / 17 读，8124 行） | ⏳ |
| 7 | pet（13 写 / **23 读** / 205 处） | ⏳ 最后做 |
| 8 | `webSecurity: false` ×5 运行期验证 | 🚫 **本机阻塞** |

### §0.4 两个必须先说清的阻塞

1. **批 8（webSecurity）必须有带窗 Electron**：5 处都已带理由注释，其中 3 处写着
   "页面 origin 取决于 `appConfig.apiBaseUrl`（用户可配远程地址），默认同源策略会不会打断
   聊天侧跨源取素材要靠**运行期**验证" ⇒ 纯静态分析得不出结论，本机 headless 跑不了。
2. **批 2~7 的每一项都需要真机冒烟**：隔离只分离 JS 全局、不分离 DOM，所以 DOM 逻辑安全；
   但凡是"页面读 preload 写的对象"的地方，形状稍有差异就会静默坏功能。静态契约只能保证
   "不再出现 `contextIsolation:false`"，**保证不了功能没坏**。

## §1 批 1 · compact chat ball 窗（✅ 完成）

### §1.1 症结

这扇窗是唯一"`preload-*.js` 里 `window.* =` **零处**"却仍开不了隔离的窗。原因写在原注释里：

```js
contextIsolation: false, // preload 要读页面内联脚本写的 window.__nekoSkipAppear
                        // （本文件 buildCompactChatBallDataUrl），跨世界耦合，迁隔离需先改成桥/URL 参数
```

即：`buildCompactChatBallDataUrl()` 往 HTML 里注入 `<script>window.__nekoSkipAppear=true</script>`，
`preload-compact-chat-ball.js` 再读 `window.__nekoSkipAppear` —— **preload 与页面共享全局**，隔离必然打不开。

### §1.2 改法：`additionalArguments`（main → preload 的规范通道）

| 侧 | 改动 |
|---|---|
| **main**（`window-manager.js`） | 新增常量 `NEKO_SKIP_APPEAR_ARG = '--neko-skip-appear'`；在 `new BrowserWindow` 前算 `skipAppear`；`webPreferences` 加 `additionalArguments: skipAppear ? [NEKO_SKIP_APPEAR_ARG] : []`；`contextIsolation: false → true` |
| **页面** | 删掉注入的 `<script>window.__nekoSkipAppear=true</script>`；`buildCompactChatBallDataUrl(baseUrl, skipAppear)` 去掉第二个参数 |
| **preload** | `if (window.__nekoSkipAppear)` → `const skipAppear = process.argv.includes('--neko-skip-appear')` |

> 为什么不用 URL 参数：页面是 `data:text/html,...`，`location.search` 不可用；
> `additionalArguments` 是 Electron 给 preload 传静态配置的**官方通道**（`process.argv`），
> 不经过页面世界，正好满足"不共享全局"的要求。

### §1.3 为什么这样改是安全的

`preload` 与隔离后仍在**同一个 DOM 上**（隔离只分离 JS 全局，不分离 DOM），
所以 `preload-compact-chat-ball.js` 里所有基于 `document.querySelector` / `window.screenX` 的逻辑照旧可用；
它唯一依赖页面全局的地方就是 `window.__nekoSkipAppear`，已改走 argv。

### §1.4 验收（实测）

```
cd neko-electron-shell && node --test "tests/*.test.js"
→ # tests 6 / # pass 6 / # fail 0     （原 5 条，新增 1 条正向断言）

grep -rn "__nekoSkipAppear" src/ tests/   → 仅剩 2 处注释（说明原因），**代码 0 处**
grep -c "contextIsolation: true"  src/window-manager.js → 7   （原 6）
grep -c "contextIsolation: false" src/window-manager.js → 5   （原 6）
node --check src/window-manager.js / src/preload-compact-chat-ball.js → OK
```

**新增契约断言**（`window-hardening.contract.test.js`）：

```js
test('compact chat ball 窗必须开 contextIsolation（WO-278 批 1）', () => {
  // 断言 ① 这扇窗不许再出现 contextIsolation:false
  // 断言 ② 它的 webPreferences 必须用 additionalArguments 传 skipAppear
});
```

白名单里原来的 `compactChatBallWindow: ['contextIsolation']` 已删除 —— 从"允许不隔离"变成"禁止不隔离"。

### §1.5 未做（诚实登记）

- **没有 Electron GUI 冒烟**：本机无法启动带窗的 Electron 会话（headless），
  "球出现时若 skipAppear 则跳过动画"这条**运行期行为**未实测，只有静态契约与语法检查。
  ⇒ 合入后请在真机跑一次「最小化 → 折叠成球 → 兼容模式重建」确认动画行为不变。
- `webSecurity: false` 未动（data: URL + 外部素材依赖，属批 7 范围）。

---

## §2 批 2 · 同源子窗口（`setWindowOpenHandler` / `preload-child.js`）（✅ 完成）

### §2.1 这批只改了一行——因为 preload 早就写好了桥

打开 `preload-child.js` 发现它**已是双模**：

```js
if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
  contextBridge.exposeInMainWorld('nekoWindowControl', { minimize, restore, maximize, isMaximized });
} else {
  window.nekoWindowControl = { ... };   // 旧路径，隔离一开就走不到了
}
```

文件头注释甚至写着"window.open 打开的子窗口使用 contextIsolation=true，因此共享宿主能力需要通过
contextBridge 暴露"。**是窗口配置没跟上**：`childWebPreferences` 里还写着
`contextIsolation: false, // preload-child.js 直写 window.* stub，迁隔离要和 preload 一起改` —— 注释已过期。

### §2.2 改动

| 文件 | 改动 |
|---|---|
| `src/window-manager.js` | `childWebPreferences.contextIsolation: false → true`，并把过期注释换成"preload 已是双模、开隔离走 bridge 分支" |
| `tests/window-hardening.contract.test.js` | 白名单移除 `[CHILD_WINDOW_LABEL]`；新增「同源子窗口必须 `contextIsolation: true`」正向断言 |

### §2.3 验收

```
node --test "tests/*.test.js" → # tests 7 / # pass 7 / # fail 0   （原 6）
contextIsolation: true 8 处（原 7）/ false 4 处（原 5）
node --check 测试文件 OK
```

### §2.4 副作用与遗留

- `preload-child.js` 里的 `else` 分支（`window.nekoWindowControl = ...`）现在是**死代码**。
  保留原因：与其它 preload 的双模写法保持一致，删掉要多改一处共享风格；
  若要清理，另开一条只删 `else` 的卫生单，**不要混在迁移里**。
- 仍未做运行期冒烟：同源子窗口打开（mini-game / 站内弹窗）后，页面读 `window.nekoWindowControl`
  走的是 bridge 代理，`minimize/restore/maximize/isMaximized` 四个方法的**行为**未实测
  （静态契约只能保证配置对不对，保证不了调用链通）。

---

## §3 批 3 · chat / full-chat / react-chat —— **设计性阻塞，改为把边界钉成测试**（✅ 本批交付）

### §3.1 为什么这四扇窗不能直接翻

原计划批 3 是 `chat`（3 写 / 0 读），看起来最容易。打开 `preload-chat.js` 才发现第一句就是：

```js
// 核心：替换 window.WebSocket 为 IPC 代理。
// Chat 窗口不建立真实 WebSocket 连接，所有通信通过 Pet 窗口中转：
//   send: Chat → IPC(ws-raw-send) → 主进程 → Pet → 真实 WebSocket → 后端
```

它做的是 `window.WebSocket = WSProxy`（**构造器替换**），而 `WSProxy` 是个**函数构造器**，
被页面里 `new WebSocket(url)` 直接调用。

**contextBridge 的硬边界就在这里**：`exposeInMainWorld` 只能**新增**命名空间属性
（`window.nekoChatWindow = {...}`），**顶替不了页面已有的全局构造器**。
⇒ 这三扇窗一旦开隔离，页面的 `new WebSocket(...)` 会退回原生实现，**WS 代理静默失效**（聊天直接不通）。

同样的问题在 `preload-chat-full.js`（L364 `window.WebSocket =`）和
`preload-chat-react.js`（L117 附近）里各有一份 —— 所以**批 3 / 5 / 6 是同一个阻塞**，
不是三个独立任务。

### §3.2 真正的解法（属于页面侧改造，不在本单范围）

要开隔离，必须先把**页面**改成从 bridge 取工厂：

```js
// 现在的页面：new WebSocket(url)   ← 依赖全局被替换
// 改造后：      const WS = window.nekoChatWindow.WebSocketFactory;  new WS(url)
```

这要动 `NEKO/N.E.K.O/static/js/**`（`app-websocket.js` 等），且**必须运行期验证**
（聊天收发、断线重连、僵尸代理那套逻辑）。⇒ 记入"待页面侧改造"，本单不碰。

### §3.3 本批实际交付：把这条边界钉成契约测试

新增测试 **「替换页面全局构造器的 preload，其窗口不得开 contextIsolation」**：

| 环节 | 做法 |
|---|---|
| 识别 | 扫 `src/preload-*.js` 里是否出现 `window.WebSocket =` / `XMLHttpRequest` / `EventSource` / `Worker`（排除 `==`/`===`） |
| 映射 | **约定表**：`preload-chat→chatWindow`、`preload-chat-full→fullChatWindow`、`preload-chat-react→reactChatWindow`、`preload-pet→petWindow` |
| 断言 | 这些窗口不得出现在 `contextIsolation: true` 的集合里；出现即红，并指名"哪个窗用了哪个 preload、替换了什么" |

> **映射为什么不用 `enclosingWindowName` 反推**：实测它会从 `createReactChatWindow` 的
> preload 行向上一路撞到 `setWindowOpenHandler(`，把 reactChat 的 preload 误判成"子窗口的"。
> 这条我在写测试时踩了一次，已写进注释。

### §3.4 验收

```
node --test "tests/*.test.js" → # tests 8 / # pass 8 / # fail 0   （原 7）
```

**「改坏 ⇒ FAIL」对照实验**（把 `reactChatWindow` 的 `contextIsolation` 临时改成 `true`）：

```
not ok 8 - 替换页面全局构造器的 preload，其窗口不得开 contextIsolation（WO-278 批 3）
reactChatWindow 用了 preload-chat-react.js（替换 WebSocket），却开了 contextIsolation:true
# fail 2
```

改完逐字节还原（sha256 一致）。

### §3.5 结论：剩余 4 扇窗的状态（诚实登记）

| 窗 | 阻塞类型 | 解除条件 |
|---|---|---|
| `chatWindow` | 构造器替换（WS 代理） | 页面侧改走 bridge 工厂 + 运行期验证 |
| `fullChatWindow` | 同上 | 同上 |
| `reactChatWindow` | 同上 + 8124 行 preload 的 17 个页面侧全局 / 65 处读 | 同上，且分批 |
| `petWindow` | **23 个页面全局 / 205 处读**（mmdManager / vrmManager / live2dManager 三个活实例占 121 处） | 需逐个决定"把调用挪进页面"还是"用 IPC 代替" |

⇒ **WO-278 到此进入决策点**：剩下的活不是"翻配置"，是页面侧重构。
