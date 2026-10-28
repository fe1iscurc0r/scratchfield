"""toolknit_mcp · PDF 文本提取（**本包唯一的可选依赖缝**）。

工单 244 原本点名 ``pdf_extract_text(path)``，要求「PDF 文本字符串 + 页码位置元数据」。
预检实测 toolknit 上游**没有**这个能力（PDF 子命令里没有任何文本提取，MCP 侧 46 个工具也没有）
⇒ 244 主单当时把它如实记进 ``list_tools().capability_gaps``。**本模块把该缺口补上。**

设计纪律：**不自研 PDF 解析**，只做引擎编排（同族「不写第二套数学」纪律）。

引擎链（逐级降级，**全部惰性导入**）::

    1. pypdf       纯 Python、轻量；**逐页提取 ⇒ 天然带页码**（``auto`` 时首选）
    2. pymupdf     PyMuPDF 原生库；复杂版面/嵌入字体更稳，``layout=True`` 时另给**行级 bbox**
    3. adapter     仓内既有 ``mcpserver/adapters/pdf2md_adapter``（Docling / MarkItDown）。
                   质量最高（OCR + 表格结构），但**只给整篇 markdown、无逐页切分** ⇒ 页码信息丢失。

⚠️ **本文件是本包唯一允许触碰第三方库的地方**（``pypdf`` / ``pymupdf`` / ``docling`` / ``markitdown``）。
``__init__.py`` / ``workspace.py`` / ``tools.py`` / ``server.py`` 仍受「零第三方依赖」
静态扫描约束（``test_cli_layer_is_pure_stdlib``）；本文件由
``test_pdf_text_is_the_only_optional_seam`` 单独把关：**顶层 import 只能标准库**，
第三方必须写在函数体内（惰性），且引用的模块名必须在 :data:`_OPTIONAL_ENGINE_MODULES` 白名单内。

为什么第三级按**文件路径**加载适配器（不走 ``import mcpserver.adapters``）：
``mcpserver/adapters/__init__.py`` 带注册副作用，而这里只要那两个纯函数；
按路径加载既避开包初始化，也让「本模块只依赖那一个 .py 文件」这件事显式化。

``engine`` 语义：``auto``（默认）走降级链；显式给名字则**只用该引擎**（诊断时更需要确定性，
不要被静默降级掩盖）。环境变量 :data:`ENGINE_ENV` 可改默认值。
"""

from __future__ import annotations

import importlib.util
import os
from importlib.metadata import version as _dist_version
from pathlib import Path
from typing import Any

from .workspace import (
    WorkspaceError,
    rel_to_workspace,
    repo_root,
    resolve_input,
    resolve_output_dir,
)

#: 引擎选择覆盖入口（``auto`` / ``pypdf`` / ``pymupdf`` / ``adapter``）
ENGINE_ENV = "TOOLKNIT_PDF_ENGINE"

#: ``auto`` 时的降级链顺序
TEXT_ENGINE_CHAIN = ("pypdf", "pymupdf", "adapter")

#: 适配器只输出整篇 markdown，无逐页切分 ⇒ 用这个标签如实标注
ADAPTER_PAGE_LABEL = "整篇（上游适配器不提供逐页切分）"

#: 每页在**返回体**里的字符上限（完整文本始终落盘，见 ``output``）；0 = 不截断
DEFAULT_MAX_CHARS_PER_PAGE = 4000

#: ``layout=True`` 时每页最多返回的行数（防止返回体爆掉）
DEFAULT_MAX_LAYOUT_LINES = 40

#: 白名单：本文件允许引用的第三方模块（静态扫描据此把关，见 test_pdf_text_is_the_only_optional_seam）
_OPTIONAL_ENGINE_MODULES = frozenset({"pypdf", "pymupdf", "fitz", "docling", "markitdown"})

#: 合法文件头（用来把「扩展名叫 .pdf 但不是 PDF」挡在引擎之前）
_PDF_MAGIC = b"%PDF-"


class TextEngineUnavailable(RuntimeError):
    """引擎不可用 / 全部引擎失败 ⇒ 报**明确错误**，绝不返回空文本冒充成功。"""


# --------------------------------------------------------------------------- 引擎探测


def _find_spec(modname: str) -> bool:
    """模块是否可 import（**不真 import**，避免探测本身触发重依赖）。"""
    try:
        return importlib.util.find_spec(modname) is not None
    except (ImportError, ValueError):  # 父包缺失 / 模块名异常
        return False


def _version(modname: str) -> str | None:
    """发行版版本号（拿不到就 ``None``，不影响可用性判断）。"""
    try:
        return _dist_version(modname)
    except Exception:  # noqa: BLE001 - 元数据缺失不是错误
        return None


def adapter_path() -> Path:
    """仓内 ``pdf2md_adapter`` 的**文件**路径（不是模块路径）。"""
    return repo_root() / "mcpserver" / "adapters" / "pdf2md_adapter" / "adapter.py"


def _load_adapter() -> Any:
    """按文件路径加载适配器模块（不经 ``mcpserver.adapters`` 包初始化）。"""
    path = adapter_path()
    if not path.is_file():
        raise TextEngineUnavailable(f"仓内适配器不存在：{path}")
    spec = importlib.util.spec_from_file_location("toolknit_pdf2md_adapter", path)
    if spec is None or spec.loader is None:  # pragma: no cover - 环境异常
        raise TextEngineUnavailable(f"无法为适配器建 spec：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _adapter_engines() -> dict[str, Any]:
    """适配器内部两引擎（docling / markitdown）的可用性；不可用时给 ``error``。"""
    try:
        return dict(_load_adapter().engines_status())
    except Exception as exc:  # noqa: BLE001 - 探测失败一律视作不可用
        return {"error": f"{type(exc).__name__}: {exc}"}


def _engine_ready(name: str) -> bool:
    """该引擎**现在能否真干活**（适配器还要求其内部至少一个引擎在）。"""
    if name == "pypdf":
        return _find_spec("pypdf")
    if name == "pymupdf":
        return _find_spec("pymupdf") or _find_spec("fitz")
    if name == "adapter":
        detail = _adapter_engines()
        return bool(detail.get("docling") or detail.get("markitdown"))
    return False


def selected_engine() -> str:
    """当前默认引擎（环境变量优先，缺省 ``auto``）。"""
    return (os.environ.get(ENGINE_ENV, "") or "").strip().lower() or "auto"


def engines_status() -> dict[str, Any]:
    """引擎可用性快照（供 ``list_tools`` 自述与排障；**只做探测，不提取**）。"""
    detail = _adapter_engines()
    versions: dict[str, Any] = {}
    if _find_spec("pypdf"):
        versions["pypdf"] = _version("pypdf")
    if _find_spec("pymupdf") or _find_spec("fitz"):
        versions["pymupdf"] = _version("pymupdf")
    for key in ("docling", "markitdown"):
        if detail.get(f"{key}_version"):
            versions[key] = detail[f"{key}_version"]
    return {
        "pypdf": _find_spec("pypdf"),
        "pymupdf": _find_spec("pymupdf") or _find_spec("fitz"),
        "adapter": _engine_ready("adapter"),
        "adapter_path": str(adapter_path()),
        "adapter_engines": detail,
        "versions": versions,
        "chain": list(TEXT_ENGINE_CHAIN),
        "available_chain": [name for name in TEXT_ENGINE_CHAIN if _engine_ready(name)],
        "selected": selected_engine(),
    }


def _engine_hint() -> str:
    """引擎全不可用时给**可执行**的安装指引。"""
    available = [name for name in TEXT_ENGINE_CHAIN if _engine_ready(name)]
    if available:
        return f"当前可用引擎：{available}（把 engine 留空或设为 auto 即走降级链）"
    return ("本机无任何 PDF 文本引擎。装任一即可：``pip install pypdf``（最轻，够用）／"
            "``pip install pymupdf``（额外给行级 bbox）／"
            "``pip install \"docling-slim[standard]\"``（OCR + 表格，最重，即 pdf2md extra）")


def _resolve_chain(requested: str) -> list[str]:
    """把 ``requested`` 解析成实际要尝试的引擎序列。

    ``auto`` ⇒ 降级链里当前可用的引擎（顺序即优先级）；
    显式名字 ⇒ **只试它**（不可用则为空 ⇒ 上层报 ``ENGINE_UNAVAILABLE``）。
    显式模式刻意不降级：诊断时最怕「以为在用 A，其实悄悄跑了 B」。
    """
    if requested and requested != "auto":
        return [requested] if (requested in TEXT_ENGINE_CHAIN and _engine_ready(requested)) else []
    return [name for name in TEXT_ENGINE_CHAIN if _engine_ready(name)]


# --------------------------------------------------------------------------- 各引擎提取
# 约定：extractor 返回 (pages, meta)，其中 pages[i]["text"] 是**完整**文本；
#       截断只发生在返回体组装阶段（落盘文件永远完整）。


def _pages_from_pypdf(src: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """pypdf：逐页 ``extract_text()``。纯 Python，**页码天然来自页序**。"""
    from pypdf import PdfReader  # 惰性：本包唯一缝

    reader = PdfReader(str(src))
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append({"page": index + 1, "chars": len(text), "text": text})
    return pages, {
        "page_numbers": True,
        "layout": False,
        "encrypted": bool(getattr(reader, "is_encrypted", False)),
    }


def _import_pymupdf() -> Any:
    """PyMuPDF 的模块名在 1.24 起由 ``fitz`` 改为 ``pymupdf``（旧名仍可用但已弃用）。"""
    try:
        import pymupdf  # type: ignore
    except ImportError:  # pragma: no cover - 旧版本布局
        import fitz  # type: ignore
        return fitz
    return pymupdf


def _layout_lines(page: Any, max_lines: int) -> list[dict[str, Any]]:
    """行级 ``bbox`` —— 「页码位置」的字面落实：**页索引 + 行框**（含页高宽见 ``page_size``）。"""
    lines: list[dict[str, Any]] = []
    data = page.get_text("dict") or {}
    for block in data.get("blocks") or []:
        for line in block.get("lines") or []:
            text = "".join(str(span.get("text") or "") for span in (line.get("spans") or [])).strip()
            if not text:
                continue
            bbox = line.get("bbox") or (0, 0, 0, 0)
            lines.append({"text": text[:200], "bbox": [round(float(v), 2) for v in bbox]})
            if len(lines) >= max_lines:
                return lines
    return lines


def _pages_from_pymupdf(src: Path, *, layout: bool, max_lines: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """PyMuPDF：逐页 ``get_text()``；``layout=True`` 时另附行级 bbox。"""
    pymupdf = _import_pymupdf()
    doc = pymupdf.open(str(src))
    pages: list[dict[str, Any]] = []
    try:
        for index in range(doc.page_count):
            page = doc[index]
            text = page.get_text() or ""
            item: dict[str, Any] = {"page": index + 1, "chars": len(text), "text": text}
            if layout:
                rect = page.rect
                item["page_size"] = [round(float(rect.width), 2), round(float(rect.height), 2)]
                item["lines"] = _layout_lines(page, max_lines)
            pages.append(item)
    finally:
        doc.close()
    return pages, {
        "page_numbers": True,
        "layout": layout,
        "engine_module": getattr(pymupdf, "__name__", "pymupdf"),
    }


def _pages_from_adapter(src: Path, out_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """仓内 ``pdf2md_adapter``：Docling → MarkItDown 降级。**只给整篇 markdown，无页码。**"""
    module = _load_adapter()
    result = module.pdf2md_convert(str(src), output_dir=str(out_dir))
    if not result.get("ok"):
        raise TextEngineUnavailable(str(result.get("error") or "适配器转换失败"))
    markdown = str(result.get("markdown") or "")
    pages = [{"page": 1, "chars": len(markdown), "text": markdown, "page_label": ADAPTER_PAGE_LABEL}]
    return pages, {
        "page_numbers": False,
        "layout": False,
        "adapter_engine": result.get("engine"),
        "adapter_md_path": result.get("md_path"),
        "adapter_images": len(result.get("images") or []),
        "adapter_fallback_reason": result.get("fallback_reason"),
    }


def _run_engine(engine: str, src: Path, *, layout: bool, max_lines: int,
                out_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """按引擎名分派（未知引擎直接抛，交由上层记进 attempts）。"""
    if engine == "pypdf":
        return _pages_from_pypdf(src)
    if engine == "pymupdf":
        return _pages_from_pymupdf(src, layout=layout, max_lines=max_lines)
    if engine == "adapter":
        return _pages_from_adapter(src, out_dir)
    raise TextEngineUnavailable(f"未知引擎 {engine!r}（合法值：auto / {' / '.join(TEXT_ENGINE_CHAIN)}）")


# --------------------------------------------------------------------------- 工具入口


def _fail(name: str, error: str, code: str, **extra: Any) -> dict[str, Any]:
    """失败返回体（与 :mod:`tools` 的 ``_fail`` 同形：``{ok, tool, error, error_code}``）。"""
    payload: dict[str, Any] = {"ok": False, "tool": name, "error": error, "error_code": code}
    payload.update(extra)
    return payload


def _page_number_note(engine: str, layout: bool) -> str:
    if engine == "adapter":
        return (f"⚠️ 该引擎（{ADAPTER_PAGE_LABEL}）**不提供逐页切分** ⇒ 页码信息缺失。"
                "需要页码请装 pypdf 或 pymupdf，或显式 engine=pypdf。")
    if layout:
        return "页码 = 逐页索引（从 1 起）；``lines[].bbox`` 为**行级**坐标（页内坐标系，原点左上）。"
    return "页码 = 逐页索引（从 1 起）；本引擎不提供字符/行级坐标（需要坐标用 layout=True + pymupdf）。"


def extract_text(pdf_path: str, *, engine: str = "", max_chars_per_page: int = DEFAULT_MAX_CHARS_PER_PAGE,
                 layout: bool = False, max_layout_lines: int = DEFAULT_MAX_LAYOUT_LINES,
                 workspace: str | None = None) -> dict[str, Any]:
    """``pdf_text(pdf_path)`` —— 逐页提取 PDF 文本（**带页码**），完整文本落盘。

    Args:
        pdf_path: PDF 路径（必须在工作区内，见 :mod:`workspace` 的路径纪律）。
        engine: ``auto``（默认，走降级链）/ ``pypdf`` / ``pymupdf`` / ``adapter``。显式名字**不降级**。
        max_chars_per_page: 每页在**返回体**里的字符上限；0 = 不截断。落盘文件**总是完整**。
        layout: ``True`` 时（需 pymupdf）额外返回每页行级 ``bbox`` —— 工单原话「页码位置元数据」。
        max_layout_lines: ``layout=True`` 时每页最多返回的行数。

    Returns:
        ``{ok, tool, engine, engine_attempts, pages[], page_count, total_chars, output, ...}``；
        失败为 ``{ok: False, error, error_code}``（``INVALID_PATH`` / ``INVALID_SUFFIX`` /
        ``NOT_A_PDF`` / ``ENGINE_UNAVAILABLE`` / ``ENGINE_FAILED`` / ``IO_ERROR``）。
    """
    name = "pdf_text"
    try:
        src = resolve_input(pdf_path, workspace=workspace)
    except WorkspaceError as exc:
        return _fail(name, str(exc), "INVALID_PATH")
    if src.suffix.lower() != ".pdf":
        return _fail(name, f"仅接受 .pdf，收到 {src.suffix!r}", "INVALID_SUFFIX")
    try:
        if src.read_bytes()[: len(_PDF_MAGIC)] != _PDF_MAGIC:
            return _fail(name, "文件头不是 %PDF-（扩展名像 PDF，内容不是）", "NOT_A_PDF")
    except OSError as exc:
        return _fail(name, f"读取源文件失败：{exc}", "IO_ERROR")
    try:
        out_root = resolve_output_dir(workspace=workspace)
    except WorkspaceError as exc:
        return _fail(name, str(exc), "INVALID_WORKSPACE")

    requested = (engine or "").strip().lower() or selected_engine()
    chain = _resolve_chain(requested)
    if not chain:
        return _fail(name, f"引擎 {requested!r} 不可用。{_engine_hint()}",
                     "ENGINE_UNAVAILABLE", engine_requested=requested, engines=engines_status())

    attempts: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] | None = None
    meta: dict[str, Any] = {}
    used = ""
    for candidate in chain:
        try:
            pages, meta = _run_engine(candidate, src, layout=layout, max_lines=max_layout_lines,
                                      out_dir=out_root)
        except Exception as exc:  # noqa: BLE001 - 逐级降级：任何异常都算该级失败
            attempts.append({"engine": candidate, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            continue
        attempts.append({"engine": candidate, "ok": True})
        used = candidate
        break
    if pages is None:
        return _fail(name, f"全部引擎均失败：{attempts}", "ENGINE_FAILED",
                     engine_requested=requested, engine_attempts=attempts, engines=engines_status())

    full_text = "\n\n".join(f"# --- page {item['page']} ---\n{item['text']}" for item in pages)
    text_output = out_root / f"{src.stem}.txt"
    try:
        out_root.mkdir(parents=True, exist_ok=True)
        text_output.write_text(full_text, encoding="utf-8", newline="\n")
    except OSError as exc:
        return _fail(name, f"写产物失败：{exc}", "IO_ERROR")

    public_pages: list[dict[str, Any]] = []
    for item in pages:
        text = str(item["text"])
        clipped = text[:max_chars_per_page] if max_chars_per_page > 0 else text
        row: dict[str, Any] = {
            "page": item["page"],
            "chars": item["chars"],
            "text": clipped,
            "truncated": len(clipped) < len(text),
        }
        for key in ("page_label", "page_size", "lines"):
            if key in item:
                row[key] = item[key]
        public_pages.append(row)

    return {
        "ok": True,
        "tool": name,
        "engine": used,
        "engine_requested": requested,
        "engine_attempts": attempts,
        "engine_fallback": used != chain[0],
        "engine_detail": meta,
        "page_numbers": bool(meta.get("page_numbers")),
        "layout": bool(meta.get("layout")),
        "page_number_note": _page_number_note(used, bool(meta.get("layout"))),
        "pages": public_pages,
        "page_count": len(pages),
        "total_chars": sum(int(item["chars"]) for item in pages),
        "max_chars_per_page": max_chars_per_page,
        "truncated_in_response": any(bool(row["truncated"]) for row in public_pages),
        "source": rel_to_workspace(src, workspace=workspace),
        "source_bytes": src.stat().st_size,
        "output": rel_to_workspace(text_output, workspace=workspace),
        "output_abs": str(text_output),
        "output_bytes": len(full_text.encode("utf-8")),
        "wrote_files": True,
        "engines": engines_status(),
    }


__all__ = [
    "ADAPTER_PAGE_LABEL",
    "DEFAULT_MAX_CHARS_PER_PAGE",
    "DEFAULT_MAX_LAYOUT_LINES",
    "ENGINE_ENV",
    "TEXT_ENGINE_CHAIN",
    "TextEngineUnavailable",
    "adapter_path",
    "engines_status",
    "extract_text",
    "selected_engine",
]
