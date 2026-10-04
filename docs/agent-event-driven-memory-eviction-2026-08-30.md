# A11 事件驱动记忆淘汰（嵌入式 Agent）

> 任务：A11 事件驱动记忆淘汰
> 来源：digest-g2-2-2026-08-30.md · 授粉点 3：AgenticRAG-FP 多跳故障传播
> 日期：2026-08-30

---

## 一、问题陈述

嵌入式 Agent（ESP32 / N.E.K.O. 等资源受限设备）的记忆容量极小，必须持续淘汰。但"该淘汰什么"如果凭直觉或 LRU，会误删关键记忆。AgenticRAG-FP 揭示了一个可用于指导淘汰的规律：

- **Hop 覆盖率随跳数骤降**：Hop1 覆盖率 0.91 → Hop3 为 0。
- 多跳检索中，故障沿跳数**传播放大**：越靠后的跳，越拿不到可靠证据。

这意味着：**记忆失效不是均匀的，而是集中在多跳链的远端**。淘汰策略应据此把"贡献了高 Hop 覆盖率的记忆"保下来，把"只在低价值远端出现、从未支撑过检索成功"的记忆淘汰。

## 二、事件驱动记忆淘汰策略

### 2.1 记忆价值度量：Hop 覆盖率贡献
对每条记忆 m，统计它在历史检索中被命中的跳数分布：
- `hop_contribution(m) = Σ_hop w(hop) · hit(m, hop)`
- 低 hop（Hop1，直接证据）权重最高；高 hop 权重随跳数衰减（因为高 hop 本身不可靠）。

### 2.2 淘汰规则（按 Hop 覆盖率衰减）
| 记忆类型 | 处置 |
|---|---|
| 支撑 Hop1 成功检索、且近期复用 | 固化保留 |
| 仅出现在 Hop3+（远端、覆盖率≈0） | 优先淘汰 |
| 长期未命中、无复用证据 | 淘汰 |
| 与"最近完成的事件"关联（事件驱动） | 事件结束后即固化，超预算再淘汰 |

### 2.3 事件驱动
结合 SDR/频谱场景的"事件完成→固化"模式（对齐 g2-1 StreamSoccer 事件驱动记忆）：记忆按**事件生命周期**组织——事件进行中保留工作记忆，事件完成固化结论，超出预算时按 Hop 贡献值淘汰低价值条目。

## 三、淘汰规则骨架

```python
def evict(memory, budget, hop_stats):
    if len(memory) <= budget:
        return memory
    for m in memory:
        m.value = sum(w(h) * hop_stats[m].hits.get(h, 0)
                      for h in hop_stats[m].hits)
        m.last_use = hop_stats[m].last_use
    # 排序：价值低 + 久未用 → 优先淘汰；保留高 Hop 贡献、近期复用
    keep = sorted(memory, key=lambda m: (m.value, m.last_use), reverse=True)[:budget]
    return keep
```

## 四、评估

- **指标**：淘汰后，多跳检索的 Hop1/Hop2/Hop3 覆盖率保持率；任务成功率相对 LRU 基线的变化。
- **预期**：相比 LRU，本策略在相同预算下保留更高 Hop1 覆盖率（因为显式保护了"直接证据"记忆），多跳任务成功率更高。

## 五、验收对照

| 验收项 | 交付 |
|---|---|
| 淘汰策略 | §二（Hop 覆盖率贡献 + 事件驱动） |
| 淘汰规则 | §三 `evict` 骨架 |
| 评估 | §四 指标与预期 |
| 文档 | `docs/agent-event-driven-memory-eviction-2026-08-30.md` |
