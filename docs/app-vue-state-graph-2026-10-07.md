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

---

## 五、进度（2026-10-11）

- ✅ **步骤① `useWindowChrome()` 已抽取**：`frontend/src/composables/useWindowChrome.ts`。
  `isElectron` / `isMac` 为**模块常量**（App.vue 的 live2d 源归一链在 setup 极早期就要用，
  与 useAuth.ts 的模块级导出同款风格）；`isMaximized` / `showResizeHandles` / `titleBarPadding`
  由 `useWindowChrome(isFloatingMode)` 提供——浮动态按上表约定**作参数注入**，
  不把路由/浮动逻辑拖进 composable。
- 上文数字（615 行 / 64 符号）为**抽取前快照**，历史分析仍有效；后续抽取（② useBackendOverlay 等）
  前重跑 `python tools/app_vue_state_graph.py` 取新值。
- App.vue 现 907 行（净 −1：本步骤主要是**结构**收益——窗口 chrome 族归位可复用的 composable）。
- ✅ **步骤② `useBackendOverlay()` 已抽取**（2026-10-11）：`frontend/src/composables/useBackendOverlay.ts`。
  覆盖 3 ref（backendDebugVisible / backendErrorVisible / backendErrorLogs）+ Ctrl+Shift+U 监听 + `electronAPI.backend.onError` 订阅（原代码不退订，语义保持）。
  ⚠️ **与原分组的偏差**：`onPaletteAction` / `onPaletteNavigate` 实际依赖 `paletteOpen`（useGlobalHotkeys 返回值）+ `router`，语义上是命令面板集成而非后端浮层 → **留在 App.vue**，未入本 composable。依赖图按前缀聚合的分组在边界处要用代码现实校正。
- App.vue 现 891 行（907 → 891）。

— 砚 · 工单204 任务三 · 步骤① 完成记录
- ✅ **步骤③ `useLive2dSource()` 已抽取**（2026-10-11）：`frontend/src/composables/useLive2dSource.ts`。
  覆盖 live2d 族「源缓存链」12 符号：`LIVE2D_SOURCE_CACHE_KEY` / `DEFAULT_STARTUP_LIVE2D_SOURCE` /
  `normalizeRuntimeLive2dSource` / `readCachedStartupLive2dSource` / `persistStartupLive2dSource` /
  `startupLive2dSource` / `activeLive2dSource` / `characterModelMap` / `activeAgentCharacterTemplate` /
  `resolvedLive2dSource` / `effectiveLive2dSource` / `loadCharacterModelMap`。
  - **零参数**：上表建议的「`isElectron` 作参数传入」已过时 —— 步骤①把它升级为 useWindowChrome 的
    **模块常量**（非响应式、全程不变）⇒ 本 composable 直接 import，参数表清空。
  - 随链一起迁走两个 watch：`effectiveLive2dSource → activeLive2dSource`（启动缓存回写）、
    `backendConnected → loadCharacterModelMap()`（后端连上才有角色模板表）。
  - **留归 App.vue**：`live2dRenderKey` 及其 watch —— 重挂载 key 属渲染/舞台族（`useLive2dStage`）的边界，
    不随源链走。
  - 顺带还一处债：原 `persistStartupLive2dSource` 声明在 `startupLive2dSource` **之前**，靠函数声明提升
    "碰巧"可跑，触发 eslint `ts/no-use-before-define`；抽取时把 ref 声明提前（逻辑零改动）。
- App.vue **775 行**（892 → 775，净 −117）；`<script setup>`：598 行 / 57 符号 → **481 行 / 45 符号**
  （−12 符号 = 本次抽出的 12 个，重跑 `tools/app_vue_state_graph.py` 复核一致）。
- 验证边界（实测）：`vue-tsc --noEmit -p tsconfig.app.json` **改前 0 错 → 改后 0 错**；
  eslint 二文件仅剩 App.vue 一处 **既存** `style/padded-blocks`（`onUnmounted` 体首空行，main 上同样存在）。
  ⚠️ 运行期行为（真机 Live2D 起播 / 非 Electron 浏览器源归一 / 角色模板切换）本机无该层，另附复测清单。
- 下一步（本图顺序）：④ `useAuthDialogs()`（7 个 auth 符号，外部依赖 `toast` + `enterMainContent`）。

— WorkBuddy · 工单204 任务三 · 步骤③ 完成记录

---

## 六、步骤④ `useAuthDialogs()` 完成记录（2026-10-11）

- ✅ **步骤④ `useAuthDialogs()` 已抽取**：`frontend/src/composables/useAuthDialogs.ts`。
  覆盖本图 auth 族全部 **7 符号**：`showLoginDialog` / `authExpiredVisible` / `openLoginDialog` /
  `onAuthExpiredRelogin` / `onAuthExpiredDismiss` / `onLoginSuccess` / `onLoginSkip`；
  随族迁走两个 watch（`authExpired → authExpiredVisible`、`sessionRestored → 关弹窗并进主内容`）。
- 外部依赖按本图上表作**参数**传入：`useAuthDialogs({ toast, enterMainContent })`。两点对原表的校正：
  1. 原表只列了 `toast` + `enterMainContent`。实测 `ACCESS_TOKEN` / `authExpired` /
     `setAuthExpiredSuppressed`（来自 `@/api`）与 `cloudUser` / `sessionRestored` / `useAuth`
     （来自 `@/composables/useAuth`）**都是模块级导出**，不属 App.vue 局部状态 ⇒ 直接 import，不必作参数。
  2. `openLoginDialog` 的唯一去向是 `provide('openLoginDialog', …)` 给子组件，App.vue 自身不引用它
     ⇒ 随 `provide` 一起进 composable；App.vue 只解构 **6** 个符号。
- **`enterMainContent` 为什么能在 setup 前段就传引用**：它是**函数声明**（hoisted）。现场用探测文件跑
  eslint 确认本仓对 `ts/no-use-before-define` 实际是 `functions: false` ⇒ 顶层引用后置**函数声明**
  不报错；而引用后置的 `const`/`let` **会报错**（步骤③ 抽 `useLive2dSource` 时正是踩这条）。
- `useAuth()` 调用点从 setup 中段提前到前段：它首次调用会触发一次 `fetchMe()`（模块级 `_initFetched`
  守卫），但结果经网络异步落地，setup 内可观察顺序不变。
- 顺带清掉本卷 3 处**既存** lint 债（`main` 上同样存在，非本步骤引入）：
  App.vue 的 `style/padded-blocks`、`useWindowChrome.ts` 的 `import/consistent-type-specifier-style`、
  `useBackendOverlay.ts` 的 `perfectionist/sort-imports`。
  ⚠️ **更正 ③ 记录**：那里把这处 `style/padded-blocks` 写成「`onUnmounted` 体首空行」——实测是
  **`onMounted` 块的尾部空行**（旧 L475，紧贴块尾 `})`）。
- 规模（重跑 `python tools/app_vue_state_graph.py` 复核，与本图同口径）：
  `<script setup>` **481 行 / 45 符号 → 433 行 / 38 符号**（−7 符号 = 本次抽出符号数，−48 行）；
  App.vue **775 → 727 行**（24566 → 23327 字节）。
  （该工具是「正则 + 声明区间」的粗粒度分析，`enterMainContent` 依赖数 12 → 10 是区间平移的副产物，
  非语义变化——原文已注明不追求类型级精确。）
- 验证边界（改前/改后同环境同命令实测）：`vue-tsc -b` 0 错 → 0 错；
  `vue-tsc --noEmit -p tsconfig.app.json` 0 错 → 0 错；`vite build` exit 0，renderer 模块数
  **1240 → 1241**（+1 = 新 composable 被引用；另两个 bundle 173/2 不变）；
  `node --test` 77 pass / 0 fail；`vitest run` 5 files / 29 passed；eslint 本卷文件 **3 错 → 0 错**。
  ⚠️ 运行期行为（CAS 失效→重登、登录成功/跳过进主内容、会话恢复自动关弹窗）本机仍无该层，另附复测清单。
- 下一步（本图顺序）：⑤ `useAppSplash()`（6 个 splash 符号，外部依赖 `enterMainContent`）；
  最后 `useLive2dStage()`（渲染/peek 变换 ~16 符号，**高风险**，与 ③⑤ 交叉）。
  `SpectrumPanel.vue` 按工单约定 block 于「频谱 UI 重构方案定稿」，不单独拆。

— WorkBuddy · 工单204 任务三 · 步骤④ 完成记录

---

## 七、步骤⑤ `useAppSplash()` 完成记录（2026-10-11）

- ✅ **步骤⑤ `useAppSplash()` 已抽取**：`frontend/src/composables/useAppSplash.ts`。
  拥有 **5 个导出符号 + 1 个内部变量**：`splashVisible` / `showMainContent` / `titlePhaseDone` /
  `onSplashDismiss` / `onTitleDone`，以及内部 `_splashDismissed`（原 `let`，只参与两个 ref 的初始值
  并在 `onSplashDismiss` 里置位；非响应式，故不导出）。
  参数表：`useAppSplash({ showLoginDialog, enterMainContent })`。
- **三处对原表的校正**（原表这一行本身有矛盾）：
  1. 原表把 `enterMainContent` **同时**记作 splash 族第 6 个符号**和**本步骤的外部依赖 —— 自相矛盾。
     定案：`enterMainContent` 留在 App.vue（18 依赖的编排汇聚点），本处只作参数接收。
  2. 真正的第 6 个符号是 `onTitleDone`（原表把它归入「未归类」）：它唯一职责就是置位 splash 的
     `titlePhaseDone`，且由模板 `<SplashScreen @title-done>` 触发 ⇒ 属 splash。
  3. 原表只列了 `enterMainContent` 一个外部依赖；实测 `onSplashDismiss` 的「未登录」分支还要
     `showLoginDialog`（步骤④ `useAuthDialogs` 的返回值）⇒ 参数表多一项。
- **本步骤引入一条顺序约束**：⑤ 的 `splashVisible` 必须早于 `onModelReady`（它读取 `splashVisible`）
  **声明**，而 ⑤ 又需要 ④ 的 `showLoginDialog` ⇒ 把 ④ 的调用点从原 L160 **前移**到「启动界面状态」块之前。
  `enterMainContent` 是函数声明（提升），前移后仍能作为参数提前传入（这条在步骤④ 已用探测文件实测过）。
- **两处「只写不读」的死状态**（本次只搬迁、未清理，行为零变化；是否删除属单独决策）：
  - `titlePhaseDone`：全文件仅 2 处（声明 + `onTitleDone` 赋值），模板与脚本均无读取方。疑似残留自
    代码注释所写的「开机语音已在 SplashScreen 标题出现时播放」那段逻辑迁入 SplashScreen 之后。
  - `_splashDismissed`：置 `true` 之后无人再读；且它是 setup 作用域内的 `let`，跨组件实例本就不保留
    ⇒ 原「二次挂载跳过闪屏」的意图其实一直是失效的。
- 规模（重跑 `python tools/app_vue_state_graph.py`）：`<script setup>` **433 行 / 38 符号 →
  420 行 / 32 符号**（−6 符号 = 本步骤搬迁符号数）；App.vue **726 → 713 行**
  （23327 → 23652 字节 —— 行数下降而字节上升，差额来自本步骤新增的说明注释）。
- 验证边界（改前/改后同环境同命令实测）：`vue-tsc -b` 0 错 → 0 错；
  `vue-tsc --noEmit -p tsconfig.app.json` 0 错 → 0 错；`vite build` exit 0，renderer 模块数
  **1241 → 1242**（+1 = 新 composable 被引用）；`node --test` 77 pass / 0 fail；
  `vitest run` 5 files / 29 passed；eslint（本卷 5 文件）**0 错 → 0 错**。
  自检新增两条**顺序不变量**断言（④ < ⑤ < `onModelReady`）+「`enterMainContent` 仍是函数声明」
  「仍能写穿 composable 的 ref」两项跨边界断言。
- 下一步（本图顺序）：**只剩最后一项** `useLive2dStage()`（渲染 / peek 变换 ~16 符号，**高风险**，
  与 ③⑤ 交叉）。⚠️ 按本图 §四 执行约定第 3 条，抽取前须先定 `isChatPeekMode` 的归属
  （它同时被渲染层与 splash 依赖）。
  `SpectrumPanel.vue` 仍 block 于「频谱 UI 重构方案定稿」，不单独拆。

— WorkBuddy · 工单204 任务三 · 步骤⑤ 完成记录

---

## 八、步骤⑥ `useLive2dStage()` 完成记录 —— 工单204 任务三 · 全部 6 步收口（2026-10-11）

- ✅ **步骤⑥ `useLive2dStage()` 已抽取**：`frontend/src/composables/useLive2dStage.ts`（11527 B / 256 行）。
  这是本图 §三 顺序表**最后一项**，抽取后本任务 6 步全部落地。
- **归属符号 20 个**（按精确计数 `tools/measure_stage.py` 口径，区分脚本侧/模板侧）：
  `Live2dModel`（异步组件）/ `width` / `height` / `scale` / `live2dRenderKey` / `modelReady` /
  `live2dTransform` / `live2dTransformOrigin` / `live2dTransition` / `initialPositionSet` /
  `onModelReady` / `live2dShouldShow` / `isChatPeekMode` / `PEEK_EXPRESSION` / `applyPeekExpression` /
  `live2dPeekShellStyle` / `live2dModelX` / `live2dModelY` / `live2dCombinedTransform` /
  `live2dCombinedTransition` / `live2dPeekShellTransition`，
  外加随族迁入的**两个 watch**（`effectiveLive2dSource` → `live2dRenderKey`；`isChatPeekMode` → 表情）。
  其中 **18 个导出**、3 个族内私有（`isChatPeekMode` / `PEEK_EXPRESSION` / `applyPeekExpression`，App.vue 零引用）。
- 参数表（8 项，全部作参数注入以避免重复实例化）：
  `useLive2dStage({ splashVisible, showMainContent, currentRoute, isFloatingMode,`
  `effectiveLive2dSource, activeLive2dSource, persistStartupLive2dSource, notifyModelReady })`。
  `CONFIG` 为模块级 ref 直接 import（App.vue 自身仍在 `onMounted` 里读 `CONFIG.value.floating`）。

### 8.1 三处对依赖图原表的校正（均为实测，非推断）

1. **`isChatPeekMode` 的归属 —— 与原表 §三 的建议相反。**
   原表建议它「留在 App.vue」（视作跨族共享点），并把它列为步骤⑥ 的关键边界。
   实测其 **6 个消费点全部落在本族内部**（`onModelReady` / `live2dPeekShellStyle` / `live2dModelX` /
   `live2dModelY` / `live2dPeekShellTransition` / `watch(isChatPeekMode, …)`），
   **模板侧引用数为 0** ⇒ 随族迁入才是内聚边界，而非留在 App.vue。
   其 5 个依赖里 `messageViewExpanded` 是模块级共享 ref（`@/utils/uiState`），按步骤④ 先例直接 import；
   其余 4 个（`splashVisible` / `showMainContent` / `currentRoute` / `isFloatingMode`）作参数注入。
2. **`width` / `height` / `scale` 原表未单列 —— 应随渲染族迁入。**
   实测三者**只被模板消费**：`width`/`height` 脚本侧仅 `useWindowSize()` 解构那一处；
   `scale` 脚本侧仅 1 处声明，另 3 处命中分别是中文注释与两处 CSS 字符串字面量（`scale(2.2)` / `scale(1.05)`），
   并非变量引用。⇒ 连同 `useWindowSize()` 调用一并迁入，App.vue 侧不再依赖 `@vueuse/core`。
3. **`live2dRenderKey` 的注解过期。**
   `useLive2dSource.ts` 文件头原记「`live2dRenderKey` 属渲染/舞台族边界、**其 watch 仍留在 App.vue**」。
   本步骤把该 watch 一并迁入（它唯一职责就是自增本族的 renderKey），并同步更正了该注释，避免留过期指引。

### 8.2 一处新发现：App.vue 的 lint 盲区（耐久事实，建议记入工程备忘）

`onModelReady` 读取 `isChatPeekMode`，而后者**声明在它之后**。这在本仓是既存写法，
且 App.vue 一直 lint 通过（步骤①~⑤ 各次验证 eslint 均为 0 错）。但把它原样搬进纯 `.ts` 后，
eslint 立刻报 `ts/no-use-before-define`（`useLive2dStage.ts:127`）。

**最小对照实验定性了根因**（`--print-config` 显示 `.ts` 与 `.vue` 的规则配置**完全相同**：
`ts/no-use-before-define: [2, { functions: false, variables: true }]`）：

| 试验体 | 结构 | 结果 |
|---|---|---|
| `__probe_ts.ts` | 顶层 `function f(){ return g.value }` + 后置 `const g` | ❌ 报 `'g' was used before it was defined` |
| `__probe_vue.vue` | 同上，放在**单个** `<script setup>` 内 | ❌ 同样报 |
| `__probe2_vue.vue` | 同上，但**前置一个 `<script lang="ts">` 空块** | ✅ **不报** |
| `App.vue`（实文件） | `<script>` + `<script setup>` 双块结构 | ✅ 不报（与 probe2 一致） |

⇒ 结论：**只要 `.vue` 是「双 script 块」结构，`ts/no-use-before-define` 对该文件实际失效**，
即 App.vue 一直是这类「函数体内引用后置 `const`」的 lint 盲区；纯 `.ts` composable 则会被正常抓到。
（这也解释了为什么前几步把代码搬出 App.vue 后才会暴露此类问题。）

处理方式与步骤③ 完全一致（`useLive2dSource.ts` 文件头早有同款说明——原 App.vue 里
`startupLive2dSource` / `persistStartupLive2dSource` 声明顺序相反，靠函数声明提升"碰巧"能跑）：
把 `isChatPeekMode` / `PEEK_EXPRESSION` / `applyPeekExpression` **整体提前到 `onModelReady` 之前**。
**仅调整声明顺序，逻辑零改动** —— `computed()` 与 `const` 对象均为惰性/无副作用创建，
函数声明本就可提升；`isChatPeekMode` 的 `immediate` watch 仍在所有依赖就绪后才注册。

### 8.3 跨边界写穿透（与步骤⑤ 同型）

`enterMainContent`（18 依赖的编排汇聚点，必须留在 App.vue）会写本族的
`live2dTransition` / `live2dTransform` / `live2dTransformOrigin` / `initialPositionSet`。
其中 `initialPositionSet` 原为 setup 作用域 `let`，跨边界写穿透要求它升级为 `ref`
（语句顺序与语义零变化；若后续希望收回内部，可改为暴露 `resetInitialPosition()`）。
迁移后 `enterMainContent` 的**语句顺序与两个 `setTimeout`（200 / 1500 ms）延时完全未变**，
自检对此有专项断言。

### 8.4 顺序不变量（更新）

原 §七 记录的「⑤ 的 `splashVisible` 必须早于 `onModelReady`（读取它）**声明**」在步骤⑥ 后升级为：

> **③ ≺ ⑥、④ ≺ ⑤ ≺ ⑥**
> - ④ ≺ ⑤：⑤ 的 `onSplashDismiss` 需要 ④ 的 `showLoginDialog`；
> - ⑤ ≺ ⑥：⑥ 内部的 `onModelReady` 读取 ⑤ 的 `splashVisible`，且 `isChatPeekMode` 依赖 ⑤ 的
>   `showMainContent` / `splashVisible`；
> - ③ ≺ ⑥：⑥ 消费 ③ 的 `effectiveLive2dSource` / `activeLive2dSource` / `persistStartupLive2dSource`。

`enterMainContent` 仍是函数声明（提升），故 ④⑤ 可继续提前传引用。

### 8.5 规模与验证（改前/改后同环境同命令实测）

规模（重跑 `python tools/app_vue_state_graph.py`）：
`<script setup>` **420 行 / 32 符号 → 322 行 / 13 符号**；App.vue **713 → 615 行**
（23652 → 21009 字节）。App.vue 现仅剩 13 个顶层符号：
`currentRoute` / `isForumRoute` / `isCompactRoute` / `hasCustomBg` / `customBgUrl` /
`floatingState` / `isFloatingMode` / `unsubStateChange` / `router` / `toast` / `enterMainContent` /
`onPaletteNavigate` / `onPaletteAction`。

| 验证项 | 改前（= main `eaebe1ed36`） | 改后（抽完 ⑥） |
|---|---|---|
| `vue-tsc -b` | 0 错 | 0 错 |
| `vue-tsc --noEmit -p tsconfig.app.json` | 0 错 | 0 错 |
| `vite build` renderer 模块数 | 1242 | **1243**（+1 = 新 composable 被引用） |
| 入口 chunk | 173.76 kB / gzip 57.24 kB | 174.75 kB / gzip 57.53 kB（+0.99 kB） |
| `node --test` | 77 pass / 0 fail | 77 pass / 0 fail |
| `vitest run` | 5 files / 29 passed | 5 files / 29 passed |
| eslint（本卷 6 文件） | 0 错 | 0 错 |

- 交付前自检 `verify_step6.py`：**129 项 PASS / 0 FAIL**（含顺序不变量 ③≺④≺⑤≺⑥、
  18 个解构符号全部被使用、`enterMainContent` 的 7 条写穿透语句与 2 个 setTimeout 延时、
  `isChatPeekMode` 声明早于 `onModelReady`、Cubism 核心注入早于 `Live2dModel` 动态 import、
  `<template>` 开闭配平 等）。
- **产物级复核**（防"抽取后被 tree-shake"的假绿）：`dist/assets/*.js` 中搬迁代码的 6 个字符串字面量
  全部存活且各 1 次 —— `translate3d(-234px, -1.6vh, 0) rotate(-4deg) scale(1.05)` / `24% 72%` /
  `transform 2.3s cubic-bezier(0.16, 0.84, 0.24, 1) 0.36s` / `transform 0.52s cubic-bezier(0.4, 0, 0.2, 1)` /
  `transform 1.2s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.8s ease` / `opacity 0.35s ease`。

### 8.6 本任务收口状态

- **工单204 任务三（App.vue 巨石拆分）6 步全部完成**：① `useWindowChrome` ② `useBackendOverlay`
  ③ `useLive2dSource` ④ `useAuthDialogs` ⑤ `useAppSplash` ⑥ `useLive2dStage`。
  App.vue 从拆分前体量收敛到 **615 行 / 13 顶层符号**，剩下的全是编排层
  （路由 / 悬浮球 / 背景 / 视差 / 弹窗装配 / 编排汇聚点 `enterMainContent` / 生命周期），
  符合「抽 composable、留编排」的目标形态。
- `SpectrumPanel.vue` 按工单约定 **block 于「频谱 UI 重构方案定稿」**，本任务不单独拆。
- 遗留（与本步骤无关，待单独决策）：
  1. `useAppSplash.ts` 的 `titlePhaseDone` 与 `_splashDismissed` 两处「只写不读」死状态（§七 已记录）；
  2. `initialPositionSet` 目前以 `ref` 形式跨边界写穿透，可考虑收回 `useLive2dStage` 内部并改暴露 `resetInitialPosition()`；
  3. **App.vue 双 script 块导致 `ts/no-use-before-define` 失效**（§8.2）——属规则/解析器层面，非本卷代码问题。

— WorkBuddy · 工单204 任务三 · 步骤⑥ 完成记录（任务收口）
