# S03 SPA Plan-First 信息流控制（跨查询信任边界）

> 任务：S03 SPA Plan-First 信息流控制
> 来源：digest-g3-2-2026-08-30.md · 核心论文 2608.27234《SPA: Securing Persistent LLM Agents Across Queries with Plan-First Information-Flow Control》
> 日期：2026-08-30

---

## 一、问题陈述

持久化 Agent 跨越多个查询运行，同时接触**不可信网页/文档/工具**和**持久状态**，并对安全敏感资源行使权限。现有防御要么只保护规划阶段、要么只保护单次工具交互——但持久 Agent 面临的是**跨查询的、累积的信息流泄漏**：一次查询里的不可信内容，可能在后续查询中被带进敏感操作。

SPA（2608.27234）提出 **Plan-First 信息流控制**：在规划阶段就按"信息流的信任边界"约束后续执行。

## 二、方案设计

### 2.1 信任边界（taint 标签）
- 给所有信息源打标签：`trusted`（系统/受信）、`untrusted`（网页/文档/工具返回）。
- 信息流规则：**untrusted 数据不得流入敏感操作**（写文件、调用特权工具、修改持久状态）。

### 2.2 Plan-First 原则
- **先规划、后放行**：Agent 在规划阶段声明"要读什么、要写什么、信任边界是什么"。
- 执行阶段按规划声明做信息流控制：任何未在规划中声明、或跨越信任边界的数据流，在执行前被拦截。

### 2.3 跨查询持久化
- 持久状态（记忆/配置）同样打标签：只有 `trusted` 来源才能写入持久状态。
- 防止"某次查询的不可信内容 → 被持久化 → 污染后续查询"。

## 三、原型骨架

```python
def plan_first(plan, taint_map):
    # plan 声明数据流：source -> sink
    for flow in plan.flows:
        src, sink = flow.source, flow.sink
        if taint_map.get(src) == "untrusted" and sink_is_sensitive(sink):
            return f"reject:untrusted->sensitive ({src}->{sink})"
    return "allow"
```

## 四、权限泄漏测试

| 泄漏向量 | 拦截 |
|---|---|
| 不可信文档内容写入持久状态 | reject:untrusted->sensitive |
| 未在规划中声明的特权工具调用 | reject（Plan-First 未声明） |
| 跨查询累积的不可信数据进入敏感操作 | reject（taint 持久化） |

**验收目标**：跨查询的权限泄漏被系统性阻断。

## 五、验收对照

| 验收项 | 交付 |
|---|---|
| Plan-First 信息流控制方案 | §二（信任边界 + Plan-First + 跨查询持久化） |
| 原型 | §三 `plan_first` 骨架 |
| 权限泄漏测试 | §四 |
| 文档 | `docs/security-spa-plan-first-2026-08-30.md` |
