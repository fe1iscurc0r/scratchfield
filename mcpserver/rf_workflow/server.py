"""rf_workflow MCP 入口（工单242 任务一）—— 三接口工作流编排。

接口（工单242 §2 指定的三条 + 两条只读）：::

    start_workflow(goal, rf_lib)      → workflow_id
    step(workflow_id, prompt)         → script + log（+ 指标）
    explain(workflow_id, output_id)   → explanation + next_step_suggestion
    workflow_status(workflow_id)      → 工作流状态（只读）
    list_workflows(limit)             → 最近的沙箱工作流（只读）

接线形态对齐同族先例（``mcpserver/antenna_sim/tools.py`` 的 ``AntennaSimBridge``）：类方法
``handle_handoff(task) -> str``（返回 JSON 字符串），由 ``mcpserver/mcp_registry.py`` 扫
``agent-manifest.json`` 自动登记，经 ``MCPManager.unified_call`` 路由。**不需要改任何既有文件。**

真值源是 :mod:`lora_phy`；本文件只做编排与错误语义（不重算任何物理量）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from . import explainer, lora_phy, prompt_to_script, sim_runner

logger = logging.getLogger(__name__)

STATE_FILENAME = "workflow.json"
EXPLANATION_FILENAME = "explanation.md"


def _combined_goal(goal: str, prompt: str = "") -> str:
    """把工作流目标与本轮精化 prompt 拼成一次生成的"目标文本"（两者都进 prompt.md）。"""
    base = str(goal or "").strip()
    extra = str(prompt or "").strip()
    if not extra:
        return base
    return f"{base}\n\n【本轮精化】{extra}"


class RfWorkflowBridge:
    """Prompt→RF 工程工作流的 MCP 入口。"""

    # ---- 工具 ----

    def start_workflow(self, goal: str, rf_lib: str = prompt_to_script.DEFAULT_RF_LIB,
                       workflow_id: str = "") -> dict[str, Any]:
        """开一条工作流：解析 goal → 建沙箱目录 → 落 prompt.md。返回 ``workflow_id``。

        ``workflow_id`` 留空则自动生成；显式给 id 时可复现同一条工作流（已存在且
        已有状态则返回 ``workflow_exists``，不静默覆盖）。
        """
        text = str(goal or "").strip()
        if not text:
            return {"ok": False, "error": "empty_goal", "hint": "goal 必须非空"}
        kind = prompt_to_script.classify(text)
        if kind is None:
            return {"ok": False, "error": "unsupported_goal", "goal": text,
                    "supported": sorted(prompt_to_script.SUPPORTED_KINDS)}
        if rf_lib not in prompt_to_script.RF_LIBS:
            return {"ok": False, "error": "invalid_rf_lib", "rf_lib": rf_lib,
                    "available": list(prompt_to_script.RF_LIBS)}

        spec = prompt_to_script.parse_goal(text)
        problems = lora_phy.validate_spec(spec)
        if problems:
            return {"ok": False, "error": "invalid_spec", "problems": problems, "spec": spec}

        resolved_id, id_error = sim_runner.safe_workflow_id(workflow_id)
        if resolved_id is None:
            return {"ok": False, "error": id_error, "workflow_id": str(workflow_id),
                    "hint": "workflow_id 只允许字母/数字/下划线/连字符（最长 64）"}
        if str(workflow_id or "").strip() and sim_runner.read_workflow_state(resolved_id):
            return {"ok": False, "error": "workflow_exists", "workflow_id": resolved_id,
                    "hint": "该 workflow_id 已有状态；换 id，或直接对它调 step"}
        directory = sim_runner.workflow_dir(resolved_id)
        prompt_path = directory / "prompt.md"
        prompt_path.write_text(prompt_to_script.render_prompt_md(text, spec, rf_lib),
                               encoding="utf-8", newline="\n")
        now = time.time()
        # 状态里**只存相对文件名**：绝对路径会跟着沙箱一起进 git（工单242 交付纪律）
        state = {
            "workflow_id": resolved_id,
            "goal": text,
            "rf_lib": rf_lib,
            "kind": kind,
            "spec": spec,
            "created_at": now,
            "updated_at": now,
            "steps": [],
            "outputs": {},
            "explanations": {},
        }
        sim_runner.write_workflow_state(resolved_id, state)
        return {"ok": True, "workflow_id": resolved_id, "kind": kind, "rf_lib": rf_lib,
                "spec": spec, "sandbox_dir": str(directory), "prompt_path": str(prompt_path),
                "artifacts": ["prompt.md"],
                "next": f"调用 step(workflow_id='{resolved_id}', prompt='') 生成并执行脚本"}

    def step(self, workflow_id: str, prompt: str = "", rf_lib: str = "",
             timeout_s: float = 0.0) -> dict[str, Any]:
        """生成脚本并执行一步：``prompt`` 非空时按它精化规格。返回 script + log + 指标。"""
        state = sim_runner.read_workflow_state(workflow_id)
        if state is None:
            return {"ok": False, "error": "workflow_not_found", "workflow_id": str(workflow_id),
                    "hint": "先用 start_workflow 建工作流"}
        directory = sim_runner.workflow_dir(workflow_id)
        index = len(state.get("steps") or []) + 1
        output_id = f"out-{index}"

        spec = dict(state.get("spec") or {})
        if str(prompt or "").strip():
            merged = prompt_to_script.parse_goal(str(prompt))
            merged_sources = dict(merged.get("spec_sources") or {})
            sources = dict(spec.get("spec_sources") or {})
            for key, origin in merged_sources.items():
                if origin == "goal":
                    spec[key] = merged[key]
                    sources[key] = "step"
            spec["spec_sources"] = sources
        effective_lib = str(rf_lib or state.get("rf_lib") or prompt_to_script.DEFAULT_RF_LIB)

        script_name = "script.py" if index == 1 else f"script_{index}.py"
        log_name = "log.txt" if index == 1 else f"log_{index}.txt"
        result_name = "result.json" if index == 1 else f"result_{index}.json"
        prompt_name = "prompt.md" if index == 1 else f"prompt_{index}.md"

        generated = prompt_to_script.generate(
            # goal 必须与原目标拼接：单看精化 prompt（"把扩频因子改成 9"）无法分类
            _combined_goal(str(state.get("goal") or ""), prompt),
            directory, rf_lib=effective_lib, spec=spec,
            script_filename=script_name, result_filename=result_name, prompt_filename=prompt_name)
        if not generated.get("ok"):
            return {"ok": False, "workflow_id": state["workflow_id"], "output_id": output_id,
                    **{k: v for k, v in generated.items() if k != "ok"}}

        outcome = sim_runner.run_script(
            generated["script_path"], workflow_id=state["workflow_id"],
            timeout_s=float(timeout_s or 0.0), log_name=log_name, result_name=result_name)

        record = {
            "output_id": output_id,
            "prompt": str(prompt or ""),
            "script": script_name,
            "log": log_name,
            "result": result_name,
            "ok": bool(outcome.get("ok")),
            "exit_code": outcome.get("exit_code"),
            "duration_s": outcome.get("duration_s"),
            "error": outcome.get("error", ""),
            "metrics": outcome.get("metrics"),
            "metrics_mismatch": outcome.get("metrics_mismatch"),
            "created_at": time.time(),
        }
        state.setdefault("steps", []).append({"output_id": output_id, "prompt": str(prompt or ""),
                                              "ok": record["ok"], "error": record["error"]})
        state.setdefault("outputs", {})[output_id] = record
        state["spec"] = generated["spec"]
        state["updated_at"] = time.time()
        sim_runner.write_workflow_state(state["workflow_id"], state)

        return {
            "ok": record["ok"],
            "workflow_id": state["workflow_id"],
            "output_id": output_id,
            "script": record["script"],
            "log": record["log"],
            "result": record["result"],
            "duration_s": record["duration_s"],
            "exit_code": record["exit_code"],
            "error": record["error"],
            "metrics": record["metrics"],
            "metrics_mismatch": record["metrics_mismatch"],
            "artifacts": ["prompt.md", script_name, log_name, result_name],
        }

    def explain(self, workflow_id: str, output_id: str = "", allow_llm: bool = True) -> dict[str, Any]:
        """解释某一步的输出并给下一步建议；落 ``explanation.md``。"""
        state = sim_runner.read_workflow_state(workflow_id)
        if state is None:
            return {"ok": False, "error": "workflow_not_found", "workflow_id": str(workflow_id)}
        outputs = state.get("outputs") or {}
        if not outputs:
            return {"ok": False, "error": "no_output", "workflow_id": state["workflow_id"],
                    "hint": "先调用 step 产出 script + log，再解释"}
        key = str(output_id or "").strip() or sorted(outputs)[-1]
        record = outputs.get(key)
        if record is None:
            return {"ok": False, "error": "output_not_found", "output_id": key,
                    "available": sorted(outputs)}
        metrics = record.get("metrics")
        if not isinstance(metrics, dict):
            return {"ok": False, "error": "no_metrics", "output_id": key,
                    "hint": "该步骤没有解析到 __RF_METRICS__ 行（脚本可能失败）"}

        spec = dict(state.get("spec") or {})
        result = explainer.explain(spec, metrics, allow_llm=bool(allow_llm))
        directory = sim_runner.workflow_dir(state["workflow_id"])
        name = EXPLANATION_FILENAME if key == "out-1" else f"explanation_{key}.md"
        path = explainer.write_explanation(state["workflow_id"], result, spec,
                                           directory=directory, filename=name)
        state.setdefault("explanations", {})[key] = {
            "mode": result["mode"], "file": name,
            "next_step_suggestion": result["next_step_suggestion"], "created_at": time.time(),
        }
        state["updated_at"] = time.time()
        sim_runner.write_workflow_state(state["workflow_id"], state)

        return {"ok": True, "workflow_id": state["workflow_id"], "output_id": key,
                "mode": result["mode"], "explanation": result["explanation"],
                "next_step_suggestion": result["next_step_suggestion"],
                "observations": result["observations"], "candidates": result["candidates"],
                "explanation_path": str(path),
                "artifacts": ["prompt.md", "script.py", "log.txt", EXPLANATION_FILENAME]}

    def workflow_status(self, workflow_id: str = "") -> dict[str, Any]:
        """查工作流状态；空 ``workflow_id`` 返回最近若干条摘要。

        状态文件里只存**相对文件名**，绝对路径在返回时按当前沙箱根解析（运行期信息，
        不落盘 ⇒ 沙箱产物可安全入库）。
        """
        if str(workflow_id or "").strip():
            state = sim_runner.read_workflow_state(workflow_id)
            if state is None:
                return {"ok": False, "error": "workflow_not_found", "workflow_id": str(workflow_id)}
            directory = sim_runner.workflow_dir(str(state.get("workflow_id") or workflow_id))
            return {"ok": True, "workflow": state, "sandbox_dir": str(directory),
                    "artifacts": sorted(p.name for p in directory.iterdir() if p.is_file())}
        return self.list_workflows()

    def list_workflows(self, limit: int = 10) -> dict[str, Any]:
        """列出沙箱里的工作流（按 ``updated_at`` 倒序）。"""
        root = sim_runner.sandbox_root()
        rows: list[dict[str, Any]] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            state = sim_runner.read_workflow_state(child.name)
            if state is None:
                continue
            rows.append({
                "workflow_id": state.get("workflow_id", child.name),
                "kind": state.get("kind"),
                "steps": len(state.get("steps") or []),
                "updated_at": state.get("updated_at"),
                "sandbox_dir": str(child),
            })
        rows.sort(key=lambda row: float(row.get("updated_at") or 0), reverse=True)
        top = rows[: max(int(limit or 10), 1)]
        return {"ok": True, "count": len(rows), "recent": top, "sandbox_root": str(root)}

    # ---- handoff ----

    _TOOLS = {
        "start_workflow": "start_workflow",
        "step": "step",
        "explain": "explain",
        "workflow_status": "workflow_status",
        "list_workflows": "list_workflows",
    }

    async def handle_handoff(self, task: dict[str, Any]) -> str:
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
                         if not k.startswith("_") and k not in ("tool_name", "agentType",
                                                                "service_name")}
        try:
            data = await asyncio.to_thread(lambda: getattr(self, fn_name)(**arguments))
        except TypeError as exc:
            return json.dumps({"status": "error", "message": f"参数错误: {exc}", "data": {}},
                              ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[rf_workflow] %s 执行失败: %s", tool, exc)
            return json.dumps({"status": "error", "message": f"{type(exc).__name__}: {exc}",
                               "data": {}}, ensure_ascii=False)
        ok = bool(data.get("ok"))
        return json.dumps({"status": "success" if ok else "error",
                           "message": "ok" if ok else str(data.get("error") or "failed"),
                           "data": data}, ensure_ascii=False, default=str)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="rf_workflow CLI（工单242 手工复现 PoC）")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="开一条工作流")
    start.add_argument("--goal", required=True)
    start.add_argument("--rf-lib", default=prompt_to_script.DEFAULT_RF_LIB)
    start.add_argument("--workflow-id", default="", help="显式指定 id（可复现同一条工作流）")

    run = sub.add_parser("run", help="一次跑完：start → step → explain")
    run.add_argument("--goal", required=True)
    run.add_argument("--rf-lib", default=prompt_to_script.DEFAULT_RF_LIB)
    run.add_argument("--workflow-id", default="", help="显式指定 id（可复现同一条工作流）")
    run.add_argument("--prompt", default="", help="第二步精化 prompt（可空）")
    run.add_argument("--no-llm", action="store_true")

    status = sub.add_parser("status", help="查工作流")
    status.add_argument("--workflow-id", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bridge = RfWorkflowBridge()
    if args.command == "start":
        print(json.dumps(bridge.start_workflow(args.goal, args.rf_lib, args.workflow_id),
                         ensure_ascii=False, indent=1))
        return 0
    if args.command == "status":
        print(json.dumps(bridge.workflow_status(args.workflow_id), ensure_ascii=False, indent=1))
        return 0

    started = bridge.start_workflow(args.goal, args.rf_lib, args.workflow_id)
    if not started.get("ok"):
        print(json.dumps(started, ensure_ascii=False, indent=1))
        return 2
    workflow_id = started["workflow_id"]
    stepped = bridge.step(workflow_id, args.prompt)
    explained = bridge.explain(workflow_id, stepped.get("output_id", ""),
                               allow_llm=not args.no_llm)
    print(json.dumps({"start": started, "step": stepped, "explain": explained},
                     ensure_ascii=False, indent=1, default=str))
    return 0 if stepped.get("ok") and explained.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EXPLANATION_FILENAME", "STATE_FILENAME", "RfWorkflowBridge", "main"]
