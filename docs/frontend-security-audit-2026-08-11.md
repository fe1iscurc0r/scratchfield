# frontend/ 模块代码审查报告

**审查范围**：`d:\my git\scratchpad\frontend`（src/ + electron/，约 52 个已提交代码文件，Vue 3 + TS + Vite + Electron）  
**审查方式**：只读全量审查，并与 apiserver/agentserver 路由交叉验证

---

## 🔴 Critical

无。未发现会导致崩溃、数据破坏或可被直接利用的安全漏洞。

---

## 🟠 High

### H1. 论坛模块前后端完全脱节：`/forum/api/*` 路由在后端不存在

**文件**：`frontend/src/forum/api.ts`（L90-L238，共 16+ 处调用，涉及 posts / comments / boards / profile / friend-requests / messages / notifications / report 全套接口）

**问题描述**：
- 前端 `src/forum/` 整套模块（api.ts + ForumListView 等约 16 个文件）通过 coreApi.instance（端口 8000）调用 `/forum/api/*` 系列路由
- 但 `apiserver/routes/` 下不存在 `forum.py`，全仓库 Python 代码中也没有任何 `/forum/api` 路由注册（已用 Test-Path 与全仓库 grep 双重确认）
- 旁证：`apiserver/travel_service.py` 有 `build_forum_post_payload()`（L619）、`extensions.py` 有 `post_to_forum` 字段，说明后端设计过该功能但路由层缺失
- 更严重的是后端侧：`agentserver/agent_server.py` L2306 `from apiserver.routes.forum import create_forum_post_internal` 导入了不存在的模块——探索旅程的"自动发布论坛精华"流程运行到此处必然抛 ImportError（虽在 try 块内不会崩服务，但功能必然失败）

**影响**：论坛所有页面请求 100% 返回 404；`api/index.ts` L140 还专门为 forum 错误做了 500/503 重试逻辑（`isTransientForumError`），说明前端是按"后端存在"的前提开发的，属典型的跨层不一致。

**修复建议**：
- 补齐 `apiserver/routes/forum.py`（含 `create_forum_post_internal`）并在 app 挂载；或
- 若论坛功能已砍掉，前端应在路由层禁用 forum 入口并下线 `src/forum/`，同时删除 `agentserver` L2306 的死引用

---

## 🟡 Medium

### M1. chatStream 未检查 HTTP 状态码，且绕过 axios 拦截器导致 401 无法自动刷新

**文件**：`frontend/src/api/core.ts` L333-L352

**问题描述**：

```ts
const { body } = await fetch(`${this.endpoint}/chat/stream`, { ... })   // 未检查 resp.ok
const reader = await body?.getReader()
...
if (!value?.startsWith('session_id: ')) {
  throw new Error('Failed to get sessionId')   // 401/500 时用户只看到这个无意义错误
}
```

- `fetch` 对 HTTP 错误不抛异常。后端返回 401/500（JSON 错误体）时，流解析失败，用户看到的是 `Error: Failed to get sessionId`，真实原因被吞掉
- 此路径用原生 fetch 而非 axios，完全绕过了 401 → refresh token 的拦截器逻辑：token 过期时流式聊天直接失败且不会触发刷新/重新登录弹窗
- 附带问题：L337 未登录时发送 `'Authorization': ''` 空头，应省略该头

**修复建议**：

```ts
const resp = await fetch(...)
if (!resp.ok) {
  if (resp.status === 401) { /* 触发与 axios 拦截器一致的刷新/authExpired 逻辑 */ }
  throw new Error(`Stream request failed: ${resp.status}`)
}
```

并在 `ACCESS_TOKEN.value` 为空时不设置 Authorization 头。

### M2. useToolStatus 的失败检测是死代码：Promise.allSettled 永不 reject

**文件**：`frontend/src/composables/useToolStatus.ts` L14-L75

**问题描述**：`poll()` 用 `Promise.allSettled` 包裹 5 个接口，它永远不会进入 catch，因此 L68-L74 的 `consecutiveFailures++` / "连续 3 次失败且已登录 → authExpired = true" 逻辑永远不会执行。同时 L25 无论单个请求成败都重置 `consecutiveFailures = 0`。

结果是：即使后端连续返回 401（token 失效），轮询这条链路也永远不会提示重新登录（仅 axios 拦截器路径生效）。

**修复建议**：改为检查各结果：

```ts
const allFailed = [status, clawdbot, tasks, live2d, music].every(r => r.status === 'rejected')
if (allFailed) {
  consecutiveFailures++
  if (consecutiveFailures >= 3 && isLoggedIn.value) { authExpired.value = true; consecutiveFailures = 0 }
  return
}
consecutiveFailures = 0
```

### M3. preload 暴露的 patcher:* IPC 通道在主进程无任何 handler

**文件**：`frontend/electron/preload.ts` L37-L39（白名单）、L224-L268（electronAPI.patcher 完整 API 面）

**问题描述**：preload 向渲染进程暴露了 `patcher:getStatus` / `checkUpdate` / `reset` / `isOfficial` / `revokeTrust` / `getTrustedSources` 及 4 个事件通道，但 `electron/main.ts`（581 行全量已读）中没有任何 `ipcMain.handle('patcher:*')` 注册，也没有 patcher 模块导入。任何调用 `window.electronAPI.patcher.*` 的代码都会得到 "No handler registered" 的 reject。

这属于半成品功能残留在发布面中——从安全角度看，preload 白名单应保持与实际 handler 一一对应，避免暴露无人维护的能力面。

**修复建议**：实现主进程 patcher 模块，或从 preload 白名单与 electronAPI 中移除 patcher 命名空间。

---

## 🔵 Low

| # | 位置 | 问题 |
|---|------|------|
| L1 | `frontend/src/utils/config.ts` L290-L302 | `loadSystemPrompt` 失败后无限 3 秒重试，且可能叠加多条重试链。建议加重试次数上限（如 5 次）+ 指数退避，并用模块级标志防止链叠加。 |
| L2 | `frontend/src/components/Markdown.vue` | DOMPurify 的 ALLOWED_ATTR 中包含 `'data-*'`、`'aria-*'` 字样——DOMPurify 不支持通配符，这两项实际无效；且同时设置 ALLOW_DATA_ATTR: false，与放行意图自相矛盾。建议删除通配项或改用 ADD_ATTR 列具体属性。 |
| L3 | `frontend/src/api/index.ts` | access token 存 localStorage（含 refresh token）。当前无已知 XSS 面，但 Electron 主进程已提供 SafeStorage 加密桥接（main.ts L437-L491），token 未利用。中期可迁移到 SafeStorage 或内存机制。 |
| L4 | `frontend/src/views/MessageView.vue` L1238-L1245 | 长对话列表无虚拟化。activeMessages 全量 v-for 渲染，超长会话时内存与渲染开销线性增长。当前规模下影响有限，量大后可引入虚拟滚动。 |

---

## ✅ 已核查且无问题的重点项

| 审查点 | 结论 |
|--------|------|
| XSS 面 | 仅 2 处 v-html：Markdown 有 DOMPurify；ArkButton 数据源为硬编码 ✓ |
| window.open | 仅 MarketView（后端商品 URL）与 useVersionCheck（下载链接），Electron 侧 setWindowOpenHandler 已限制 http/https ✓ |
| 内存泄漏 | 所有 setInterval/RAF/listener 均有清理 ✓ |
| SSE 协议 | `data: session_id:` 首行格式与 apiserver 完全一致 ✓ |
| WebSocket | `/ws` 路由匹配，重连有指数退避+10s 上限+手动关闭标志+HMR 清理 ✓ |
| Electron 安全基线 | contextIsolation:true / nodeIntegration:false / IPC 白名单 / 自定义协议路径穿越检查 ✓ |
| 敏感信息 | config.ts 中 API key 均为占位符（your-api-key-here），无真实密钥入库 ✓ |
| 竞态防护 | ForumListView loadId 令牌防乱序、session.ts loadingAgents Set 防重复、useStartupProgress 幂等守卫 ✓ |

---

## 总体质量结论

frontend 整体工程质量较好：Electron 安全基线完备、定时器/监听器清理纪律性强、SSE/WebSocket 协议与后端一致、错误处理覆盖面广。

**最严重的问题是论坛模块前后端完全脱节**（前端 16 个文件调用不存在的 `/forum/api/*`，agentserver 还引用了缺失模块），属于跨层协作失灵的典型缺陷，应优先处置。

其次需修复 chatStream 绕过鉴权拦截器与 useToolStatus 死代码这两处认证链路缺陷，其余均为低风险改进项。

---

*报告生成时间：2026-08-11 | 审查模式：只读*
