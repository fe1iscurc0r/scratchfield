# 授粉报告 Batch-1A：openclaw + deepseek-harness

> 日期：2026-08-22 晚 | 模式：API 直读（大仓不 clone）| 许可：openclaw MIT / dsh MIT

## 一、openclaw/openclaw（387k★, MIT）— 全平台个人 AI 助手

### 架构（monorepo，packages/）

| Package | 职责 | 与 NEKO 契合点 |
|---------|------|---------------|
| **acp-core** | ACP（Agent Client Protocol）核心：session-identity / session-lineage-meta / structured-auth-redaction / interaction-mode | ⭐ 会话身份+血统追踪（NEKO 缺） |
| **agent-core** | agent-loop + harness/compaction：**branch-summarization** / compaction-image-tokens / trailing-toolresult | ⭐⭐ 压缩机制（对照 context_compressor） |
| **memory-host-sdk** | 记忆宿主 SDK | ⭐ 记忆层（对照 48912） |
| **plugin-sdk / plugin-package-contract** | 插件 SDK + 包契约 | ⭐ 插件体系（对照 mcp_manager） |
| **gateway-protocol / gateway-client** | 网关协议 + 客户端 | 多端网关 |
| **net-policy** | 网络策略 | 安全边界 |
| **model-catalog-core** | 模型目录 | 多模型路由 |
| **llm-core / ai / media-*** | LLM/媒体能力 | 通用 |

### 核心机制（值得抄）

1. **session-lineage-meta**：会话血统元数据——跟踪"这个会话从哪来、衍生自哪个分支"（NEKO 缺会话衍生链）
2. **branch-summarization compaction**：压缩时**分支摘要**而非简单截断——上下文满时按分支做摘要（比 context_compressor 的纯压缩多一层"分支认知"）
3. **structured-auth-redaction**：结构化认证信息脱敏（提示词里不泄露 token）
4. **interaction-mode**：会话交互模式显式声明

### 授粉建议

- NEKO 加 **session-lineage** 模块：会话 ID 继承父会话 ID + 分支标记（~200 行）
- context_compressor 升级：抄 branch-summarization 思路（压缩前先做"分支摘要"层）
- 不做整体移植（387k★ 大仓太重），只抄 2-3 个机制

## 二、deepseek-ai/deepseek-harness（181k★, MIT）— DSH 插件化 harness

### 架构核心：everything is a plugin（Cordis 范式）

```
vendor/     vendored Cordis 源码（manifest + sync 流程）
packages/   @deepseek-ai/dsh-<pkg> workspaces
  core/       API 主干：session/system-prompt/tools/agent/agent-loop
  api/        Remote BFF + Typert RPC 网关
  typert/     类型图生成器/加载器/运行时注册表
  llm/        LLM 能力：Service Definition/Consumer + DeepSeek providers
  skill/      skill provider 注册表 + 本地实现 + catalog/loader 工具
  compaction/ 压缩能力 + 基础 provider
  subagent/   subagent 能力：Service Definition + providers + delegation Consumers
  self-modification/  agent 检查/挂载自己的插件
```

### 核心机制（值得抄）

1. **Service Definition/Consumer 模式**：每个能力（shell/fs/web/subagent）都拆成"服务定义 + provider 实现 + Consumer 调用"三层——**彻底解耦能力与实现**
2. **self-modification**：agent 能检查并挂载自己的插件（元编程）
3. **typert 类型图**：类型驱动的 RPC 网关（类型即契约）
4. **preset 会话组合**：per-session agent 组合从 cordis.yml 预设加载

### 授粉建议

- mcpserver 的 adapter 层抄 **Service Definition/Consumer** 模式（现有 adapter 是直接透传，加服务定义层后更规范）
- rf_brain 的 demod 链可抄 **provider 注册表**（每个解调器一个 provider）
- 注意：DSH 是 developer preview，API 不稳定，只抄设计不抄代码

## 三、对照总结

| 维度 | openclaw | dsh | NEKO 现状 | 建议 |
|------|----------|-----|----------|------|
| 会话血统 | session-lineage ⭐ | session 主干 | 无 | 抄 openclaw |
| 压缩 | branch-summarization | compaction provider | context_compressor | 升级抄 openclaw |
| 插件体系 | plugin-sdk | Service Definition/Consumer | mcp_manager manifest | 规范化抄 dsh |
| 记忆 | memory-host-sdk | - | 48912 关 | 参考 |
| 子代理 | - | subagent capability | delegate_task 有 | 保留 |
