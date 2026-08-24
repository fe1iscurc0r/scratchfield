"""academic MCP 桥 — AcademicBridge（agent-manifest.json entryPoint）。

Lumo 调用面（handle_handoff 分发）：
- academic_levels / academic_interfaces：层级总表（16 包）/ 接口元数据
- coolprop_props / coolprop_constant：热物性真算
- chem_parse：化学式离线解析
- tespy_check / tespy_solve_network：热力网络（缺依赖时明确降级）
- slices_check / slices_encode / slices_decode：晶体↔字符串（同上）

fail-fast：依赖缺失返回 AcademicDependencyError 文本（含 pip install 提示），
拼错参数返回白名单错误，不静默空返回。
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AcademicBridge:
    """academic 科研数据底座 MCP 服务实例。"""

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        tool_name = str(tool_call.get("tool_name") or "").strip()
        params = {k: v for k, v in tool_call.items()
                  if k not in ("service_name", "tool_name", "message",
                               "session_id", "callback_url")}
        try:
            result = self._dispatch(tool_name, params)
        except Exception as e:
            logger.warning("[academic] %s 失败: %s", tool_name, e)
            return json.dumps({"status": "error", "service": "academic",
                               "tool": tool_name, "error": str(e)},
                              ensure_ascii=False)
        return json.dumps({"status": "ok", "service": "academic",
                           "tool": tool_name, "result": result},
                          ensure_ascii=False)

    def _dispatch(self, tool_name: str, p: dict[str, Any]) -> dict[str, Any]:
        from mcpserver.academic import get_interfaces, get_levels, levels_summary

        if tool_name == "academic_levels":
            return {"ok": True, "packages": get_levels(),
                    "summary": levels_summary()}
        if tool_name == "academic_interfaces":
            return {"ok": True, "interfaces": get_interfaces()}

        if tool_name == "coolprop_props":
            from mcpserver.academic.coolprop_interface import coolprop_props
            return coolprop_props(p["output"], p["name1"], p["prop1"],
                                  p["name2"], p["prop2"], p["fluid"])
        if tool_name == "coolprop_constant":
            from mcpserver.academic.coolprop_interface import coolprop_constant
            return coolprop_constant(p["output"], p["fluid"])

        if tool_name == "chem_parse":
            from mcpserver.academic.chemformula_interface import chem_parse
            return chem_parse(p["formula"], charge=int(p.get("charge", 0) or 0),
                              name=p.get("name"))

        if tool_name == "tespy_check":
            from mcpserver.academic.tespy_interface import tespy_check
            return tespy_check()
        if tool_name == "tespy_solve_network":
            from mcpserver.academic.tespy_interface import tespy_solve_network
            return tespy_solve_network(p["spec"])

        if tool_name == "slices_check":
            from mcpserver.academic.slices_interface import slices_check
            return slices_check()
        if tool_name == "slices_encode":
            from mcpserver.academic.slices_interface import slices_encode
            return slices_encode(p["cif_path"])
        if tool_name == "slices_decode":
            from mcpserver.academic.slices_interface import slices_decode
            return slices_decode(p["slices_str"])

        if tool_name == "indigo_molinfo":
            from mcpserver.academic.indigo_interface import indigo_molinfo
            return indigo_molinfo(p["smiles"])
        if tool_name == "indigo_substructure":
            from mcpserver.academic.indigo_interface import indigo_substructure
            return indigo_substructure(p["query"], p["target"])

        if tool_name == "chembl_molecule":
            from mcpserver.academic.chembl_interface import chembl_molecule
            return chembl_molecule(p["chembl_id"])
        if tool_name == "chembl_search_smiles":
            from mcpserver.academic.chembl_interface import chembl_search_smiles
            return chembl_search_smiles(p["smiles"],
                                        similarity=int(p.get("similarity", 90)),
                                        limit=int(p.get("limit", 5)))

        raise ValueError(
            f"academic 不支持的工具: {tool_name!r}（可用: academic_levels/"
            "academic_interfaces/coolprop_props/coolprop_constant/chem_parse/"
            "tespy_check/tespy_solve_network/slices_check/slices_encode/"
            "slices_decode/indigo_molinfo/indigo_substructure/chembl_molecule/"
            "chembl_search_smiles）")
