"""tespy MODEL_INTERFACE — 热力系统网络仿真（依赖缺失时明确降级）。

上游：https://github.com/oemof/tespy （MIT）
版本敏感性：0.9 与 0.11 的单位设定 API 不同（v0.11 起单位可入构造器）。
本接口把"拓扑 JSON → Network 组装 → solve → 结果 JSON"钉死在一份 spec 上，
版本漂移时只需改本文件的适配层，调用方契约不变。
"""
from __future__ import annotations

from typing import Any

from mcpserver.academic.errors import require

MODEL_INTERFACE: dict[str, Any] = {
    "name": "tespy",
    "package": "tespy",
    "vendor_repo": "https://github.com/oemof/tespy",
    "pip": "tespy",
    "license": "MIT",
    "fusion_level": "MCP",
    "description": "热力循环（电厂/ORC/热泵/制冷）组件网络建模与求解",
    "entrypoints": [
        {
            "command": "tespy_solve_network",
            "params": {
                "spec": ("拓扑 spec：{fluids:[], units:{p,T,h}, components:["
                         "{type:'Source|Sink|Pump|HeatExchanger',id:...}], "
                         "connections:[{from,id from_id=,to,to_id=,fluid=,"
                         "state:{...}}], mode:'design|offdesign'}"),
            },
            "returns": {"solved": "bool", "results": "{连接线: 态量}",
                        "iterations": "int"},
            "example": "spec 见 docs/academic/MODEL_INTERFACE.md 附例",
        },
        {
            "command": "tespy_check",
            "params": {},
            "returns": {"available": "bool", "version": "str|None"},
        },
    ],
    "runtime_deps": ["tespy（未装时抛 AcademicDependencyError，pip install tespy）"],
    "degradation": "pip install tespy 即恢复；物性后端可用 CoolProp（本仓已装）",
    "verified": "2026-08-23 本仓 .venv 未装 tespy，降级契约实测通过",
}

# spec 允许的组件类型（与 tespy.components 同名）
_ALLOWED_COMPONENTS = {"Source", "Sink", "Pump", "HeatExchanger", "Pipe",
                       "Compressor", "Turbine", "Mixing chamber"}


def tespy_check() -> dict[str, Any]:
    """依赖探测（不抛错，返回 available + 版本）。"""
    try:
        tespy = require("tespy", "tespy")
        return {"available": True,
                "version": getattr(tespy, "__version__", "unknown")}
    except Exception as e:
        return {"available": False, "error": str(e)}


def tespy_solve_network(spec: dict[str, Any]) -> dict[str, Any]:
    """拓扑 JSON → tespy Network → design/offdesign 求解。

    未装 tespy 时抛 AcademicDependencyError（Lumo 转述给用户自助恢复）。
    """
    if not isinstance(spec, dict):
        raise ValueError("spec 必须是拓扑 JSON 对象")
    problems = []
    for key in ("fluids", "components", "connections"):
        if key not in spec:
            problems.append(f"spec 缺字段 {key}")
    for comp in spec.get("components", []):
        ctype = comp.get("type")
        if ctype and ctype not in _ALLOWED_COMPONENTS:
            problems.append(f"组件类型 {ctype!r} 不在白名单")
    if problems:
        raise ValueError("；".join(problems))

    networks = require("tespy.networks", "tespy")
    components_mod = require("tespy.components", "tespy")
    connections_mod = require("tespy.connections", "tespy")

    # 构造（0.9+ 通用形态：构造后 set_attr 单位）
    kwargs: dict[str, Any] = {"fluids": list(spec["fluids"])}
    try:
        nw = networks.Network(**kwargs)
        nw.set_attr(**(spec.get("units") or {}))
    except TypeError as e:  # 0.11 单位入构造器的兼容分支
        kwargs.update(spec.get("units") or {})
        nw = networks.Network(**kwargs)

    comps: dict[str, Any] = {}
    for comp in spec["components"]:
        cls = getattr(components_mod, comp["type"])
        comps[comp["id"]] = cls(comp.get("label") or comp["id"])
        nw.add_comps(comps[comp["id"]])

    for conn in spec["connections"]:
        c = connections_mod.Connection(
            comps[conn["from"]], conn["from_id"],
            comps[conn["to"]], conn["to_id"])
        if conn.get("fluid"):
            c.fluid.set_attr(**conn["fluid"])
        if conn.get("state"):
            c.set_attr(**conn["state"])
        nw.add_conns(c)

    mode = spec.get("mode", "design")
    solved = nw.solve(mode=mode)
    results = {}
    for conn in nw.conns["object"]:
        results[str(conn)] = {"m": getattr(conn.m, "val", None),
                              "p": getattr(conn.p, "val", None),
                              "h": getattr(conn.h, "val", None)}
    return {"ok": True, "solved": True, "mode": mode,
            "results": results, "source": MODEL_INTERFACE["package"]}
