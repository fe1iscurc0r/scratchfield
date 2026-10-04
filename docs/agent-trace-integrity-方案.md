# S21 Trace Integrity 数据 Agent 审计方案

> 来源：digest-g1-4 2608.26036（Trace Integrity for LLM Data Agents: A Vision for Auditing）
> 核心命题：**答案准确 ≠ 可靠**。LLM 数据 Agent 的可靠性不能只看最终答案对不对，还要看
> "支撑答案的数据轨迹是否有效"——CAIT Rate 衡量的正是"答案正确但轨迹无效"的比例。

## 1. 审计目标

对 NEKO 数据 Agent（查库/聚合/计算/出报告）建立审计框架：追踪**数据来源 → 转换 →
使用**的完整痕迹，评估"这个答案是真的算出来的，还是编出来的/抄错了来源"。

## 2. 审计事件模型

每个数据操作发一条**不可变审计事件**（append-only，带 provenance）：

```
AuditEvent:
  id           事件唯一 ID（时间序 + 随机）
  ts           时间戳
  agent_id     执行 agent
  op           操作类型：read | transform | join | filter | aggregate | cite | output
  tool         使用的工具（如 sql/表格/mcp 工具）
  inputs       上游事件/数据源 ID 列表（lineage 的父节点）
  output_ref   产出数据引用（含哈希）
  source       数据来源（对齐 trust_layer 来源分级：user_direct/agent/file/external）
  params       操作参数摘要（供复现）
```

关键：`inputs` 字段把每个输出**链接回它的上游数据**，形成有向血缘图（lineage DAG）。

## 3. 追踪流程

1. **插桩**：数据 Agent 的每个数据读写/转换点都 emit 一条 AuditEvent（写入 append-only 日志，建议哈希链防篡改）。
2. **血缘构建**：由 `inputs → output_ref` 边构建 provenance DAG，每个最终答案对应一条从原始数据源到输出的路径。
3. **轨迹校验（CAIT 检查）**：审计时对每个"答案"回放/校验——答案引用的数据是否真实存在于其血缘路径上？转换是否可复现（重跑得到同一 output_ref 哈希）？答案与轨迹不一致 → 判为 invalid trace。
4. **可靠性指标**：
   - `CAIT Rate = 答案正确但轨迹无效 / 全部答案`（越低越好，目标逼近 0）
   - `tool-call adherence`：声明用到的工具是否真的被调用
   - `provenance coverage`：最终答案中被溯源覆盖的声明比例

## 4. 与 NEKO 既有体系的对齐

- 复用 `mcpserver/trust_layer.py` 的来源分级与评分（source_history/signature/lineage/review）。
- 复用 `docs/neko-trust-memory-设计稿.md` 的 provenance 字段约定（P0 必填）。
- 审计日志可作为 `summer_memory` / NEKO memory 的 evidence 事件源，供回溯与告警。

## 5. 落地形态

先落一个轻量 `audit_event` 记录器（append-only + 哈希链）与一个 `CAIT` 离线校验器，
无需改造所有数据工具；审计事件按 NEKO 现有 evidence/lineage 模块的 schema 对齐。
