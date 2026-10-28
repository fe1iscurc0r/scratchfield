"""冻结跳反事实探针 · Agent 轨迹诊断器 PoC（工单227 任务一）.

料源：docs/pollination/failure-attribution-probe-2026-10.md（工单226 任务三设计稿）。

机制：对多跳轨迹的第 i 跳——冻结其输出为参考值，从 i+1 跳起重放后段，
比对最终输出 delta。delta 显著 → i 跳是因果跳（病根在 i 或其前）。

PoC 边界（设计稿 §4）：
- 重放走"步骤函数注册表"（chains.py 失败短路的反向利用——本 PoC 用同型轻实现，
  真接 chains.py 留给非 PoC 阶段）；
- 非确定跳（LLM 采样）显式标注"低置信"；
- 只做单参考轨迹归因，输出标注"需 ≥2 参考交叉验证"。
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Hop:
    """轨迹一跳：工具名 + 输入 + 实际输出 + 是否确定性（LLM 采样跳=False）."""

    name: str
    inp: dict[str, Any]
    out: Any
    deterministic: bool = True


@dataclass
class DiagnoseResult:
    causal_hop: int | None = None      # 1-based；None = 未定位出因果跳
    hop_deltas: list[float] = field(default_factory=list)
    confidences: list[str] = field(default_factory=list)  # 每跳 "高/低"
    notes: list[str] = field(default_factory=list)


# ── 重放引擎（chains.py 失败短路的反向利用：从任意前缀续跑）──

StepFn = Callable[[dict[str, Any]], Any]
_REGISTRY: dict[str, StepFn] = {}


def register(name: str) -> Callable[[StepFn], StepFn]:
    """步骤函数注册器（诊断器重放时按名取）。"""

    def deco(fn: StepFn) -> StepFn:
        _REGISTRY[name] = fn
        return fn

    return deco


def replay_from(hops: list[Hop], prefix_outs: list[Any], start: int) -> Any:
    """从 start 跳（0-based）起重放：前置输出用 prefix_outs 替换。"""
    outs = list(prefix_outs)
    for i in range(start, len(hops)):
        h = hops[i]
        fn = _REGISTRY.get(h.name)
        if fn is None:
            raise KeyError(f"未注册的步骤: {h.name}（诊断器需要可重放的步骤函数）")
        outs.append(fn({**h.inp, "_prev": outs[-1] if outs else None}))
    return outs[-1] if outs else None


# ── delta 度量（PoC：输出是 JSON 可比结构 → 结构化 diff 比例）──

def delta_score(a: Any, b: Any) -> float:
    """两输出的差异度 0~1：JSON 序列化后按叶子路径比对不同比例。"""
    if a == b:
        return 0.0

    def leaves(x: Any, path: str = "") -> dict[str, Any]:
        if isinstance(x, dict):
            out: dict[str, Any] = {}
            for k, v in x.items():
                out.update(leaves(v, f"{path}.{k}"))
            return out
        if isinstance(x, list):
            return {f"{path}[{i}]": v for i, v in enumerate(x) for v in [leaves(v, f"{path}[{i}]")][0].values()} or {path: x}
        return {path or "$": x}

    la, lb = leaves(a), leaves(b)
    keys = set(la) | set(lb)
    if not keys:
        return 0.0
    diff = sum(1 for k in keys if la.get(k) != lb.get(k))
    return diff / len(keys)


def diagnose(
    failed: list[Hop],
    reference: list[Hop],
    threshold: float = 0.15,
) -> DiagnoseResult:
    """冻结跳反事实归因.

    failed/reference：等长轨迹（同一任务失败/成功各一次）。
    对每个 i：prefix 用 failed[:i-1] 实际输出 + reference[i-1] 冻结值，重放 i+1 起，
    delta_i = diff(重放终值, failed 终值)。delta 越大 → i 越可能是因果跳。
    """
    assert len(failed) == len(reference), "失败/参考轨迹必须等长"
    n = len(failed)
    res = DiagnoseResult()
    for i in range(1, n + 1):
        prefix = [h.out for h in failed[: i - 1]] + [reference[i - 1].out]
        try:
            replayed = replay_from(failed, prefix, start=i)  # i 跳本身也重放（用冻结输入）
            d = delta_score(replayed, failed[-1].out)
        except Exception as e:  # noqa: BLE001 — 单跳重放失败不中断整体诊断
            res.notes.append(f"跳{i} 重放失败: {e}")
            d = float("nan")
        res.hop_deltas.append(d)
        res.confidences.append("高" if failed[i - 1].deterministic else "低(含LLM采样跳)")
    # 判据（设计稿修正）：因果跳 = **首个** delta≥阈值 的跳——冻结它能让输出翻好，
    # 说明病根在该跳或其前；其后跳的显著 delta 是"继承效应"（前病传导），不是源头。
    valid = [(d, i + 1) for i, d in enumerate(res.hop_deltas) if d == d]
    if valid:
        sig = [(d, i) for d, i in valid if d >= threshold]
        if sig:
            _, res.causal_hop = min(sig, key=lambda x: x[1])
        else:
            res.notes.append(f"全部 delta < 阈值 {threshold}：未定位出显著因果跳")
    else:
        res.notes.append("所有跳重放均失败")
    res.notes.append("单参考轨迹=单样本归因；生产使用需 ≥2 参考交叉验证")
    return res


# ── demo：合成 3 跳注入链（跳1坏/跳2好/跳3好）──

@register("fetch")
def _fetch(inp: dict[str, Any]) -> Any:
    return {"rows": inp.get("rows", [])}


@register("transform")
def _transform(inp: dict[str, Any]) -> Any:
    prev = inp.get("_prev") or {}
    rows = prev.get("rows", [])
    # 跳1 的病：丢了第一行（注入点）
    drop_first = inp.get("drop_first", False)
    return {"sum": sum(r for r in (rows[1:] if drop_first else rows))}


@register("report")
def _report(inp: dict[str, Any]) -> Any:
    prev = inp.get("_prev") or {}
    return {"total": prev.get("sum", 0), "label": inp.get("label", "r")}


def _demo() -> int:
    rows = [10, 20, 30]
    # 成功轨迹：fetch(rows) → transform(全量) → report
    good = [
        Hop("fetch", {"rows": rows}, {"rows": rows}),
        Hop("transform", {}, {"sum": 60}),
        Hop("report", {"label": "ok"}, {"total": 60, "label": "ok"}),
    ]
    # 失败轨迹：transform 带 drop_first=True（跳2 的输入坏了——因果源头是跳2）
    bad = [
        Hop("fetch", {"rows": rows}, {"rows": rows}),
        Hop("transform", {"drop_first": True}, {"sum": 50}),
        Hop("report", {"label": "ok"}, {"total": 50, "label": "ok"}),
    ]
    res = diagnose(bad, good)
    print("=== 冻结跳反事实诊断 demo（注入点=跳2 的 transform 输入）===")
    for i, (d, c) in enumerate(zip(res.hop_deltas, res.confidences), 1):
        print(f"  跳{i} ({bad[i-1].name}): delta={d:.3f}  置信={c}")
    print("因果跳 =", res.causal_hop)
    for n in res.notes:
        print("  注:", n)
    return 0 if res.causal_hop == 2 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="冻结跳反事实轨迹诊断器（工单227 PoC）")
    ap.add_argument("--demo", action="store_true", help="跑合成 3 跳注入链 demo")
    ap.add_argument("--trace", help="轨迹 ndjson 文件（PoC 后续接 tool_calls.ndjson）")
    args = ap.parse_args()
    if args.demo:
        return _demo()
    if args.trace:
        hops = [Hop(**h) for h in map(json.loads, open(args.trace, encoding="utf-8"))]
        print(f"读到 {len(hops)} 跳（重放需步骤注册表，PoC 演示见 --demo）")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
