# 陆墨桌面助手 · 第三阶段开发报告

**日期**：2026-07-30  
**协作**：沈遥(架构) · 铁锚(审查) · 杜赞(决策) · 主代理(编码)  
**模型**：GLM5.2 / deepseek-v4-pro / 千文3.7plus / kimi2.7code

---

## 一、核心修复清单

### 1.1 Matchat DOM 选择器实抓校准
通过 `dom_probe.py` 在真实 Edge 浏览器中抓取 MatChat 页面 DOM，获取到：

| 元素 | 旧选择器 | 新选择器 (2026-07-30 校验) |
|---|---|---|
| 输入框 | `textarea[aria-label*=输入]` | `textarea#ai-input` |
| 发送按钮 | `button[type=submit]` | `button[data-tooltip-id='send-btn-tooltip']` |
| 聊天流容器 | `main [class*=chat]` | `#chat-scroll-container` |

### 1.2 MatchatBridge 架构升级
- **双模式桥接**：`persistent`（自管理 Edge）+ `cdp`（外部连接）
- **新增 `_wait_for_chat_ready()`**：Next.js hydration 完成判定，等待 20s
- **重写 `_wait_for_response()`**：基于消息块数量/文本稳定度的动态等待，替代旧的"等待 selector 出现"
- **新增 `_capture_latest_ai_text()`**：用 `TreeWalker` 提取高文本密度块，支持 Markdown/代码块识别

### 1.3 前端 TypeScript 编译修复（14 处错误 → 0）
- `src/forum/api.ts`（4 处）：`as unknown as T` 解包 AxiosResponseResult
- `src/views/KnowledgeView.vue`（9 处）：`WIN` 引用替换模板 `window`；`arr[arr.length-1]` 替换 `.at(-1)`；`(currentUrl||'')` 判空
- `electron/modules/matchat.ts`（1 处）：`cache_storage` → `cachestorage`

---

## 二、验证结果

| 测试项 | 结果 | 详情 |
|---|---|---|
| 前端 Build | ✅ 0 错误 | `npm run build` 全部通过，仅 2 个 chunk size 警告 |
| RAG 文本直入 | ✅ 通过 | 文档入库 `doc_a02bfec8`，1 个分块，25ms |
| RAG 检索 | ✅ 通过 | 3 条结果，2ms 延迟 |
| RAG 清理 | ✅ 通过 | `delete_document` 返回 success |
| main.py 模块导入 | ✅ 通过 | 任务管理器/GRAG 记忆系统初始化 OK |
| Matchat e2e | 🔄 后台运行 | v2 版本带选择器校验 + hydration 等待 |

---

## 三、修改文件清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `mcpserver/material_science/matchat_bridge.py` | 重构 | 双模式桥接 + DOM 选择器 + 等待逻辑 |
| `mcpserver/material_science/matchat_tools.py` | 适配 | 新增 `matchat_login_check` 工具 |
| `mcpserver/material_science/materialscience_agent.py` | 优化 | `run_in_executor` 隔离 Playwright |
| `mcpserver/material_science/agent-manifest.json` | 扩展 | 新增工具描述 |
| `frontend/src/forum/api.ts` | 修复 | AxiosResponseResult 解包 |
| `frontend/src/views/KnowledgeView.vue` | 修复 | 9 处 TS 错误 |
| `frontend/electron/modules/matchat.ts` | 修复 | cachestorage 拼写 |
| `apiserver/routes/rag.py` | 验证 | 文档入库接口可用 |
| `config.json` | 更新 | API key + 模型切换 |

---

## 四、架构决策

| 决策项 | 结论 | 理由 |
|---|---|---|
| MatChat 调用方式 | 浏览器自动化 (Playwright) | MatChat 不开放 API，只能 DOM 操作 |
| 内嵌方案 | BrowserView（Electron 内嵌） | 用户可手动操作，结果可自动提取入库 |
| 双模式选择 | persistent 优先 | 用户登录态持久化，无需每次手动登录 |
| RAG 降级策略 | 随机向量 → 真实嵌入 | 无 GPU 时用占位向量保证流程可跑 |
| 安全基线 | ContextVar + 文件权限 + CORS 锚定 | 防止 Token 泄露和 XSS 攻击 |

---

## 五、下一步计划

1. **Matchat e2e 全流程验证**：等待 v2 后台测试结果，必要时微调选择器
2. **Electron BrowserView 内嵌联调**：主进程与渲染进程 IPC 通信用
3. **知识库入库闭环**：MatChat 问答对 → RAG 自动入库 → 陆墨对话可检索
4. **安全审查（铁锚）**：对全部改动做最终安全审计
5. **完整端到端演示**：启动 `main.py`，验证陆墨 + MatChat + RAG 三方联动