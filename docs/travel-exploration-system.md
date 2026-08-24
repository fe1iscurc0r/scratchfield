# 网络探索系统说明

## 1. 目的

本文档描述 Naga 当前的“网络探索”系统，覆盖：

- 用户可见业务流程
- 后端调度与 OpenClaw 执行模型
- 探索状态、进展、发现、来源、总结文件
- 认证失效与中断恢复
- 关键接口与测试清单

本文档面向：

- 产品/测试同学做回归验证
- 新接手的研发同学快速理解探索链路

## 2. 用户入口

当前用户实际使用的探索入口以论坛页为准：

- 页面：`frontend/src/forum/ForumQuotaView.vue`
- 用户动作：
  - 打开“网络探索”
  - 点击“新建探索”
  - 选择执行干员
  - 填写探索方向
  - 设置时间上限、积分上限
  - 设置浏览器策略
  - 点击“开始探索”

探索相关的辅助入口：

- 干员通讯录里的“探索中”标签可点击
  - 文件：`frontend/src/components/AgentContacts.vue`
  - 行为：跳转到该干员当前探索上下文
- 干员聊天页顶部有“探索中”横条
  - 文件：`frontend/src/views/MessageView.vue`
  - 行为：展示当前探索概览
- 干员聊天页在探索完成后展示“探索完成成果”
  - 文件：`frontend/src/views/MessageView.vue`
  - 行为：自动读取探索成果 markdown 文件

## 3. 业务语义

### 3.1 干员与探索的关系

- 同一干员的聊天和探索必须复用同一个 OpenClaw 实例
- 不允许为了探索再起第二个同干员实例
- 聊天和探索使用不同的 `session_key`
  - 聊天：`agent:main:{agent_id}`
  - 探索：`travel:{agent_id}:{session_id前8位}`

### 3.2 干员何时启动

- 仅在真正开始探索后启动干员
- 仅“选中干员”不会预热或唤醒 OpenClaw
- 聊天页点击干员会自动唤醒该干员实例

### 3.3 关闭逻辑

- 关闭聊天 tab：不会关闭干员 OpenClaw
- 探索完成：不会自动关闭干员 OpenClaw
- 关闭整个 Naga：会统一关闭所有干员 OpenClaw 子实例和主 Gateway

## 4. 端到端流程

### 4.1 创建探索任务

前端调用：

- `POST /travel/sessions`

后端处理位置：

- `apiserver/routes/extensions.py`

处理步骤：

1. 校验干员存在且为 `openclaw`
2. 检查该干员是否已有未结束探索
3. 创建 `TravelSession`
4. 将 session 持久化到 `.naga/travel/{session_id}.json`
5. 转发到 `agent_server` 的 `/travel/execute`

### 4.2 agent_server 启动探索

处理位置：

- `agentserver/agent_server.py`

核心流程：

1. 读取 `TravelSession`
2. 若指定干员，则 `ensure_running(agent_id)`
3. 生成探索会话键：
   - `travel:{agent_id or 'main'}:{session_id[:8]}`
4. 发送主探索 prompt
5. 进入轮询循环：
   - 周期性读取该 travel session 的 OpenClaw 历史
   - 解析进展、发现、来源、预算
6. 接近配额上限时发送收束提示
7. 最终进入总结/通知阶段

## 5. 持久化模型

### 5.1 探索 session 文件

目录：

- `.naga/travel/{session_id}.json`

关键字段：

- `status`
- `phase`
- `agent_id`
- `agent_name`
- `goal_prompt`
- `time_limit_minutes`
- `credit_limit`
- `credits_used`
- `elapsed_minutes`
- `discoveries`
- `sources`
- `unique_sources`
- `progress_events`
- `summary`
- `summary_report_path`
- `summary_report_title`
- `notification_delivery_statuses`
- `interrupted_reason`

### 5.2 探索成果文件

目录：

- `.naga/travel/{random_uuid}.md`

用途：

- 保存最终完整探索报告
- 聊天页在探索完成后自动读取并展示
- 若文件缺失，聊天页显示“找不到探索成果文件”

## 6. 状态与阶段

### 6.1 status

`TravelStatus`：

- `pending`
- `running`
- `interrupted`
- `completed`
- `failed`
- `cancelled`

### 6.2 phase

当前阶段字段 `phase` 用于展示探索当前卡点：

- `pending`
- `bootstrapping`
- `running`
- `wrapping_up`
- `finalizing`
- `publishing`
- `delivering_report`
- `notifying`
- `completed`
- `failed`
- `interrupted`

## 7. 进展、发现、来源、总结

### 7.1 进展

“最近进展”来自两部分：

1. 后端主动写入的阶段事件
   - 例如 `phase_changed`、`quota_warning`、`completed`
2. 从 OpenClaw 工具结果自动提取的事件
   - 例如：
     - `tool.web_search`
     - `tool.browser.open`
     - `tool.web_fetch`
     - `travel_progress`

解析位置：

- `apiserver/travel_service.py`
  - `_progress_event_from_tool_result(...)`
  - `analyze_history(...)`

### 7.2 发现

发现有两种来源：

1. AI 主动调用 `travel_discovery`
2. 后端自动从工具结果推导
   - `web_search`
   - `browser`
   - `web_fetch`

解析位置：

- `apiserver/travel_service.py`
  - `_discoveries_from_web_search_result(...)`
  - `_discovery_from_browser_result(...)`
  - `_discovery_from_web_fetch_result(...)`
  - `_discovery_from_travel_tool_result(...)`

### 7.3 来源

来源不是单独输入字段，而是从 `discoveries` 自动归纳：

- 优先使用 `site_name`
- 否则使用 `url` 的 host

归纳位置：

- `apiserver/travel_service.py`
  - `_collect_sources_from_discoveries(...)`

### 7.4 总结

总结有两层：

1. `summary`
   - 存在于 session JSON 中
   - 用于探索页摘要展示
2. `travel_summary` 生成的 markdown 文件
   - 存在于 `.naga/travel/{uuid}.md`
   - 用于聊天页展示完整成果

## 8. 探索专用工具

这些工具仅在 travel session 中暴露给 OpenClaw：

- `travel_progress`
- `travel_discovery`
- `travel_state`
- `travel_summary`

定义位置：

- `vendor/openclaw/src/agents/tools/travel-tools.ts`

注册位置：

- `vendor/openclaw/src/agents/openclaw-tools.ts`

### 8.1 travel_progress

用途：

- 让 AI 在关键阶段主动写入进展

典型场景：

- 开始搜索
- 切换方向
- 遇到阻塞
- 准备收束

### 8.2 travel_discovery

用途：

- 让 AI 主动写入结构化发现

字段：

- `url`
- `title`
- `summary`
- `tags`
- `source`
- `siteName`

### 8.3 travel_state

用途：

- 让 AI 查询当前累计状态

返回内容：

- 当前 status / phase
- 已用积分 / 时间
- discoveries
- sources
- progressEvents

### 8.4 travel_summary

用途：

- 让 AI 将最终完整成果写入 markdown 文件

字段：

- `title`
- `content`

写入结果：

- `.naga/travel/{uuid}.md`

## 9. 提示词中如何使用这些工具

### 9.1 主探索提示词

函数：

- `build_travel_prompt(...)`
- 文件：`apiserver/travel_service.py`

当前已明确要求：

- 关键阶段优先调用 `travel_progress`
- 确认发现优先调用 `travel_discovery`
- 需要当前累计上下文时调用 `travel_state`

### 9.2 收尾提示词

函数：

- `build_wrap_up_prompt(...)`
- 文件：`apiserver/travel_service.py`

当前已明确要求：

- 开始写最终报告前先调用 `travel_state`
- 生成完整 markdown 报告后调用 `travel_summary`
- `travel_summary` 成功后再返回简短 plain text 结论

### 9.3 补充指令提示词

函数：

- `build_travel_instruction_prompt(...)`
- 文件：`apiserver/travel_service.py`

当前已明确要求：

- 若补充指令改变探索方向或阻塞，优先调用 `travel_progress` 记录

## 10. 认证失效与中断恢复

### 10.1 认证失效

当 `openai_proxy` 上游返回 `401` 时：

1. 先尝试 refresh token
2. 若 refresh 后仍失败：
   - 将未完成探索标为 `interrupted`
   - `interrupted_reason = "auth_expired"`
   - 通知 `agent_server` 取消对应协程

### 10.2 退出与关闭

- 用户 logout：
  - 所有未完成探索转 `interrupted`
- 服务关闭：
  - 所有未完成探索转 `interrupted`
- 下次启动：
  - 自动恢复 `open` 状态的探索任务

## 11. 当前测试要点

建议最小测试集：

### A. 主链路

1. 新建一条最小探索
2. 确认 session 从 `pending -> bootstrapping -> running`
3. 确认 transcript 中出现：
   - `travel_progress`
   - `web_search`
   - `travel_discovery`
   - `travel_state`
   - `travel_summary`

### B. UI 数据

1. 探索页“最近进展”出现 tool 事件
2. 探索页“发现”数量 > 0
3. 探索页“来源”数量 > 0
4. `credits_used` > 0

### C. 成果文件

1. session 中出现：
   - `summary_report_path`
   - `summary_report_title`
2. 文件存在于 `.naga/travel/*.md`
3. 打开干员聊天页时自动展示成果文件
4. 手动删除该文件后，聊天页显示：
   - `找不到探索成果文件。`

### D. 中断恢复

1. 运行中让 token 过期或失效
2. 确认探索转为：
   - `status = interrupted`
   - `interrupted_reason = auth_expired`
3. 重新登录后再恢复

## 12. 当前已知风险

- `browser start` 仍可能超时，需要单独继续修浏览器/CDP 启动稳定性
- 某些 `web_fetch` 目标可能被 SSRF/私网规则误拦
- 若模型不主动调用 `travel_summary`，则不会产生成果 markdown 文件
- 当前积分是本地近似估算，不是业务后端真实计费账本

