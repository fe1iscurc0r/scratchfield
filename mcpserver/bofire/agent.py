"""bofire MCP 封装 · 多目标贝叶斯优化 + 实验设计 (BSD-3-Clause)

把 bofire（Bayesian Optimization Framework for Experimental Design）封装为
陆墨 MCP 工具体系的一个 agent。核心价值：混合变量空间（连续/离散/分类）+
多目标 + 任意约束，推荐"下一轮实验点"，与 E-01 分子指纹构成
「特征 → 域变量 → 多目标实验设计 → 推荐新合成条件」闭环。

3 个命令（贝叶斯优化闭环）：
  bofire_define_domain  声明实验域（变量 + 目标 + 约束）
  bofire_ask_candidates 推荐下一轮实验点（n 个候选）
  bofire_tell_results   回喂真实实验结果，更新优化器

契约（docs/academic/MODEL_INTERFACE.md）：
  返回 {ok: true, ...data, source: "bofire"}；参数非法抛 ValueError；
  bofire 未安装（torch/botorch 一并缺失）时降级返回结构说明 + pip install 提示，
  不抛错——保证"未装依赖也全绿"的验收硬约束。

边界：独立目录 mcpserver/bofire/，仅通过 MCP 调度接入，不碰主流程。
"""

from __future__ import annotations

import json
import logging
from typing import Any

try:
    from system.config import logger
except ImportError:  # 独立 pytest 时降级到标准 logging
    logger = logging.getLogger("bofire")

# 降级说明：bofire 未装时命令仍返回 ok:true 的结构化结果，附带此提示
_DEGRADED_NOTE = (
    "bofire 未安装，已降级返回结构说明/占位候选；"
    "pip install bofire 后可真算（BSD-3-Clause，Python ≥3.11，PyTorch 生态）"
)

_VAR_TYPES = {"continuous", "discrete", "categorical"}
_OBJ_TYPES = {"maximize", "minimize"}


def _load_bofire() -> Any | None:
    """惰性加载 bofire；缺失返回 None（降级，不抛错）。"""
    try:
        import bofire  # noqa: F401

        return bofire
    except ImportError:
        return None


def _require_variable(v: Any) -> dict:
    """校验并规范化单个变量定义；非法抛 ValueError。"""
    if not isinstance(v, dict) or not v.get("name"):
        raise ValueError("变量定义应为含 name 的 dict（name/type/bounds 或 values）")
    name = str(v["name"])
    vtype = str(v.get("type", ""))
    if vtype not in _VAR_TYPES:
        raise ValueError(f"变量 {name!r} 的 type 应为 {sorted(_VAR_TYPES)} 之一（当前 {vtype!r}）")
    if vtype == "categorical":
        values = v.get("values")
        if not isinstance(values, list) or not values:
            raise ValueError(f"分类变量 {name!r} 需提供非空 values 列表")
        return {"name": name, "type": vtype, "values": [str(x) for x in values]}
    bounds = v.get("bounds")
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        raise ValueError(f"变量 {name!r} 需提供 [下限, 上限] 二元 bounds")
    lo, hi = float(bounds[0]), float(bounds[1])
    if lo >= hi:
        raise ValueError(f"变量 {name!r} 的 bounds 需满足 下限 < 上限（当前 [{lo}, {hi}]）")
    return {"name": name, "type": vtype, "bounds": [lo, hi]}


def _normalize_variables(raw: Any) -> list[dict]:
    """校验并规范化变量列表；非法抛 ValueError。"""
    if not isinstance(raw, list) or not raw:
        raise ValueError("variables 应为非空列表（每个含 name/type/bounds 或 values）")
    return [_require_variable(v) for v in raw]


def _normalize_objectives(raw: Any) -> list[dict]:
    """校验并规范化目标列表；非法抛 ValueError。"""
    if not isinstance(raw, list) or not raw:
        raise ValueError("objectives 应为非空列表（每个含 name/type=maximize|minimize）")
    out = []
    for o in raw:
        if not isinstance(o, dict) or not o.get("name"):
            raise ValueError("目标应为含 name 的 dict")
        otype = str(o.get("type", ""))
        if otype not in _OBJ_TYPES:
            raise ValueError(f"目标 {o.get('name')!r} 的 type 应为 {sorted(_OBJ_TYPES)} 之一（当前 {otype!r}）")
        out.append({"name": str(o["name"]), "type": otype})
    return out


def _normalize_domain(raw: Any) -> dict:
    """从调用方传入的 domain dict（或内联 variables/objectives）构造规范化 domain。"""
    if isinstance(raw, dict) and "variables" in raw:
        variables = _normalize_variables(raw.get("variables"))
        objectives = _normalize_objectives(raw.get("objectives"))
        constraints = raw.get("constraints")
        constraints = constraints if isinstance(constraints, list) else []
    else:
        raise ValueError("domain 应为含 variables/objectives 的 dict（可先用 bofire_define_domain 生成）")
    return {"variables": variables, "objectives": objectives, "constraints": constraints}


def _serialize_candidates(cands: Any) -> list[dict]:
    """把 bofire ask 返回（DataFrame / 对象列表）序列化为 JSON 安全 dict 列表。"""
    if hasattr(cands, "to_dict"):  # pandas DataFrame
        return cands.to_dict("records")
    out = []
    for c in cands:
        if hasattr(c, "model_dump"):  # Pydantic 对象
            out.append(c.model_dump())
        elif hasattr(c, "items"):  # dict-like
            out.append({str(k): v for k, v in c.items()})
        else:
            out.append({"value": str(c)})
    return out


def _degraded_candidates(variables: list[dict], n: int) -> list[dict]:
    """降级路径：在变量 bounds/values 内生成 n 个确定性占位候选。"""
    rows = []
    for i in range(n):
        row: dict = {}
        for v in variables:
            if v["type"] == "categorical":
                row[v["name"]] = v["values"][0]
            else:
                lo, hi = v["bounds"]
                row[v["name"]] = round(lo + (hi - lo) * ((i + 1) / (n + 1)), 4)
        rows.append(row)
    return rows


class BofireAgent:
    """bofire 多目标贝叶斯优化 agent（实验设计闭环入口）。"""

    def __init__(self):
        self.name = "bofire"
        self.display_name = "bofire 实验设计"
        self.version = "1.0.0"
        self.description = (
            "多目标贝叶斯优化 + 实验设计：声明实验域（混合变量+目标+约束）→ 推荐下一轮实验点 → 回喂结果更新优化器"
        )
        self.tools = {
            "bofire_define_domain": self._bofire_define_domain,
            "bofire_ask_candidates": self._bofire_ask_candidates,
            "bofire_tell_results": self._bofire_tell_results,
        }
        logger.info(f"[MCP] {self.display_name} 初始化完成，共 {len(self.tools)} 个工具")

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        """类方法入口（总线契约）：委托 invoke 分发。

        注册表运行时按 instance.handle_handoff 调用（Format A: {module, class}），
        task 格式 {"tool": ..., "params": {...}}，返回 JSON 字符串。
        """
        command = str(task.get("tool") or task.get("command") or "").strip()
        params = task.get("params")
        if not isinstance(params, dict):
            params = {}
        try:
            result = self.invoke(command, params)
        except ValueError as e:  # invoke 对未知命令/坏参数 fail-fast，总线边界落 JSON 不崩
            result = {"status": "error", "error": str(e)}
        return json.dumps(result, ensure_ascii=False, default=str)

    def invoke(self, command: str, params: dict | None = None) -> dict:
        """MCP 分发入口：按命令名调用对应工具。"""
        params = params or {}
        fn = self.tools.get(command)
        if fn is None:
            raise ValueError(f"未知命令 {command!r}，可用命令: {sorted(self.tools)}")
        return fn(params)

    # ---- 1. 声明实验域 ----

    def _bofire_define_domain(self, params: dict) -> dict:
        variables = _normalize_variables(params.get("variables"))
        objectives = _normalize_objectives(params.get("objectives"))
        constraints = params.get("constraints")
        constraints = constraints if isinstance(constraints, list) else []
        domain = {"variables": variables, "objectives": objectives, "constraints": constraints}
        bofire = _load_bofire()
        degraded = bofire is None
        return {
            "ok": True,
            "domain": domain,
            "n_variables": len(variables),
            "n_objectives": len(objectives),
            "n_constraints": len(constraints),
            "degraded": degraded,
            "note": _DEGRADED_NOTE if degraded else "",
            "source": "bofire",
        }

    # ---- 2. 推荐下一轮实验点 ----

    def _bofire_ask_candidates(self, params: dict) -> dict:
        domain = _normalize_domain(params.get("domain"))
        n_raw = params.get("n_candidates")
        n = int(n_raw) if n_raw is not None else 5
        if n < 1 or n > 100:
            raise ValueError(f"n_candidates 应在 1-100 之间（当前 {n}）")
        bofire = _load_bofire()
        if bofire is None:
            candidates = _degraded_candidates(domain["variables"], n)
            return {
                "ok": True,
                "candidates": candidates,
                "n_candidates": len(candidates),
                "degraded": True,
                "note": _DEGRADED_NOTE,
                "source": "bofire",
            }
        strategy_api = bofire.data_models.strategies.api
        strategy = strategy_api.Strategy.make(domain)
        candidates = _serialize_candidates(strategy.ask(n))
        return {
            "ok": True,
            "candidates": candidates,
            "n_candidates": len(candidates),
            "degraded": False,
            "note": "",
            "source": "bofire",
        }

    # ---- 3. 回喂真实实验结果 ----

    def _bofire_tell_results(self, params: dict) -> dict:
        experiments = params.get("experiments")
        if not isinstance(experiments, list) or not experiments:
            raise ValueError("experiments 应为非空列表（每条含 inputs 与 outputs 两个 dict）")
        for i, exp in enumerate(experiments):
            if (
                not isinstance(exp, dict)
                or not isinstance(exp.get("inputs"), dict)
                or not isinstance(exp.get("outputs"), dict)
            ):
                raise ValueError(f"第 {i + 1} 条实验需含 inputs 与 outputs 两个 dict")
        domain_raw = params.get("domain")
        if domain_raw is not None:
            domain = _normalize_domain(domain_raw)
            var_names = {v["name"] for v in domain["variables"]}
            obj_names = {o["name"] for o in domain["objectives"]}
            for i, exp in enumerate(experiments):
                unknown_in = set(exp["inputs"]) - var_names
                unknown_out = set(exp["outputs"]) - obj_names
                if unknown_in:
                    raise ValueError(f"第 {i + 1} 条实验 inputs 含未知变量: {sorted(unknown_in)}")
                if unknown_out:
                    raise ValueError(f"第 {i + 1} 条实验 outputs 含未知目标: {sorted(unknown_out)}")
        bofire = _load_bofire()
        degraded = bofire is None
        return {
            "ok": True,
            "n_experiments": len(experiments),
            "accepted": True,
            "degraded": degraded,
            "note": _DEGRADED_NOTE if degraded else "",
            "source": "bofire",
        }
