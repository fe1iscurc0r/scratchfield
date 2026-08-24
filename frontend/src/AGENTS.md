# frontend/src/ — Agent 引导

本模块是陆墨的 Vue 3 渲染进程 UI 层，运行在 Electron 窗口内，通过 HTTP/WebSocket 与 apiserver 通信。

## 模块职责

- **主界面**：聊天（MessageView）、配置（ConfigView）、知识（KnowledgeView）、记忆（MemoryView）、思维（MindView）、技能（SkillView）、市场（MarketView）、旅行（TravelView）、悬浮窗（FloatingView）
- **社区论坛**：`forum/` — 完整的论坛子应用（帖子/评论/好友/消息/通知）
- **旅行系统前端**：`travel/` — 旅行会话配置、运行、历史展示
- **API 通信层**：`api/` — 封装与 apiserver (port 8000) 和 agentserver (port 8001) 的 HTTP 通信
- **Composables**：`composables/` — Vue 组合式函数（音频/认证/背景/视差/启动进度/工具状态/TTS）
- **工具函数**：`utils/` — 配置管理、Live2D 控制、会话存储、编码/流式处理、遥测

## 关键入口文件

| 文件 | 职责 |
|------|------|
| `main.ts` | Vue 3 应用入口、Vue Router 路由定义、PrimeVue 主题配置 |
| `App.vue` | 根组件（Live2D 背景 + 标题栏 + 路由视图 + 全局状态） |
| `api/index.ts` | `ApiClient` 类 — 与 apiserver 的 axios 实例，snake_case/camelCase 自动转换 |
| `api/core.ts` | 核心 API 函数（对话/流式/工具/配置/系统/MCP/技能/旅行/记忆） |
| `api/business.ts` | NagaBusiness 社区论坛直连客户端 |
| `electron.d.ts` | Electron IPC 类型声明 |
| `utils/config.ts` | 运行时配置类型与管理 |
| `utils/session.ts` | 会话/消息本地存储 |
| `utils/live2dController.ts` | Live2D 模型交互控制 |

## 数据契约位置

- **API 请求/响应**：`api/core.ts` 和 `api/index.ts` 中的函数参数与返回类型
- **旅行类型**：`travel/types.ts` — `TravelSession` 等
- **论坛类型**：`forum/types.ts` — 帖子/评论/用户等
- **配置类型**：`utils/config.ts` — `Config` 接口
- **流式编码**：`utils/encoding.ts` — `StreamChunk` 等 SSE 流式数据类型
- **Electron IPC**：`electron.d.ts` — 主进程 ↔ 渲染进程通信契约
- **snake_case/camelCase 转换**：`api/index.ts` 中 `transformRequest`/`transformResponse` 自动处理

## 测试路由

```bash
# 前端单元测试
cd frontend && npm run test

# 前端 lint
cd frontend && npm run lint

# 前端类型检查
cd frontend && npx vue-tsc --noEmit
```

测试文件位于 `frontend/tests/`：
- `ttsText.test.ts` — TTS 文本处理
- `windowState.test.ts` — 窗口状态管理

## 模块特有约束

1. **双后端通信**：`ApiClient` 连接 apiserver (port 8000)，`api/core.ts` 中的 `agentAxios` 连接 agentserver (port 8001)。两个实例各自管理 Token 拦截器和 snake_case/camelCase 转换。
2. **命名转换**：所有 API 请求自动 snake_case → camelCase（响应）/ camelCase → snake_case（请求），使用 `snakecase-keys` 和 `camelcase-keys` 库。新增 API 函数必须遵循此约定，不要手动转换。
3. **Electron IPC 边界**：渲染进程通过 `window.electronAPI`（见 `electron.d.ts`）与主进程通信。不要直接引用 Node.js API 或 `require()`。
4. **路由结构**：使用 `vue-router` 的 `createWebHashHistory`，所有路由在 `main.ts` 中定义。新增页面需在此注册。
5. **UI 组件库**：使用 PrimeVue（Lara 主题），支持暗色模式（`.p-dark` CSS 类）。新增组件应优先使用 PrimeVue 组件。
6. **Live2D 集成**：`utils/live2dController.ts` + `utils/live2dCoreLoader.ts` 管理 Live2D 模型加载与交互。角色资源在 `characters/` 目录。
7. **Token 管理**：`ACCESS_TOKEN` 存储在 `localStorage`（通过 `@vueuse/core` 的 `useStorage`）。Token 过期时设置 `authExpired = true`，由 `App.vue` 监听弹窗。
8. **ESLint + Prettier**：前端代码使用 ESLint + Prettier 格式化（`npm run lint:fix`）。
9. **不要硬编码绝对路径**，所有 API Key/Token 走环境变量。
10. **Vite 构建**：开发服务器 `npm run dev`，构建 `npm run build`。Electron 构建使用 `electron-builder`。
