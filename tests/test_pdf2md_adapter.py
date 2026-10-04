"""台账⑤ pdf2md_adapter：fail-fast 与降级链单测。

真实 Docling 转换较重（模型下载+OCR），不放进单测；
真实论文验收走 papers/input 手工跑 pdf2md_convert。
这里覆盖：
- 路径校验 fail-fast（文件不存在/非 PDF/目录不存在）
- 双引擎均缺失时报错不静默
- Docling 缺失时走 MarkItDown 降级（手工最小 PDF 端到端）
- Bridge handle_handoff 分发约定（tool_name/平铺参数/错误格式）
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

_ADAPTER_PATH = (
    Path(__file__).resolve().parents[1]
    / "mcpserver"
    / "adapters"
    / "pdf2md_adapter"
    / "adapter.py"
)


def _load_adapter(monkeypatch) -> types.ModuleType:
    """文件级加载，假父包避免拉起 mcpserver/__init__ 全量依赖。"""
    pkg_chain = ["mcpserver", "mcpserver.adapters", "mcpserver.adapters.pdf2md_adapter"]
    for i, name in enumerate(pkg_chain):
        if name not in sys.modules:
            stub = types.ModuleType(name)
            stub.__path__ = []  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, name, stub)
    spec = importlib.util.spec_from_file_location("pdf2md_adapter_under_test", _ADAPTER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def adapter(monkeypatch):
    return _load_adapter(monkeypatch)


def _make_minimal_pdf(path: Path, text: str = "Hello pdf2md") -> None:
    """手工构造单页最小合法 PDF（文本层可被 pdfminer 提取）。"""
    stream_body = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream_body) + stream_body + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    path.write_bytes(bytes(out))


# ---------------------------------------------------------------------------
# fail-fast 路径校验
# ---------------------------------------------------------------------------


def test_convert_missing_file_fails(adapter):
    r = adapter.pdf2md_convert("/no/such/file.pdf")
    assert r["ok"] is False
    assert "不存在" in r["error"]


def test_convert_non_pdf_rejected(adapter, tmp_path):
    txt = tmp_path / "note.txt"
    txt.write_text("not a pdf", encoding="utf-8")
    r = adapter.pdf2md_convert(str(txt))
    assert r["ok"] is False
    assert "仅支持 .pdf" in r["error"]


def test_batch_missing_dir_fails(adapter):
    r = adapter.pdf2md_batch("/no/such/dir")
    assert r["ok"] is False
    assert "目录不存在" in r["error"]


def test_convert_no_engines_with_real_pdf(adapter, monkeypatch, tmp_path):
    monkeypatch.setattr(adapter, "_docling_available", lambda: False)
    monkeypatch.setattr(adapter, "_markitdown_available", lambda: False)
    pdf = tmp_path / "x.pdf"
    _make_minimal_pdf(pdf)

    r = adapter.pdf2md_convert(str(pdf))
    assert r["ok"] is False
    assert "引擎均不可用" in r["error"]


# ---------------------------------------------------------------------------
# MarkItDown 降级路径（端到端）
# ---------------------------------------------------------------------------


def test_markitdown_fallback_when_docling_missing(adapter, monkeypatch, tmp_path):
    monkeypatch.setattr(adapter, "_docling_available", lambda: False)
    monkeypatch.setattr(adapter, "_markitdown_available", lambda: True)
    pdf = tmp_path / "sample.pdf"
    _make_minimal_pdf(pdf, text="Fallback works")

    out_dir = tmp_path / "out"
    r = adapter.pdf2md_convert(str(pdf), output_dir=str(out_dir))

    assert r["ok"] is True, r
    assert r["engine"] == "markitdown"
    assert "Fallback works" in r["markdown"]
    assert Path(r["md_path"]).exists()


def test_batch_converts_all_pdfs(adapter, monkeypatch, tmp_path):
    monkeypatch.setattr(adapter, "_docling_available", lambda: False)
    monkeypatch.setattr(adapter, "_markitdown_available", lambda: True)
    src = tmp_path / "papers"
    src.mkdir()
    _make_minimal_pdf(src / "a.pdf", text="Paper A")
    _make_minimal_pdf(src / "b.pdf", text="Paper B")
    (src / "readme.txt").write_text("ignore me", encoding="utf-8")

    r = adapter.pdf2md_batch(str(src), output_dir=str(tmp_path / "out"))

    assert r["ok"] is True
    assert r["total"] == 2 and r["succeeded"] == 2
    names = sorted(x["filename"] for x in r["results"])
    assert names == ["a.pdf", "b.pdf"]


# ---------------------------------------------------------------------------
# Bridge handle_handoff
# ---------------------------------------------------------------------------


def test_bridge_missing_tool_name(adapter):
    r = asyncio.run(adapter.Pdf2MdBridge().handle_handoff({}))
    assert '"status": "error"' in r
    assert "tool_name" in r


def test_bridge_unknown_tool(adapter):
    r = asyncio.run(
        adapter.Pdf2MdBridge().handle_handoff({"tool_name": "nope"})
    )
    assert "未知工具" in r


def test_bridge_dispatches_status_with_flat_args(adapter):
    """registry 约定：tool_name + 参数平铺。pdf2md_status 无参也要能过。"""
    r = asyncio.run(
        adapter.Pdf2MdBridge().handle_handoff(
            {"tool_name": "pdf2md_status", "agentType": "mcp"}
        )
    )
    assert '"status": "success"' in r
    assert "docling" in r


def test_bridge_error_shape_for_bad_file(adapter):
    """工具级失败转成 status=error（fail-fast），不吞成 success。"""
    r = asyncio.run(
        adapter.Pdf2MdBridge().handle_handoff(
            {"tool_name": "pdf2md_convert", "file_path": "/no/such.pdf"}
        )
    )
    assert '"status": "error"' in r
    assert "不存在" in r


# ---------------------------------------------------------------------------
# registry 扫描加载（验收：接入 mcpserver/adapters/ 后能通过 MCPManager 加载）
# ---------------------------------------------------------------------------


def test_registry_scan_loads_adapter():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from mcpserver import mcp_registry

    mcp_registry.clear_registry()
    try:
        registered = mcp_registry.scan_and_register_mcp_agents(str(repo_root / "mcpserver"))
        assert "pdf2md_adapter" in registered
        instance = mcp_registry.get_service_instance("pdf2md_adapter")
        assert hasattr(instance, "handle_handoff")
        tools = mcp_registry.get_available_tools("pdf2md_adapter")
        assert {t["command"] for t in tools} == {
            "pdf2md_convert",
            "pdf2md_batch",
            "pdf2md_status",
        }
    finally:
        mcp_registry.clear_registry()
