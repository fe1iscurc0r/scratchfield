# SPEC-06 · mcpserver 总线优化

> 日期 2026-08-22 深夜 | 状态：设计完成，待实施
> 铁律：NEKO 冻结，总线外围优化；token 不给图像

## 一、现状（代码实测）

- 三表注册中心：`MCP_REGISTRY`（服务池）/ `MANIFEST_CACHE`（manifest 缓存）/ `_ADAPTER_CAPABILITIES`（adapter 能力登记）
- 统一调度：`MCPManager.unified_call()` 路由；跨源冲突检测 `_check_cross_source_conflict()` 只 WARNING 不阻断
- 安全：`security_utils.py` 模块加载白名单（`mcpserver.` / `vendor.` 前缀）+ 路径校验
- 外部 MCP：`mcporter_bridge.py` + `external_services.example.json`（toolbox-postgres / swarmvault / mentedb / arcrift / apify 全 `_disabled`）
- 参考仓：mcp-gateway-registry（MIT，集中鉴权/动态发现/安全扫描）、arcade-mcp（MIT，decorator + 声明式 OAuth 22 provider）

## 二、优化目标

1. 冲突从"静默警告"变"可配置阻断"——防止同名工具被第三方悄悄覆盖
2. 接入 Context7——写码防 API 幻觉（最大痛点）
3. 外部记忆服务按需解禁——与五维记忆融合互补
4. 可观测性——知道每个工具调用的延迟/失败率
5. 声明式鉴权——凭证不落 LLM 上下文

## 三、B1 跨源冲突严格化

**现状**：三条写入路径（manifest / mcporter / adapter）登记前统一调 `_check_cross_source_conflict()`，发现冲突只打 WARNING 并在 `list_registered_capabilities` 附 `conflict_sources` 字段。

**改造**：
- 新增环境变量 `CONFLICT_STRICT`（默认 `0`，保持现状）
- `=1` 时：冲突登记直接拒绝，返回错误码 `CONFLICT_REJECTED`，并记录到 `_CONFLICT_LOG`（内存表，供审计查询）
- 优先级规则（严格模式下也不一刀切）：
  1. `adapter` 覆盖 `manifest`（adapter 是后接能力，更新）
  2. `manifest` 覆盖 `mcporter`（本地优先于外部）
  3. 同类源冲突（adapter vs adapter）→ 必拒

**验收**：
- `CONFLICT_STRICT=0` 行为不变（回归）
- `=1` 时构造同名工具注册 → 返回拒绝 + `_CONFLICT_LOG` 有记录
- 优先级规则单测 3 条

## 四、B2 Context7 MCP 接入

**背景**：Context7（`npx @upstash/context7-mcp`）按需拉最新库文档，37k 下载，防 API 幻觉（写码时猜 API 是我们的痛点）。

**接入方式**（不引入 Node 运行时）：
- 方案：本地 `context7` HTTP API（Context7 提供 `https://context7.com/api/v1/...` 查询端点）→ 封装为 `mcpserver/adapters/context7.py`
- 注册为 MCP 工具 `context7_query_docs`（参数：`lib` / `query` / `limit`）
- 超时 3s，失败降级跳过（铁律5：总线挂了不影响主对话）

**验收**：
- `context7_query_docs("fastapi", "streaming response", 3)` 返回真实文档片段
- 无网络/超时 → 返回空字符串，不报错

## 五、B3 外部记忆服务解禁（按需）

**现状**：`external_services.example.json` 里 5 个服务全 `_disabled`：
- toolbox-postgres（Google 数据库 MCP）
- swarmvault（LLM Wiki/RAG）
- **mentedb（AI 记忆引擎）**
- **arcrift（编程跨会话记忆）**
- apify（网页抓取/搜索/数据提取）

**策略**：与五维记忆融合（SPEC-05）协同，按需逐个启用：
- **mentedb / arcrift**：先做能力对照（vs summer_memory + memclaw），不重复则启用为"跨会话编程记忆"补充——P2
- toolbox-postgres：等 Lumo 数据底座（W-09）需要时启用——P3
- 启用即改 `"disabled": false` + 健康检查通过

## 六、B4 声明式鉴权（借鉴 arcade-mcp）

**现状**：adapter 凭证 fail-fast（缺凭证跳过），但无声明式 OAuth。

**改造（轻量）**：
- adapter manifest 增加可选字段：`requires_auth: {"provider": "github", "scopes": [...]}`
- 注册时校验：无凭证 → 工具标记 `auth_required=true`，调用时返回明确错误"请先配置 {provider} 凭证"（不进 LLM）
- 第一落地：hamlog_adapter（电台日志）无需；优先给需外部 API 的 adapter（如 apify / context7 若需 key）

**验收**：
- 无凭证工具可注册但调用被拦，返回标准错误格式
- 配好凭证后正常调用

## 七、B5 工具级可观测

**改造**：`unified_call()` 内埋点：
- 内存表 `_TOOL_METRICS = {tool_name: {"calls", "latency_sum", "errors", "last_call"}}`
- 新端点 `GET /metrics/tools`（mcpserver HTTP 入口扩展）
- 不做外部 exporter（P3 再考虑 Prometheus）

**验收**：
- 连续调用 3 个工具后 `/metrics/tools` 返回聚合数据
- 错误调用计 error+1

## 八、B6 插件化热插拔（dsh 心智）

**现状**：adapter 注册走 `register_all_adapters()`，启动时一次性。

**改造（P3，轻量）**：
- 每个 adapter 目录加 `plugin.yaml`（name / entry / enabled / deps）
- `MCPManager.reload_adapter(name)` 支持运行中重载（重新 import + 注册，失败回滚旧实例）
- 开关：`ENABLE_ADAPTER_<NAME>` 环境变量（已有 memclaw 先例，推广到全部）

**验收**：
- 运行中 disable→enable 一个 adapter，注册表正确增减
- 重载失败不影响其他 adapter

## 九、实施顺序与工作量

| 步 | 内容 | 代码量 | 优先级 |
|----|------|--------|--------|
| B1 | 冲突严格化 | ~80 行 | P1 |
| B2 | Context7 adapter | ~120 行 | P1 |
| B3 | 外部服务解禁评估 | ~60 行（对照表） | P2 |
| B4 | 声明式鉴权 | ~100 行 | P2 |
| B5 | 可观测指标 | ~90 行 | P2 |
| B6 | 插件化热插拔 | ~150 行 | P3 |

**总计 ≈ 600 行，沈遥线，不占 Trae 工单**
