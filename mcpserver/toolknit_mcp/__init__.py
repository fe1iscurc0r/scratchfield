"""toolknit 本地文件处理工作台（工单244 · 漏斗 2.0 轻量猎手第 3 单）。

把 **外部 npm 包** ``@toolknit/cli`` 的本地文件处理能力接入 scratchpad 的
``mcpserver/`` 体系，只暴露白名单内少数工具，**不引入上游约 154 MB 的桌面端 monorepo**
（实测其仓库体积 157,367 KB）。

模块划分：

- :mod:`workspace` 工作区路径纪律（工单 §1 目标 4：禁止相对路径 / 跨目录）
- :mod:`tools`     CLI 适配层（子进程转发 + 参数校验 + 输出归一 + JSONL 日志）
- :mod:`pdf_text`  **PDF 文本提取**（工单原话「文本 + 页码位置」）—— 不经 CLI，
  由**仓内引擎**（pypdf / PyMuPDF / ``mcpserver/adapters/pdf2md_adapter``）承接
- :mod:`server`    MCP 入口（``ToolknitBridge``，9 个白名单工具 + 手工复现 CLI）

依赖边界
--------
``__init__`` / ``workspace`` / ``tools`` / ``server`` 为**零第三方运行时依赖**（纯标准库）。
唯一的例外是 :mod:`pdf_text`：它按需**惰性**导入 PDF 引擎（``pypdf`` / ``pymupdf`` / Docling），
且引擎全部缺失时会返回明确的 ``ENGINE_UNAVAILABLE`` 而**不是**假装成功。
这条缝由 ``test_pdf_text_is_the_only_optional_seam`` 单独把关。

真正的文件处理能力来自外部 npm 包 ``@toolknit/cli``（实测 latest ``2.3.1``），
由 ``npx`` 按需拉起 ⇒ **不要把 npm 包写进 Python 依赖**（见 :mod:`tools` 的
``CLI_PACKAGE`` 与 ``requirements.txt`` 的说明）。

能力边界（实测）
--------------
上游 **没有** PDF 文本提取（``pdf_extract_text`` 不存在）⇒ 本包用 :mod:`pdf_text`
（仓内引擎）**承接**该需求，不再列为缺口。
``ppt_to_pdf`` 依赖本机 LibreOffice，缺失时返回 ``DEPENDENCY_MISSING`` 而不假装成功；
输出路径过长触发 soffice 静默 fail-fast 时会**自动改短目录重试再把产物搬回**（见 :mod:`tools`）。
"""

from . import pdf_text
from .server import ToolknitBridge, build_parser, main
from .workspace import WorkspaceError

__all__ = ["ToolknitBridge", "WorkspaceError", "build_parser", "main", "pdf_text"]
