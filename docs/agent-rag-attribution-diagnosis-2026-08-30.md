# A15 Agentic RAG 归因诊断（Hop 覆盖率故障传播）

> 任务：A15 Agentic RAG 归因诊断
> 来源：digest-g2-2-2026-08-30.md · 授粉点 3（AgenticRAG-FP）+ 核心论文 2608.20627《When Failures Propagate》
> 日期：2026-08-30

---

## 一、问题陈述

Agentic RAG 是多跳的：检索 → 推理 → 再检索 → 再推理……当最终答案失败时，**故障到底发生在哪一跳**？缺乏归因，就无法定位"记忆失效在何处"。

AgenticRAG-FP 揭示了关键规律：**Hop 覆盖率随跳数骤降**——Hop1 覆盖率 0.91 → Hop3 为 0。多跳检索的故障不是独立分布，而是**沿跳数传播放大**：前面一跳的证据缺失，会级联导致后续跳拿不到可靠证据，最终答案崩溃。

## 二、诊断工具设计：Hop 覆盖率追踪

对一次失败的多跳 Agent 轨迹，逐跳记录"该跳本应检索到的证据，实际检索到了多少"，定位故障源头：

```
Hop1 → 覆盖率 C1（0.91 正常）
Hop2 → 覆盖率 C2（依赖 Hop1 证据）
Hop3 → 覆盖率 C3（≈0，故障爆发）
```

### 诊断输出
- **故障跳定位**：第一个覆盖率跌破阈值的跳，即故障"源头"（而非最终答案失败处）。
- **传播链**：从源头跳到最终失败的级联路径。
- **失效类型**：证据缺失 / 检索错配 / 上游错误继承。

## 三、诊断工具骨架

```python
def diagnose(trace, expected_evidence, threshold=0.8):
    hops = []
    prev_ok = True
    for hop in trace.hops:
        cov = coverage(hop.retrieved, expected_evidence[hop.idx])
        hops.append((hop.idx, cov))
        if cov < threshold and prev_ok:
            fault_source = hop.idx          # 首个跌破阈值的跳 = 故障源头
        prev_ok = cov >= threshold
    return {"hops": hops, "fault_source": fault_source}
```

## 四、诊断案例报告（模板）

| 跳 | 覆盖率 | 状态 |
|---|---|---|
| Hop1 | 0.91 | 正常 |
| Hop2 | 0.55 | 正常（略降） |
| Hop3 | 0.0 | **故障源头**（证据全缺失） |

**结论**：最终答案失败根因在 Hop3 的证据缺失，而非推理逻辑错误；修复应指向 Hop3 的检索策略（而非调推理 prompt）。

## 五、验收对照

| 验收项 | 交付 |
|---|---|
| 诊断工具 | §三 `diagnose` 骨架 |
| 案例报告 | §四 报告模板 |
| 定位记忆失效点 | §二 故障跳定位 |
| 文档 | `docs/agent-rag-attribution-diagnosis-2026-08-30.md` |
