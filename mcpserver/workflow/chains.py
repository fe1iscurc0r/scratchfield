"""chains.py — 声明式工具链定义与执行器（卷189-C1）。

目标：把「搜论文 → digest → 入库 → 授粉」这类**常用工具序列**从"每次人工点名"
变成可复用、可重试、可观测的声明式链。

链定义（YAML 或 dict 皆可）：
    name: paper_pipeline
    steps:
      - tool: paper_miner.extract_paper        # service.tool（也可只写 service）
        in: { paper_id: "{{query}}" }
        out: hits
      - tool: paper_miner.query_experiments
        in: { ids: "{{hits[].id}}" }
        out: digests
    retry: { max: 2, backoff: 3 }

数据插值（步骤间传参）支持：
    {{key}}              → 上下文值
    {{key.field}}        → 取字段
    {{key[0].field}}     → 取下标字段
    {{key[].field}}      → 收集列表（jq 风格）

执行语义：
- 顺序执行；每步结果按 `out` 存入上下文；
- 失败短路：某步失败（重试耗尽）后**停止后续步骤，但返回已成功步骤的部分结果**；
- 重试：按 retry.max + retry.backoff（指数退避，backoff 秒起点）；
- 不做定时调度（工单红线：已有 cron 体系，不重复造）。

依赖：仅标准库（YAML 可选，缺失时退回 dict 输入）。调用函数由外部注入
（call_fn），便于单测用 mock 工具。
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# 插值占位：{{ expr }}
_TPL_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
_INDEX_RE = re.compile(r"^([A-Za-z0-9_]+)\[(\d*)\]")


# ---------------------------------------------------------------- 定义


@dataclass
class ChainStep:
    """单个步骤：调哪个工具、传什么参、结果存哪。"""

    tool: str                     # "service.tool" 或 "service"
    in_: dict[str, Any] = field(default_factory=dict)
    out: str = ""                 # 结果存入上下文的键（空 = 不保存）
    optional: bool = False        # 可选步骤：失败不短路

    @property
    def service(self) -> str:
        return self.tool.split(".", 1)[0]

    @property
    def tool_name(self) -> str:
        parts = self.tool.split(".", 1)
        return parts[1] if len(parts) > 1 else ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChainStep:
        return cls(
            tool=str(d.get("tool") or d.get("service") or ""),
            in_=dict(d.get("in") or d.get("params") or {}),
            out=str(d.get("out") or ""),
            optional=bool(d.get("optional") or False),
        )


@dataclass
class Chain:
    """一条链的定义。"""

    name: str
    steps: list[ChainStep]
    retry: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    @property
    def max_retry(self) -> int:
        return int(self.retry.get("max", 0) or 0)

    @property
    def backoff(self) -> float:
        return float(self.retry.get("backoff", 0) or 0)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Chain:
        return cls(
            name=str(d.get("name") or ""),
            steps=[ChainStep.from_dict(s) for s in (d.get("steps") or [])],
            retry=dict(d.get("retry") or {}),
            description=str(d.get("description") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "retry": self.retry,
            "steps": [
                {"tool": s.tool, "in": s.in_, "out": s.out, "optional": s.optional}
                for s in self.steps
            ],
        }


def load_chain(source: dict[str, Any] | str) -> Chain:
    """从 dict 或 YAML 文本加载链定义。"""
    if isinstance(source, str):
        try:
            import yaml  # 可选依赖
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("加载 YAML 链需要 pyyaml；或直接传 dict") from e
        data = yaml.safe_load(source)
    else:
        data = source
    if not isinstance(data, dict):
        raise ValueError("链定义必须是映射（name/steps/retry）")
    return Chain.from_dict(data)


# ---------------------------------------------------------------- 插值


def _get_path(ctx: dict[str, Any], expr: str) -> Any:
    """解析 `key[].field` / `key[0].field` / `key.field` / `key`。"""
    expr = expr.strip()
    if not expr:
        return None
    # 拆分下标段：a[].x / a[0].x / a.x
    m = _INDEX_RE.match(expr)
    collect = False
    index: int | None = None
    if m:
        key, idx = m.group(1), m.group(2)
        collect = idx == ""
        index = None if collect else int(idx)
        rest = expr[m.end():].lstrip(".")
    else:
        key, _, rest = expr.partition(".")
        index = None
        collect = False
    if key not in ctx:
        return None
    val = ctx[key]
    if collect:
        seq = val if isinstance(val, list) else [val]
        if not rest:
            return seq
        return [_dig(_item, rest) for _item in seq]
    if index is not None:
        seq = val if isinstance(val, list) else [val]
        if index >= len(seq):
            return None
        val = seq[index]
    return _dig(val, rest) if rest else val


def _dig(val: Any, path: str) -> Any:
    """按点号逐层取值（列表则逐项取）。"""
    if not path:
        return val
    head, _, tail = path.partition(".")
    if isinstance(val, dict):
        return _dig(val.get(head), tail) if tail else val.get(head)
    if isinstance(val, list):
        return [_dig(v, path) for v in val]
    return None


def resolve(value: Any, ctx: dict[str, Any]) -> Any:
    """递归解析入参里的 {{...}} 占位。整串是单个占位时保留原始类型。"""
    if isinstance(value, str):
        whole = _TPL_RE.fullmatch(value)
        if whole:
            return _get_path(ctx, whole.group(1))
        return _TPL_RE.sub(lambda m: _stringify(_get_path(ctx, m.group(1))), value)
    if isinstance(value, dict):
        return {k: resolve(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, ctx) for v in value]
    return value


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


# ---------------------------------------------------------------- 执行


@dataclass
class StepResult:
    tool: str
    ok: bool
    out_key: str
    result: Any = None
    error: str = ""
    attempts: int = 1
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool, "ok": self.ok, "out": self.out_key,
            "error": self.error, "attempts": self.attempts,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class ChainRun:
    run_id: str
    chain: str
    status: str                       # ok / failed / partial
    steps: list[StepResult] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    failed_step: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0

    def to_dict(self, *, with_context: bool = True) -> dict[str, Any]:
        d = {
            "run_id": self.run_id, "chain": self.chain, "status": self.status,
            "failed_step": self.failed_step,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "steps": [s.to_dict() for s in self.steps],
        }
        if with_context:
            d["context"] = self.context
        return d


# call_fn(service, tool_call) → str | dict
CallFn = Callable[[str, dict[str, Any]], Awaitable[Any]]


class ChainExecutor:
    """链执行器：顺序 + 插值 + 重试 + 失败短路（保部分结果）。"""

    def __init__(self, call_fn: CallFn, *,
                 sleep_fn: Callable[[float], Awaitable[None]] | None = None):
        self._call = call_fn
        self._sleep = sleep_fn or asyncio.sleep
        self._runs: dict[str, ChainRun] = {}

    def get_run(self, run_id: str) -> ChainRun | None:
        return self._runs.get(run_id)

    async def run(self, chain: Chain, inputs: dict[str, Any] | None = None) -> ChainRun:
        ctx: dict[str, Any] = dict(inputs or {})
        run = ChainRun(run_id=uuid.uuid4().hex[:12], chain=chain.name,
                       status="ok", context=ctx, started_at=time.time())
        self._runs[run.run_id] = run

        for step in chain.steps:
            params = resolve(step.in_, ctx)
            params = params if isinstance(params, dict) else {"value": params}
            tool_call = {"service_name": step.service, "tool_name": step.tool_name, **params}

            sr = await self._run_step(step, tool_call, chain)
            run.steps.append(sr)

            if sr.ok:
                if step.out:
                    ctx[step.out] = _coerce(sr.result)
                continue

            # 失败：可选步骤放行，否则短路（已成功步骤的 ctx 保留）
            if step.optional:
                run.status = "partial"
                continue
            run.status = "partial" if any(s.ok for s in run.steps) else "failed"
            run.failed_step = step.tool
            break

        run.context = ctx
        run.finished_at = time.time()
        return run

    async def _run_step(self, step: ChainStep, tool_call: dict[str, Any],
                        chain: Chain) -> StepResult:
        attempts = 0
        last_err = ""
        max_attempts = max(1, chain.max_retry + 1)
        t0 = time.time()
        while attempts < max_attempts:
            attempts += 1
            try:
                raw = await self._call(step.service, tool_call)
                parsed, err = _interpret(raw)
                if err is None:
                    return StepResult(step.tool, True, step.out, parsed,
                                      attempts=attempts,
                                      duration_ms=(time.time() - t0) * 1000)
                last_err = err
            except Exception as e:      # 调用异常 → 视为失败，可重试
                last_err = f"{type(e).__name__}: {e}"
            if attempts < max_attempts and chain.backoff > 0:
                await self._sleep(chain.backoff ** attempts)
        return StepResult(step.tool, False, step.out, error=last_err,
                          attempts=attempts, duration_ms=(time.time() - t0) * 1000)


def _interpret(raw: Any) -> tuple[Any, str | None]:
    """把工具返回解释为 (结果, 错误)。JSON 里 status=error 视为失败。"""
    data = raw
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                data = json.loads(s)
            except json.JSONDecodeError:
                return raw, None      # 非 JSON 文本，按成功处理
        else:
            return raw, None
    if isinstance(data, dict) and str(data.get("status", "")).lower() == "error":
        return data, str(data.get("message") or data.get("error_type") or "工具返回 error")
    return data, None


def _coerce(v: Any) -> Any:
    return v


# ---------------------------------------------------------------- 种子链

SEED_CHAINS: dict[str, dict[str, Any]] = {
    "paper_pipeline": {
        "name": "paper_pipeline",
        "description": "搜论文 → 提取实验 → 入库（授粉前置）",
        "steps": [
            {"tool": "paper_miner.query_experiments",
             "in": {"query": "{{query}}"}, "out": "hits"},
            {"tool": "paper_miner.extract_paper",
             "in": {"ids": "{{hits[].id}}"}, "out": "digests", "optional": True},
        ],
        "retry": {"max": 2, "backoff": 3},
    },
    "spectrum_scan": {
        "name": "spectrum_scan",
        "description": "rf_brain 扫描 → 事件判定（对接卷187 哨兵事件）",
        "steps": [
            {"tool": "rf_brain.analyze_signal",
             "in": {"source": "{{source}}"}, "out": "scan"},
            {"tool": "rf_brain.sentinel_ingest",
             "in": {"payload": "{{scan}}"}, "out": "ingested", "optional": True},
        ],
        "retry": {"max": 1, "backoff": 2},
    },
    "daily_report": {
        "name": "daily_report",
        "description": "拼装日报各段 → 单端点出稿",
        "steps": [
            {"tool": "sentinel_intel.intel_query",
             "in": {"since": "{{since}}"}, "out": "intel"},
            {"tool": "paper_miner.query_experiments",
             "in": {"query": "{{topic}}"}, "out": "papers", "optional": True},
        ],
        "retry": {"max": 2, "backoff": 3},
    },
}


def seed_chains() -> list[Chain]:
    """三条种子链（从现有 cron/人工流程提取）。"""
    return [Chain.from_dict(d) for d in SEED_CHAINS.values()]


def get_chain(name: str) -> Chain | None:
    for c in seed_chains():
        if c.name == name:
            return c
    return None


# ---------------------------------------------------------------- 推荐（C2）

# 链推荐：基于调用画像的共现统计（同一 caller 会话内 A→B 的频次）。
# 不做自动执行，只给建议，人工确认后固化为链（工单 C2）。


def suggest_chains(stats: dict[str, Any], *, top_n: int = 5) -> list[dict[str, Any]]:
    """从画像聚合结果给出「可固化为链」的候选（当前按调用量 + 失败率排序）。

    stats 形如 {tool: {calls, p95_ms, error_rate, ...}}（CallRecorder.stats 输出）。
    说明：真正的共现对需要会话序列（tool_calls 表带 caller/trace），此处先用
    「高频且低失败率」作为种子工具建议；共现对留待画像积累后再启（工单允许轻量）。
    """
    ranked = []
    for tool, m in (stats or {}).items():
        calls = int(m.get("calls") or 0)
        if calls <= 0:
            continue
        ranked.append({
            "tool": tool,
            "calls": calls,
            "error_rate": m.get("error_rate", 0.0),
            "p95_ms": m.get("p95_ms", 0.0),
            "score": calls * (1 - float(m.get("error_rate") or 0)),
        })
    ranked.sort(key=lambda r: (-r["score"], r["tool"]))
    return ranked[:top_n]


def cooccurrence_pairs(rows: list[tuple[str, str]], *, top_n: int = 5) -> list[dict[str, Any]]:
    """从 (caller, tool) 序列计算 A→B 共现对（供链推荐；需按 caller 分组后传入）。"""
    from collections import Counter
    pairs: Counter = Counter()
    by_caller: dict[str, list[str]] = {}
    for caller, tool in rows:
        by_caller.setdefault(caller, []).append(tool)
    for tools in by_caller.values():
        for a, b in zip(tools, tools[1:]):
            if a != b:
                pairs[(a, b)] += 1
    out = [{"from": a, "to": b, "count": n} for (a, b), n in pairs.most_common(top_n)]
    return out
