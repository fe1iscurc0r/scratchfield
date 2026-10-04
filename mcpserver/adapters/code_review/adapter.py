"""code-review-graph MCP 桥 — CodeReviewGraphBridge（agent-manifest.json entryPoint）。

接入方式与 graphify/hamlog 同构（manifest 型，scan_and_register_mcp_agents
自动注册，mcp_manager.unified_call 走 handle_handoff 分发）。

开关门禁（工单要求默认关，不破坏现状）：
- ENABLE_ADAPTER_CODE_REVIEW 未显式开启（=1/true/yes/on）时，本桥 __init__ 直接
  raise CodeReviewError → create_agent_instance 捕获 → 不注册。默认关。
- 区别于 mcpserver/adapters/__init__.py 三件套 Protocol 型（默认开）。

工具（4 核心 + 1 建图，前缀 code_review_ 防冲突）：
- code_review_build_index(root): 目录 → crg-out/index.json 并挂载
- code_review_detect_changes(base, max_depth): git diff → 变更函数 + 风险分 +
  测试缺口 + 受影响执行流
- code_review_get_impact_radius(changed_files, max_depth): 反向 BFS 影响半径
- code_review_query_graph(name, limit): 定义 + 调用者/被调者
- code_review_get_architecture_overview(): 枢纽节点/大函数/目录分布

上游 https://github.com/tirth8205/code-review-graph（MIT，见 UPSTREAM-LICENSE）。
fail-fast：目录/索引/节点缺失一律 CodeReviewError → error 信封，绝不静默空返回。
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from mcpserver.adapters.code_review.engine import (
    CodeReviewError,
    GraphIndex,
    estimate_tokens,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_INDEX_ENV = "CRG_INDEX_JSON"
_GATE_ENV = "ENABLE_ADAPTER_CODE_REVIEW"
_UPSTREAM = {
    "repo": "https://github.com/tirth8205/code-review-graph",
    "license": "MIT",
    "scope": "审查专用代码知识图谱（风险分 + 测试缺口 + 影响半径），"
             "与 graphify（通用知识图谱）互补",
}


def is_enabled() -> bool:
    """ENABLE_ADAPTER_CODE_REVIEW 门禁：仅 1/true/yes/on 视为开启，默认关。"""
    return os.environ.get(_GATE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


class CodeReviewGraphBridge:
    """code-review-graph 审查图谱 MCP 服务实例（默认关，需显式开启）。"""

    def __init__(self) -> None:
        if not is_enabled():
            raise CodeReviewError(
                f"{_GATE_ENV} 未开启（默认关）：显式设 ENABLE_ADAPTER_CODE_REVIEW=1 "
                f"才注册本 adapter，不破坏现状。索引可用 python tools/crg_index.py --build 预生成。")
        self._index: GraphIndex | None = None
        self._index_path: str | None = None

    # ---- 索引定位（显式路径 > 环境变量 > 仓库默认输出位）----
    def _active_index(self, candidate: str | None = None) -> GraphIndex:
        if candidate:
            self._index = GraphIndex.load(candidate)
            self._index_path = candidate
            return self._index
        if self._index is not None:
            return self._index
        env = os.environ.get(_DEFAULT_INDEX_ENV, "").strip()
        if env:
            self._index = GraphIndex.load(env)
            self._index_path = env
            return self._index
        default = _REPO_ROOT / "crg-out" / "index.json"
        if default.is_file():
            self._index = GraphIndex.load(str(default))
            self._index_path = str(default)
            return self._index
        raise CodeReviewError(
            "尚未建索引：先 code_review_build_index(root)，或 "
            f"python tools/crg_index.py --build <目录>（或设 {_DEFAULT_INDEX_ENV}）")

    # ---- 工具实现 ----
    def tool_build_index(self, root: str) -> dict[str, Any]:
        idx = GraphIndex.build(root)
        default = _REPO_ROOT / "crg-out" / "index.json"
        self._index_path = idx.save(default)
        self._index = idx
        return {
            "index_json": self._index_path,
            "root": idx.root,
            "files": len(idx._module_of_file),
            "nodes": len(idx.nodes),
            "edges": len(idx.edges),
            "gate": _GATE_ENV,
            "upstream": _UPSTREAM,
        }

    def tool_detect_changes(self, base: str = "HEAD~1",
                            changed_files: list[str] | None = None,
                            max_depth: int = 2) -> dict[str, Any]:
        idx = self._active_index()
        result = idx.detect_changes(base=base, changed_files=changed_files,
                                    max_depth=max_depth)
        result["tokens"] = estimate_tokens(json.dumps(result, ensure_ascii=False))
        result["token_note"] = "chars/4 估算口径（与上游 CHARS_PER_TOKEN 同口径）"
        return result

    def tool_get_impact_radius(self, changed_files: list[str],
                               max_depth: int = 2) -> dict[str, Any]:
        idx = self._active_index()
        result = idx.impact_radius(changed_files=changed_files, max_depth=max_depth)
        result["tokens"] = estimate_tokens(json.dumps(result, ensure_ascii=False))
        return result

    def tool_query_graph(self, name: str, limit: int = 10) -> dict[str, Any]:
        idx = self._active_index()
        result = idx.query(name, limit=limit)
        result["tokens"] = estimate_tokens(json.dumps(result, ensure_ascii=False))
        return result

    def tool_get_architecture_overview(self, top_k: int = 10) -> dict[str, Any]:
        idx = self._active_index()
        result = idx.architecture_overview(top_k=top_k)
        result["tokens"] = estimate_tokens(json.dumps(result, ensure_ascii=False))
        return result

    # ---- MCP 分发 ----
    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        """unified_call 入口：按 tool_name 分发，参数从 tool_call 平铺取。"""
        tool_name = str(tool_call.get("tool_name") or "").strip()
        params = {k: v for k, v in tool_call.items()
                  if k not in ("service_name", "tool_name", "message",
                               "session_id", "callback_url")}
        try:
            if tool_name == "code_review_build_index":
                result = self.tool_build_index(str(params.get("root", "")))
            elif tool_name == "code_review_detect_changes":
                result = self.tool_detect_changes(
                    base=str(params.get("base") or "HEAD~1"),
                    changed_files=_as_list(params.get("changed_files")),
                    max_depth=int(params.get("max_depth", 2) or 2))
            elif tool_name == "code_review_get_impact_radius":
                result = self.tool_get_impact_radius(
                    changed_files=_as_list(params.get("changed_files")),
                    max_depth=int(params.get("max_depth", 2) or 2))
            elif tool_name == "code_review_query_graph":
                result = self.tool_query_graph(
                    str(params.get("name") or ""),
                    limit=int(params.get("limit", 10) or 10))
            elif tool_name == "code_review_get_architecture_overview":
                result = self.tool_get_architecture_overview(
                    top_k=int(params.get("top_k", 10) or 10))
            else:
                raise CodeReviewError(
                    f"code_review 不支持的工具: {tool_name!r}（可用: build_index/"
                    "detect_changes/get_impact_radius/query_graph/get_architecture_overview，"
                    "前缀 code_review_）")
        except CodeReviewError as e:
            logger.warning("[code_review] %s 失败: %s", tool_name or "(no-tool)", e)
            return json.dumps({"status": "error", "service": "code_review",
                               "tool": tool_name, "error": str(e)},
                              ensure_ascii=False)
        except Exception as e:  # 兜底：不让单次调用炸掉整个 MCP 服务
            logger.exception("[code_review] %s 未预期异常", tool_name)
            return json.dumps({"status": "error", "service": "code_review",
                               "tool": tool_name, "error": f"未预期异常: {e}"},
                              ensure_ascii=False)
        return json.dumps({"status": "ok", "service": "code_review",
                           "tool": tool_name, "result": result},
                          ensure_ascii=False)


def _as_list(value: Any) -> list[str] | None:
    """changed_files 兼容平铺列表 / 逗号分隔串 / 空。"""
    if value is None or value == "":
        return None
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [s.strip() for s in str(value).split(",") if s.strip()]
