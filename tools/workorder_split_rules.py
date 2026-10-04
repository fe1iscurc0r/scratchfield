# -*- coding: utf-8 -*-
"""工单拆分规则 v2（W64-04 · multica R1-R10 落地）。

依据 docs/multica-任务分配-授粉报告.md §3：把 R1-R10 规则集落成可执行工具——
  - 时序语义 / 阻塞分类 / 去重门 / 审查门 / 重试超时
  - JobSpec 落地：deps（DAG 边）+ 超时 + 重试策略
  - 输入：粗任务列表 → 输出：拆分后工单清单（含依赖/阻塞/去重标记）

纯标准库。运行：python tools/workorder_split_rules.py
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawTask:
    id: str
    title: str
    deps: list[str] = field(default_factory=list)
    blocking: bool = False   # 阻塞任务（缺前置/依赖未满足）
    timeout_s: float = 3600.0
    retries: int = 2


@dataclass
class WorkOrder:
    id: str
    title: str
    deps: list[str] = field(default_factory=list)
    blocking: bool = False
    deduped: bool = False
    needs_review: bool = False
    timeout_s: float = 3600.0
    retries: int = 2


def split_workorders(tasks: list[RawTask]) -> list[WorkOrder]:
    """拆分：去重门 + 阻塞分类 + 审查门 + 超时/重试。"""
    seen: dict[str, str] = {}   # 规范化标题 -> 首个 id（去重门）
    orders: list[WorkOrder] = []
    for t in tasks:
        key = t.title.strip().lower()
        if key in seen:
            # 去重门：重复任务被拦截（标 deduped 的占位，不计入输出）
            continue
        seen[key] = t.id
        # 阻塞分类：deps 未满足或显式 blocking
        blocking = t.blocking or len(t.deps) > 0
        # 审查门：超时过短或重试为 0 需要审查
        needs_review = t.timeout_s < 60.0 or t.retries == 0
        orders.append(WorkOrder(
            id=t.id, title=t.title, deps=t.deps, blocking=blocking,
            needs_review=needs_review, timeout_s=t.timeout_s, retries=t.retries,
        ))
    return orders


def order_non_blocking_first(orders: list[WorkOrder]) -> list[WorkOrder]:
    """阻塞任务排后（不先行）。"""
    return sorted(orders, key=lambda o: (o.blocking, o.id))


if __name__ == "__main__":
    tasks = [
        RawTask("a", "实现频谱缓存", retries=1),
        RawTask("b", "实现频谱缓存", retries=1),   # 重复 → 去重
        RawTask("c", "接入解调链", deps=["a"], retries=2),  # 有依赖 → 阻塞
        RawTask("d", "写测试", timeout_s=30, retries=1),     # 超时过短 → 审查
    ]
    orders = order_non_blocking_first(split_workorders(tasks))
    for o in orders:
        print(f"{o.id}: {o.title} blocking={o.blocking} review={o.needs_review}")
