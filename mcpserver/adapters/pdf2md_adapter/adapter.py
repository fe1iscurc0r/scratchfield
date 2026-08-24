"""pdf2md_adapter — 论文 PDF → Markdown 管线（四靶子 D / 台账 ⑤）。

工具选型（工单要求）：Docling（IBM，主力）+ MarkItDown（降级）。
- Docling：版面分析 + 表格结构保留 + OCR（中文 ch_sim+en）+ 图像提取
- MarkItDown：Docling 缺失或转换失败时的兜底（无 OCR，仅文本层提取）

工具接口：
- pdf2md_convert(file_path, output_dir?) → {ok, markdown, images, engine, ...}
- pdf2md_batch(dir_path, output_dir?) → {ok, results: [{filename, ok, markdown?...}]}

设计要点：
1. fail-fast：文件不存在 / 两个引擎都不可用时报错，不静默空返回
2. 图像提取到 <output_dir>/<stem>_assets/，markdown 内引用相对路径
3. 独立进程能力：--stdio 启动最小 MCP stdio server，可经 mcporter_bridge 接入
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 引擎探测
# ---------------------------------------------------------------------------


def _docling_available() -> bool:
    try:
        import docling  # noqa: F401

        return True
    except Exception:
        return False


def _markitdown_available() -> bool:
    try:
        import markitdown  # noqa: F401

        return True
    except Exception:
        return False


def engines_status() -> dict:
    """两个引擎的可用性快照（供状态工具与 fail-fast 报错展示）。"""
    status: dict[str, Any] = {
        "docling": _docling_available(),
        "markitdown": _markitdown_available(),
    }
    try:
        from importlib.metadata import version as _v

        status["docling_version"] = _v("docling") if status["docling"] else None
        status["markitdown_version"] = (
            _v("markitdown") if status["markitdown"] else None
        )
    except Exception:
        pass
    return status


# ---------------------------------------------------------------------------
# Docling 转换（主力：OCR + 表格结构 + 图像提取）
# ---------------------------------------------------------------------------


def _convert_with_docling(src: Path, assets_dir: Optional[Path]) -> dict:
    """Docling 转换。中文 OCR（ch_sim+en）、表格结构保留、脚注随正文导出。

    图像提取：Docling markdown 导出默认以 ``<!-- image -->`` 占位，
    按出现顺序替换为 assets_dir 下的实际图片相对路径。
    """
    from docling.datamodel.base_models import InputFormat  # type: ignore
    from docling.datamodel.pipeline_options import (  # type: ignore
        PdfPipelineOptions,
    )
    from docling.document_converter import (  # type: ignore
        DocumentConverter,
        PdfFormatOption,
    )

    # 中文 OCR：优先 RapidOCR（docling 2.120 默认随包装好，轻量且中文支持好），
    # 回退 EasyOCR（需另装 easyocr 包）；两者都无则用引擎默认
    ocr_options = None
    try:
        from docling.datamodel.pipeline_options import RapidOcrOptions  # type: ignore

        import rapidocr  # noqa: F401  运行时依赖在才用

        ocr_options = RapidOcrOptions(lang=["ch"])  # PP-OCRv6 ch 模型自带中英混排识别
    except Exception:
        try:
            from docling.datamodel.pipeline_options import EasyOcrOptions  # type: ignore

            import easyocr  # noqa: F401

            ocr_options = EasyOcrOptions(lang=["ch_sim", "en"])
        except Exception:
            logger.warning("[pdf2md] RapidOCR/EasyOCR 均不可用，退回引擎默认 OCR（中文可能缺失）")

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    if ocr_options is not None:
        pipeline_options.ocr_options = ocr_options
    # 表格结构保留（ADIF/HTML 表格依赖此开关）
    pipeline_options.do_table_structure = True
    try:
        pipeline_options.table_structure_options.do_cell_matching = True
    except Exception:
        pass
    # 图像提取：渲染图片供导出
    try:
        pipeline_options.generate_picture_images = True
        pipeline_options.images_scale = 2.0
    except Exception:
        pass

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    result = converter.convert(str(src))
    doc = result.document
    if doc is None:
        raise RuntimeError(f"Docling 转换未产出文档对象: {src}")

    markdown = doc.export_to_markdown()

    # 图像提取：按 <!-- image --> 占位顺序落盘并替换为引用路径
    images: list[str] = []
    if assets_dir is not None and "<!-- image -->" in markdown:
        assets_dir.mkdir(parents=True, exist_ok=True)
        pictures = list(getattr(doc, "pictures", []) or [])
        parts = markdown.split("<!-- image -->")
        # 占位符数 = len(parts) - 1；图片对象不足时剩余占位原样保留
        rebuilt = [parts[0]]
        for idx, tail in enumerate(parts[1:]):
            ref = None
            if idx < len(pictures):
                try:
                    # docling 2.x：get_image 需要回传 document 才能定位页面位图
                    img = pictures[idx].get_image(doc)
                except Exception:
                    img = None
                if img is not None:
                    fname = f"fig_{idx + 1:03d}.png"
                    img_path = assets_dir / fname
                    try:
                        img.save(img_path)
                        # 标准 Markdown 图片语法，渲染器可直接显示
                        ref = f"![figure {idx + 1}]({assets_dir.name}/{fname})"
                        images.append(str(img_path))
                    except Exception as e:
                        logger.warning("[pdf2md] 图片 %s 落盘失败: %s", idx + 1, e)
            rebuilt.append(ref if ref is not None else "<!-- image -->")
            rebuilt.append(tail)
        markdown = "".join(rebuilt)

    return {"markdown": markdown, "images": images, "engine": "docling"}


# ---------------------------------------------------------------------------
# MarkItDown 降级转换（无 OCR，仅文本层/结构提取）
# ---------------------------------------------------------------------------


def _convert_with_markitdown(src: Path) -> dict:
    from markitdown import MarkItDown  # type: ignore

    result = MarkItDown().convert_local(str(src))
    markdown = (getattr(result, "markdown", "") or "").strip()
    if not markdown:
        raise RuntimeError(f"MarkItDown 转换结果为空: {src}")
    return {"markdown": markdown, "images": [], "engine": "markitdown"}


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------


def _resolve_source(file_path: str) -> Path:
    src = Path(file_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {file_path}")
    if not src.is_file():
        raise ValueError(f"路径不是文件: {file_path}")
    if src.suffix.lower() != ".pdf":
        raise ValueError(f"仅支持 .pdf 文件，收到: {src.suffix or '(无扩展名)'}")
    return src


def _default_output_dir(src: Path) -> Path:
    """默认输出到 papers/output（管线约定），不存在则建在源文件旁。"""
    repo_root = Path(__file__).resolve().parents[3]
    papers_out = repo_root / "papers" / "output"
    if (repo_root / "papers").is_dir():
        return papers_out
    return src.parent


def pdf2md_convert(file_path: str, output_dir: str = "") -> dict:
    """把单个论文 PDF 转为 Markdown。

    Args:
        file_path: PDF 文件路径
        output_dir: 输出目录（默认 papers/output）。markdown 写入
                    <output_dir>/<文件名>.md，图像提取到
                    <output_dir>/<文件名>_assets/

    Returns:
        {ok, markdown, md_path, images, engine, characters, engines}
    """
    try:
        src = _resolve_source(file_path)
        engines = engines_status()
        if not engines["docling"] and not engines["markitdown"]:
            raise RuntimeError(
                "pdf2md 引擎均不可用：请安装 docling（主力，含中文 OCR）"
                "或 markitdown（降级）。"
            )

        out_root = Path(output_dir).expanduser().resolve() if output_dir else _default_output_dir(src)
        out_root.mkdir(parents=True, exist_ok=True)
        assets_dir = out_root / f"{src.stem}_assets"

        error = None
        converted: Optional[dict] = None
        if engines["docling"]:
            try:
                converted = _convert_with_docling(src, assets_dir)
            except Exception as e:
                error = f"docling: {type(e).__name__}: {e}"
                logger.warning("[pdf2md] Docling 失败，尝试 MarkItDown 降级: %s", error)
        if converted is None:
            if engines["markitdown"]:
                converted = _convert_with_markitdown(src)
                if error:
                    converted["fallback_reason"] = error
            else:
                raise RuntimeError(f"Docling 转换失败且无降级引擎可用。{error}")

        md_path = out_root / f"{src.stem}.md"
        md_path.write_text(converted["markdown"], encoding="utf-8")

        return {
            "ok": True,
            "markdown": converted["markdown"],
            "md_path": str(md_path),
            "images": converted["images"],
            "engine": converted["engine"],
            "fallback_reason": converted.get("fallback_reason"),
            "characters": len(converted["markdown"]),
            "source": str(src),
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def pdf2md_batch(dir_path: str, output_dir: str = "") -> dict:
    """批量转换目录下所有 PDF。

    Args:
        dir_path: 待扫描目录（递归查找 *.pdf）
        output_dir: 输出目录（默认 papers/output）

    Returns:
        {ok, total, succeeded, results: [{filename, ok, markdown?, md_path?, error?}]}
    """
    try:
        root = Path(dir_path).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"目录不存在: {dir_path}")
        pdfs = sorted(root.rglob("*.pdf"))
        if not pdfs:
            return {"ok": True, "total": 0, "succeeded": 0, "results": []}

        results = []
        for pdf in pdfs:
            r = pdf2md_convert(str(pdf), output_dir=output_dir)
            if r.get("ok"):
                results.append(
                    {
                        "filename": pdf.name,
                        "ok": True,
                        "markdown": r["markdown"],
                        "md_path": r["md_path"],
                        "engine": r["engine"],
                        "characters": r["characters"],
                    }
                )
            else:
                results.append({"filename": pdf.name, "ok": False, "error": r["error"]})
        succeeded = sum(1 for r in results if r["ok"])
        return {
            "ok": succeeded > 0 or len(pdfs) == 0,
            "total": len(pdfs),
            "succeeded": succeeded,
            "results": results,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def pdf2md_status() -> dict:
    """管线状态：引擎可用性 + 版本。"""
    return {"ok": True, **engines_status()}


_TOOLS: dict[str, Any] = {
    "pdf2md_convert": pdf2md_convert,
    "pdf2md_batch": pdf2md_batch,
    "pdf2md_status": pdf2md_status,
}


# ---------------------------------------------------------------------------
# MCP agent 桥（manifest 型，agent-manifest.json 指向这里）
# ---------------------------------------------------------------------------


class Pdf2MdBridge:
    """mcpserver scan_and_register_mcp_agents 入口（同 hamlog_adapter 约定）。"""

    name = "pdf2md_adapter"

    async def handle_handoff(self, task: dict) -> str:
        tool_name = str(task.get("tool_name") or "").strip()
        if not tool_name:
            return json.dumps(
                {"status": "error", "message": "缺少 tool_name", "data": {}},
                ensure_ascii=False,
            )
        fn = _TOOLS.get(tool_name)
        if fn is None:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"未知工具 {tool_name}，可用: {', '.join(sorted(_TOOLS))}",
                    "data": {},
                },
                ensure_ascii=False,
            )
        # 参数平铺在 task 里（registry 约定）；兼容嵌套 params/arguments（stdio 直连）。
        # 注意用键存在判断而非真值：空 dict 也是合法参数集（无参工具）
        if isinstance(task.get("params"), dict):
            arguments = task["params"]
        elif isinstance(task.get("arguments"), dict):
            arguments = task["arguments"]
        else:
            arguments = {
                k: v for k, v in task.items()
                if k not in ("tool_name", "agentType", "service_name", "_tool_call_id")
            }
        try:
            data = fn(**arguments)
            if isinstance(data, dict) and data.get("ok") is False:
                return json.dumps(
                    {"status": "error", "message": data.get("error", "未知错误"), "data": data},
                    ensure_ascii=False,
                )
            return json.dumps(
                {"status": "success", "message": "ok", "data": data},
                ensure_ascii=False,
                default=str,
            )
        except TypeError as e:
            return json.dumps(
                {"status": "error", "message": f"参数错误: {e}", "data": {}},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"status": "error", "message": f"{type(e).__name__}: {e}", "data": {}},
                ensure_ascii=False,
            )


# ---------------------------------------------------------------------------
# 最小 MCP stdio server（--stdio，供 mcporter_bridge 接入）
# ---------------------------------------------------------------------------


def _stdio_main() -> None:
    bridge = Pdf2MdBridge()
    import asyncio

    tool_defs = [
        {
            "name": "pdf2md_convert",
            "description": "把单个论文 PDF 转为 Markdown（Docling 中文 OCR + 表格结构 + 图像提取，MarkItDown 降级）",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "PDF 文件路径"},
                    "output_dir": {"type": "string", "description": "输出目录（可选）"},
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "pdf2md_batch",
            "description": "批量转换目录下所有 PDF",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "dir_path": {"type": "string", "description": "目录路径"},
                    "output_dir": {"type": "string", "description": "输出目录（可选）"},
                },
                "required": ["dir_path"],
            },
        },
        {
            "name": "pdf2md_status",
            "description": "pdf2md 引擎可用性状态",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]

    async def _handle(msg: dict) -> Optional[dict]:
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "pdf2md_adapter", "version": "1.0.0"},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": tool_defs}}
        if method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name", "")
            args = params.get("arguments") or {}
            raw = await bridge.handle_handoff({"tool_name": name, "params": args})
            payload = json.loads(raw)
            is_err = payload.get("status") != "success"
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "content": [{"type": "text", "text": raw}],
                    "isError": is_err,
                },
            }
        if method in ("notifications/initialized", "ping"):
            return None
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }

    loop = asyncio.new_event_loop()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = loop.run_until_complete(_handle(msg))
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        _stdio_main()
    else:
        print("用法: python adapter.py --stdio  (MCP stdio server)")
