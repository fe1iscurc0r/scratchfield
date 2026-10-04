# TencentDB-Agent-Memory 团队记忆中枢评估（W101-03）

> 2026-09-09 · 评估（不写实现）· 上游：TencentCloud/TencentDB-Agent-Memory（26,200★，MIT 原文确认，TypeScript，2026-09-08 活跃）
> 许可：MIT（授粉报告已读 LICENSE 原文裁决）
> 源码：shallow clone 到本机 D:/my git/haul-backfill/TencentDB-Agent-Memory——以下引用为实读行号。

## 一、架构拆解

- MemoryCore：核心存储与检索；MemoryKnowledge：知识注入面；统一检索索引。
- 数据域：对话 / 文档 / 代码三类源 → 统一检索。
- MCP 接入形态：作为 MCP server 暴露记忆工具。
- 团队共享模型：多用户共享 + 权限隔离。

## 二、授粉三大件①：源→目标映射

| 源组件（TencentDB-Agent-Memory） | 目标模块 | 授粉方式 | 收益 |
|----------------------------------|---------|---------|------|
| 团队记忆 hub（多用户共享+隔离） | scratchpad 记忆层 | 架构参考 | 多 Hermes 实例共享记忆 |
| 统一检索索引（对话/文档/代码） | memory_maas 混合检索 | 跨源索引设计参考 | 检索面扩展 |
| MCP 接入形态 | mcpserver 外部桥 | 注册评估 | 团队级记忆服务 |

## 三、授粉三大件②：核心数据结构共鸣（2-3 处，实读引用）

1. **Host-neutral 抽象接口层**（MemoryCore/src/core/types.ts:2-9 头部注释「TDAI Core depends ONLY on these
   interfaces」+ `HostAdapter` :238）：核心与宿主解耦的接口化设计——本仓记忆层「引擎/宿主」分离的参考。
2. **统一记忆生命周期接口**（`CaptureResult` types.ts:305 / `RecallResult` types.ts:283 / `CompletedTurn` :257）：
   捕获→召回→回合三接口与 memory_maas capture/hybrid_search 一一对应，吸收点=接口边界划分。
3. **四件套模块拆分**（MemoryCore/MemoryKnowledge/MemoryPanel/MemoryProxy 顶层目录）：核心/知识/面板/代理
   分层——与 mcpserver（引擎/桥/注册）的模块对照。

## 四、MCP 接入可行性

- 按 mcpserver 三表注册流程，可走 external/mcporter 桥登记（作为团队记忆外部服务）。
- 接入方案：登记评估（不立即启用）——多 Hermes 实例共享记忆是本仓真实场景，
  接入价值中高；工作量（启用级）1-2 天（服务部署 + 注册 + 隔离配置）。

## 五、许可裁定与结论

MIT 可借鉴；结论：**架构参考 + MCP 登记候选**（多实例共享记忆的价值判定：高，暂缓启用）。

---
*评估：fe1iscurc0r · 2026-09-09 · 行号引用基于 shallow clone 实读（D:/my git/haul-backfill）*
