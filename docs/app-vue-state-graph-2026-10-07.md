# App.vue 状态依赖图（工单204 任务三 · App.vue 第一步）

> 2026-10-07 · 工具：`tools/app_vue_state_graph.py`（正则 + 声明区间；TS 无法用 Python `ast` 解析）
> **这是抽取 composable 的硬性前置**：`resolvedLive2dSource` 一类计算同时依赖路由态与启动缓存，
> 不先看清依赖就抽，产出的 composable 会带隐式耦合（比 615 行巨石更难维护）。

## 一、规模与家族分布

`<script setup>` **615 行 / 64 个顶层符号**，按前缀与语义聚为 6 族：

| 家族 | 符号数 | 代表符号 |
|---|---|---|
| **live2d** | **28** | `Live2dModel` `resolvedLive2dSource` `effectiveLive2dSource` `startupLive2dSource` `characterModelMap` `applyPeekExpression` `live2dTransform*` `isChatPeekMode` `modelReady` |
| **auth**（登录 + 会话过期） | 7 | `showLoginDialog` `openLoginDialog` `onLoginSuccess` `onLoginSkip` `authExpiredVisible` `onAuthExpiredRelogin/Dismiss` |
| **splash**（启动闪屏） | 6 | `_splashDismissed` `splashVisible` `showMainContent` `titlePhaseDone` `onSplashDismiss` `enterMainContent` |
| **window/floating** | 6 | `isElectron` `isMac` `showResizeHandles` `titleBarPadding` `floatingState` `isFloatingMode` |
| **backend-overlay**（后端日志浮层） | 5 | `backendDebugVisible` `backendErrorVisible` `backendErrorLogs` `onPaletteAction` `onPaletteNavigate` |
| **route** | 4 | `router` `currentRoute` `isForumRoute` `isCompactRoute` |
| 未归类 | 8 | `toast` `hasCustomBg` `customBgUrl` `scale` `loadCharacterModelMap` `onModelReady` `onTitleDone` `unsubStateChange` |

## 二、关键耦合点（被引用最多的符号 = 抽边界时必须稳定的接口）

| 符号 | 被引用 | 引用方（部分） |
|---|---|---|
| `showLoginDialog` | **6** | `onAuthExpiredRelogin` `openLoginDialog` `onSplashDismiss` `onLoginSuccess` `onLoginSkip` |
| `isChatPeekMode` | **6** | `onModelReady` `live2dPeekShellStyle` `live2dModelX/Y` `live2dPeekShellTransition` |
| `isFloatingMode` | **5** | `showResizeHandles` `titlePhaseDone` `isChatPeekMode` `router` `onPaletteAction` |
| `isElectron` | 4 | `DEFAULT_STARTUP_LIVE2D_SOURCE` `normalizeRuntimeLive2dSource` `showResizeHandles` `titleBarPadding` |
| `DEFAULT_STARTUP_LIVE2D_SOURCE` | 4 | `readCachedStartupLive2dSource` `persistStartupLive2dSource` `effectiveLive2dSource` `enterMainContent` |
| `normalizeRuntimeLive2dSource` | 4 | `readCached...` `persist...` `resolvedLive2dSource` `loadCharacterModelMap` |
| **`enterMainContent`（自身依赖 18 个）** | — | **编排汇聚点**：同时驱动 Live2D 就绪、闪屏退场、主内容显示 |

## 三、⭐ 结论：抽取顺序**与原方案的猜测不同**

原方案猜"先抽 titlebar / resize handles"——数据支持这个猜测，但要**再精确一步**：

| 顺序 | 目标 composable | 覆盖符号 | 外部依赖（需作参数传入） | 风险 |
|---|---|---|---|---|
| **① 最先** | `useWindowChrome()` | `isElectron` `isMac` `isMaximized` `showResizeHandles` `titleBarPadding` | **无** ✅ | **最低** |
| **② 其次** | `useBackendOverlay()` | `backendDebugVisible` `backendErrorVisible` `backendErrorLogs` `onPaletteAction` `onPaletteNavigate` | 仅 `router` | 低 |
| ③ | `useLive2dSource()` | 源缓存链 12 个（`LIVE2D_SOURCE_CACHE_KEY` → … → `effectiveLive2dSource`） | **`isElectron`**（见上表） | 中 |
| ④ | `useAuthDialogs()` | 7 个 auth 符号 | `toast` + `enterMainContent` | 中 |
| ⑤ | `useAppSplash()` | 6 个 splash 符号 | `enterMainContent` | 中 |
| **最后** | `useLive2dStage()` | 渲染/peek 变换 ~16 个 | `isChatPeekMode` `scale` | **高**（与 ③⑤ 交叉） |

**必须留在 App.vue 的**：`enterMainContent`（18 依赖的编排点）、`router`/`currentRoute`（路由容器本身）、
`toast`（全局提示）。把它们抽走只会把"编排"变成"跨 composable 的隐式时序耦合"。

## 四、执行约定

1. **一次只抽一个**，抽完立刻 `npm run build`（vue-tsc 能抓未定义/类型错）+ 手动扫一眼启动路径；
2. 步骤 ① 是**零外部依赖**的纯提取，适合作为第一次验证方法论的机会；
3. 步骤 ③⑤ 抽取前，先确认 `isChatPeekMode` 的定义归属（它同时被渲染层与 splash 依赖 → 可能需要提升到 App.vue）；
4. 本图由脚本生成，**改代码后重跑** `python tools/app_vue_state_graph.py` 即可刷新（不必手工维护）。

— 砚 · 工单204 任务三 · App.vue 依赖图（抽取前的必备依据）
