"""eis 总线接入层 — EisAgent（agent-manifest.json entryPoint）。

按总线契约（Format A: {module, class} + ``handle_handoff``）包装阻抗谱三工具：
    task 格式 {"tool": "linkk|drt|ecm|kernels", "params": {...}}
    params 统一承载谱数据：{"freqs": [...], "z_real": [...], "z_imag": [...]}

返回：JSON 字符串（与 rf_brain 等同款契约）。未知工具/缺参走 error dict，
不抛异常（总线层容错口径）。
"""
from __future__ import annotations

import json
from typing import Any

from . import kernel as _kernel
from . import tools as _tools

_TOOLS = ("linkk", "drt", "ecm")


class EisAgent:
    """电化学阻抗谱（EIS）工具组的总线入口。"""

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        tool = str(tool_call.get("tool") or tool_call.get("tool_name") or "").strip()
        params = tool_call.get("params")
        if not isinstance(params, dict):
            # 允许扁平调用：{"tool": "drt", "freqs": [...], ...}
            params = {k: v for k, v in tool_call.items()
                      if k not in ("tool", "tool_name", "params")}

        if tool in ("", "kernels"):
            result: dict[str, Any] = {
                "status": "ok",
                "available_tools": list(_TOOLS),
                "kernels": _kernel.list_kernels(),
                "default_kernel": _kernel.DEFAULT_KERNEL,
            }
        elif tool in ("linkk", "drt", "ecm"):
            result = self._run_spectrum_tool(tool, params)
        else:
            result = {
                "status": "error",
                "error": f"unknown_tool: {tool}",
                "available": list(_TOOLS) + ["kernels"],
            }
        return json.dumps(result, ensure_ascii=False, default=str)

    # -- 内部 ---------------------------------------------------------------

    def _run_spectrum_tool(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        freqs = params.get("freqs")
        z_real = params.get("z_real")
        z_imag = params.get("z_imag")
        if freqs is None or z_real is None or z_imag is None:
            return {
                "status": "error",
                "error": "missing_spectrum: 需要 freqs / z_real / z_imag 三个等长数组",
            }
        try:
            if tool == "linkk":
                kwargs: dict[str, Any] = {}
                if params.get("threshold") is not None:
                    kwargs["threshold"] = float(params["threshold"])
                if params.get("n_tau") is not None:
                    kwargs["n_tau"] = int(params["n_tau"])
                return _tools.linkk(freqs, z_real, z_imag, **kwargs)
            if tool == "drt":
                kwargs = {}
                if params.get("kernel"):
                    kwargs["kernel"] = str(params["kernel"])
                if params.get("n_tau") is not None:
                    kwargs["n_tau"] = int(params["n_tau"])
                if params.get("lam") is not None:
                    kwargs["lam"] = float(params["lam"])
                return _tools.drt(freqs, z_real, z_imag, **kwargs)
            # ecm
            kwargs = {}
            if params.get("num_elements") is not None:
                kwargs["num_elements"] = int(params["num_elements"])
            return _tools.ecm(freqs, z_real, z_imag, **kwargs)
        except ValueError as exc:      # 形状/参数类错误 → 结构化返回
            return {"status": "error", "error": f"bad_input: {exc}"}
        except KeyError as exc:
            return {"status": "error", "error": str(exc)}
