"""glyco 总线接入层 — GlycoAgent（agent-manifest.json entryPoint）。

按总线契约（Format A: {module, class} + ``handle_handoff``）包装糖链信息学工具：
    task 格式 {"tool": "parse_glycan|to_tree|glytoucan_lookup|annotate_glycan", "params": {...}}
    params 承载：{"text": "<GlycoCT 或 IUPAC>", "fmt": "auto|glycoct|iupac"} 或 {"accession": "..."}

返回：JSON 字符串（与 eis / rf_brain 同款契约）。未知工具/缺参走 error dict，不抛异常。
"""
from __future__ import annotations

import json
from typing import Any

from . import tools as _tools

_TOOLS = _tools.TOOLS


class GlycoAgent:
    """糖链信息学（glyco）工具组的总线入口。"""

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        tool = str(tool_call.get("tool") or tool_call.get("tool_name") or "").strip()
        params = tool_call.get("params")
        if not isinstance(params, dict):
            # 允许扁平调用：{"tool": "parse_glycan", "text": "...", "fmt": "glycoct"}
            params = {k: v for k, v in tool_call.items()
                      if k not in ("tool", "tool_name", "params")}

        try:
            if tool in ("", "tools"):
                result: dict[str, Any] = {"status": "ok", "available_tools": list(_TOOLS)}
            elif tool == "parse_glycan":
                result = _tools.parse_glycan(str(params.get("text") or ""),
                                             str(params.get("fmt") or "auto"))
            elif tool == "to_tree":
                result = _tools.to_tree(str(params.get("text") or ""),
                                        str(params.get("fmt") or "auto"))
            elif tool == "glytoucan_lookup":
                result = _tools.glytoucan_lookup(str(params.get("accession") or ""))
            elif tool == "annotate_glycan":
                result = _tools.annotate_glycan(str(params.get("text") or ""),
                                                str(params.get("fmt") or "auto"))
            else:
                result = {"status": "error", "error": f"unknown_tool: {tool}",
                          "available": list(_TOOLS)}
        except ValueError as exc:      # 参数类错误 → 结构化返回
            result = {"status": "error", "error": f"bad_input: {exc}"}
        except KeyError as exc:
            result = {"status": "error", "error": str(exc)}
        return json.dumps(result, ensure_ascii=False, default=str)
