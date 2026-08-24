"""MarkItDown MCP 适配层（论文 PDF → Markdown 知识管线，靶子 D）。

上游: microsoft/markitdown (MIT)，隔离 venv 安装 `markitdown[all]==0.1.6`
skill: skills/markitdown/ — 批量/文献工作流脚本在 scripts/ 下

适配策略（headroom.py Path B 纯 Python 退化模式）：
- healthcheck: 探测 markitdown 是否可 import（venv 或全局）
- register:   暴露 convert_to_markdown + pipeline_status 两个薄工具，
               不重复 skills/markitdown 的批量逻辑，只做单文件转换外壳
- 退化：markitdown 缺失时 healthcheck 返回 False，门禁自动跳过，不影响全局
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mcpserver.adapters._common import register_capability_safe

logger = logging.getLogger(__name__)

CAPABILITY: dict = {
    "name": "markitdown",
    "displayName": "MarkItDown 文档转换",
    "description": "调用 markitdown 将本地 PDF/Office/HTML/CSV 转为 Markdown，保留表格/公式/图注结构。",
    "version": "0.1.6",
    "license": "MIT",
    "vendor": "microsoft/markitdown",
    "degradation_mode": "skip-if-markitdown-missing",
    "_from_adapter": "markitdown",
}


def healthcheck() -> bool:
    """MarkItDown 健康检查：markitdown 必须可 import。"""
    try:
        import markitdown  # noqa: F401
        return True
    except Exception as e:
        logger.warning(
            "[adapter:markitdown] markitdown 未安装（需在隔离 venv 装 markitdown[all]==0.1.6）: %s",
            e,
        )
        return False


def register(mcp_server: Any, mcp_registry: Any = None) -> None:
    """注册 MarkItDown 转换工具。"""
    from markitdown import MarkItDown  # type: ignore

    converter = MarkItDown()

    async def convert_to_markdown(path: str) -> dict:
        """把单个本地文件转换为 Markdown（PDF/Office/HTML/CSV）。

        Args:
            path: 本地文件绝对路径
        """
        return _convert_one(converter, path)

    async def pipeline_status() -> dict:
        """MarkItDown 知识管线状态（版本 + papers 目录盘点）。"""
        status: dict[str, Any] = {"ok": True, "engine": "markitdown"}
        try:
            from importlib.metadata import version as _pkg_version
            status["markitdown_version"] = _pkg_version("markitdown")
        except Exception as e:
            status["markitdown_version"] = f"unknown ({e})"
        # 盘点论文目录（存在则统计，不存在则说明）
        for key, rel in (("papers_input", "papers/input"), ("papers_output", "papers/output")):
            d = Path(__file__).resolve().parents[2] / rel
            if not d.is_dir():
                status[key] = "missing"
                continue
            pdfs = [p for p in d.rglob("*.pdf")] if rel.endswith("input") else []
            mds = [p for p in d.rglob("*.md")] if rel.endswith("output") else []
            status[key] = {"dir": str(d), "file_count": len(pdfs or mds)}
        return status

    if hasattr(mcp_server, "add_tool"):
        mcp_server.add_tool(convert_to_markdown, name="convert_to_markdown")
        mcp_server.add_tool(pipeline_status, name="pipeline_status")

    register_capability_safe(mcp_registry, CAPABILITY)


def _convert_one(converter: Any, path: str) -> dict:
    """同步执行单文件转换，返回结构化结果。"""
    try:
        src = Path(path).resolve(strict=True)
        if not src.is_file():
            return {"ok": False, "error": f"路径不是文件: {path}"}
        result = converter.convert_local(src)
        if not (result and getattr(result, "markdown", "").strip()):
            return {"ok": False, "error": "转换结果为空"}
        return {
            "ok": True,
            "markdown": result.markdown,
            "title": (result.title or "").strip(),
            "characters": len(result.markdown),
            "source": str(src),
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}