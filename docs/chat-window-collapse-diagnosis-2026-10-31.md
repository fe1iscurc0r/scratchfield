# 对话框「不见了」诊断（2026-10-31）

## 结论先说

**不是崩溃、不是被 hide、不是被遮挡**——是被设计成**折叠成 58px 的毛线球**。
触发条件是**宠物进入猫咪待机的 `cat2` / `cat3` 档**，不是「聊天窗自己闲置太久」。

## 现场证据（用户机器上的实测快照）

```
visibility:      "visible"            ← 窗口没被 hide
shellClasses:    "neko-e-collapsed"   ← 壳被加上「折叠」类
shellOpacity:    "0"                  ← 壳整体透明
rootRect:        [0, 0, 0, 0]         ← 内容区零尺寸
ballIcon:        rect=[339,114,58,58] opacity=1  display=block  ← 球是可见的
```

也就是说：**点那个球就能展开**，对话框并没有丢。球不是页面里的 DOM 元素，而是**独立的
Electron 窗口**（`window-manager.js` 的 `compactChatBallWindow`，视觉 58px / 锚点 88px），
点击时它发 `neko:compact-chat-ball-click`，由 `main.js:1876` 的 handler 还原对话窗 ——
这条链是「球能用」的依据，不是推测。

## 触发链（逐文件点名）

| 步骤 | 位置 | 做什么 |
|---|---|---|
| 1 | `NEKO/N.E.K.O/static/app/app-cat-mind.js` | 猫咪心智，`AUTONOMOUS_TICK_INTERVAL_MS = 30s` 一次 tick；tier 变化时派发 `neko:auto-goodbye:state-change { type: 'visual-tier', tier }` |
| 2 | `.../app-react-chat-window/resize-drag-and-api.js:769` | 监听该事件，`I.idleDockTier = (tier === cat2 \|\| cat3) ? tier : none` |
| 3 | `.../app-react-chat-window/minimize-and-idle-dock.js` | `isIdleDockTierActive()` 为真 → `enterIdleDock()` → 壳加 `neko-e-collapsed` + `opacity: 0`，露出球 |

## 什么**不会**触发（都实测过，别重复怀疑这两条）

- **打开「模型管理」**：走菜单同一条 `window.openOrFocusWindow('/model_manager?lanlan_name=…')`
  ⇒ 之后 chat 仍是 `visible` / `opacity 1` / 无 `neko-e-collapsed`。
- **重载 pet 页**（`location.reload()`）⇒ 同上。所以「切完模型页面重载把折叠态带回来」这个猜想不成立。

## 为什么之前查不到「谁干的」

主进程那两处 `hideReactChatForFullSurfaceSwitch()`（`window-manager.js:2268`）与
`dimReactChatForMinimize()`（`:3230`）**都不打日志**，所以主进程日志里没有任何痕迹。
真正的触发发生在**渲染层**（页面内的 CustomEvent），跟主进程这两条无关 —— 这也是为什么
早先「按 tag 查 `/releases`」「翻主进程日志」都看不到东西。

## 三个可选修法（都涉及改上游 NEKO，**未执行**）

1. **关掉自动折叠（现成逃生门）**：把配置 `goodbyeIdleAppearance` 设成 `ball`。
   依据：`minimize-and-idle-dock.js:36` 的 `isGoodbyeIdleBallAppearanceActive()` 为真时，
   `resize-drag-and-api.js:773` 会把 `idleDockTier` 恒置 `NONE` ⇒ 根本不进 `enterIdleDock()`。
   ⚠️ 副作用：**宠物待机时会显示成球**（这个开关本意是「球形态下返回控件不是猫，最小化球不该去贴靠」，
   顺带把折叠一起关了）。语义被绑在一起，不是干净的开关。
2. **只关折叠、不动外观**：在 `resize-drag-and-api.js:773` 那个赋值处加一个显式开关/配置判断。
   这是干净做法，但**要改上游文件**（产生 NEKO 分叉）。
3. **提上游 issue**：这确实是设计行为，但「折叠后用户以为对话框没了」是体验缺陷
   （球只有 58px、无提示、无动画强调）。

## 怎么复现 / 取证

```bash
# 一次说清对话窗是「被 hide」「折叠成球」还是「真死状态」
node neko-electron-shell/scripts/pet-live-verify.mjs chat
```

`verdict` 三态：`窗口被 hide`（看主进程 reason）/ `窗口在场且可见`/`折叠成球`。

复现环境（本轮用的）：`_chat_repro_start.sh`（NEKO 48911 + electron CDP 9222）。
⚠️ 该脚本刻意**不带** `--disable-gpu` / `--disable-software-rasterizer` —— 那两个参数会掐掉
WebGL，Live2D 加载不出来，切形象类问题就复现不了。
