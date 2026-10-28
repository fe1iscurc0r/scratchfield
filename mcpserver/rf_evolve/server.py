"""`mcpserver.rf_evolve` 的 MCP 入口（工单246）。

对外暴露的是**演化框架**：列编辑面 / 跑约束门 / 跑演化 / 出白盒产物。
契约形态与 `mcpserver/rf_workflow/server.py::RfWorkflowBridge`、
`mcpserver/kicad_mcp/server.py::KicadBridge` 一致：``handle_handoff(task) -> JSON 字符串``。

⚠️ 本模块**不实现滤波算法**，也不复制 `rf_brain` 的任何实现 —— 它只做四件事：
受限编辑面提案、约束门、执行打分编排、白盒产物生成。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any

from . import codegen
from .candidate import Candidate
from .constraints import check_params, gate
from .editspace import spaces
from .evolve import EvolveConfig, evolve, get_space
from .evolve import baseline as run_baseline
from .proposers import make_proposer
from .scorer import DEFAULT_SCENARIOS

logger = logging.getLogger(__name__)


class RfEvolveBridge:
    """RF/信号处理算法演化框架的 MCP 入口。"""

    # ---- 工具一：列编辑面 ----

    def list_spaces(self) -> dict[str, Any]:
        """列出已登记的**受限编辑面**（哪些参数可演化、哪些组件被冻结）。"""
        out = []
        for name, sp in spaces().items():
            out.append({
                "space": name, "task": sp.task, "target": sp.target,
                "editable_params": sp.names(), "frozen_count": len(sp.frozen),
            })
        return {"ok": True, "tool": "list_spaces", "data": {"count": len(out), "spaces": out}}

    # ---- 工具二：编辑面详情 ----

    def describe_space(self, space: str = "rfi_mitigation") -> dict[str, Any]:
        """编辑面详情：每个参数为什么可改、影响算法的哪一环，以及**冻结组件清单**。"""
        return {"ok": True, "tool": "describe_space", "data": get_space(space).describe()}

    # ---- 工具三：基线读数 ----

    def baseline(self) -> dict[str, Any]:
        """仓库默认参数在各场景上的执行读数（演化必须相对它说明收益）。"""
        return {"ok": True, "tool": "baseline",
                "data": {"scenarios": [s.name for s in DEFAULT_SCENARIOS],
                         "per_scenario": run_baseline()}}

    # ---- 工具四：约束门探针 ----

    def gate_probe(self, params: dict) -> dict[str, Any]:
        """单独跑约束门：某组参数会被哪一条拦、卡在哪一段、省下多少算力。

        诊断用 —— 不用跑完整演化就能看出「这组参数为什么进不了打分」。
        """
        sc = DEFAULT_SCENARIOS[0]
        reference, dirty = sc.build()
        res = gate(params, dirty, sc.sample_rate_hz, signal_band_hz=sc.signal_band_hz)
        return {"ok": True, "tool": "gate_probe",
                "data": {"params": dict(params), "gate": res.as_dict()}}

    # ---- 工具五：跑演化 ----

    def evolve_run(self, generations: int = 4, batch: int = 6, proposal: str = "rules",
                   seed: int = 20261016, max_notches: int = 12,
                   max_notch_band_fraction: float = 0.5,
                   time_budget_s: float = 180.0) -> dict[str, Any]:
        """跑一次演化：提案 → 约束门 → 执行打分 → 选择，返回**全轨迹**与统计。

        默认 `proposal="rules"`（**确定性、可离线复现**）；`"llm"` 是可选旁路 ——
        不可用时**不静默降级**，会在 `notes` 与 `proposal_mode` 里明说。
        """
        cfg = EvolveConfig(generations=generations, batch=batch, proposal=proposal, seed=seed,
                           max_notches=max_notches,
                           max_notch_band_fraction=max_notch_band_fraction,
                           time_budget_s=time_budget_s)
        return {"ok": True, "tool": "evolve_run", "data": evolve(cfg).as_dict()}

    # ---- 工具六：出白盒产物 ----

    def render_whitebox(self, generations: int = 4, batch: int = 6, seed: int = 20261016,
                        output_path: str = "") -> dict[str, Any]:
        """演化一次并生成**自包含白盒算法源码**。

        默认**只返回源码不落盘**；给 `output_path` 才写入（显式写盘，沿用本仓纪律）。
        产物只依赖 numpy —— 推理期不需要 agent / 神经网络 / 本仓模块。
        """
        res = evolve(EvolveConfig(generations=generations, batch=batch, seed=seed))
        src = codegen.render_from_result(res)
        data: dict[str, Any] = {
            "params": res.best["params"], "score": res.best["score"],
            "source_chars": len(src), "source": src, "wrote": "",
        }
        if output_path:                       # 显式给路径才写盘（默认只回传源码）
            data["wrote"] = str(codegen.write(output_path, src))
        return {"ok": True, "tool": "render_whitebox", "data": data}

    # ---- 工具七：单候选评估（打分，不演化）----

    def score_params(self, params: dict) -> dict[str, Any]:
        """给**一组**参数做约束门 + 执行打分（不提案、不迭代）。"""
        from .scorer import score as run_score

        sp = get_space("rfi_mitigation")
        canonical = sp.canonical(params)
        sc = DEFAULT_SCENARIOS[0]
        reference, dirty = sc.build()
        g = gate(canonical, dirty, sc.sample_rate_hz, signal_band_hz=sc.signal_band_hz)
        if not g.passed:
            return {"ok": True, "tool": "score_params",
                    "data": {"params": canonical, "rejected": True, "gate": g.as_dict()}}
        sr = run_score(canonical)
        return {"ok": True, "tool": "score_params",
                "data": {"params": canonical, "rejected": False, "score": sr.as_dict()}}

    # ---- 工具八：自述 ----

    def doctor(self) -> dict[str, Any]:
        """能力与**边界**自述。"""
        ok_llm = make_proposer(get_space("rfi_mitigation"), "llm").available()
        return {
            "ok": True, "tool": "doctor", "module": "mcpserver.rf_evolve",
            "can": [
                "受限编辑面上的候选提案（默认确定性 rules，可离线复现）",
                "物理/工程约束门（A 段参数级 O(1) / B 段检测级 1 次 FFT，**不跑陷波**）",
                "执行打分（真跑 rf_brain 既有实现，读数 = 对干净参考的 S/N 提升 dB）",
                "生成**自包含白盒算法**（只依赖 numpy，推理期不需要 agent/NN）",
            ],
            "cannot": [
                "自己不实现任何滤波算法（被演化算法在 rf_brain，**冻结**）",
                "不做 Gerber/硬件在环/真实射频发射（纯离线数值实验）",
                "LLM 提案**不是必由之路**：无 key 时按设计走 rules 路径（不静默降级）",
            ],
            "llm_proposal": {"available": ok_llm[0], "reason": ok_llm[1]},
            "notes": [
                "与 rf_workflow(242) 的边界：242 是「规格→仿真脚本」的**单次生成**；"
                "本模块是「受限编辑面上的**多候选演化搜索**」，用执行打分选优，输出白盒算法。",
                "与 rf_brain 的边界：rf_brain 提供**被演化的算法**，本模块提供**搜索**。",
            ],
        }

    # ---- 白名单 ----

    _TOOLS: dict[str, str] = {
        "list_spaces": "list_spaces",
        "describe_space": "describe_space",
        "baseline": "baseline",
        "gate_probe": "gate_probe",
        "evolve_run": "evolve_run",
        "render_whitebox": "render_whitebox",
        "score_params": "score_params",
        "doctor": "doctor",
        # ⚠️ list_tools 必须在此表内（由 test_manifest_commands_match_dispatch_table 盯着）
        "list_tools": "list_tools",
    }

    def list_tools(self) -> dict[str, Any]:
        """自述白名单。"""
        return {"ok": True, "tool": "list_tools", "count": len(self._TOOLS),
                "tools": sorted(self._TOOLS),
                "framework_note": ("本模块是**框架**：被演化的算法在 rf_brain（冻结）；"
                                   "框架只做提案/约束/打分/出产物。")}

    # ---- handoff ----

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        """MCP 契约入口：``task -> JSON 字符串``（形态对齐 RfWorkflowBridge / KicadBridge）。"""
        tool = str((task or {}).get("tool_name") or "")
        fn_name = self._TOOLS.get(tool)
        if fn_name is None:
            return json.dumps(
                {"status": "error",
                 "message": f"未知工具 {tool}，可用: {', '.join(sorted(self._TOOLS))}",
                 "data": {}}, ensure_ascii=False)
        if isinstance(task.get("params"), dict):
            arguments = dict(task["params"])
        else:
            arguments = {k: v for k, v in task.items()
                         if not k.startswith("_")
                         and k not in ("tool_name", "agentType", "service_name")}
        try:
            data = await asyncio.to_thread(lambda: getattr(self, fn_name)(**arguments))
        except TypeError as exc:
            return json.dumps({"status": "error", "message": f"参数错误: {exc}", "data": {}},
                              ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[rf_evolve] %s 执行失败: %s", tool, exc)
            return json.dumps({"status": "error", "message": f"{type(exc).__name__}: {exc}",
                               "data": {}}, ensure_ascii=False)
        return json.dumps({"status": "success", "data": data}, ensure_ascii=False)


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    """命令行入口。"""
    ap = argparse.ArgumentParser(prog="rf_evolve", description="RF 算法演化框架（工单246）")
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("list-spaces", help="列编辑面")
    p = sub.add_parser("describe-space", help="编辑面详情")
    p.add_argument("--space", default="rfi_mitigation")
    sub.add_parser("baseline", help="基线读数")
    p = sub.add_parser("gate-probe", help="约束门探针")
    p.add_argument("params", help="JSON：一组参数")
    p = sub.add_parser("evolve", help="跑演化")
    p.add_argument("--generations", type=int, default=4)
    p.add_argument("--batch", type=int, default=6)
    p.add_argument("--proposal", default="rules", choices=("rules", "llm"))
    p.add_argument("--seed", type=int, default=20261016)
    p = sub.add_parser("score", help="给一组参数打分")
    p.add_argument("params", help="JSON：一组参数")
    p = sub.add_parser("whitebox", help="出白盒产物")
    p.add_argument("--generations", type=int, default=4)
    p.add_argument("--out", default="", help="落盘路径（缺省只打印源码）")
    sub.add_parser("doctor", help="能力/边界自述")
    return ap


def main(argv: list[str] | None = None) -> int:
    """跑一个 CLI 子命令并打印 JSON。"""
    args = build_parser().parse_args(argv)
    br = RfEvolveBridge()
    c = args.command
    if c == "describe-space":
        out = br.describe_space(args.space)
    elif c == "baseline":
        out = br.baseline()
    elif c == "gate-probe":
        out = br.gate_probe(json.loads(args.params))
    elif c == "evolve":
        out = br.evolve_run(generations=args.generations, batch=args.batch,
                            proposal=args.proposal, seed=args.seed)
    elif c == "score":
        out = br.score_params(json.loads(args.params))
    elif c == "whitebox":
        out = br.render_whitebox(generations=args.generations, output_path=args.out)
        if not args.out and out.get("data", {}).get("source"):
            print(out["data"]["source"])
            return 0
    elif c == "doctor":
        out = br.doctor()
    else:
        out = br.list_spaces()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["Candidate", "RfEvolveBridge", "build_parser", "check_params", "main"]
