"""工单244 验收：toolknit 本地文件工作台（toolknit_mcp）。

覆盖：

- 任务一骨架：白名单工具集合、``handle_handoff`` 契约（未知工具 / 参数错误 / JSON 字符串返回）、
  manifest Format A 的 ``entryPoint`` 可解析且类具备 ``handle_handoff``
- 任务二三个 PoC **真跑**（子进程转发 ``npx @toolknit/cli``）：
  色板（双色 / 纯色两种形态）、PDF 元数据、PDF 压缩、PPTX→PDF
- 工作区路径纪律（工单 §1 目标 4）：相对路径 / 跨目录 / 不存在的路径 / 非法工作区名全部拒绝
- 调用日志 JSONL **append** 语义（工单铁律）
- 两条**反直觉事实的回归**（都在 README/requirements 里写明，靠测试钉死）：
  1. ``doctor`` **不检查 LibreOffice**（拿它判依赖会假阴性）
  2. ``image colors --count`` 是**上界不是产量**（纯色图 count=2 也只返回 1 色）
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from mcpserver.toolknit_mcp import server, tools, workspace

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

#: ToolKnit CLI 是**外部二进制**（PDF 的 qpdf、office 的 libreoffice、调色都经它）。
#: 本机 / CI 没装时只跳过**真正要调它**的用例 —— 不整文件跳过，因为静态契约类
#: （行尾 / 文件清单 / 骨架）不依赖 CLI，必须继续跑。
#: 2026-10-30 实测：CI 上 10 条红的全是同一个原因「'toolknit' 不是内部或外部命令」，
#: 长期挂着会把真故障淹掉。
_TOOLKNIT_CLI = shutil.which("toolknit")
requires_toolknit = pytest.mark.skipif(
    _TOOLKNIT_CLI is None,
    reason="本机没有 ToolKnit CLI（外部依赖），该用例需要真实 CLI 才能跑",
)

#: 模块内相对资源（夹具随模块交付，路径不依赖当前工作目录）
PKG_ROOT = Path(server.__file__).resolve().parent
FIXTURES = PKG_ROOT / "tests" / "_fixtures"
REPO_ROOT = PKG_ROOT.parent.parent

#: 夹具实测字节数（生成器 make_fixtures 的确定性产物，作为「产物没被改坏」的锚点）
SAMPLE_PDF = FIXTURES / "sample.pdf"
SAMPLE_PPTX = FIXTURES / "sample.pptx"
SOLID_RED = FIXTURES / "solid_red.png"
TWO_TONE = FIXTURES / "two_tone.png"

SAMPLE_PDF_BYTES = 114618
SAMPLE_PDF_PAGES = 3
SAMPLE_PPTX_SLIDES = 2

#: 夹具 two_tone.png 的两个颜色（左红右蓝，各 50%）
TWO_TONE_HEXES = {"#DC1E28", "#1428DC"}
TWO_TONE_PIXELS = 1280


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(scope="module", autouse=True)
def ws(tmp_path_factory):
    """把工作区根重定向到一个**短**临时目录，并把夹具复制进去。

    ⚠️ 为什么不用 pytest 的 ``tmp_path``：实测本机 ``tmp_path`` 形如
    ``%TEMP%\\pytest-of-ASUS\\pytest-N\\toolknit-ws0``，加上 ``toolknit-output``
    后长度 **87 字符 > 83**，会让 LibreOffice 静默 fail-fast
    （见 README §5.1 与 ``tools.LIBREOFFICE_OUTPUT_PATH_LIMIT``）——
    于是 PPT 用例全红，**但根因不在被测代码**。故这里自建短目录并自行清理。

    直接改 ``os.environ`` 是因为工作区根是**每次调用现读**的；退出时完整还原，
    避免污染同进程内的其它测试。
    """
    root = Path(tempfile.mkdtemp(prefix="tk244-"))
    try:
        shutil.copy2(SAMPLE_PDF, root / "sample.pdf")
        shutil.copy2(SAMPLE_PPTX, root / "sample.pptx")
        shutil.copy2(SOLID_RED, root / "solid_red.png")
        shutil.copy2(TWO_TONE, root / "two_tone.png")
        log = root / "logs" / "calls.jsonl"

        # 前置守卫：环境本身的 TEMP 若已太深，直接说清楚而不是让 PPT 用例神秘失败
        probe_len = len(str(root / workspace.OUTPUT_SUBDIR))
        assert probe_len <= tools.LIBREOFFICE_OUTPUT_PATH_LIMIT, (
            f"临时工作区路径 {root} 过长（{probe_len} > "
            f"{tools.LIBREOFFICE_OUTPUT_PATH_LIMIT}），LibreOffice 必然 fail-fast。"
            f"请把 %TEMP% 指到更短的路径再跑测试。"
        )

        saved = {k: os.environ.get(k)
                 for k in (workspace.WORKSPACE_ROOT_ENV, "TOOLKNIT_LOG_PATH")}
        os.environ[workspace.WORKSPACE_ROOT_ENV] = str(root)
        os.environ["TOOLKNIT_LOG_PATH"] = str(log)
        try:
            yield root
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture()
def bridge():
    return server.ToolknitBridge()


@pytest.fixture(scope="module")
def renderer():
    """LibreOffice 可用性（**唯一可靠判据**：``renderer_probe``，不是 ``doctor``）。"""
    return tools.renderer_probe()


def _call(bridge, tool_name, **params):
    """同步跑一次 handoff（契约入口本身就是它，测试不该绕过它调方法）。"""
    import asyncio

    task = {"tool_name": tool_name}
    if params:
        task["params"] = params
    raw = asyncio.run(bridge.handle_handoff(task))
    assert isinstance(raw, str), "handle_handoff 必须返回 JSON 字符串"
    return json.loads(raw)


# ----------------------------------------------------------------- 任务一：骨架 / 契约


def test_whitelist_is_small_and_stable(bridge):
    """工单 §4：只暴露少数工具，避免上游 46 工具导致 LM 选择混乱。"""
    info = bridge.list_tools()
    assert info["ok"] is True
    assert info["count"] == len(server.ToolknitBridge._TOOLS)
    # 四个内容处理工具必须在
    for name in ("extract_palette", "pdf_inspect", "pdf_compress", "ppt_to_pdf"):
        assert name in info["tools"]
    # 白名单必须远小于上游 46（否则等于没做白名单）
    assert info["count"] < 46
    # 已知能力缺口要如实列出，不能假装有
    assert any("pdf_extract_text" in gap for gap in info["capability_gaps"])


def test_manifest_entrypoint_resolves_and_has_handoff_contract():
    """manifest 用 Format A；且 ``mcp_registry`` 的深检契约必须能通过。

    复刻 ``mcp_registry.verify_entrypoint`` 的判定：前缀白名单 → import →
    getattr → ``handle_handoff`` 存在。
    """
    manifest = json.loads((PKG_ROOT / "agent-manifest.json").read_text(encoding="utf-8"))
    assert manifest["agentType"] == "mcp"
    assert manifest["name"] == "toolknit_mcp"

    ep = manifest["entryPoint"]
    module_name, class_name = ep["module"], ep["class"]
    assert any(module_name.startswith(p) for p in ("mcpserver.", "vendor."))
    assert module_name == "mcpserver.toolknit_mcp.server"

    module = importlib.import_module(module_name)
    target = getattr(module, class_name)
    assert hasattr(target, "handle_handoff")

    # 声明的 invocationCommands 必须与代码里的白名单**逐一对上**（防文档漂移）
    declared = {c["command"] for c in manifest["capabilities"]["invocationCommands"]}
    assert declared == set(server.ToolknitBridge._TOOLS)


def test_handoff_unknown_tool_is_structured_error(bridge):
    out = _call(bridge, "no_such_tool")
    assert out["status"] == "error"
    assert "未知工具" in out["message"]
    assert "可用" in out["message"]


def test_handoff_bad_params_is_type_error(bridge):
    """参数名写错应得到「参数错误」而不是 500。"""
    out = _call(bridge, "extract_palette", wrong_kwarg=1)
    assert out["status"] == "error"
    assert "参数错误" in out["message"]


@requires_toolknit
def test_handoff_accepts_flat_task_without_params(bridge):
    """除 ``params`` 外，也接受扁平 task（与 242/243 同款）。"""
    import asyncio

    task = {"tool_name": "extract_palette", "image_path": str(ws_path("two_tone.png")),
            "count": 2, "_internal": "ignored", "agentType": "mcp"}
    out = json.loads(asyncio.run(bridge.handle_handoff(task)))
    assert out["status"] == "success", out
    assert out["data"]["returned_count"] == 2


def ws_path(name: str) -> Path:
    """夹具在工作区里的绝对路径（工作区根由 module fixture 设好）。"""
    return workspace.workspace_root() / name


# --------------------------------------------------------------------- 任务二 PoC：色板


@requires_toolknit
def test_palette_two_tone_happy_path(bridge):
    """happy path：双色图返回两色，像素数与占比可复算。"""
    out = _call(bridge, "extract_palette", image_path=str(ws_path("two_tone.png")), count=5)
    assert out["status"] == "success", out
    data = out["data"]

    assert data["ok"] is True
    assert data["returned_count"] == 2
    assert data["wrote_files"] is False          # 只读，绝不写盘
    assert data["dominant"] in TWO_TONE_HEXES
    assert {e["hex"] for e in data["palette"]} == TWO_TONE_HEXES

    # 不变量：像素数加起来等于可见像素；占比加起来等于 100
    assert sum(e["pixels"] for e in data["palette"]) == TWO_TONE_PIXELS
    assert sum(e["percentage"] for e in data["palette"]) == pytest.approx(100.0)
    for entry in data["palette"]:
        assert {"hex", "rgb", "hsl", "pixels", "percentage"} <= set(entry)


@requires_toolknit
def test_palette_count_is_an_upper_bound_not_a_quota(bridge):
    """**反直觉事实的回归**：纯色图即使 ``count=2`` 也只返回 1 色。

    实测（2026-10-14）：``color.extract`` 的 ``--count`` 是上界，不是保证。
    若哪天上游改成「凑够 N 色」，本测试会红——那时要同步改 README 与 docstring。
    """
    out = _call(bridge, "extract_palette", image_path=str(ws_path("solid_red.png")), count=2)
    assert out["status"] == "success", out
    data = out["data"]
    assert data["requested_count"] == 2
    assert data["returned_count"] == 1
    assert data["returned_count"] <= data["requested_count"]
    assert data["palette"][0]["hex"] == "#DC1E28"
    assert data["palette"][0]["percentage"] == pytest.approx(100.0)


@pytest.mark.parametrize("bad", [1, 0, -1, 10, 99])
def test_palette_count_out_of_range_is_rejected(bridge, bad):
    """count 合法区间 2-9；越界必须在**调 CLI 之前**就被拦下（错误码可区分）。"""
    out = _call(bridge, "extract_palette", image_path=str(ws_path("two_tone.png")), count=bad)
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "INVALID_COUNT"


def test_palette_count_non_integer_is_rejected(bridge):
    out = _call(bridge, "extract_palette", image_path=str(ws_path("two_tone.png")), count="five")
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "INVALID_COUNT"


# ------------------------------------------------------------------ 任务二 PoC：PDF


@requires_toolknit
def test_pdf_inspect_happy_path(bridge):
    """happy path：页数 / 字节 / 名称与夹具一致。"""
    out = _call(bridge, "pdf_inspect", pdf_path=str(ws_path("sample.pdf")))
    assert out["status"] == "success", out
    data = out["data"]
    assert data["ok"] is True
    assert data["pages"] == SAMPLE_PDF_PAGES
    assert data["bytes"] == SAMPLE_PDF_BYTES
    assert data["name"] == "sample.pdf"
    assert data["wrote_files"] is False


def test_pdf_inspect_missing_file_is_boundary_case(bridge):
    """**边界（工单 §3.1 点名）**：PDF 不存在 ⇒ 结构化错误，不是异常。"""
    out = _call(bridge, "pdf_inspect", pdf_path=str(ws_path("nope.pdf")))
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "WORKSPACE_VIOLATION"
    assert "不存在" in out["data"]["error"]


def test_pdf_inspect_rejects_non_pdf_suffix(bridge):
    out = _call(bridge, "pdf_inspect", pdf_path=str(ws_path("two_tone.png")))
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "INVALID_SUFFIX"


@requires_toolknit
def test_pdf_compress_happy_path(bridge):
    """happy path：压缩后更小、页数不变、产物落工作区且**不回写源目录**。"""
    src = ws_path("sample.pdf")
    src_bytes = src.stat().st_size
    out = _call(bridge, "pdf_compress", pdf_path=str(src), level="high",
                output_name="compressed.pdf")
    assert out["status"] == "success", out
    data = out["data"]

    assert data["exists"] is True
    assert data["source_bytes"] == src_bytes
    assert data["output_bytes"] < src_bytes          # 压缩真的生效
    assert data["source"] != data["output"]          # 产物不是源文件
    assert src.stat().st_size == src_bytes           # 源文件未被改动
    # 产物必须落 toolknit-output/，不落源目录
    assert data["output"].startswith(f"{workspace.OUTPUT_SUBDIR}/")


def test_pdf_compress_level_must_be_whitelisted(bridge):
    out = _call(bridge, "pdf_compress", pdf_path=str(ws_path("sample.pdf")), level="ultra")
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "INVALID_LEVEL"


@requires_toolknit
def test_pdf_compress_refuses_to_overwrite_source(bridge, ws):
    """源文件本身已在 ``toolknit-output/`` 内、且产物同名 ⇒ 拒绝，避免覆盖源 PDF。

    ⚠️ 这条守卫的**可达条件**要说清楚：产物恒落 ``toolknit-output/``，而源文件通常
    在工作区别处 ⇒ 两者天然不同路径，「与源同名」本身并不危险。
    只有**源文件恰好也在产物目录里**时才会撞车。

    （第一版把源放在工作区根，断言「应当拒绝」——测试红了，实测证明守卫根本没触发，
    错的是测试前提不是代码。这条注释就是那次实测的留证。）
    """
    out_dir = ws / workspace.OUTPUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    src = out_dir / "redo.pdf"
    shutil.copy2(SAMPLE_PDF, src)

    out = _call(bridge, "pdf_compress", pdf_path=str(src), output_name="redo.pdf")
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "OUTPUT_IS_SOURCE"
    assert src.stat().st_size == SAMPLE_PDF_BYTES     # 源文件分毫未动


@requires_toolknit
def test_pdf_compress_same_name_outside_output_dir_is_safe(bridge, ws):
    """对照组：源在工作区别处时，产物同名**无害**（落产物目录，源不动）。"""
    src = ws / "shadow.pdf"
    shutil.copy2(SAMPLE_PDF, src)

    out = _call(bridge, "pdf_compress", pdf_path=str(src), output_name="shadow.pdf")
    assert out["status"] == "success", out
    assert out["data"]["output"] == f"{workspace.OUTPUT_SUBDIR}/shadow.pdf"
    assert out["data"]["source"] == "shadow.pdf"
    assert src.stat().st_size == SAMPLE_PDF_BYTES


def test_pdf_compress_output_name_cannot_escape(bridge):
    """产物名含路径分隔符 / ``..`` ⇒ 工作区层拒绝（防 ``../`` 逃逸）。"""
    for bad in ("../evil.pdf", "sub/evil.pdf", "\\\\evil.pdf"):
        out = _call(bridge, "pdf_compress", pdf_path=str(ws_path("sample.pdf")),
                    output_name=bad)
        assert out["status"] == "error", bad
        assert out["data"]["error_code"] == "WORKSPACE_VIOLATION", bad


# ------------------------------------------------------------------ 任务二 PoC：PPT


def test_ppt_to_pdf_dry_run_writes_nothing(bridge, renderer):
    """``dry_run`` 只探测：给出页数与渲染器状态，**不产出任何文件**。"""
    if not renderer["available"]:
        pytest.skip(f"LibreOffice 不可用（{renderer.get('error')}）")

    out = _call(bridge, "ppt_to_pdf", pptx_path=str(ws_path("sample.pptx")), dry_run=True)
    assert out["status"] == "success", out
    data = out["data"]
    assert data["dry_run"] is True
    assert data["slide_count"] == SAMPLE_PPTX_SLIDES
    assert data["page_count"] == SAMPLE_PPTX_SLIDES
    assert data["renderer_available"] is True
    assert data["outputs"] == []
    assert data["exists"] is False
    assert data["output_pdf"] == ""


def test_ppt_to_pdf_happy_path(bridge, renderer, ws):
    """happy path：真渲染出 PDF。缺 LibreOffice 的机器明确跳过（不假装通过）。"""
    if not renderer["available"]:
        pytest.skip(f"LibreOffice 不可用（{renderer.get('error')}）")

    out_dir = ws / workspace.OUTPUT_SUBDIR
    before = {p for p in out_dir.rglob("*.pdf")} if out_dir.is_dir() else set()

    out = _call(bridge, "ppt_to_pdf", pptx_path=str(ws_path("sample.pptx")),
                output_name="deck-244")
    assert out["status"] == "success", out
    data = out["data"]

    assert data["exists"] is True
    assert len(data["outputs"]) == 1
    produced = Path(data["outputs_abs"][0])
    assert produced.is_file()
    assert produced.stat().st_size > 0
    assert produced.name == "deck-244.pdf"
    assert produced not in before                       # 确实是本次新增
    assert data["outputs"][0].startswith(f"{workspace.OUTPUT_SUBDIR}/")
    assert data["renderer_source"] == renderer["source"]


def test_ppt_to_pdf_auto_names_uniquely_when_output_name_absent(bridge, renderer):
    """``output_name`` 留空 ⇒ 自动唯一命名（工单要求产物不被覆盖）。"""
    if not renderer["available"]:
        pytest.skip(f"LibreOffice 不可用（{renderer.get('error')}）")

    first = _call(bridge, "ppt_to_pdf", pptx_path=str(ws_path("sample.pptx")))
    second = _call(bridge, "ppt_to_pdf", pptx_path=str(ws_path("sample.pptx")))
    assert first["status"] == "success" and second["status"] == "success"
    assert first["data"]["output_name"] and second["data"]["output_name"]
    assert first["data"]["output_name"] != second["data"]["output_name"]
    assert first["data"]["outputs_abs"][0] != second["data"]["outputs_abs"][0]
    # 两次都真出盘
    for res in (first, second):
        assert Path(res["data"]["outputs_abs"][0]).is_file()


def test_ppt_to_pdf_rejects_non_pptx(bridge):
    out = _call(bridge, "ppt_to_pdf", pptx_path=str(ws_path("sample.pdf")))
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "INVALID_SUFFIX"


@pytest.mark.parametrize(
    ("length", "disable_fallback", "should_work"),
    [
        (tools.LIBREOFFICE_OUTPUT_PATH_LIMIT, True, True),        # 83 + 关降级 ⇒ 界内，成功
        (tools.LIBREOFFICE_OUTPUT_PATH_LIMIT + 1, True, False),   # 84 + 关降级 ⇒ **上游 fail-fast（留证）**
        (tools.LIBREOFFICE_OUTPUT_PATH_LIMIT + 1, False, True),   # 84 + 默认   ⇒ 本模块降级救回
    ],
)
def test_known_boundary_output_dir_length_limit(renderer, length, disable_fallback, should_work,
                                                monkeypatch):
    """**已知边界留证（三行受控矩阵）**：``--output-dir`` 长度 ≤83 成功、≥84 静默 fail-fast。

    本机实测（2026-10-14，LibreOffice 26.8.1.1 + @toolknit/cli 2.3.1），每档各跑 2 次：
    82 ✅/✅、83 ✅/✅、84 ❌/❌、85 ❌/❌；且**与层级无关**（长而浅 109 字符失败、
    短而深 71 字符成功）。成因是上游把 ``-env:UserInstallation`` 以 ``file:///`` URL
    传给 soffice，URL 跨过 127 字符即崩（``8 + 36 + 84 = 128``）。

    ⚠️ **244b 之后必须带开关跑**：本模块新增了「长路径自动降级重试」（默认开启），
    它会把 84 那一档**救回成功**。若不加 ``TOOLKNIT_NO_PATH_FALLBACK=1``，
    这条留证用例就观察不到上游的真实行为 —— 那就变成了「测我们自己的缓解」，
    而不是「留证上游的边界」。**故意保持关降级那一行**，正是为了守住这个区分。

    同理，第三行（84 + 默认）断言的是**我们的缓解生效**，两行缺一不可：
    只有它们并排存在，「上游有边界」与「我们绕过了它」才是同一个受控实验的两个臂。

    构造方式：``ppt_to_pdf`` 的输出目录恒为 ``<工作区根>/toolknit-output``，
    故把它精确造到目标长度 —— 即工作区根取 ``length - 16`` 个字符。

    这条**故意断言「上游有 bug」**：**上游一旦修好，第二行会变红**——那时请删掉
    README §5.1、去掉 ``LIBREOFFICE_OUTPUT_PATH_LIMIT`` 与失败 hint 里的对应文案
    （第一行的 83 断言也要跟着重新校准）。**红不是回归，是「该更新文档了」的信号。**
    """
    if not renderer["available"]:
        pytest.skip(f"LibreOffice 不可用（{renderer.get('error')}）")

    base = Path(tempfile.mkdtemp(prefix="tk244-lim-"))
    want_ws_len = length - len(workspace.OUTPUT_SUBDIR) - 1
    pad = want_ws_len - len(str(base)) - 1
    assert pad > 0, f"基准目录过长（{base}），无法构造 {length} 字符目标"
    root = base / ("p" * pad)
    root.mkdir(parents=True)
    try:
        assert len(str(root / workspace.OUTPUT_SUBDIR)) == length, (
            f"构造失败：{len(str(root / workspace.OUTPUT_SUBDIR))} != {length}")
        shutil.copy2(SAMPLE_PPTX, root / "deck.pptx")
        monkeypatch.setenv(workspace.WORKSPACE_ROOT_ENV, str(root))
        if disable_fallback:
            monkeypatch.setenv(tools.PATH_FALLBACK_ENV, "1")
        else:
            monkeypatch.delenv(tools.PATH_FALLBACK_ENV, raising=False)

        out = _call(server.ToolknitBridge(), "ppt_to_pdf",
                    pptx_path=str(root / "deck.pptx"), output_name="lim")

        if should_work:
            assert out["status"] == "success", (
                f"长度 {length}（关降级={disable_fallback}）本应成功，实际失败：{out}\n"
                "若上游改了行为，请同步 README §5.1 与 LIBREOFFICE_OUTPUT_PATH_LIMIT")
            if length > tools.LIBREOFFICE_OUTPUT_PATH_LIMIT:
                assert out["data"]["path_fallback"]["used"] is True, (
                    "超过上限却成功 ⇒ 必然是降级重试救回来的，返回体必须标注")
        else:
            assert out["status"] == "error", (
                f"长度 {length} 本应触发上游 fail-fast，实际成功——"
                f"**说明上游已修复该边界**，请删掉 README §5.1 并把 "
                f"LIBREOFFICE_OUTPUT_PATH_LIMIT 一并移除。原始返回：{out}")
            data = out["data"]
            assert data["error_code"] == "PROCESSING_FAILED"
            assert "3221226505" in str(data.get("error"))
            # 关掉降级时，返回体必须**如实**说明没试过（而不是假装试过）
            assert data["path_fallback"] == {"used": False, "attempted": False}
            # 失败必须带**可执行指引**（指出长度这一真因），而不是只丢一个 exit code
            assert str(tools.LIBREOFFICE_OUTPUT_PATH_LIMIT) in str(data.get("hint"))
    finally:
        shutil.rmtree(base, ignore_errors=True)



# --------------------------------------------------- 反直觉事实回归：doctor vs LibreOffice


@requires_toolknit
def test_doctor_does_not_report_libreoffice(bridge):
    """**反直觉事实的回归**：``doctor`` 的 result 里**没有** LibreOffice。

    LibreOffice 是渲染时懒探测的，只出现在 ``ppt to-pdf`` 的 ``renderer`` 字段。
    所以判 LibreOffice **只能**用 ``renderer_probe``——本条若红，说明上游新增了
    doctor 的 LibreOffice 检查，README §5 与 ``tools.doctor`` 的 docstring 都要改。
    """
    out = _call(bridge, "doctor")
    data = out["data"]
    assert data["checks_libreoffice"] is False
    assert "libreoffice" not in data["dependencies"]
    assert set(data["dependencies"]) >= {"version", "node", "qpdf", "ffmpeg"}


@requires_toolknit
def test_renderer_probe_reports_both_directions(renderer):
    """``renderer_probe`` 无论可用与否都必须给出**可判定**的结论（不静默）。"""
    assert isinstance(renderer["available"], bool)
    assert renderer["override_env"] == "TOOLKNIT_LIBREOFFICE_PATH"
    if renderer["available"]:
        assert renderer["command"]
        assert renderer["source"]
        assert renderer["ok"] is True
    else:
        # 不可用时必须有原因 + 错误码，供上层提示用户安装/配置
        assert renderer["ok"] is False
        assert renderer["error"]
        assert renderer["error_code"] in {"DEPENDENCY_MISSING", "TIMEOUT", "RC_3"}


def test_renderer_probe_needs_no_repo_relative_asset():
    """探测载荷是**现场用标准库生成**的，包内没有二进制资产、不依赖 cwd。"""
    assert "_PROBE_PPTX_PARTS" in vars(tools)
    parts = tools._PROBE_PPTX_PARTS
    assert "ppt/slides/slide1.xml" in parts
    assert "ppt/presentation.xml" in parts
    # 包目录下不应有 pptx 资产（只有 tests/_fixtures 里的夹具）
    assert not list(PKG_ROOT.glob("*.pptx"))


@requires_toolknit
def test_cli_version_probe_reports_pinned_version(bridge):
    """连通性探针：请求版本与实际报告版本都要给出（诊断必需）。"""
    out = _call(bridge, "cli_version")
    data = out["data"]
    assert data["package"] == "@toolknit/cli"
    assert data["requested_version"] == tools.DEFAULT_CLI_VERSION
    assert data["spec"] == f"@toolknit/cli@{tools.DEFAULT_CLI_VERSION}"
    assert data["reported_version"] == tools.DEFAULT_CLI_VERSION


# ------------------------------------------------------------- 工作区路径纪律（任务一）


def test_relative_path_is_rejected(bridge):
    """工单 §1 目标 4：**禁止相对路径**。"""
    out = _call(bridge, "pdf_inspect", pdf_path="sample.pdf")
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "WORKSPACE_VIOLATION"
    assert "相对路径" in out["data"]["error"]


def test_path_outside_workspace_is_rejected(bridge):
    """跨目录访问必须被拒——哪怕是真实存在的文件。"""
    outside = Path(os.environ.get("SystemRoot", "C:/Windows")) / "win.ini"
    if not outside.is_file():
        pytest.skip("缺少工作区外的样本文件")
    out = _call(bridge, "pdf_inspect", pdf_path=str(outside))
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "WORKSPACE_VIOLATION"
    assert "跨目录" in out["data"]["error"]


def test_empty_path_is_rejected(bridge):
    out = _call(bridge, "pdf_inspect", pdf_path="")
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "WORKSPACE_VIOLATION"


@pytest.mark.parametrize("bad", ["../etc", "a/b", "..", "", "  ", "C:\\abs", ".hidden",
                                 "-dash", "x" * 65, "a..b"])
def test_illegal_workspace_name_is_rejected(bad):
    """工作区名必须是单段安全标识符：拒绝分隔符 / ``..`` / 前导点横线 / 超长。"""
    with pytest.raises(workspace.WorkspaceError):
        workspace.resolve_workspace(bad)


def test_legal_workspace_name_resolves_under_root():
    name = "paper-2026_v1"
    got = workspace.resolve_workspace(name)
    assert got.name == name
    assert workspace.workspace_root() in got.parents or got.parent == workspace.workspace_root()


def test_nested_workspace_name_narrows_the_boundary():
    """给出工作区名后，边界收紧到该子目录 ⇒ 根下的文件反而不可见。"""
    sub = workspace.workspace_root() / "narrow"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "inner.pdf").write_bytes((SAMPLE_PDF).read_bytes())

    # 以 narrow 为边界：inner.pdf 可见，根下的 sample.pdf 不可见
    ok = workspace.resolve_input(str(sub / "inner.pdf"), workspace="narrow")
    assert ok.name == "inner.pdf"
    with pytest.raises(workspace.WorkspaceError):
        workspace.resolve_input(str(ws_path("sample.pdf")), workspace="narrow")


def test_rel_to_workspace_falls_back_for_outside_paths(tmp_path):
    """``rel_to_workspace`` 是展示用助手，**不抛异常**（日志不该因路径口径失败）。"""
    inside = workspace.rel_to_workspace(ws_path("sample.pdf"))
    assert inside == "sample.pdf"
    outside = workspace.rel_to_workspace(tmp_path / "x.pdf")
    assert outside.endswith("x.pdf")
    assert Path(outside).is_absolute() or "/" in outside or "\\" in outside


def test_output_dir_is_created_inside_workspace():
    target = workspace.resolve_output_dir()
    assert target.is_dir()
    assert target.name == workspace.OUTPUT_SUBDIR
    assert workspace.workspace_root() in target.parents


def test_log_path_override_env_wins(tmp_path, monkeypatch):
    custom = tmp_path / "deep" / "custom.jsonl"
    monkeypatch.setenv("TOOLKNIT_LOG_PATH", str(custom))
    got = workspace.resolve_log_path()
    assert got == custom.resolve()
    assert got.parent.is_dir()


# ------------------------------------------------------------ 调用日志（JSONL append）


def test_call_log_is_jsonl_append(bridge, ws):
    """工单铁律：JSONL **append**。两次调用后必须是**两行**，不是被覆盖成一行。"""
    log = Path(os.environ["TOOLKNIT_LOG_PATH"])
    log.unlink(missing_ok=True)

    _call(bridge, "list_tools")                      # 无 CLI 调用，最快
    _call(bridge, "workspace_info")
    _call(bridge, "pdf_inspect", pdf_path=str(ws_path("sample.pdf")))

    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 3, f"append 语义失效，实际 {len(lines)} 行"

    entries = [json.loads(ln) for ln in lines]
    assert [e["tool"] for e in entries] == ["list_tools", "workspace_info", "pdf_inspect"]
    for entry in entries:
        assert isinstance(entry["ts"], float)
        assert isinstance(entry["ok"], bool)
        assert entry["elapsed_s"] >= 0

    # 只记标量参数，且路径只留文件名（不把绝对路径灌进日志）
    pdf_entry = entries[-1]
    assert pdf_entry["args"]["pdf_path"] == "sample.pdf"


def test_call_log_records_failures_with_error_code(bridge, ws):
    log = Path(os.environ["TOOLKNIT_LOG_PATH"])
    log.unlink(missing_ok=True)
    _call(bridge, "pdf_inspect", pdf_path=str(ws_path("missing.pdf")))

    entry = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert entry["tool"] == "pdf_inspect"
    assert entry["ok"] is False
    assert entry["error_code"] == "WORKSPACE_VIOLATION"


def test_call_log_never_breaks_the_call(monkeypatch, bridge):
    """日志写失败**绝不能**影响主调用（best-effort）。"""

    def boom(*_a, **_k):
        raise workspace.WorkspaceError("模拟日志不可写")

    monkeypatch.setattr(server.tk_tools, "log_call", boom)
    out = _call(bridge, "list_tools")
    assert out["status"] == "success"


# --------------------------------------------------------------- 交付纪律 / 结构自证


#: 标准库白名单（本包允许出现的全部顶层模块名；**声明范围必须与守卫范围一致**）
_STDLIB_OK = frozenset({
    "__future__", "argparse", "asyncio", "importlib", "json", "logging", "os", "pathlib",
    "re", "shutil", "subprocess", "sys", "tempfile", "time", "typing", "uuid", "zipfile",
})

#: 本包内的兄弟模块（相对 import）
_SIBLING_OK = frozenset({"pdf_text", "server", "tools", "workspace"})

#: 本包**唯一**允许惰性引用第三方的文件（显式依赖缝）
_OPTIONAL_SEAM = "pdf_text.py"

#: 该缝允许引用的第三方模块（必须与 pdf_text._OPTIONAL_ENGINE_MODULES 逐项一致）
_SEAM_ALLOWED = frozenset({"pypdf", "pymupdf", "fitz", "docling", "markitdown"})

#: 交付的**文本**文件全集里、不在 PKG_ROOT 下的那几个（写成清单而不是 glob，
#: 这样个数是显式的；**改动交付文件集就必须同步这里与文档里的数字**）
_DELIVERABLE_TEXT_EXTERNAL = (
    "docs/integration-graph/toolknit_mcp.txt",
    "reports/workorder244_toolknit_mcp_2026-10-14.md",
    "reports/workorder244b_toolknit_hardening_2026-10-15.md",
    "tests/test_toolknit_mcp.py",
    "tools/toolknit_license_audit.py",
)


def _import_statements(path: Path) -> list[tuple[int, str]]:
    """返回 ``[(缩进宽度, 语句), ...]``；缩进宽度用来区分**顶层**与**函数内**（惰性）。"""
    out: list[tuple[int, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not (stripped.startswith("import ")
                or (stripped.startswith("from ") and " import " in stripped)):
            continue
        out.append((len(line) - len(line.lstrip()), stripped))
    return out


def _module_root(statement: str) -> str:
    """语句里的**顶层模块名**（剥掉行尾注释，去掉相对前导点与子模块）。

    ⚠️ 必须剥注释：实测 ``import pymupdf  # type: ignore`` 若整句参与比对，
    会被判成模块名 ``'pymupdf  # type: ignore'`` 而误报越界。
    """
    code = statement.split("#", 1)[0].strip()
    body = code[5:].split(" import ")[0] if code.startswith("from ") else code[7:]
    return body.split(" as ")[0].split(",")[0].strip().lstrip(".").split(".")[0]


def _is_third_party(root: str) -> bool:
    return bool(root) and not root.startswith("mcpserver") and root not in _STDLIB_OK \
        and root not in _SIBLING_OK


def test_cli_layer_is_pure_stdlib():
    """CLI 驱动层（``__init__`` / ``workspace`` / ``tools`` / ``server``）**任何位置**
    都不得引用第三方 —— 连惰性都不许（这些文件是纯标准库的举证对象）。
    """
    offenders: list[str] = []
    for name in ("__init__.py", "workspace.py", "tools.py", "server.py"):
        path = PKG_ROOT / name
        assert path.is_file(), f"缺文件 {name}"
        offenders.extend(f"{name}: {stmt}" for _, stmt in _import_statements(path)
                         if _is_third_party(_module_root(stmt)))
    assert not offenders, f"CLI 驱动层出现第三方 import: {offenders}"


def test_top_level_imports_are_stdlib_only():
    """**任何**模块文件的**顶层** import 都必须是标准库或兄弟模块。

    第三方只允许写在函数体内（惰性）——否则 ``import mcpserver.toolknit_mcp``
    就会在**导入期**把 pypdf / docling 之类拉起来，让「没装也能用」变成谎话。
    """
    offenders: list[str] = []
    for path in sorted(PKG_ROOT.glob("*.py")):
        offenders.extend(f"{path.name}: {stmt}" for indent, stmt in _import_statements(path)
                         if indent == 0 and _is_third_party(_module_root(stmt)))
    assert not offenders, f"顶层出现第三方 import: {offenders}"


def test_pdf_text_is_the_only_optional_seam():
    """第三方引用**只允许**出现在 ``pdf_text.py``、**只允许**惰性、**只允许**白名单模块。

    「缝」这种东西最怕两件事：① 悄悄扩张到别的文件；② 缝自己声明的白名单与守卫的白名单
    各写一份然后漂移。本用例把两件都钉住（后者用**逐项相等**断言，不是包含关系）。
    """
    from mcpserver.toolknit_mcp import pdf_text

    offenders: list[str] = []
    lazy: set[str] = set()
    for path in sorted(PKG_ROOT.glob("*.py")):
        for indent, stmt in _import_statements(path):
            root = _module_root(stmt)
            if not _is_third_party(root):
                continue
            if path.name != _OPTIONAL_SEAM:
                offenders.append(f"{path.name}: {stmt}")
            elif indent == 0:
                offenders.append(f"{path.name}（顶层，必须惰性）: {stmt}")
            else:
                lazy.add(root)
    assert not offenders, f"第三方 import 越界（只允许 {_OPTIONAL_SEAM} 内惰性出现）: {offenders}"
    assert lazy <= _SEAM_ALLOWED, f"{_OPTIONAL_SEAM} 引用了白名单外模块: {sorted(lazy - _SEAM_ALLOWED)}"
    assert set(pdf_text._OPTIONAL_ENGINE_MODULES) == _SEAM_ALLOWED, (
        "pdf_text._OPTIONAL_ENGINE_MODULES 与本用例的白名单漂移："
        f"{sorted(set(pdf_text._OPTIONAL_ENGINE_MODULES) ^ _SEAM_ALLOWED)}"
    )


def test_license_audit_script_is_pure_stdlib():
    """``tools/toolknit_license_audit.py`` 必须零第三方依赖（要在干净环境里可跑）。"""
    path = REPO_ROOT / "tools" / "toolknit_license_audit.py"
    assert path.is_file(), f"缺文件 {path}"
    offenders = [f"{indent}: {stmt}" for indent, stmt in _import_statements(path)
                 if _is_third_party(_module_root(stmt))]
    assert not offenders, f"审计脚本出现第三方 import: {offenders}"


def test_whitelist_never_touches_the_table_path():
    """把「``buffers@0.1.1`` 无许可声明但可接受」这个**判断**变成**可复算的断言**。

    依据（2026-10-15 实测）：``buffers@0.1.1`` 无任何许可声明，
    但引入链是 ``exceljs → unzipper → binary → buffers`` —— **只在表格路径上**。
    本模块白名单既不暴露表格类子命令，CLI 驱动层也不出现表格关键词
    ⇒ 「不经过该链」这件事**每次 CI 都会被重新证明**，而不是留在报告里的一句话。
    """
    src = (PKG_ROOT / "tools.py").read_text(encoding="utf-8").lower()
    for keyword in ("xlsx", "excel", "spreadsheet", "sheet"):
        assert keyword not in src, f"tools.py 出现表格路径关键词 {keyword!r} ⇒ 许可结论需重评"
    assert not [name for name in server.ToolknitBridge._TOOLS
                if any(word in name for word in ("excel", "sheet", "xls", "csv"))], \
        "白名单里出现了表格类工具 ⇒ 会经过 buffers@0.1.1（无许可声明）"


def test_no_package_lock_or_tauri_contact_in_module():
    """§3.3/§3.4：模块内不带 package-lock.json / package.json，也不碰桌面端前端。

    ⚠️ 本测试**故意把三个被禁串拆成碎片拼装**（``"src" + "-tauri"`` 等）：
    工单 §3.3 要求 `git grep` 这三个串时**只允许集成图命中**——
    如果这里写字面量，**测试自己就成了命中项**，反倒破坏它要守护的验收项。
    碎片拼装让本文件保持干净，同时断言照跑。
    """
    assert not list(PKG_ROOT.rglob("package-lock.json"))
    assert not list(PKG_ROOT.rglob("package.json"))

    banned = ("src" + "-tauri", "tauri" + "." + "devtools", "vi" + "te")
    offenders = []
    for path in PKG_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".json", ".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in banned:
            if token in text:
                offenders.append(f"{path.relative_to(PKG_ROOT)}: {token}")
    assert not offenders, f"模块内出现桌面端前端串: {offenders}"

    # 反向自证「碎片拼对了」：这三个串**允许**出现在集成图里，
    # 故拿集成图当参照物——若拼错，这里就找不到，从而抓出前面的断言空跑。
    # （集成图不在时（如只覆盖子树跑测试）跳过此项，不误报。）
    doc = REPO_ROOT / "docs" / "integration-graph" / "toolknit_mcp.txt"
    if doc.is_file():
        doc_text = doc.read_text(encoding="utf-8")
        missing = [token for token in banned if token not in doc_text]
        assert not missing, (
            f"集成图应逐字写明被禁串（§0.1 的 grep 原文），实际缺 {missing}——"
            "要么拼错导致本文件断言空跑，要么集成图漏写")


def test_five_piece_skeleton_is_present():
    """工单 §3.2：server.py / tools.py / workspace.py / __init__.py / README.md / requirements.txt。"""
    for name in ("server.py", "tools.py", "workspace.py", "__init__.py",
                 "README.md", "requirements.txt", "agent-manifest.json"):
        assert (PKG_ROOT / name).is_file(), f"缺 {name}"
    for name in ("sample.pdf", "sample.pptx", "solid_red.png", "two_tone.png"):
        assert (FIXTURES / name).is_file(), f"缺夹具 {name}"


def test_subprocess_never_uses_shell():
    """注入防线：所有 CLI 调用必须 ``shell=False`` 且 argv 由代码构造。"""
    text = (PKG_ROOT / "tools.py").read_text(encoding="utf-8")
    assert "shell=False" in text
    assert "shell=True" not in text
    # npx 必须经 shutil.which 解析成绝对路径（不依赖 shell 查找）
    assert 'shutil.which("npx")' in text


def test_cli_argv_shape_is_pinned():
    argv = tools.cli_argv("pdf", "inspect", "--input", "x.pdf", "--json")
    assert argv[:3] == ["npx", "-y", f"@toolknit/cli@{tools.DEFAULT_CLI_VERSION}"]
    assert argv[3:] == ["pdf", "inspect", "--input", "x.pdf", "--json"]


def test_cli_version_env_overrides_pin(monkeypatch):
    monkeypatch.setenv(tools.CLI_VERSION_ENV, "9.9.9-test")
    assert tools.cli_version() == "9.9.9-test"
    assert tools.cli_spec() == "@toolknit/cli@9.9.9-test"
    assert tools.cli_argv("doctor")[2] == "@toolknit/cli@9.9.9-test"


def test_cli_spec_matches_measured_latest():
    """钉死版本必须是组件列表里**实测存在**的那个（工单写的 3.0.0 不存在）。"""
    assert tools.DEFAULT_CLI_VERSION == "2.3.1"
    assert tools.CLI_PACKAGE == "@toolknit/cli"


def test_cli_unavailable_is_reported_not_raised(monkeypatch, bridge):
    """Node/npx 缺失时必须得到结构化 ``CLI_UNAVAILABLE``，而不是抛异常。"""
    monkeypatch.setattr(tools.shutil, "which", lambda _name: None)
    out = _call(bridge, "extract_palette", image_path=str(ws_path("two_tone.png")))
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "CLI_UNAVAILABLE"


def test_error_codes_are_stable_vocabulary():
    """错误码是外部契约，集中列出防漂移（README/工单依赖这些串）。"""
    codes = {"INVALID_COUNT", "INVALID_LEVEL", "INVALID_SUFFIX", "OUTPUT_IS_SOURCE",
             "WORKSPACE_VIOLATION", "CLI_UNAVAILABLE", "DEPENDENCY_MISSING", "TIMEOUT"}
    text = (PKG_ROOT / "tools.py").read_text(encoding="utf-8")
    for code in codes:
        assert code in text, f"错误码 {code} 不再出现，契约可能已改"


def test_deliverable_is_lf_only():
    """交付纪律：**本包交付的全部文本文件**必须 LF。

    ⚠️ 口径（2026-10-15 修正，勿再放宽）：交付里有 **4 个二进制夹具**
    （`.pdf`/`.pptx`/`.png`，无行尾概念）⇒ 文本集合 = **13** 个
    （PKG_ROOT 下 8 个 + 清单里 5 个）。

    早期版本只扫 ``PKG_ROOT``（实覆盖 **7** 个模块文件），
    而报告/PR 却宣称「14 个文本文件全 LF」—— **声明超出了守卫范围**（见 REFERENCE §R13.2）。
    现在按**显式清单 + 计数断言 == 13** 钉住：将来谁增删交付文本文件而忘记同步文档，
    这里会先红。
    """
    text_suffix = {".py", ".md", ".txt", ".json", ".yaml"}
    targets = sorted(
        [p for p in PKG_ROOT.rglob("*") if p.is_file() and p.suffix in text_suffix]
        + [REPO_ROOT / rel for rel in _DELIVERABLE_TEXT_EXTERNAL]
    )
    missing = [str(p) for p in targets if not p.is_file()]
    assert not missing, f"清单里的交付文本文件不存在: {missing}"
    assert len(targets) == 13, (
        "交付文本文件应为 13 个（PKG_ROOT 8 + 清单 5；二进制夹具 4 个除外），实为 "
        f"{len(targets)}：{[str(p.relative_to(REPO_ROOT)) for p in targets]}"
        "；若刚增删过交付文件，请同步 _DELIVERABLE_TEXT_EXTERNAL 与文档里的计数"
    )
    crlf = [str(p.relative_to(REPO_ROOT)) for p in targets if b"\r\n" in p.read_bytes()]
    assert not crlf, f"出现 CRLF: {crlf}"


# ===================================================== 244b：pdf_text（仓内引擎缝）
#
# 这一组用例守的是「工单原话『PDF 文本 + 页码位置』」被真正补上，
# 而且补的方式**没有偷偷扩权**：不支持就明确报错、显式引擎不许被静默替换。


def _pymupdf_available() -> bool:
    try:
        return (importlib.util.find_spec("pymupdf") is not None
                or importlib.util.find_spec("fitz") is not None)
    except (ImportError, ValueError):
        return False


def test_pdf_text_engines_status_shape():
    """引擎快照的结构 + 降级链顺序（顺序即优先级，是本模块的对外契约）。"""
    from mcpserver.toolknit_mcp import pdf_text

    assert list(pdf_text.TEXT_ENGINE_CHAIN) == ["pypdf", "pymupdf", "adapter"]
    status = pdf_text.engines_status()
    for key in ("pypdf", "pymupdf", "adapter", "available_chain", "versions", "adapter_path"):
        assert key in status, f"缺字段 {key}"
    order = [name for name in pdf_text.TEXT_ENGINE_CHAIN if name in status["available_chain"]]
    assert status["available_chain"] == order, "available_chain 必须是降级链的保序子序列"
    assert status["adapter_path"].replace("\\", "/").endswith(
        "mcpserver/adapters/pdf2md_adapter/adapter.py")
    assert status["chain"] == list(pdf_text.TEXT_ENGINE_CHAIN)


def test_pdf_text_extracts_pages_with_page_numbers(bridge, ws):
    """happy path：逐页提取 + **页码** + 完整文本落盘。"""
    out = _call(bridge, "pdf_text", pdf_path=str(ws_path("sample.pdf")), max_chars_per_page=200)
    assert out["status"] == "success", out
    data = out["data"]
    assert data["ok"] is True
    assert data["engine"] in {"pypdf", "pymupdf"}, "本机装的是这两个引擎之一"
    assert data["page_count"] == SAMPLE_PDF_PAGES == 3
    assert [page["page"] for page in data["pages"]] == [1, 2, 3]
    assert data["page_numbers"] is True
    assert all(page["chars"] > 0 for page in data["pages"])
    assert data["total_chars"] == sum(page["chars"] for page in data["pages"])
    assert all(len(page["text"]) <= 200 for page in data["pages"])
    saved = Path(data["output_abs"])
    assert saved.is_file(), "完整文本必须落盘"
    body = saved.read_text(encoding="utf-8")
    assert "# --- page 1 ---" in body and "# --- page 3 ---" in body
    assert "\r\n" not in body, "落盘文本必须 LF"
    assert len(body) > data["total_chars"], "落盘文件含页分隔头，必然长于纯文本总长"


def test_pdf_text_truncation_affects_response_only(bridge, ws):
    """截断只作用于**返回体**；落盘文件永远完整（这条最容易写反）。"""
    tiny = _call(bridge, "pdf_text", pdf_path=str(ws_path("sample.pdf")), max_chars_per_page=32)
    full = _call(bridge, "pdf_text", pdf_path=str(ws_path("sample.pdf")), max_chars_per_page=0)
    assert tiny["data"]["total_chars"] == full["data"]["total_chars"]
    assert len(tiny["data"]["pages"][0]["text"]) == 32
    assert len(full["data"]["pages"][0]["text"]) == full["data"]["pages"][0]["chars"]
    assert tiny["data"]["truncated_in_response"] is True
    assert full["data"]["truncated_in_response"] is False
    # max_chars_per_page 不改变落盘内容
    assert Path(tiny["data"]["output_abs"]).read_bytes() == \
        Path(full["data"]["output_abs"]).read_bytes()


def test_pdf_text_explicit_engine_never_silently_falls_back(bridge, ws):
    """显式指定引擎时**只**用该引擎；不可用就报 ``ENGINE_UNAVAILABLE``，绝不偷偷降级。

    守的是「排查的可信度」：若显式 ``pymupdf`` 却悄悄跑了 ``pypdf``，
    那么所有「换个引擎试试」的诊断都失去意义。
    """
    from mcpserver.toolknit_mcp import pdf_text

    if pdf_text.engines_status()["adapter"]:
        pytest.skip("本机装了 docling/markitdown ⇒ adapter 可用，本用例前提不成立")
    out = _call(bridge, "pdf_text", pdf_path=str(ws_path("sample.pdf")), engine="adapter")
    assert out["status"] == "error", out
    assert out["data"]["ok"] is False
    assert out["data"]["error_code"] == "ENGINE_UNAVAILABLE"
    message = str(out["data"]["error"])
    assert "adapter" in message
    assert "pypdf" in message, "错误里要列出**当前可用**引擎，否则调用方无法自救"


def test_pdf_text_unknown_engine_is_rejected(bridge, ws):
    """拼错的引擎名与「不可用引擎」同样处理 —— 不能因为不认识就当 auto。"""
    out = _call(bridge, "pdf_text", pdf_path=str(ws_path("sample.pdf")), engine="bogus")
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "ENGINE_UNAVAILABLE"


def test_pdf_text_auto_uses_head_of_chain(bridge, ws):
    """``auto`` 走降级链：首选可得引擎，且 attempts 如实记录第一次就成功。"""
    out = _call(bridge, "pdf_text", pdf_path=str(ws_path("sample.pdf")), max_chars_per_page=16)
    from mcpserver.toolknit_mcp import pdf_text

    data = out["data"]
    assert data["engine_requested"] == "auto"
    assert data["engine"] == data["engine_attempts"][0]["engine"]
    assert data["engine_attempts"][0]["ok"] is True
    assert data["engine_fallback"] is (data["engine"] != pdf_text.engines_status()["available_chain"][0])


@pytest.mark.skipif(not _pymupdf_available(), reason="需要 pymupdf")
def test_pdf_text_layout_gives_line_bbox(bridge, ws):
    """``layout=True`` ⇒ 「页码位置元数据」的字面落实：每页给页尺寸 + 行级 bbox。"""
    out = _call(bridge, "pdf_text", pdf_path=str(ws_path("sample.pdf")), engine="pymupdf",
                layout=True, max_layout_lines=5, max_chars_per_page=64)
    data = out["data"]
    assert data["ok"] is True, data
    assert data["layout"] is True
    assert data["page_numbers"] is True
    page = data["pages"][0]
    assert len(page["page_size"]) == 2 and all(value > 0 for value in page["page_size"])
    assert 1 <= len(page["lines"]) <= 5
    for line in page["lines"]:
        assert line["text"]
        assert isinstance(line["bbox"], list) and len(line["bbox"]) == 4
        assert all(isinstance(value, float) for value in line["bbox"])
    # bbox 必须落在页内（右上角不超过页尺寸）
    width, height = page["page_size"]
    for line in page["lines"]:
        assert 0 <= line["bbox"][0] < line["bbox"][2] <= width + 1
        assert 0 <= line["bbox"][1] < line["bbox"][3] <= height + 1


def test_pdf_text_adapter_engine_loses_page_numbers_if_available(bridge, ws):
    """第三级（adapter）**只给整篇 markdown ⇒ 页码丢失**；这里把这件事钉成可观测事实。

    本机未装 docling/markitdown 时跳过 —— 但「页码会丢」这件事必须在
    返回体里有明确字段（``page_numbers`` / ``page_number_note``），不能靠调用方猜。
    """
    from mcpserver.toolknit_mcp import pdf_text

    if not pdf_text.engines_status()["adapter"]:
        pytest.skip("本机 adapter 不可用（docling/markitdown 均未安装）")
    out = _call(bridge, "pdf_text", pdf_path=str(ws_path("sample.pdf")), engine="adapter")
    data = out["data"]
    assert data["ok"] is True, data
    assert data["page_numbers"] is False
    assert data["pages"][0]["page_label"] == pdf_text.ADAPTER_PAGE_LABEL
    assert "不提供逐页切分" in data["page_number_note"]


def test_pdf_text_rejects_non_pdf_magic(bridge, ws):
    """扩展名像 PDF、内容不是 ⇒ 在进引擎之前就挡住（避免引擎抛难懂的异常）。"""
    bogus = ws_path("fake.pdf")
    bogus.write_bytes(b"not a pdf at all")
    out = _call(bridge, "pdf_text", pdf_path=str(bogus))
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "NOT_A_PDF"


def test_pdf_text_rejects_wrong_suffix(bridge, ws):
    note = ws_path("note.txt")
    note.write_text("hello", encoding="utf-8", newline="\n")
    out = _call(bridge, "pdf_text", pdf_path=str(note))
    assert out["data"]["error_code"] == "INVALID_SUFFIX"


def test_pdf_text_missing_file_is_boundary_case(bridge, ws):
    out = _call(bridge, "pdf_text", pdf_path=str(ws_path("nope.pdf")))
    assert out["data"]["error_code"] == "INVALID_PATH"


def test_pdf_text_failure_shape_matches_cli_tools(bridge, ws):
    """失败返回体与 :mod:`tools` 的 ``_fail`` 同形 —— 调用方不该为不同工具写两套解析。"""
    out = _call(bridge, "pdf_text", pdf_path=str(ws_path("nope.pdf")))
    assert {"ok", "tool", "error", "error_code"} <= set(out["data"])
    assert out["data"]["tool"] == "pdf_text"


def test_pdf_text_no_engine_at_all_is_explicit_error(monkeypatch, bridge, ws):
    """三级引擎全不可用 ⇒ **明确报错 + 安装指引**，绝不返回空文本冒充成功。"""
    from mcpserver.toolknit_mcp import pdf_text

    monkeypatch.setattr(pdf_text, "_engine_ready", lambda name: False)
    monkeypatch.delenv(pdf_text.ENGINE_ENV, raising=False)
    out = _call(bridge, "pdf_text", pdf_path=str(ws_path("sample.pdf")))
    assert out["status"] == "error"
    assert out["data"]["error_code"] == "ENGINE_UNAVAILABLE"
    assert "pip install" in str(out["data"]["error"]), "要给可执行的安装指引"


def test_pdf_text_engine_env_var_is_honoured(monkeypatch, bridge, ws):
    """``TOOLKNIT_PDF_ENGINE`` 改默认引擎（显式参数仍然优先）。"""
    from mcpserver.toolknit_mcp import pdf_text

    monkeypatch.setenv(pdf_text.ENGINE_ENV, "pymupdf")
    assert pdf_text.selected_engine() == "pymupdf"
    if _pymupdf_available():
        out = _call(bridge, "pdf_text", pdf_path=str(ws_path("sample.pdf")), max_chars_per_page=16)
        assert out["data"]["engine"] == "pymupdf"
        assert out["data"]["engine_requested"] == "pymupdf"


def test_pdf_text_is_listed_in_bridge_and_manifest(bridge):
    """白名单自述 / 声明的工具集必须都含 ``pdf_text``（防「方法写了但登记漏了」）。"""
    listed = bridge.list_tools()
    assert "pdf_text" in listed["tools"]
    assert listed["in_repo_tools"] == ["pdf_text"]
    assert all(name in listed["tools"] for name in listed["cli_tools"])
    assert "pdf_text_engines" in listed
    assert "pdf_text" in server.ToolknitBridge._TOOLS


# ================================ 244b：输出路径过长的**自动降级重试**（受控对照）


def test_path_fallback_reason_requires_all_four_conditions(monkeypatch):
    """四条判据缺一不可 —— 刻意保守，避免把一次真失败重试成两次。"""
    long_dir = Path("C:/" + "x" * 90)
    short_dir = Path("C:/tk")
    failfast = {"error_code": "PROCESSING_FAILED", "rc": 1,
                "error": f"LibreOffice conversion failed: exit code {tools.LIBREOFFICE_FAILFAST_RC}"}
    monkeypatch.delenv(tools.PATH_FALLBACK_ENV, raising=False)
    assert tools._path_fallback_reason(failfast, long_dir) != ""
    assert tools._path_fallback_reason(failfast, short_dir) == "", "① 路径不够长"
    assert tools._path_fallback_reason(
        {**failfast, "error_code": "DEPENDENCY_MISSING"}, long_dir) == "", "② 错误码不对"
    assert tools._path_fallback_reason(
        {**failfast, "error": "LibreOffice crashed"}, long_dir) == "", "③ 消息里没有 fail-fast 退出码"
    assert tools._path_fallback_reason(
        {"error_code": "PROCESSING_FAILED", "error": "boom"}, long_dir) == ""
    assert str(tools.LIBREOFFICE_FAILFAST_RC) in tools._path_fallback_reason(failfast, long_dir)


def test_path_fallback_disable_switch(monkeypatch):
    """``TOOLKNIT_NO_PATH_FALLBACK`` 是**显式开关**（改行为必须有开关，见 REFERENCE §R6）。"""
    long_dir = Path("C:/" + "x" * 90)
    failfast = {"error_code": "PROCESSING_FAILED", "rc": 1,
                "error": f"exit code {tools.LIBREOFFICE_FAILFAST_RC}"}
    monkeypatch.delenv(tools.PATH_FALLBACK_ENV, raising=False)
    assert tools.path_fallback_disabled() is False
    assert tools._path_fallback_reason(failfast, long_dir) != ""
    monkeypatch.setenv(tools.PATH_FALLBACK_ENV, "1")
    assert tools.path_fallback_disabled() is True
    assert tools._path_fallback_reason(failfast, long_dir) == ""


def test_reserve_dir_appends_suffix_on_collision(tmp_path):
    """回落点撞名时按 ``_1``/``_2`` 顺延（与上游 ``_reserveUniqueDirectory`` 习惯一致）。"""
    first = tools._reserve_dir(tmp_path, "deck_ppt_to_pdf")
    assert first == tmp_path / "deck_ppt_to_pdf"
    first.mkdir()
    second = tools._reserve_dir(tmp_path, "deck_ppt_to_pdf")
    assert second == tmp_path / "deck_ppt_to_pdf_1"
    second.mkdir()
    assert tools._reserve_dir(tmp_path, "deck_ppt_to_pdf") == tmp_path / "deck_ppt_to_pdf_2"


def test_rewrite_manifest_paths_replaces_temp_prefix(tmp_path):
    """搬回后重写 ``manifest.json`` 里的临时路径，**且不碰无关字段**。"""
    old_root = tmp_path / "tklo-abc" / "deck_ppt_to_pdf"
    old_root.mkdir(parents=True)
    manifest = old_root / "manifest.json"
    manifest.write_text(json.dumps({
        "outputs": [{"path": str(old_root / "deck.pdf"), "pages": 2}],
        "output_dir": str(old_root),
        "note": "不要改我",
    }, ensure_ascii=False), encoding="utf-8", newline="\n")
    new_root = tmp_path / "out" / "deck_ppt_to_pdf"
    assert tools._rewrite_manifest_paths(manifest, old_root, new_root) is True
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["outputs"][0]["path"] == str(new_root / "deck.pdf")
    assert data["outputs"][0]["pages"] == 2
    assert data["output_dir"] == str(new_root)
    assert data["note"] == "不要改我"
    assert "\r\n" not in manifest.read_text(encoding="utf-8")


def test_rewrite_manifest_paths_is_best_effort(tmp_path):
    """清单坏了也不该把已生成的 PDF 拖下水 ⇒ 返回 ``False`` 而不是抛。"""
    broken = tmp_path / "manifest.json"
    broken.write_text("{ not json", encoding="utf-8", newline="\n")
    assert tools._rewrite_manifest_paths(broken, tmp_path, tmp_path / "x") is False


@pytest.mark.parametrize(("disabled", "should_succeed"), [(False, True), (True, False)])
def test_ppt_to_pdf_long_output_path_is_rescued(renderer, monkeypatch, disabled, should_succeed):
    """**真跑 + 受控对照**：输出路径 >83 字符时自动改短目录重试，产物搬回原落点。

    同一份 pptx、同一个长路径工作区，**只改** ``TOOLKNIT_NO_PATH_FALLBACK``：
    开启 ⇒ 成功且 ``path_fallback.used`` 为真；关闭 ⇒ 原样透出 ``PROCESSING_FAILED``。

    关闭那一档不只是陪跑：它证明「降级没生效时调用方**仍能看见真实错误**」，
    不会被静默吞掉 —— 这正是 REFERENCE §R13.1 说的「留证」。
    """
    if not renderer["available"]:
        pytest.skip(f"LibreOffice 不可用（{renderer.get('error')}）")
    long_root = Path(tempfile.mkdtemp(prefix="toolknit-long-path-rescue-probe-"))
    shutil.copy2(SAMPLE_PPTX, long_root / "sample.pptx")
    out_root = long_root / workspace.OUTPUT_SUBDIR
    if len(str(out_root)) <= tools.LIBREOFFICE_OUTPUT_PATH_LIMIT:
        shutil.rmtree(long_root, ignore_errors=True)
        pytest.skip(f"本机临时目录太短（{len(str(out_root))} ≤ "
                    f"{tools.LIBREOFFICE_OUTPUT_PATH_LIMIT}），构造不出该场景")
    monkeypatch.setenv("TOOLKNIT_WORKSPACE_ROOT", str(long_root))
    if disabled:
        monkeypatch.setenv(tools.PATH_FALLBACK_ENV, "1")
    else:
        monkeypatch.delenv(tools.PATH_FALLBACK_ENV, raising=False)
    try:
        data = tools.ppt_to_pdf(str(long_root / "sample.pptx"), timeout=240)
        if should_succeed:
            assert data["ok"] is True, data
            assert data["path_fallback"]["used"] is True
            assert data["path_fallback"]["attempted"] is True
            assert str(tools.LIBREOFFICE_OUTPUT_PATH_LIMIT) in data["path_fallback"]["reason"]
            assert data["path_fallback"]["moved"], "必须记下搬回了哪个目录"
            landed = sorted(p.relative_to(out_root).as_posix() for p in out_root.rglob("*.pdf"))
            assert len(landed) == 1, f"原落点下应恰好一个 PDF：{landed}"
            assert landed[0].split("/")[-2].endswith("_ppt_to_pdf"), landed[0]
            assert Path(data["outputs_abs"][0]).is_file()
            # outputs 是**相对工作区**的路径（含 toolknit-output/ 前缀），landed 是相对落点的
            assert data["outputs"] == [f"{workspace.OUTPUT_SUBDIR}/{landed[0]}"], data["outputs"]
            assert data["output_dir"] == workspace.OUTPUT_SUBDIR
        else:
            assert data["ok"] is False
            assert data["error_code"] == "PROCESSING_FAILED"
            assert data["path_fallback"] == {"used": False, "attempted": False}
            assert not list(out_root.rglob("*.pdf")), "关闭降级时不该留下任何产物"
    finally:
        shutil.rmtree(long_root, ignore_errors=True)
