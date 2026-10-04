"""失败会话 trace 回放（纯 stdlib · JSON 落盘 · 无外部依赖）。

授粉来源：dreadnode/agent-lens（MIT ★115）的 trace+replay 设计思想，独立实现。
目的：给自反馈层补「失败会话落盘 → 可回放 → 定位根因」能力——agent/流程失败后
把关键步骤（调用/输入/输出/错误/耗时）落盘为结构化 trace，事后按时间序重放，
并定位首个失败步及前 3 步上下文，产出可喂给规则生成的失败摘要。

实现纪律（授粉）：
- 纯标准库（json/datetime/pathlib），不引新依赖。
- 只落盘/重放/摘要，不修改 radio_brain 现有链路（纯新增，对接由调用方决定）。
- 中文注释与输出；损坏/空 trace 明确报错，不静默吞异常。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# 步骤必填键（缺键视为损坏 trace，明确报错）
_REQUIRED_STEP_KEYS = {"call", "ok"}


def _normalize_step(step: dict, index: int) -> dict:
    """补全/规范化单个步骤；缺 call/ok 视为损坏。"""
    missing = _REQUIRED_STEP_KEYS - set(step)
    if missing:
        raise ValueError(f"步骤 {index} 缺少必填键: {sorted(missing)}")
    return {
        "index": index,
        "call": step.get("call", ""),
        "input": step.get("input"),
        "output": step.get("output"),
        "error": step.get("error"),
        "ok": bool(step.get("ok")),
        "duration_ms": step.get("duration_ms", 0),
    }


def capture_session(steps: list[dict], trace_path: str | Path) -> str:
    """把一次执行的关键步骤落盘为结构化 JSON trace。

    参数
    ----
    steps : list[dict]，每步 ``call``（调用名）与 ``ok``（是否成功）为必填，
        可选 ``input``/``output``/``error``/``duration_ms``。
    trace_path : 落盘路径（父目录不存在则创建）。

    返回
    ----
    str：实际落盘路径。
    """
    normalized = [_normalize_step(s, i) for i, s in enumerate(steps)]
    trace = {
        "session_id": f"session-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "steps": normalized,
    }
    path = Path(trace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _load_trace(trace_path: str | Path) -> dict:
    """读取并校验 trace；文件缺失/JSON 损坏/缺 steps 键 → 明确报错。"""
    path = Path(trace_path)
    if not path.exists():
        raise ValueError(f"trace 不存在: {path}")
    try:
        trace = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"trace 损坏（非法 JSON）: {e}") from e
    if not isinstance(trace, dict) or "steps" not in trace:
        raise ValueError("trace 结构非法（缺 steps 键）")
    return trace


def replay_session(trace_path: str | Path) -> list[dict]:
    """按时间序重放 trace，标注每步成功/失败与耗时。

    返回
    ----
    list[dict]：按原序的步骤，每步含 ``index``/``call``/``ok``/``duration_ms``
        /``elapsed_ms``（相对首步累计耗时）/``status``（"ok"|"fail"）。
    """
    trace = _load_trace(trace_path)
    steps = trace.get("steps", [])
    out: list[dict] = []
    elapsed = 0.0
    for s in steps:
        if not isinstance(s, dict):
            raise ValueError("trace 步骤含非 dict 条目（损坏）")
        elapsed += float(s.get("duration_ms", 0) or 0)
        out.append({
            "index": s.get("index", len(out)),
            "call": s.get("call", ""),
            "ok": bool(s.get("ok")),
            "duration_ms": s.get("duration_ms", 0),
            "elapsed_ms": round(elapsed, 3),
            "status": "ok" if s.get("ok") else "fail",
        })
    return out


def summarize_failure(trace_path: str | Path) -> dict:
    """定位首个失败步 + 前 3 步上下文，产出失败摘要。

    返回
    ----
    dict：``{"failed_index", "failed_call", "error", "context_before",
    "summary"}``；无失败步时 ``failed_index`` 为 -1 且 summary 说明全部成功。
    空 trace（无步骤）→ 抛 ValueError（无法定位失败）。
    """
    trace = _load_trace(trace_path)
    steps = trace.get("steps", [])
    if not steps:
        raise ValueError("trace 无步骤（空 trace），无法定位失败")
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            raise ValueError("trace 步骤含非 dict 条目（损坏）")
        if not s.get("ok"):
            context = steps[max(0, i - 3):i]
            summary = (
                f"首个失败步：第 {i + 1} 步（{s.get('call', '')}），"
                f"错误：{s.get('error') or '未记录错误'}；"
                f"上下文前 {len(context)} 步："
                + " → ".join(c.get("call", "") or "?" for c in context)
            )
            return {
                "failed_index": i,
                "failed_call": s.get("call", ""),
                "error": s.get("error"),
                "context_before": [c.get("call", "") for c in context],
                "summary": summary,
            }
    return {
        "failed_index": -1,
        "failed_call": "",
        "error": None,
        "context_before": [],
        "summary": "全部步骤成功，无失败步",
    }
