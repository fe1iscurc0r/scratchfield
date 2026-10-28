"""toolknit_mcp MCP 入口（工单244 任务一/二）—— 本地文件处理工作台。

对外工具（**白名单 5 个**，工单 §4 风险表：「46 个工具导致 LM 工具选择混乱」）::

    extract_palette(image_path, count)         → 色板（hex + 占比），只读
    pdf_inspect(pdf_path)                      → 页数/字节/名称，只读
    pdf_compress(pdf_path, level, output_name) → 压缩 PDF（用包自带 qpdf）
    ppt_to_pdf(pptx_path, output_name, dry_run)→ PPTX → PDF（依赖 LibreOffice）
    pdf_text(pdf_path, engine, layout)         → **逐页文本（带页码）**，由仓内引擎承接

其中 ``pdf_text`` 不在 toolknit CLI 里（上游**没有**该能力），而是由同包 :mod:`pdf_text`
用**仓内引擎**（pypdf / PyMuPDF / ``mcpserver/adapters/pdf2md_adapter``）承接 ——
补上工单原话「PDF 文本字符串 + 页码位置元数据」的缺口。

外加四个**只读诊断**（不产生产物，用于排障而非内容处理）::

    renderer_probe()      → LibreOffice 渲染器是否可用（唯一可靠判据）
    doctor()              → 外部依赖体检（qpdf / ffmpeg）
    workspace_info()      → 当前工作区边界与日志路径
    list_tools()          → 白名单自述

接线形态**对齐同族先例**（``mcpserver/rf_workflow/server.py`` 的 ``RfWorkflowBridge``、
``mcpserver/antenna_sim/tools.py`` 的 ``AntennaSimBridge``）：类方法
``handle_handoff(task) -> str``（返回 JSON 字符串），由 ``mcpserver/mcp_registry.py`` 扫
``agent-manifest.json`` 自动登记（Format A），经 ``MCPManager.unified_call`` 路由。
**不需要改任何既有文件。**

⚠️ 与工单 §2 任务一.1 的**刻意偏离**：工单写「用 ``mcp`` Python SDK 启 stdio 子进程」。
实测本仓 ``requirements.txt`` **不含 ``mcp`` 包**，且 ``mcpserver/AGENTS.md`` 明载原生范式
是「manifest + ``ALLOWED_MODULE_PREFIXES``」⇒ 引一个用不上的 SDK 依赖只会增加面。
**工单要的实质（Python server 用 subprocess 驱动 npm CLI）本模块完全满足**
（见 :mod:`tools` 的 ``run_cli``），只是接线走仓内既有契约而非另起一套。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from . import pdf_text as tk_pdf_text
from . import tools as tk_tools
from .workspace import (
    OUTPUT_SUBDIR,
    WORKSPACE_ROOT_ENV,
    WorkspaceError,
    rel_to_workspace,
    resolve_log_path,
    workspace_root,
)

logger = logging.getLogger(__name__)


class ToolknitBridge:
    """toolknit 本地文件处理能力的 MCP 入口（薄编排层，不重算任何文件处理逻辑）。"""

    # ---- 工具一：色板 ----

    def extract_palette(self, image_path: str, count: int = 5,
                        workspace: str | None = None,
                        timeout: int = tk_tools.DEFAULT_TIMEOUT_S) -> dict[str, Any]:
        """图片主色板。``count`` 合法区间 2-9，且为**上界**（纯色图可能只返回 1 色）。"""
        return tk_tools.extract_palette(image_path, count=count, workspace=workspace,
                                        timeout=timeout)

    # ---- 工具二：PDF 元数据 ----

    def pdf_inspect(self, pdf_path: str, workspace: str | None = None,
                    timeout: int = tk_tools.DEFAULT_TIMEOUT_S) -> dict[str, Any]:
        """PDF 元数据（页数/字节/名称）。**替代工单点名的 ``pdf_extract_text``**。

        ⚠️ toolknit 的 PDF 子命令只有
        ``inspect/merge/split/rotate/encrypt/decrypt/compress/enhance/to-image``，
        MCP 侧 46 个工具里也**没有任何 PDF 文本提取** ⇒ 「PDF 文本字符串 + 页码位置」
        这一能力在上游**不存在**（详见 README 偏差表与预检报告 §1）。
        仓内既有文本提取在 ``mcpserver/adapters/pdf2md_adapter``（Docling/MarkItDown），
        本模块**不重复造**，故此处只提供上游真实存在的能力。
        """
        return tk_tools.pdf_inspect(pdf_path, workspace=workspace, timeout=timeout)

    # ---- 工具三：PDF 压缩 ----

    def pdf_compress(self, pdf_path: str, level: str = "medium", output_name: str = "",
                     workspace: str | None = None,
                     timeout: int = tk_tools.DEFAULT_TIMEOUT_S) -> dict[str, Any]:
        """压缩 PDF（qpdf 由 npm 包自带，实测 ``vendor/qpdf/qpdf.exe``）。产物落工作区。"""
        return tk_tools.pdf_compress(pdf_path, level=level, output_name=output_name,
                                     workspace=workspace, timeout=timeout)

    # ---- 工具四：PPTX → PDF ----

    def ppt_to_pdf(self, pptx_path: str, output_name: str = "", dry_run: bool = False,
                   workspace: str | None = None,
                   timeout: int = tk_tools.DEFAULT_TIMEOUT_S) -> dict[str, Any]:
        """PPTX → PDF。**依赖本机 LibreOffice**；``dry_run=True`` 只探测不写盘。

        输出路径过长触发 soffice 静默 fail-fast 时**会自动改短目录重试再搬回**，
        详见返回体的 ``path_fallback``。
        """
        return tk_tools.ppt_to_pdf(pptx_path, output_name=output_name, dry_run=dry_run,
                                   workspace=workspace, timeout=timeout)

    # ---- 工具五：PDF 文本（**仓内引擎**，非 toolknit CLI）----

    def pdf_text(self, pdf_path: str, engine: str = "",
                 max_chars_per_page: int = tk_pdf_text.DEFAULT_MAX_CHARS_PER_PAGE,
                 layout: bool = False,
                 max_layout_lines: int = tk_pdf_text.DEFAULT_MAX_LAYOUT_LINES,
                 workspace: str | None = None) -> dict[str, Any]:
        """**逐页**提取 PDF 文本（带页码），完整文本落盘到工作区。

        ⚠️ 本工具**不经 toolknit CLI** —— 上游没有 PDF 文本提取能力（预检实证）。
        引擎链 ``pypdf → pymupdf → pdf2md_adapter``：``engine="auto"``（默认）逐级降级；
        显式给名字则**只用该引擎**（诊断时不被静默降级掩盖）。
        ``layout=True``（需 pymupdf）额外返回每页行级 ``bbox`` = 工单原话的「页码位置元数据」。
        """
        return tk_pdf_text.extract_text(pdf_path, engine=engine,
                                        max_chars_per_page=max_chars_per_page,
                                        layout=layout, max_layout_lines=max_layout_lines,
                                        workspace=workspace)

    # ---- 只读诊断 ----

    def renderer_probe(self, timeout: int = tk_tools.DEFAULT_TIMEOUT_S) -> dict[str, Any]:
        """LibreOffice 渲染器可用性（``ppt to-pdf --dry-run``，约 3.2 s，不写盘）。"""
        return tk_tools.renderer_probe(timeout=timeout)

    def doctor(self, timeout: int = tk_tools.DEFAULT_TIMEOUT_S) -> dict[str, Any]:
        """外部依赖体检。⚠️ 实测**不检查 LibreOffice**，要判它用 ``renderer_probe``。"""
        return tk_tools.doctor(timeout=timeout)

    def cli_version(self, timeout: int = tk_tools.DEFAULT_TIMEOUT_S) -> dict[str, Any]:
        """CLI 连通性 + 实际版本（``npx -y <pkg> --version``）。"""
        info = tk_tools.cli_version_probe(timeout=timeout)
        return {"ok": info["ok"], "tool": "cli_version",
                "requested_version": info["requested_version"],
                "reported_version": info["reported_version"],
                "package": tk_tools.CLI_PACKAGE, "spec": tk_tools.cli_spec(),
                "error": info["error"], "elapsed_s": info["elapsed_s"]}

    def workspace_info(self) -> dict[str, Any]:
        """当前工作区根、产物目录、日志路径（排障用；**不触碰网络或子进程**）。"""
        root = workspace_root()
        try:
            log = resolve_log_path(create=False)
            log_path: str | None = str(log)
        except (WorkspaceError, OSError):
            log_path = None
        return {
            "ok": True,
            "tool": "workspace_info",
            "workspace_root": str(root),
            "workspace_root_env": WORKSPACE_ROOT_ENV,
            "output_subdir": OUTPUT_SUBDIR,
            "repo_root": str(Path(__file__).resolve().parents[2]),
            "log_path": log_path,
            "exists": root.is_dir(),
        }

    # ---- 白名单自述 ----

    _TOOLS: dict[str, str] = {
        "extract_palette": "extract_palette",
        "pdf_inspect": "pdf_inspect",
        "pdf_compress": "pdf_compress",
        "ppt_to_pdf": "ppt_to_pdf",
        "pdf_text": "pdf_text",
        "renderer_probe": "renderer_probe",
        "doctor": "doctor",
        "cli_version": "cli_version",
        "workspace_info": "workspace_info",
        # ⚠️ list_tools 必须在此表内，否则 handle_handoff 会把它当未知工具。
        # 这个漏登记由 test_manifest_entrypoint_resolves_and_has_handoff_contract
        # （比对 manifest 声明的 invocationCommands 与 _TOOLS）抓出并修掉——
        # 只把方法写在类上、不登记进 _TOOLS，LM 是**调不到**的。
        "list_tools": "list_tools",
    }

    def list_tools(self) -> dict[str, Any]:
        """自述白名单（工单 §4：「只暴露 PoC 工具 + 白名单」，避免 LM 工具选择混乱）。"""
        return {
            "ok": True,
            "tool": "list_tools",
            "count": len(self._TOOLS),
            "tools": sorted(self._TOOLS),
            "not_exposed_note": (
                f"{tk_tools.CLI_PACKAGE} 自带 46 个 MCP 工具；本模块**只**转发上述白名单，"
                "其余一律不经由本 server 暴露（避免 LM 工具选择混乱）。"
            ),
            "cli_tools": ["extract_palette", "pdf_inspect", "pdf_compress", "ppt_to_pdf"],
            "in_repo_tools": ["pdf_text"],
            "pdf_text_engines": tk_pdf_text.engines_status(),
            "capability_gaps": [
                "pdf_extract_text（**toolknit 上游不存在**）⇒ 由本包 pdf_text 用仓内引擎承接，"
                "已**不是**缺口（见 README §2 / §5.2）",
            ],
        }

    # ---- handoff ----

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        """MCP 契约入口：``task -> JSON 字符串``（形态对齐 ``RfWorkflowBridge``）。"""
        tool = str((task or {}).get("tool_name") or "")
        fn_name = self._TOOLS.get(tool)
        if fn_name is None:
            return json.dumps(
                {"status": "error",
                 "message": f"未知工具 {tool}，可用: {', '.join(sorted(self._TOOLS))}",
                 "data": {}}, ensure_ascii=False)

        if isinstance(task.get("params"), dict):
            arguments = dict(task["params"])
        else:
            arguments = {k: v for k, v in task.items()
                         if not k.startswith("_")
                         and k not in ("tool_name", "agentType", "service_name")}

        started = time.monotonic()
        try:
            data = await asyncio.to_thread(lambda: getattr(self, fn_name)(**arguments))
        except TypeError as exc:
            self._log(tool, arguments, None, started)
            return json.dumps({"status": "error", "message": f"参数错误: {exc}", "data": {}},
                              ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[toolknit_mcp] %s 执行失败: %s", tool, exc)
            self._log(tool, arguments, None, started, error=f"{type(exc).__name__}: {exc}")
            return json.dumps({"status": "error", "message": f"{type(exc).__name__}: {exc}",
                               "data": {}}, ensure_ascii=False)
        self._log(tool, arguments, data, started)
        ok = bool(data.get("ok"))
        return json.dumps({"status": "success" if ok else "error",
                           "message": "ok" if ok else str(data.get("error") or "failed"),
                           "data": data}, ensure_ascii=False, default=str)

    # ---- 调用日志（JSONL append）----

    def _log(self, tool: str, arguments: dict[str, Any], data: dict[str, Any] | None,
             started: float, *, error: str | None = None) -> None:
        """每次 handoff 追加一行 JSONL。**日志失败绝不影响主调用**（best-effort）。"""
        entry = {
            "ts": time.time(),
            "tool": tool,
            "args": _safe_args(arguments),
            "ok": bool((data or {}).get("ok")) if data is not None else False,
            "error": error or (None if data is None else (data.get("error") if
                                                          not data.get("ok") else None)),
            "error_code": None if data is None else data.get("error_code"),
            "cli_version": data.get("cli_version") if data else None,
            "elapsed_s": round(time.monotonic() - started, 3),
        }
        if data:
            for key in ("source", "output", "output_dir", "pages", "returned_count"):
                if key in data:
                    entry[key] = data[key]
        try:
            tk_tools.log_call(entry)
        except (WorkspaceError, OSError) as exc:  # pragma: no cover - 环境相关
            logger.debug("[toolknit_mcp] 写调用日志失败（忽略）: %s", exc)


def _safe_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """只记录**标量**参数（避免把大对象/路径全文灌进日志）；路径只记文件名。"""
    safe: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            if key.endswith("_path") and isinstance(value, str):
                safe[key] = Path(value).name
            else:
                safe[key] = value
    return safe


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    """手工复现入口（工单要求每个 PoC 必须**可观测**，故提供等价 CLI）。"""
    parser = argparse.ArgumentParser(
        description="toolknit_mcp CLI（工单244 手工复现 PoC）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pal = sub.add_parser("palette", help="图片主色板")
    pal.add_argument("--image", required=True)
    pal.add_argument("--count", type=int, default=5)

    ins = sub.add_parser("pdf-inspect", help="PDF 元数据")
    ins.add_argument("--pdf", required=True)

    cmp_ = sub.add_parser("pdf-compress", help="压缩 PDF")
    cmp_.add_argument("--pdf", required=True)
    cmp_.add_argument("--level", default="medium", choices=list(tk_tools.COMPRESS_LEVELS))
    cmp_.add_argument("--output-name", default="")

    ppt = sub.add_parser("ppt-to-pdf", help="PPTX → PDF")
    ppt.add_argument("--pptx", required=True)
    ppt.add_argument("--output-name", default="")
    ppt.add_argument("--dry-run", action="store_true")

    txt = sub.add_parser("pdf-text", help="PDF 逐页文本（仓内引擎，非 toolknit CLI）")
    txt.add_argument("--pdf", required=True)
    txt.add_argument("--engine", default="",
                     choices=["", *tk_pdf_text.TEXT_ENGINE_CHAIN, "auto"])
    txt.add_argument("--max-chars-per-page", type=int, default=tk_pdf_text.DEFAULT_MAX_CHARS_PER_PAGE)
    txt.add_argument("--layout", action="store_true")

    sub.add_parser("renderer-probe", help="LibreOffice 渲染器探测")
    sub.add_parser("doctor", help="外部依赖体检")
    sub.add_parser("version", help="CLI 连通性与版本")
    sub.add_parser("workspace-info", help="工作区边界")
    sub.add_parser("list-tools", help="白名单自述")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bridge = ToolknitBridge()
    if args.command == "palette":
        out = bridge.extract_palette(args.image, count=args.count)
    elif args.command == "pdf-inspect":
        out = bridge.pdf_inspect(args.pdf)
    elif args.command == "pdf-compress":
        out = bridge.pdf_compress(args.pdf, level=args.level, output_name=args.output_name)
    elif args.command == "ppt-to-pdf":
        out = bridge.ppt_to_pdf(args.pptx, output_name=args.output_name, dry_run=args.dry_run)
    elif args.command == "pdf-text":
        out = bridge.pdf_text(args.pdf, engine=args.engine, layout=args.layout,
                              max_chars_per_page=args.max_chars_per_page)
    elif args.command == "renderer-probe":
        out = bridge.renderer_probe()
    elif args.command == "doctor":
        out = bridge.doctor()
    elif args.command == "version":
        out = bridge.cli_version()
    elif args.command == "workspace-info":
        out = bridge.workspace_info()
    else:
        out = bridge.list_tools()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["ToolknitBridge", "build_parser", "main"]
