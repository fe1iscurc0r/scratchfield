# neko-electron-shell/ 只读代码审查报告

**审查范围**：`d:\my git\scratchpad\neko-electron-shell`（47 个已提交文件，约 3.8 万行，Electron 40 桌面外壳）

---

## Critical（必须修复）

### C1. 多个窗口以 nodeIntegration:true + contextIsolation:false + webSecurity:false 加载后端（可为远程）内容 → XSS 即 RCE

**位置**：`window-manager.js` L485-L493（Chat 窗口）

同样模式还出现在：
- Subtitle 窗口：`window-manager.js` L546-L554
- SubtitleSettings 窗口：`window-manager.js` L782-L790
- AgentHUD 窗口：`window-manager.js` L871-L879

**问题**：Chat/Subtitle/SubtitleSettings/AgentHUD 四类窗口均开启 `nodeIntegration: true`、关闭 `contextIsolation`、关闭 `webSecurity`，并 `loadURL` 后端地址（`/chat`、`/subtitle`、`/agenthud`、`/static/subtitle-settings.html`）。

同时应用明确支持用户配置任意远程后端 URL（`main.js` L3129-L3157 的 `save-port-config` 接受任何 `http(s)://` URL，启动时 L4049-L4055 直接应用）。

**后果**：
- 后端页面任意一处 XSS（聊天内容、Markdown 渲染、第三方资源）即可 `require('child_process')` → 完整系统级 RCE
- 指向远程/不可信后端时（这是正式功能路径），远端服务器内容天然拥有 Node 权限
- `webSecurity:false` 还允许这些页面跨域读取任意来源与本地 `file://` 资源

**修复方向**：这是 Electron 官方安全清单（checklist #2/#3/#11）明确禁止的组合。应改为 `nodeIntegration:false, contextIsolation:true, sandbox:true`，所有能力通过 preload 的 `contextBridge` 暴露最小 API；`webSecurity` 恢复默认 true，跨域需求由后端加 CORS 或主进程代理解决。若短期无法重构，至少应硬性限制 `originalUrl` 只允许 `127.0.0.1`/`localhost`。

---

## High（应尽快修复）

### H1. 主窗口/子窗口缺少导航与弹窗 URL 白名单，preload 会随导航注入任意页面

- Pet 主窗口无 `will-navigate` 守卫：全仓库只有 exit-retention 弹窗注册了 `will-navigate`（`exit-retention.js` L1510-L1515）；`installNavigationShortcutGuard`（`window-manager.js` L248-L290）只拦截 F5/Ctrl+R 快捷键，不拦 URL 导航。
- 三处 `setWindowOpenHandler` 无条件 `action:'allow'` 任意 URL：
  - `pet-window-lifecycle.js` L387-L445
  - `window-manager.js` L1680-L1714（React Chat 子窗口，`contextIsolation:false` + `webSecurity:false`）
  - `window-manager.js` L1101-L1140（Jukebox 子窗口）

**问题**：Pet 窗口以 `contextIsolation:false` + `sandbox:false` 加载后端页面，`preload-pet.js`/`preload.js` 会在每次导航后重新执行并把完整 IPC 桥注入新页面。一旦页面被导航（XSS 后 `location.href`、后端返回的重定向、`window.open`）到攻击者 URL，攻击页面即获得全部 IPC 能力（控制窗口、截图、隐藏所有窗口、向 WebSocket 发消息等）。全仓库也没有 `app.on('web-contents-created')` 级别的兜底守卫。

**修复方向**：

```js
app.on('web-contents-created', (_e, wc) => {
  wc.on('will-navigate', (event, url) => {
    if (!isAllowedNekoOrigin(url)) event.preventDefault();
  });
  wc.setWindowOpenHandler(({ url }) =>
    isAllowedNekoOrigin(url) ? { action: 'allow', ... } : { action: 'deny' });
});
```

并在三个现有 handler 中对非白名单 URL 返回 `{ action: 'deny' }`（外部链接改走已校验的 `open-external-url`）。

### H2. upload-logs-and-feedback 接受渲染进程任意路径 → 任意本地文件读取并上传

**位置**：`feedback.js` L1278-L1286（IPC handler），上传实现在 `feedback.js` L904-L933

**问题**：IPC handler 直接把渲染进程传入的 `zipPath` 交给 `uploadLogsAndFeedback`，后者仅 `fs.existsSync(zipPath)` 检查后就 `fs.createReadStream(zipPath)` 并 POST 到日志服务器。代码里已存在 `isManagedFeedbackZipPath`（L681-691，限定 `temp/N.E.K.O/feedback` 目录）和签名校验函数，但上传路径没有调用它做门禁。

任何能执行 JS 的窗口（结合 C1/H1 门槛极低）都可让主进程读取任意本地文件（如 `%USERPROFILE%\.ssh\...`、浏览器 cookie 库）并外发到 log_store_server。

**修复**：

```js
ipcMain.handle('upload-logs-and-feedback', async (event, zipPath, feedback) => {
  if (zipPath && !isManagedFeedbackZipPath(zipPath)) {
    return { success: false, error: 'invalid zip path' };
  }
  ...
});
```

---

## Medium（建议修复）

### M1. 敏感权限对任意来源自动授予

**位置**：`main.js` L3897-L3914（full 分区同样处理于 L3982-L3985）

**问题**：`setPermissionRequestHandler` 对 `display-capture`、`clipboard-read`、`media` 等无条件 `callback(true)`，不校验请求方 origin。与 C1/H1 叠加后，任何被加载/导航进来的第三方页面可静默截屏、读剪贴板、开麦克风。

**修复方向**：handler 中校验 `new URL(webContents.getURL()).origin` 是否属于可信后端 origin，非可信一律拒绝。

### M2. IPC 路由无发送方身份校验，子窗口可冒充 Chat/Pet 注入消息

**位置**：`ipc-router.js` L176-L203

**问题**：约 30 条路由（含 `neko:chat-send-text`、`neko:ws-raw-send`、`neko:agent-toggle`）对任何 `event.sender` 一律转发。由于 H1 允许在子窗口加载任意 URL，一个不可信页面可以直接向 Pet 注入"用户消息"或向 WebSocket 发原始数据。

**修复方向**：在路由注册处按 `event.sender` 反查窗口类型（`_nekoKind` / `BrowserWindow.fromWebContents`），限制每条通道的合法来源窗口；至少对 RAW_SEND/SEND_TEXT 做 sender 白名单。

### M3. save-hotkey-config 对渲染进程输入零校验即落盘并注册全局快捷键

**位置**：`hotkey-manager.js` L957-L967（注册在 L1207-L1216）

**问题**：`currentHotkeys = { ...config }` 直接接受任意键值（非字符串、超长、未知 action），持久化后用于 `globalShortcut.register`。虽然注册有 try/catch 不会崩溃，但可被用来覆盖/污染快捷键配置，且缺少 action 白名单意味着未来新增 action 时面更大。

**修复方向**：校验仅接受已知 action 集合 + 字符串型 accelerator，并用 `globalShortcut.isRegistered`/格式正则预检。

---

## Low（可选改进）

| # | 位置 | 问题 |
|---|------|------|
| L1 | `backend-runtime.js` L754-L759 | PowerShell 命令以字符串插值拼接：`Expand-Archive -Path '${archivePath}' ...`。路径目前由应用自身构造（风险低），但若安装路径含单引号会直接破坏命令语义；同文件 L536-L538 的 `Get-NetTCPConnection -LocalPort ${port}` 属同类模式（port 为数字，风险可忽略）。修复方向：改用参数数组传参，或对路径做单引号转义（`path.replace(/'/g, "''")`）。 |
| L2 | `main.js` L3521-L3524 | Loading 窗口 `contextIsolation:false` 且无 preload/sandbox。只加载本地 data URL/本地 HTML 且 `nodeIntegration:false`，实际风险很低，但属于不完整的安全配置，建议补齐 `contextIsolation:true`（Electron 默认值）保持一致性。 |
| L3 | 全仓库 | Pet/Chat 渲染进程崩溃无自动恢复。全仓库没有针对主窗口的 `render-process-gone`/`crashed` 重载逻辑（仅 backend 进程有 3 次重启，`backend-runtime.js` L948-L988）。渲染崩溃后桌面宠物会静默消失，建议对 Pet 窗口加 `render-process-gone → reload` 兜底。 |

---

## 值得肯定的做法

- `open-external-url` 严格校验 http(s) 前缀（`screen-capture-ipc.js` L566-L578）
- 所有 data URL HTML 生成统一使用 `escapeHtml`/`safeScriptJson`（`html-escape.js`），exit-retention 弹窗还带 CSP
- 未发现硬编码密钥/token；所有 spawn 均使用参数数组、`shell:false`，无 exec 拼接
- 文件写入全部指向固定路径（`userData/temp`），无渲染进程可控的写入路径
- 单实例锁、窗口/进程生命周期清理（`isDestroyed` 检查、listener 解绑）做得较细致

---

## 总体质量结论

该模块工程化水平不低（生命周期管理、HTML 转义、openExternal 校验、子进程参数化都做得规范），但**安全基线存在系统性缺陷**：四个窗口以 `nodeIntegration:true` + `webSecurity:false` 加载（可配置为远程的）后端内容，且全站缺少导航/弹窗 URL 白名单，使得任何后端 XSS 或被加载的第三方页面都能直达 Node 权限与完整 IPC 面，构成"XSS→RCE"的短链路。

**最高优先级**应是 C1 的 webPreferences 收敛与 H1 的导航守卫（可用 `web-contents-created` 一次性兜底），其次封堵 H2 的任意文件上传缺口。

---

*报告生成时间：2026-08-11 | 审查模式：只读*
