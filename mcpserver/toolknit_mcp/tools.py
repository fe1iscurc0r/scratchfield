"""对外四工具的 CLI 适配层（工单244 §2 任务二）。

设计口径
--------
1. **只白名单四个工具**（工单 §4 风险表：「MCP 协议暴露 46 个工具导致 LM 工具选择混乱」）
   ⇒ 这里就是白名单本体，不暴露 toolknit 的全部 46 个能力。
2. **不写第二套文件处理实现** —— 全部经 ``npx @toolknit/cli`` 子进程转发，本层只做
   ① 路径纪律 ② 参数校验 ③ 输出归一 ④ 错误语义。
3. **子进程不走 shell**：``shutil.which("npx")`` 拿到的是 ``npx.CMD``（Windows），
   实测 `subprocess.run([...], shell=False)` 可直接拉起 ⇒ **无命令注入面**。
4. **版本钉死**：``TOOLKNIT_CLI_VERSION`` 可覆盖，默认 ``DEFAULT_CLI_VERSION``。
   ⚠️ 工单 §0 写的 ``v3.0.0`` 在 npm **不存在**（实测仅 8 个版本，latest 2.3.1），
   故此处钉 2.3.1 并把偏差写进 README（定式见工单244 预检报告 §2）。
5. **四个工具与工单点名的对应**（实测能力重构，见预检报告 §1）：

   ===========================  ==========================================
   工单 §2 任务二要求            本模块对外工具
   ===========================  ==========================================
   ``pdf_extract_text``         ❌ toolknit 上游不存在 ⇒ 由 ``pdf_inspect``（元数据）替代；
                                文本+页码由同包的 :mod:`pdf_text` 用**仓内引擎**承接
   ``ppt_to_pdf``               ✅ ``ppt_to_pdf``（依赖 LibreOffice）
   ``extract_palette``          ✅ ``extract_palette``
   （无）                        ➕ ``pdf_compress``（用包自带 qpdf）
   ===========================  ==========================================
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

from .workspace import (
    WorkspaceError,
    rel_to_workspace,
    resolve_input,
    resolve_log_path,
    resolve_output_dir,
    resolve_output_file,
)

#: npm 包名（工单 §2 任务一.2；⚠️ 它是 npm 包，**不能**写进 Python 依赖）
CLI_PACKAGE = "@toolknit/cli"

#: 版本覆盖入口
CLI_VERSION_ENV = "TOOLKNIT_CLI_VERSION"

#: 实测最新版（2026-10-14 查 npm registry：8 个版本，latest=2.3.1；工单写的 3.0.0 不存在）
DEFAULT_CLI_VERSION = "2.3.1"

#: 单次 CLI 调用上限（冷启动实测 2.5~2.8 s；LibreOffice 渲染留足余量）
DEFAULT_TIMEOUT_S = 240

#: LibreOffice 覆盖入口（toolknit 原生支持；缺省时 CLI 返回 DEPENDENCY_MISSING）
LIBREOFFICE_ENV = "TOOLKNIT_LIBREOFFICE_PATH"

#: **实测边界**（2026-10-14，本机 LibreOffice 26.8.1.1 + @toolknit/cli 2.3.1）：
#: ``ppt to-pdf`` 的 ``--output-dir`` 绝对路径长度 **>83** 时，soffice 静默 fail-fast
#: （exit 3221226505 / 0xC0000409，stderr 为空）。
#:
#: 受控实测（同一基准目录，只改输出目录长度，各跑 2 次）：82 ✅/✅、83 ✅/✅、
#: 84 ❌/❌、85 ❌/❌。成因是上游把
#: ``-env:UserInstallation=<out>/.toolknit-libreoffice-XXXXXX/profile`` 以 ``file:///``
#: URL 传给 soffice，跨过 127 字符即崩
#: （``8 + 36 + 84 = 128``）。**与目录层级无关**：长而浅（1 层 109 字符）失败，
#: 短而深（6 层 71 字符）成功。
#:
#: 本模块**不据此拒绝调用**（那是上游行为，会随版本变），只在失败时把这条写进 hint，
#: 并用测试留证（``test_known_boundary_output_dir_length_limit``）。
#:
#: **处置策略升级（2026-10-15）**：除 hint 之外，再自动做**一次降级重试** ——
#: 若失败**同时**满足〔① 输出路径 > 83 ② ``error_code == PROCESSING_FAILED``
#: ③ 消息里带 fail-fast 退出码〕，就把这次渲染改到**短临时目录**跑，
#: 成功后再把产物**搬回原落点**（``out_root``）⇒ **调用契约与产物位置完全不变**，
#: 只是绕开了上游的限制。可用 :data:`PATH_FALLBACK_ENV` 关掉；
#: 返回体用 ``path_fallback`` 字段如实标注是否用过（含临时目录路径）。
LIBREOFFICE_OUTPUT_PATH_LIMIT = 83

#: 实测 soffice 静默 fail-fast 退出码：3221226505 == ``0xC0000409``（STATUS_STACK_BUFFER_OVERRUN）
LIBREOFFICE_FAILFAST_RC = 3221226505
LIBREOFFICE_FAILFAST_RC_HEX = "0xc0000409"

#: 关掉「输出路径过长 ⇒ 自动改短目录重试」的开关（设 1/true/yes/on 生效）
PATH_FALLBACK_ENV = "TOOLKNIT_NO_PATH_FALLBACK"

#: 色板数量的 CLI 合法区间（``image colors --count 2-9``）
PALETTE_MIN_COUNT = 2
PALETTE_MAX_COUNT = 9

#: 压缩等级（``pdf compress --level``）
COMPRESS_LEVELS = ("low", "medium", "high")

#: 会被当作「环境噪声」剥掉的 npm 前缀行（不是 toolknit 的输出）
_NPM_NOISE_PREFIXES = ("npm warn", "npm notice")


class CliUnavailable(RuntimeError):
    """Node / npx 不在 PATH 上 ⇒ 本模块无法工作（与「参数错」区分开）。"""


def cli_version() -> str:
    """当前生效的 CLI 版本（环境变量优先）。"""
    return os.environ.get(CLI_VERSION_ENV, "").strip() or DEFAULT_CLI_VERSION


def cli_spec() -> str:
    """``@toolknit/cli@<version>``。"""
    return f"{CLI_PACKAGE}@{cli_version()}"


def cli_argv(*args: str) -> list[str]:
    """构造 ``npx -y <pkg> <args...>`` 的 argv（不执行）。"""
    return ["npx", "-y", cli_spec(), *args]


def _resolve_exe(name: str) -> str:
    """在 PATH 上找可执行文件；找不到抛 :class:`CliUnavailable`。"""
    found = shutil.which(name)
    if not found:
        raise CliUnavailable(f"未找到可执行文件 {name!r}（需要 Node >= 20.12 与 npx）")
    return found


def _strip_noise(text: str) -> str:
    """剥掉 npm 的 deprecation/notice 行（实测冷启动会往 stderr 打 5 行 ``npm warn``）。"""
    kept = [ln for ln in (text or "").splitlines()
            if not ln.lstrip().lower().startswith(_NPM_NOISE_PREFIXES)]
    return "\n".join(kept).strip()


def _first_json(text: str) -> dict[str, Any] | None:
    """从（已剥噪声的）文本里取第一个可解析的 JSON 对象。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def run_cli(args: list[str], *, timeout: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """跑一次 CLI，返回**归一化结果**（不抛业务异常；环境缺失才抛 :class:`CliUnavailable`）。

    返回结构::

        {"ok": bool, "rc": int, "argv": [...], "stdout": str, "stderr": str,
         "payload": dict|None,        # CLI 的 {"ok":..., "result"/"error":...}
         "error": str|None, "error_code": str|None, "elapsed_s": float,
         "cli_version": str}
    """
    argv = cli_argv(*args)
    exe = _resolve_exe("npx")
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [exe, *argv[1:]],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            # 刻意 shell=False：npx.CMD 在 Windows 上可被直接拉起（实测），
            # 从而彻底规避 shell 元字符注入。
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "rc": -1, "argv": argv, "stdout": "", "stderr": "",
                "payload": None, "error": f"CLI 超时（>{timeout}s）", "error_code": "TIMEOUT",
                "elapsed_s": round(time.monotonic() - started, 3), "cli_version": cli_version()}

    stdout, stderr = _strip_noise(proc.stdout or ""), _strip_noise(proc.stderr or "")
    payload = _first_json(stdout) or _first_json(stderr)
    ok = proc.returncode == 0 and bool(payload and payload.get("ok"))
    error: str | None = None
    error_code: str | None = None
    if not ok:
        if payload and isinstance(payload.get("error"), dict):
            error_code = str(payload["error"].get("code") or "")
            error = str(payload["error"].get("message") or "")
        elif payload and payload.get("error"):
            error = str(payload["error"])
        else:
            error = (stderr or stdout or f"CLI 退出码 {proc.returncode}").strip()[:500]
        error_code = error_code or f"RC_{proc.returncode}"
    return {
        "ok": ok, "rc": proc.returncode, "argv": argv,
        "stdout": stdout, "stderr": stderr, "payload": payload,
        "error": error, "error_code": error_code,
        "elapsed_s": round(time.monotonic() - started, 3),
        "cli_version": cli_version(),
    }


def cli_version_probe(*, timeout: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """连通性探针：``npx -y <pkg> --version``（工单 §4 风险表建议的检查点）。"""
    result = run_cli(["--version"], timeout=timeout)
    reported = (result["stdout"] or "").strip().splitlines()
    return {
        "ok": result["ok"],
        "reported_version": reported[-1].strip() if reported else "",
        "requested_version": cli_version(),
        "error": result["error"],
        "elapsed_s": result["elapsed_s"],
    }


def doctor(*, timeout: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """外部依赖体检：``npx -y <pkg> doctor --json``。

    ⚠️ **实测两条反直觉事实**（2026-10-14，@toolknit/cli 2.3.1）：

    1. ``doctor`` 的 ``result`` **只有 ``version`` / ``node`` / ``qpdf`` / ``ffmpeg`` 四个键，
       根本不含 LibreOffice**。LibreOffice 是**渲染时按需懒探测**的，只出现在
       ``ppt to-pdf`` 返回体的 ``result.renderer`` 里 ⇒ **拿 doctor 判断 LibreOffice 必然假阴性**。
       要判 LibreOffice 用 :func:`renderer_probe`。
    2. ``doctor`` 会在 ``ffmpeg`` 缺失时整体返回 ``ok:false`` / **rc=5**（本机实测），
       尽管 qpdf 完全可用 ⇒ **不能用它的 rc 判断「工具链是否健康」**。

    因此本函数的 ``ok`` 语义被刻意收窄为「doctor 自身跑通」，而不是「外部依赖齐全」。
    """
    result = run_cli(["doctor", "--json"], timeout=timeout)
    payload = result.get("payload") or {}
    data = payload.get("result") or {}
    return {
        "ok": result["ok"],
        "cli_version": data.get("version", ""),
        "node": data.get("node", ""),
        "dependencies": data,
        #: 显式告知调用方：本字段不含 LibreOffice（见 docstring）
        "checks_libreoffice": False,
        "missing": [k for k in ("qpdf", "ffmpeg") if not (data.get(k) or {}).get("available")],
        "error": result["error"] if not result["ok"] else None,
        "rc": result["rc"],
        "elapsed_s": result["elapsed_s"],
    }


def renderer_probe(*, timeout: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """LibreOffice 渲染器探测 —— **唯一可靠的判定入口**（零参数、零副作用）。

    为什么不用 ``doctor``
    --------------------
    实测 ``doctor`` 的 ``result`` 只有 ``version``/``node``/``qpdf``/``ffmpeg``，
    **根本不含 LibreOffice**（它渲染时才懒探测）⇒ 用 doctor 判 LibreOffice 会**假阴性**。

    做法
    ----
    ``ppt to-pdf --dry-run``。实测（2026-10-14，2.3.1）：

    * rc=0、**约 3.2 s**、``output_dir`` 与 ``output_path`` 均为 ``null``
      ⇒ **不产出任何文件、不建目录**（在 ``tempfile.TemporaryDirectory`` 内验证过）
    * 返回 ``result.renderer = {available, command, source, version}``
    * 本机装好 LibreOffice 后 ``source`` 自动命中 ``windows-install``
      （候选表含 ``%ProgramFiles%\\LibreOffice\\program\\soffice.com``），**无需任何环境变量**

    输入必须真实存在
    ----------------
    实测 ``--dry-run`` 下 ``--input`` 与 ``--output-dir`` **都是必填**，且**输入校验先于渲染器探测**：

    * 不存在的路径 ⇒ rc=3 ``INPUT_NOT_FOUND``（**不会**报告 renderer）
    * 空文件     ⇒ rc=3 ``INPUT_INVALID``

    而且即便 ``--dry-run`` 也要求 ``--output-dir`` 存在与否无关（实测传不存在的目录亦 rc=0）。
    故本函数在临时目录里**用纯标准库现场生成**一个 1 页最简 PPTX
    （实测 1,824 B，被 CLI 正常接受、``slide_count=1``）作为探测载荷 ——
    **不向包里塞二进制资产**，也无 repo 相对路径依赖，函数可独立工作。
    """
    with tempfile.TemporaryDirectory(prefix="toolknit-renderer-probe-") as tmp:
        root = Path(tmp)
        probe_file = root / "renderer-probe.pptx"
        try:
            _write_probe_pptx(probe_file)
        except OSError as exc:
            return _fail("renderer_probe", f"无法生成探测用 PPTX：{exc}", "PROBE_WRITE_FAILED")
        result = run_cli(
            ["ppt", "to-pdf", "--dry-run", "--input", str(probe_file),
             "--output-dir", str(root / "out"), "--json"],
            timeout=timeout,
        )
    data = (result.get("payload") or {}).get("result") or {}
    renderer = data.get("renderer") or {}
    available = bool(renderer.get("available"))
    out = {
        "ok": available,
        "tool": "renderer_probe",
        "available": available,
        "command": renderer.get("command"),
        "source": renderer.get("source"),
        "version": renderer.get("version"),
        "override_env": LIBREOFFICE_ENV,
        "probe_input_bytes": len(_PROBE_PPTX_PARTS[_PROBE_SLIDE_PART]),
        "elapsed_s": result["elapsed_s"],
    }
    if not available:
        out["error"] = (result["error"]
                        or "LibreOffice 渲染器不可用：请安装 LibreOffice，"
                           f"或把 {LIBREOFFICE_ENV} 指向 soffice.com / soffice.exe")
        out["error_code"] = result["error_code"] or "DEPENDENCY_MISSING"
    return out


#: 探测用最简 PPTX 的部件名常量（**供返回值引用**；写成常量是因为键是全路径，
#: 曾因写成裸 ``"slide1"`` 触发 ``KeyError`` —— 由
#: ``test_renderer_probe_reports_both_directions`` 抓出）
_PROBE_SLIDE_PART = "ppt/slides/slide1.xml"

#: 探测用最简 PPTX 的部件（纯标准库现场打包，实测 1,824 B 且被 CLI 接受）
_PROBE_PPTX_PARTS: dict[str, str] = {
    "[Content_Types].xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.presentationml.slide+xml"/></Types>'
    ),
    "_rels/.rels": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>'
    ),
    "ppt/presentation.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>'
        '<p:sldSz cx="9144000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/>'
        '</p:presentation>'
    ),
    "ppt/_rels/presentation.xml.rels": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/slide" Target="slides/slide1.xml"/></Relationships>'
    ),
    _PROBE_SLIDE_PART: (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/>'
        '<p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr><a:spLocks noGrp="1"/>'
        '</p:cNvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="457200" y="274638"/><a:ext cx="8229600" cy="1143000"/>'
        '</a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r>'
        '<a:rPr lang="zh-CN" sz="2800"/><a:t>renderer probe</a:t></a:r></a:p></p:txBody>'
        '</p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    ),
}


def _write_probe_pptx(path: Path) -> None:
    """把 :data:`_PROBE_PPTX_PARTS` 打包成一个最简 1 页 PPTX（纯标准库）。"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in _PROBE_PPTX_PARTS.items():
            zf.writestr(name, body)


def log_call(entry: dict[str, Any], *, workspace: str | None = None,
             path: str | os.PathLike[str] | None = None) -> Path:
    """把一次调用按 **JSONL append** 落盘（工单 §2 任务二铁律）。

    「用 append 别 json.dump 一次性，杀进程只坏末行」⇒ 本函数只做 ``open(..., "a")``，
    一行一个 JSON，显式 ``newline="\\n"``（Windows 上不会翻成 CRLF）。
    """
    target = Path(path).resolve() if path else resolve_log_path(workspace=workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with target.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")
    return target


def _ok(name: str, payload: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {"ok": True, "tool": name, "cli_version": cli_version()}
    out.update(extra or {})
    if payload:
        out["raw"] = payload
    return out


def _fail(name: str, error: str, code: str, **extra: Any) -> dict[str, Any]:
    out = {"ok": False, "tool": name, "error": error, "error_code": code,
           "cli_version": cli_version()}
    out.update(extra)
    return out


#: 失败时回带给调用方的 CLI 原始输出上限（够排障又不至于把上下文灌爆）
_DIAG_LIMIT = 1200


def _cli_failure(name: str, result: dict[str, Any], *, hint: str = "",
                 **extra: Any) -> dict[str, Any]:
    """CLI 失败 → 结构化错误，**并把 CLI 的 stderr/stdout 原样回带**。

    为什么必须带：上游的错误语义分两段——``{"ok":false,"error":{code,message}}`` 给
    错误码，但像 ``LibreOffice conversion failed: exit code N`` 这种**只有 message、
    没有细节**的情况，真正的线索（LibreOffice 自己的报错）在 stderr 里。
    不回带就等于让调用方对着一个 exit code 猜。

    ``extra``：附加诊断字段（如 ``path_fallback``），由调用方按需传入。
    """
    out = _fail(
        name, result.get("error") or "CLI 失败",
        result.get("error_code") or "CLI_ERROR",
        cli_rc=result.get("rc"),
        argv=result.get("argv"),
        cli_stderr=(result.get("stderr") or "")[:_DIAG_LIMIT],
        cli_stdout=(result.get("stdout") or "")[:_DIAG_LIMIT],
        **extra,
    )
    if hint:
        out["hint"] = hint
    return out


def _guard(name: str, fn: Any) -> dict[str, Any]:
    """统一把工作区违例 / CLI 缺失转成结构化错误（不把异常泄漏成 500）。"""
    try:
        return fn()
    except WorkspaceError as exc:
        return _fail(name, str(exc), "WORKSPACE_VIOLATION")
    except CliUnavailable as exc:
        return _fail(name, str(exc), "CLI_UNAVAILABLE")
    except subprocess.TimeoutExpired:
        return _fail(name, "CLI 超时", "TIMEOUT")


# --------------------------------------------------------------------------- 工具一


def extract_palette(image_path: str, *, count: int = 5, workspace: str | None = None,
                    timeout: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """``extract_palette(image_path)`` —— 图片主色板（工单 §2 任务二第 3 行）。

    转发 ``toolknit image colors``。**只读**：CLI 侧保证「不写出文件或回显图像数据」，
    返回体里 ``outputs`` 为 ``null``。

    ⚠️ **``count`` 是上界而非产量**（实测，2026-10-14）：纯色图 ``solid_red.png``（32×32）
    即使传 ``--count 2`` 也只返回 **1** 个颜色 ⇒ 断言只能写
    ``returned_count <= requested_count``，**不能**写相等。
    双色图 ``two_tone.png`` 返回 2 个、``percentage`` 各 50、``pixels`` 各 640。

    返回色板元素形状：``{"hex", "rgb":{r,g,b}, "hsl":{h,s,l}, "pixels", "percentage"}``，
    按占比降序 ⇒ ``palette[0]`` 即主色。
    """

    def _run() -> dict[str, Any]:
        if not isinstance(count, int) or isinstance(count, bool):
            return _fail("extract_palette", f"count 必须是整数，收到 {type(count).__name__}",
                         "INVALID_COUNT")
        if not PALETTE_MIN_COUNT <= count <= PALETTE_MAX_COUNT:
            return _fail("extract_palette",
                         f"count 必须在 {PALETTE_MIN_COUNT}-{PALETTE_MAX_COUNT} 之间，收到 {count}",
                         "INVALID_COUNT")
        src = resolve_input(image_path, workspace=workspace)
        result = run_cli(["image", "colors", "--input", str(src), "--count", str(count), "--json"],
                         timeout=timeout)
        if not result["ok"]:
            return _cli_failure("extract_palette", result)
        data = (result["payload"] or {}).get("result", {}) or {}
        palette = list(data.get("palette") or [])
        return _ok("extract_palette", result["payload"], {
            "source": rel_to_workspace(src, workspace=workspace),
            "requested_count": count,
            "returned_count": len(palette),
            "dominant": palette[0]["hex"] if palette else "",
            "palette": palette,
            "image": data.get("input") or {},
            "sampled": data.get("sampled") or {},
            "wrote_files": False,
            "elapsed_s": result["elapsed_s"],
        })

    return _guard("extract_palette", _run)


# --------------------------------------------------------------------------- 工具二


def pdf_inspect(pdf_path: str, *, workspace: str | None = None,
                timeout: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """``pdf_inspect(pdf_path)`` —— PDF 元数据（**替代工单的 ``pdf_extract_text``**）。

    ⚠️ 工单 §2 任务二第 1 行要求「PDF 文本字符串 + 页码位置元数据」，但 toolknit 的 PDF
    子命令只有 ``inspect/merge/split/rotate/encrypt/decrypt/compress/enhance/to-image``，
    MCP 侧 46 个工具里也没有任何 pdf 文本提取 ⇒ **该能力不存在**（预检报告 §1）。
    本工具转发 ``toolknit pdf inspect``，返回规范路径 / 文件名 / 字节数 / 页数，是**只读**操作。
    """

    def _run() -> dict[str, Any]:
        src = resolve_input(pdf_path, workspace=workspace)
        if src.suffix.lower() != ".pdf":
            return _fail("pdf_inspect", f"仅接受 .pdf，收到 {src.suffix!r}", "INVALID_SUFFIX")
        result = run_cli(["pdf", "inspect", "--input", str(src), "--json"], timeout=timeout)
        if not result["ok"]:
            return _cli_failure("pdf_inspect", result)
        data = (result["payload"] or {}).get("result", {}) or {}
        info = data.get("input") or {}
        return _ok("pdf_inspect", result["payload"], {
            "source": rel_to_workspace(src, workspace=workspace),
            "pages": info.get("pages"),
            "name": info.get("name") or src.name,
            "bytes": info.get("bytes"),
            "path": info.get("path") or str(src),
            "wrote_files": False,
            "elapsed_s": result["elapsed_s"],
        })

    return _guard("pdf_inspect", _run)


# --------------------------------------------------------------------------- 工具三


def pdf_compress(pdf_path: str, *, level: str = "medium", output_name: str = "",
                 workspace: str | None = None, timeout: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """``pdf_compress(pdf_path, level)`` —— 压缩 PDF（用 npm 包**自带**的 qpdf）。

    产物固定落 ``<workspace>/toolknit-output/<output_name>``（默认 ``<stem>-compressed.pdf``），
    **绝不写回源目录**。``--overwrite`` 保证重复调用幂等。
    """

    def _run() -> dict[str, Any]:
        if level not in COMPRESS_LEVELS:
            return _fail("pdf_compress", f"level 必须是 {COMPRESS_LEVELS} 之一，收到 {level!r}",
                         "INVALID_LEVEL")
        src = resolve_input(pdf_path, workspace=workspace)
        if src.suffix.lower() != ".pdf":
            return _fail("pdf_compress", f"仅接受 .pdf，收到 {src.suffix!r}", "INVALID_SUFFIX")
        target = resolve_output_file(output_name or f"{src.stem}-compressed.pdf",
                                     workspace=workspace)
        if target == src:
            return _fail("pdf_compress", "产物路径与源文件相同，拒绝覆盖源文件", "OUTPUT_IS_SOURCE")
        result = run_cli(["pdf", "compress", "--input", str(src), "--output", str(target),
                          "--level", level, "--overwrite", "--json"], timeout=timeout)
        if not result["ok"]:
            return _cli_failure("pdf_compress", result)
        return _ok("pdf_compress", result["payload"], {
            "source": rel_to_workspace(src, workspace=workspace),
            "output": rel_to_workspace(target, workspace=workspace),
            "output_abs": str(target),
            "exists": target.exists(),
            "source_bytes": src.stat().st_size,
            "output_bytes": target.stat().st_size if target.exists() else None,
            "level": level,
            "elapsed_s": result["elapsed_s"],
        })

    return _guard("pdf_compress", _run)


# ------------------------------------------- 输出路径过长 ⇒ 自动降级重试（2026-10-15）

#: 降级重试用的短临时目录前缀（``%TEMP%\tklo-xxxxxxxx`` ≈ 22 字符，离 83 有充足余量）
_FALLBACK_TMP_PREFIX = "tklo-"


def path_fallback_disabled() -> bool:
    """``TOOLKNIT_NO_PATH_FALLBACK`` 是否打开了「禁止自动降级」开关。"""
    return (os.environ.get(PATH_FALLBACK_ENV, "") or "").strip().lower() in (
        "1", "true", "yes", "on")


def _path_fallback_reason(result: dict[str, Any], out_root: Path) -> str:
    """这次失败是否**足够确定**是「输出路径过长」——四个条件全中才返回非空字符串。

    刻意保守：只判**可观测症状**（长度 + 错误码 + fail-fast 退出码），不猜上游内部状态。
    宁可不重试，也不要因误判把一次真失败变成两次。
    """
    if path_fallback_disabled():
        return ""
    length = len(str(out_root))
    if length <= LIBREOFFICE_OUTPUT_PATH_LIMIT:
        return ""
    if result.get("error_code") != "PROCESSING_FAILED":
        return ""
    message = str(result.get("error") or "").lower()
    if str(LIBREOFFICE_FAILFAST_RC) not in message and LIBREOFFICE_FAILFAST_RC_HEX not in message:
        return ""
    return (f"输出路径 {length} 字符 > 实测上限 {LIBREOFFICE_OUTPUT_PATH_LIMIT}，"
            f"且 soffice 静默 fail-fast（exit code {LIBREOFFICE_FAILFAST_RC} / 0xC0000409）")


def _reserve_dir(parent: Path, name: str) -> Path:
    """在 ``parent`` 下占一个目录名（重名依次 ``name_1``/``name_2``…）。

    与上游 ``_reserveUniqueDirectory`` 的命名习惯保持一致，避免回落点后与既有产物撞名。
    """
    candidate = parent / name
    index = 1
    while candidate.exists():
        candidate = parent / f"{name}_{index}"
        index += 1
    return candidate


def _rewrite_manifest_paths(manifest: Path, old_root: Path, new_root: Path) -> bool:
    """把 ``manifest.json`` 里指向**临时目录**的路径改写成回落点路径。

    best-effort：解析/写盘失败返回 ``False``（调用方如实上报），**不影响 PDF 交付**。
    """
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    old_keys = (str(old_root), old_root.as_posix())

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: _walk(value) for key, value in node.items()}
        if isinstance(node, list):
            return [_walk(item) for item in node]
        if isinstance(node, str):
            for key in old_keys:
                if node.startswith(key):
                    return str(new_root) + node[len(key):]
        return node

    try:
        manifest.write_text(json.dumps(_walk(data), ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")
    except OSError:
        return False
    return True


def _render_via_short_path(src: Path, name: str, out_root: Path, *,
                           timeout: int, reason: str) -> dict[str, Any] | None:
    """在**短临时目录**里重跑一次渲染，成功后把产物**搬回** ``out_root``。

    为什么产物位置不变：``--output-dir`` 只决定**渲染时**的落点；渲染完只是一次普通
    文件移动（不经过 soffice）⇒ 最终目录布局与正常路径**完全一致**
    （``<out_root>/<name>_ppt_to_pdf/<name>.pdf`` + ``manifest.json``），
    调用方看到的 ``output_dir`` / ``outputs`` 契约不变。

    返回 ``{"result", "fallback", "produced"}``；救不回来返回 ``None``
    （此时上层报**原始**失败，并把 ``attempted=True`` 记进 ``path_fallback``）。
    """
    temp_root = Path(tempfile.mkdtemp(prefix=_FALLBACK_TMP_PREFIX))
    info: dict[str, Any] = {
        "used": True,
        "attempted": True,
        "reason": reason,
        "temp_dir": str(temp_root),
        "from": str(out_root),
        "to": str(out_root),
        "moved": [],
        "manifest_rewritten": None,
    }
    try:
        args = ["ppt", "to-pdf", "--input", str(src), "--output-dir", str(temp_root)]
        if name:
            args += ["--output-name", name]
        args += ["--json"]
        retry = run_cli(args, timeout=timeout)
        if not retry["ok"]:
            info["used"] = False
            info["retry_error"] = retry.get("error")
            info["retry_error_code"] = retry.get("error_code")
            return None
        data = (retry["payload"] or {}).get("result", {}) or {}
        produced = _discover_pdfs(temp_root, data, fallback_glob=True)
        if not produced:
            info["used"] = False
            info["retry_error"] = "短路径重试返回成功，但未发现产物 PDF"
            return None
        out_root.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        for pdf in produced:
            subdir = pdf.parent
            key = os.path.normcase(str(subdir))
            if key in seen:
                continue
            seen.add(key)
            target = _reserve_dir(out_root, subdir.name)
            shutil.move(str(subdir), str(target))
            info["moved"].append(str(target))
            manifest = target / "manifest.json"
            if manifest.is_file():
                info["manifest_rewritten"] = _rewrite_manifest_paths(manifest, subdir, target)
        final = sorted(p for moved in info["moved"] for p in Path(moved).rglob("*.pdf"))
        return {"result": retry, "fallback": info, "produced": [p.resolve() for p in final]}
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


# --------------------------------------------------------------------------- 工具四


def ppt_to_pdf(pptx_path: str, *, output_name: str = "", dry_run: bool = False,
               workspace: str | None = None,
               timeout: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """``ppt_to_pdf(pptx_path, out_dir)`` —— PPTX → PDF（工单 §2 任务二第 2 行）。

    转发 ``toolknit ppt to-pdf``。**依赖本机 LibreOffice**：缺失时 CLI 返回
    ``DEPENDENCY_MISSING``（不会产出空结果），本函数原样透出该错误码 ——
    官方 agent guide 明确要求「缺失时应提示用户安装或配置，**不能假装转换成功**」。

    输出布局（**实测**）：CLI 在 ``--output-dir`` 下**自建独立子文件夹**
    ``<name>_ppt_to_pdf/``，内含 ``<name>.pdf`` 与 ``manifest.json``；
    子目录名带 ``_1``/``_2`` 后缀以避开重名（源码 ``_reserveUniqueDirectory``）。

    ``output_name`` 留空时**自动生成唯一名** ``<stem>-<8位hex>``
    （工单 §2 任务二要求产物落 ``<workspace>/toolknit-output/<uuid>.pdf``；
    实测 CLI **恒建子目录**，故本模块落实为
    ``<workspace>/toolknit-output/<stem>-<hex8>_ppt_to_pdf/<stem>-<hex8>.pdf`` ——
    唯一性满足、路径多一层子目录是与工单的字面偏差，已在 README 偏差表记录；
    带上 ``<stem>`` 是为了产物可追溯到源文件，比裸 uuid 更可读）。

    ``dry_run=True`` 时只做能力/页数探测：**不写任何文件**（``output_path`` 为 ``null``），
    但仍返回 ``slide_count``/``page_count``/``renderer``，实测约 3.2 s。

    **长输出路径自适应（2026-10-15）**：若失败同时满足〔输出路径 >83 字符 +
    ``PROCESSING_FAILED`` + 消息带 fail-fast 退出码〕，本函数会把这次渲染改到**短临时目录**
    重试一次，成功后再把产物**搬回** ``out_root``（目录布局与正常路径一致，``manifest.json``
    内的路径一并改写）。是否用过由返回体 ``path_fallback`` 如实标注；
    ``TOOLKNIT_NO_PATH_FALLBACK=1`` 可关闭该行为。
    """

    def _run() -> dict[str, Any]:
        src = resolve_input(pptx_path, workspace=workspace)
        if src.suffix.lower() != ".pptx":
            return _fail("ppt_to_pdf", f"仅接受 .pptx，收到 {src.suffix!r}", "INVALID_SUFFIX")
        name = str(output_name or "").strip()
        if not name and not dry_run:
            name = f"{src.stem}-{uuid.uuid4().hex[:8]}"
        out_root = resolve_output_dir(workspace=workspace)
        args = ["ppt", "to-pdf", "--input", str(src), "--output-dir", str(out_root)]
        if name:
            args += ["--output-name", name]
        if dry_run:
            args += ["--dry-run"]
        args += ["--json"]
        result = run_cli(args, timeout=timeout)

        # ---- 输出路径过长（上游 soffice 静默 fail-fast）⇒ 自动改短目录重试，再把产物搬回 ----
        fallback: dict[str, Any] = {"used": False, "attempted": False}
        rescued_paths: list[Path] | None = None
        first_elapsed = result["elapsed_s"]
        if not result["ok"] and not dry_run:
            reason = _path_fallback_reason(result, out_root)
            if reason:
                rescued = _render_via_short_path(src, name, out_root, timeout=timeout,
                                                 reason=reason)
                if rescued is None:
                    fallback = {"used": False, "attempted": True, "reason": reason,
                                "from": str(out_root)}
                else:
                    result = rescued["result"]
                    fallback = rescued["fallback"]
                    rescued_paths = rescued["produced"]
        if not result["ok"]:
            return _cli_failure("ppt_to_pdf", result,
                                hint=_libreoffice_hint(result["error_code"]),
                                path_fallback=fallback)

        data = (result["payload"] or {}).get("result", {}) or {}
        # dry-run 不产出文件 ⇒ 关掉目录兜底，避免把既有的旧 PDF 误当成本次产物
        if rescued_paths is not None:
            produced = rescued_paths
        else:
            produced = _discover_pdfs(out_root, data, fallback_glob=not dry_run)
        renderer = data.get("renderer") or {}
        elapsed = result["elapsed_s"] if not fallback.get("used") else first_elapsed + result["elapsed_s"]
        return _ok("ppt_to_pdf", result["payload"], {
            "source": rel_to_workspace(src, workspace=workspace),
            "output_dir": rel_to_workspace(out_root, workspace=workspace),
            "outputs": [rel_to_workspace(p, workspace=workspace) for p in produced],
            "outputs_abs": [str(p) for p in produced],
            "output_pdf": rel_to_workspace(produced[0], workspace=workspace) if produced else "",
            "exists": bool(produced),
            "dry_run": dry_run,
            "output_name": name,
            "slide_count": data.get("slide_count"),
            "page_count": data.get("page_count"),
            "renderer_available": bool(renderer.get("available")),
            "renderer_source": renderer.get("source"),
            "path_fallback": fallback,
            "wrote_files": bool(produced),
            "elapsed_s": elapsed,
        })

    return _guard("ppt_to_pdf", _run)


def _libreoffice_hint(error_code: str | None) -> str:
    """渲染类失败给出**可执行**的修复指引（而不是空错误）。

    ``DEPENDENCY_MISSING``：根本没装/找不到 LibreOffice。
    ``PROCESSING_FAILED``：装了但转换崩了。实测（2026-10-14，本机 LibreOffice 26.8.1.1
    + @toolknit/cli 2.3.1）**主因是输出路径过长**：上游把
    ``-env:UserInstallation=<output-dir>/.toolknit-libreoffice-XXXXXX/profile``
    以 ``file:///…`` URL 传给 soffice，**该 URL 一旦跨过 127 字符，soffice 就静默
    fail-fast（exit code 3221226505 = 0xC0000409），stderr 为空**。

    受控实测（同一基准目录，只改 ``--output-dir`` 长度，各跑 2 次）::

        --output-dir 长度  82  → 成功    83  → 成功
                           84  → 失败    85  → 失败

    （``128 - 8(``file:///``) - 36(``/.toolknit-libreoffice-XXXXXX/profile``) = 84``）
    注意：**与目录层级无关**——实测「长而浅」（1 层、109 字符）失败，
    「短而深」（6 层、71 字符）成功。
    """
    if error_code == "DEPENDENCY_MISSING":
        return (f"未找到 LibreOffice 渲染器：请安装 LibreOffice，或把 {LIBREOFFICE_ENV} "
                "指向 soffice.com / soffice.exe；可用 renderer_probe 复核。")
    if error_code == "PROCESSING_FAILED":
        return ("LibreOffice 已找到但转换失败。**先查输出路径长度**：实测 ``--output-dir`` "
                "绝对路径 >83 字符时 soffice 会静默 fail-fast（exit 3221226505，stderr 为空），"
                "因为上游传给它的 ``-env:UserInstallation`` 文件 URL 跨过了 127 字符上限。"
                "把工作区根换到更短的路径即可（如 ``C:\\\\tk``）。"
                "注意：本模块**已自动试过一次**短目录降级重试（见返回的 ``path_fallback``）——"
                "若 ``path_fallback.attempted`` 为真而 ``used`` 为假，说明**重试也没救回来**，"
                "问题不在路径长度（重点看 ``path_fallback.retry_error`` 与 ``cli_stderr``）。"
                "若路径很短且未触发重试，则可能是并发调用共用 LibreOffice profile：串行化后重试。")
    return ""


def _discover_pdfs(out_root: Path, data: dict[str, Any],
                   *, fallback_glob: bool = True) -> list[Path]:
    """从 CLI 返回体里取产物 PDF 路径（**两个工具形状不同，实测**）。

    实测形状（2026-10-14，2.3.1）::

        ppt to-pdf    : result.output_path = "<…>/sample_ppt_to_pdf/sample.pdf"   ← 单数字段
                        （**没有** result.outputs 键）
        pdf compress  : result.outputs = [{"path": …, "pages": …, "bytes": …}]    ← 数组

    故按 **output_path → outputs[].path → files[].path** 顺序取；
    三者都取不到才退回扫目录（按 mtime 新→旧），并用 ``fallback_glob`` 关闭兜底。
    """
    found: list[Path] = []

    single = data.get("output_path")
    if isinstance(single, str) and single.strip():
        path = Path(single)
        if not path.is_absolute():
            path = out_root / path
        if path.is_file():
            found.append(path.resolve())

    for key in ("outputs", "files"):
        raw = data.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            candidate = item.get("path") if isinstance(item, dict) else item
            if not candidate:
                continue
            path = Path(str(candidate))
            if not path.is_absolute():
                path = out_root / path
            if path.is_file():
                found.append(path.resolve())

    # 去重且保持顺序
    seen: set[str] = set()
    unique: list[Path] = []
    for path in found:
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            unique.append(path)
    if unique:
        return [p for p in unique if p.suffix.lower() == ".pdf"] or unique
    if not fallback_glob or not out_root.is_dir():
        return []
    return sorted((p.resolve() for p in out_root.rglob("*.pdf")),
                  key=lambda p: p.stat().st_mtime, reverse=True)


__all__ = [
    "CLI_PACKAGE",
    "CLI_VERSION_ENV",
    "COMPRESS_LEVELS",
    "DEFAULT_CLI_VERSION",
    "DEFAULT_TIMEOUT_S",
    "LIBREOFFICE_ENV",
    "LIBREOFFICE_FAILFAST_RC",
    "LIBREOFFICE_OUTPUT_PATH_LIMIT",
    "PALETTE_MAX_COUNT",
    "PALETTE_MIN_COUNT",
    "PATH_FALLBACK_ENV",
    "CliUnavailable",
    "cli_argv",
    "cli_spec",
    "cli_version",
    "cli_version_probe",
    "doctor",
    "extract_palette",
    "log_call",
    "path_fallback_disabled",
    "pdf_compress",
    "pdf_inspect",
    "ppt_to_pdf",
    "renderer_probe",
    "run_cli",
]
