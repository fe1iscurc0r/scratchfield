"""academic 16 项目 MCP 工具注册（SPEC-02 Phase 1）。

两个工具：
- academic_status  16 项目清单 + 依赖安装状态 + 文档路径
- academic_call    统一调用入口（当前启用 5 项：thermo/coolprop/
                   chemformula/affine_gaps/pynite）
"""
from __future__ import annotations

import logging
from typing import Any

from .bridge import academic_call
from .registry import PROJECTS, doc_path, is_installed

logger = logging.getLogger(__name__)


def register_academic_tools(agent) -> None:
    """往 MaterialScienceAgent 注入 academic 调用桥工具。

    本模块无第三方硬依赖（调用包装内部延迟导入），
    单项依赖缺失仅影响该项目的可调用性，不影响注册。
    """

    def _tool_status(params: dict[str, Any]) -> dict[str, Any]:
        rows = []
        for name, meta in PROJECTS.items():
            doc = doc_path(name)
            rows.append({
                "project": name,
                "label": meta["label"],
                "domain": meta["domain"],
                "license": meta["license"],
                "installed": is_installed(name),
                "callable": bool(meta["call"]),
                "doc": str(doc) if doc else None,
            })
        callable_now = sum(1 for r in rows if r["installed"] and r["callable"])
        return {"success": True, "total": len(rows),
                "callable_installed": callable_now, "projects": rows}

    def _tool_call(params: dict[str, Any]) -> dict[str, Any]:
        project = params.get("project") or ""
        action = params.get("action") or ""
        if not project or not action:
            return {"success": False, "error": "请提供 project 与 action"}
        kwargs = {k: v for k, v in params.items()
                  if k not in ("project", "action")}
        try:
            result = academic_call(project, action, **kwargs)
        except ImportError as e:
            return {"success": False, "error":
                    f"依赖未安装（项目 {project}）: {e}，"
                    f"安装指引见 academic/{project}/MODEL_INTERFACE.md"}
        except Exception as e:  # 上游调用失败如实上报
            return {"success": False, "error": f"{project}.{action}: {e}"}
        return {"success": True, "project": project, "action": action,
                "result": result}

    agent.tools["academic_status"] = _tool_status
    agent.tools["academic_call"] = _tool_call
    n = sum(1 for name in PROJECTS if is_installed(name) and PROJECTS[name]["call"])
    logger.info(f"[MCP] academic 调用桥已注入（当前可用 {n} 项）")
