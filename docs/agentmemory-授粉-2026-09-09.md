# agentmemory 轻量持久记忆授粉（W101-02）

> 2026-09-09 · 评估（不写实现）· 上游：rohitg00/agentmemory（28,189★，Apache-2.0，TypeScript，2026-09-07 活跃）
> 许可：Apache-2.0（授粉报告已复核）
> 源码：shallow clone 到本机 D:/my git/haul-backfill/agentmemory——以下引用为实读行号。

## 一、架构拆解

- 记忆类型：对话记忆 / 代码事实 / 用户偏好 三类（面向 coding agent）。
- 存储后端：本地轻量（文件/SQLite 级），零服务依赖。
- 自动提取时机：会话结束/工具调用后提取；注入时机：任务开始时按相关性注入。

## 二、授粉三大件①：源→目标映射

| 源组件（agentmemory） | 目标模块 | 授粉方式 | 收益 |
|----------------------|---------|---------|------|
| 编码 agent 记忆模式（三类记忆） | Hermes/scratchpad agent 记忆层 | 轻量记忆写法吸收 | 会话间上下文延续 |
| 自动提取+注入时机 | memory_maas capture 线 | 时机规则对照 | 注入 token 效率 |
| 去重 | memory_maas 写时校验 | 机制对齐 | 冗余下降 |

## 三、授粉三大件②：核心数据结构共鸣（2-3 处，实读引用）

1. **观察类型枚举（ObservationType 12 类）**（src/types.ts:85-99）：file_read/file_write/conversation/
   decision/discovery/task…与 memory_maas 的 observation/decision/intent 同构，吸收点=观察粒度划分。
2. **记忆实体六类 + 强度/到期字段**（src/types.ts:102-120 `Memory`：type ∈ pattern/preference/architecture/
   bug/workflow/fact + `strength` + `forgetAfter`）：**preference 类 + strength + 软过期**正是
   memory_maas v2 的 intent 实体与 retention_rule 的对照样板——双源印证「偏好抽取 + 软过期」。
3. **观察→压缩→记忆三级**（Session types.ts:1 → RawObservation :47 → CompressedObservation :64 → Memory :102）：
   与 claude-mem 三阶段（观察→压缩→记忆）同构的压缩层级。

## 四、关系判定 + 接入方案

- 与 memory_maas：**补充**（轻量降级路径 + 偏好抽取规则）；与 agentmemory-ts 生态同源对照。
- 接入方案：不独立接入——把「偏好自动抽取 + 任务边界提取时机」吸收进 memory_maas v2；
  工作量 0.5 天（规则级，评估后另立工单）。

## 五、许可裁定与结论

Apache-2.0 可借鉴；结论：**机制吸收（评估级）**，落点 memory_maas v2。

---
*评估：fe1iscurc0r · 2026-09-09 · 行号引用基于 shallow clone 实读（D:/my git/haul-backfill/agentmemory）*
