"""工具链 · Trace Integrity 数据 Agent 审计（W60-01）

来源 docs/agent-trace-integrity-方案.md（S21 · digest-g1-4 2608.26036）：
「答案准确 ≠ 可靠」——LLM 数据 Agent 的可靠性不能只看最终答案对不对，还要看支撑
答案的数据轨迹是否有效。CAIT Rate = 答案正确但轨迹无效 / 全部答案。

原型（纯 stdlib，无新依赖）：
  - AuditEvent  不可变审计事件（inputs 形成血缘 DAG，cited_refs 为答案声称引用）
  - lineage_ancestors  由 inputs 构建每个事件的祖先集合
  - is_trace_valid     轨迹校验：cited_refs 必须在其血缘祖先内且被真实覆盖
  - cait_rate          计算 CAIT Rate + 无效轨迹明细

验收口径：能识别「答案正确但引用了不存在/无关中间结果」的 CAIT 案例。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["AuditEvent", "lineage_ancestors", "is_trace_valid", "is_answer_correct", "cait_rate"]


@dataclass
class AuditEvent:
    """一条不可变审计事件（append-only，带 provenance）。

    - inputs:     上游事件 ID 列表（lineage 父节点）
    - output_ref: 本事件产出数据引用（唯一标识 + 哈希语义）
    - cited_refs: 若本事件是「答案/报告」，它声称引用的数据引用列表
    - value:      输出值（供正确性校验；None 表示非答案事件）
    """
    id: str
    op: str
    inputs: list[str] = field(default_factory=list)
    output_ref: str = ""
    cited_refs: list[str] = field(default_factory=list)
    value: Any = None


def lineage_ancestors(events: list[AuditEvent]) -> dict[str, set[str]]:
    """由 inputs 边构建每个事件的血缘祖先集合（含自身）。"""
    by_id = {e.id: e for e in events}
    ancestors: dict[str, set[str]] = {}

    def dfs(eid: str) -> set[str]:
        if eid in ancestors:
            return ancestors[eid]
        e = by_id[eid]
        s = {eid}
        for parent in e.inputs:
            if parent in by_id:
                s |= dfs(parent)
        ancestors[eid] = s
        return s

    for e in events:
        dfs(e.id)
    return ancestors


def is_trace_valid(event: AuditEvent, events_by_id: dict[str, AuditEvent],
                   ancestors: dict[str, set[str]]) -> bool:
    """轨迹校验：答案声称引用的每个 cited_ref（数据引用）必须由其血缘祖先事件真实产出。

    即 cited_ref 需命中某个祖先事件的 output_ref——引用幽灵/无关数据 → 无效轨迹。
    """
    own = ancestors.get(event.id, {event.id})
    own_refs = {events_by_id[eid].output_ref for eid in own if eid in events_by_id}
    return all(ref in own_refs for ref in event.cited_refs)


def is_answer_correct(event: AuditEvent, ground_truth: dict[str, Any]) -> bool:
    """答案正确性：value 与 ground_truth[event.id] 相等。"""
    if event.id not in ground_truth:
        return False
    return event.value == ground_truth[event.id]


def cait_rate(answers: list[AuditEvent], events: list[AuditEvent],
              ground_truth: dict[str, Any]) -> dict:
    """计算 CAIT Rate = 答案正确但轨迹无效 / 全部答案，并给出无效轨迹明细。"""
    ancestors = lineage_ancestors(events)
    events_by_id = {e.id: e for e in events}
    total = len(answers)
    cait = []
    for a in answers:
        correct = is_answer_correct(a, ground_truth)
        valid = is_trace_valid(a, events_by_id, ancestors)
        if correct and not valid:
            cait.append(a.id)
    return {
        "total_answers": total,
        "cait_count": len(cait),
        "cait_rate": (len(cait) / total) if total else 0.0,
        "invalid_trace_ids": cait,
    }
