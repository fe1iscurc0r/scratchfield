"""rf_brain 总线接入层 — RfBrainAgent（agent-manifest.json entryPoint）。

历史缺口：manifest 的 entryPoint 一直指向 ``loop.run_loop``（纯函数，iq 为
必传参数），注册表 create_agent_instance 无参调用必然 TypeError → 该能力
从未成功注册过总线，且 import-only 的可用性检查对此说谎。

本类按总线契约（Format A: {module, class} + handle_handoff）包装闭环入口：
task 格式 {"tool": "run_loop", "params": {"iq_path", "sample_rate",
"center_freq", ...}} → np.load 读 IQ → run_loop 闭环 → JSON 字符串。
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any


class RfBrainAgent:
    """物理层 AI 决策闭环（感知→特征→决策→解调→反馈）的总线入口。"""

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        tool = str(tool_call.get("tool") or tool_call.get("tool_name") or "").strip()
        params = tool_call.get("params")
        if not isinstance(params, dict):
            params = {}
        if tool in ("", "run_loop"):
            result: dict[str, Any] = self._run_loop(params)
        else:
            result = {
                "status": "error",
                "error": f"unknown_tool: {tool}",
                "available": ["run_loop"],
            }
        return json.dumps(result, ensure_ascii=False, default=str)

    def _run_loop(self, params: dict[str, Any]) -> dict[str, Any]:
        iq_path = str(params.get("iq_path") or "").strip()
        if not iq_path:
            return {"status": "error", "error": "missing_iq_path"}
        try:
            import numpy as np

            from mcpserver.rf_brain.loop import run_loop

            iq = np.load(iq_path)
            result = run_loop(
                iq,
                sample_rate=float(params.get("sample_rate") or 0),
                center_freq=float(params.get("center_freq") or 0),
                ground_truth_modulation=params.get("ground_truth_modulation"),
                max_attempts=int(params.get("max_attempts") or 3),
            )
        except FileNotFoundError:
            return {"status": "error", "error": f"iq_file_not_found: {iq_path}"}
        except Exception as e:  # 闭环内部错误不崩总线，落 JSON
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
        return {"status": "ok", **asdict(result)}
