"""Headroom MCP 适配层（上下文压缩 CCR / 记忆）。

上游 vendor: vendor/top5/headroom (Apache-2.0)
Rust 部分: crates/headroom-py/ — maturin Python binding，**Windows wheel 未验证**

适配策略：
- Path A：Rust _core 扩展可用 → 合并 headroom.ccr.mcp_server + headroom.memory.mcp_server 双 FastMCP
- Path B：Rust 不可用 → 暴露 headroom_compress_text + headroom_stats 外壳（纯 Python pipeline 或 truncate-fallback）
"""
from __future__ import annotations

import importlib
import inspect
import logging
from typing import Any

from mcpserver.adapters._common import (
    inject_vendor_path,
    merge_tools,
    register_capability_safe,
)

logger = logging.getLogger(__name__)

# 模块级 CAPABILITY（描述是基础版；register 时按 Rust 可用性追加说明文字）
CAPABILITY: dict = {
    "name": "headroom",
    "displayName": "上下文压缩",
    "description": "LLM 上下文压缩（Rust Kompress-v2，JSON 省 60-95%，对话省 15-20%）。",
    "version": "0.34.0",
    "license": "Apache-2.0",
    "vendor": "headroom",
    "degradation_mode": "auto-fallback-to-pure-python-if-rust-core-missing",
    "_from_adapter": "headroom",
}


def healthcheck() -> bool:
    """Headroom 健康检查。两条可运行路径：

    A. PyPI 版已安装（含 Rust _core.pyd/.so）→ 完整版
    B. 未安装但源码可用（当前默认）→ 退化到纯 Python transform pipeline
    """
    inject_vendor_path("headroom")
    try:
        import headroom  # noqa: F401
        from headroom.compression import universal as _u  # type: ignore  # noqa: F401
    except Exception as e:
        logger.warning("[adapter:headroom] headroom Python 包未安装: %s", e)
        return False
    try:
        from headroom import _core as _rust_core  # type: ignore  # noqa: F401
        logger.info("[adapter:headroom] 检测到 Rust 扩展可用，启用全功能模式")
    except Exception:
        logger.info(
            "[adapter:headroom] 源码可用但 Rust _core 扩展未就绪。"
            "启用纯 Python 退化模式（压缩比降低 15~30%）。"
        )
    return True


def register(mcp_server: Any, mcp_registry: Any = None) -> None:
    """注册 Headroom MCP 工具。"""
    inject_vendor_path("headroom")

    rust_available = False
    try:
        from headroom import _core  # type: ignore  # noqa: F401
        rust_available = True
    except Exception:
        rust_available = False

    merged = 0
    if rust_available:
        # Path A: CCR + memory 双 MCP server 合并（用统一 merge_tools）
        for mod_path in ("headroom.ccr.mcp_server", "headroom.memory.mcp_server"):
            try:
                mod = importlib.import_module(mod_path)
                merged += merge_tools(mod, mcp_server, prefix="headroom")
            except Exception as e:
                logger.debug("[adapter:headroom] 合并 %s 工具跳过: %s", mod_path, e)

    if not merged:
        # Path B: 退化 Python 模式，暴露 compress + stats 外壳
        logger.info("[adapter:headroom] 启用纯 Python 退化模式（通用压缩 pipeline + 本地统计）")
        try:
            from headroom.compression import universal as hr_comp  # type: ignore
        except Exception as e:
            logger.warning("[adapter:headroom] 压缩 pipeline 导入失败: %s，回退到最朴素 truncate", e)
            hr_comp = None

        async def headroom_compress_text(text: str, max_ratio: float = 0.7, mode: str = "general") -> dict:
            """压缩长文本（Python pipeline 退化模式，或 Rust 模式时直接调）。

            Args:
                text: 待压缩文本
                max_ratio: 目标压缩比（保留字符比例，0.1-0.9）
                mode: general / code / conversation
            """
            try:
                if hr_comp is not None and hasattr(hr_comp, "compress"):
                    if inspect.iscoroutinefunction(hr_comp.compress):
                        logger.warning(
                            "[adapter:headroom] hr_comp.compress 是 async，"
                            "当前 merge_tools 不支持 async 调用，回退 truncate"
                        )
                    else:
                        result = hr_comp.compress(text)  # type: ignore[call-arg]
                        return {"ok": True, "compressed": result.compressed, "ratio": result.compression_ratio}
                # truncate-fallback：对短文本直接返回原文，不产生重复
                if len(text) <= 300:
                    return {"ok": True, "compressed": text, "ratio": 1.0, "mode": "no-truncation"}
                keep = max(300, int(len(text) * max(max_ratio, 0.05)))
                if keep >= len(text):
                    return {"ok": True, "compressed": text, "ratio": 1.0, "mode": "no-truncation"}
                head_len = min(keep // 2, len(text))
                tail_len = min(keep - head_len, len(text) - head_len)
                head = text[:head_len]
                tail = text[len(text) - tail_len:] if tail_len > 0 else ""
                omitted = len(text) - head_len - tail_len
                result_str = head + (f"\n\n[⋯中间{omitted}字已省略⋯]\n\n" + tail if omitted > 0 else "")
                return {"ok": True, "compressed": result_str, "ratio": len(result_str) / max(1, len(text)), "mode": "truncate-fallback"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        async def headroom_stats() -> dict:
            """headroom 运行状态（退化版：只报告模式与 Python 包版本）。"""
            version = "unknown"
            try:
                from headroom._version import __version__  # type: ignore
                version = __version__
            except Exception as e:
                logger.debug("[adapter:headroom] _version 导入失败: %s", e)
            return {
                "ok": True,
                "version": version,
                "rust_core_available": rust_available,
                "mode": "full" if rust_available else "python_pipeline_fallback",
            }

        if hasattr(mcp_server, "add_tool"):
            mcp_server.add_tool(headroom_compress_text, name="headroom_compress_text")
            mcp_server.add_tool(headroom_stats, name="headroom_stats")

    # 按 Rust 可用性拼接 description 再登记能力卡片
    desc = CAPABILITY["description"]
    if rust_available:
        desc += " 当前已启用 Rust 扩展。"
    else:
        desc += " 当前使用 Python 退化模式，压缩比降低 15-30%，待 Windows wheel 实测后升级。"
    register_capability_safe(
        mcp_registry,
        {**CAPABILITY, "description": desc, "rust_core_available": rust_available},
    )
