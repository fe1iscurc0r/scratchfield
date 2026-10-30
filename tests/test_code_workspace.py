"""W121-01 / W121-04 验收：Code Workspace 工具集 + 沙箱安全边界；
WO-269 T1（P0-2）：子进程环境白名单 + 解释器隔离 + cwd 固定在沙箱根。

对应工单验收：
- W121-01：code_exec 跑 print(1+1) → stdout 含 2/exit 0；白名单外命令被拒；file_write 后 file_read 一致；
  test_run 对 1 个故意失败的测试返回 failed=1；≥6 用例
- W121-04：路径穿越被拒（../、绝对路径、symlink 逃逸）；超时 kill；白名单拒绝；内存超限被杀；audit 记录
- WO-269 T1：父进程 OPENAI_API_KEY=leak-canary ⇒ 子进程读到 None 且 PATH 仍可见；
  子进程 sys.flags.isolated == 1；白名单表可被单测直接断言；原有 10 条用例全过（现共 21 条）
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json
import os
import sys
from pathlib import Path

import pytest

from mcpserver.code_workspace import sandbox
from mcpserver.code_workspace.tools import CodeWorkspaceBridge


@pytest.fixture()
def bridge(tmp_path, monkeypatch):
    """工作区内嵌到 tmp；审计文件也重定向到 tmp（不污染用户目录）。"""
    monkeypatch.setattr(sandbox, "workspace_root", lambda: tmp_path / "code_workspace")
    monkeypatch.setattr(sandbox, "_audit_path", lambda: tmp_path / "audit" / "code_workspace.ndjson")
    return CodeWorkspaceBridge()


# --------------------------------------------------------------------------
# W121-01 工具集
# --------------------------------------------------------------------------


def test_code_exec_success_and_failure(bridge):
    ok = bridge.code_exec("print(1+1)", language="python")
    assert ok["ok"] is True and "2" in ok["stdout"] and ok["exit_code"] == 0

    bad = bridge.code_exec("raise SystemExit(3)", language="python")
    assert bad["ok"] is False and bad["exit_code"] == 3

    unsupported = bridge.code_exec("print(1)", language="ruby")
    assert unsupported["error"] == "unsupported_language"


def test_code_exec_timeout_kills_process(bridge):
    result = bridge.code_exec("import time\nwhile True: time.sleep(0.2)", language="python", timeout_s=1)
    assert result.get("error") == "timeout"
    assert "超时" in result.get("message", "")


def test_file_write_read_roundtrip_and_diff(bridge):
    preview = bridge.file_write("pkg/main.py", "print(1)\n", dry_run=True)
    assert preview["ok"] is True and preview["created"] is True
    assert "+print(1)" in preview["diff"]
    assert bridge.file_read("pkg/main.py")["error"] == "not_found"  # dry_run 未落盘

    written = bridge.file_write("pkg/main.py", "print(1)\n")
    assert written["ok"] is True
    read_back = bridge.file_read("pkg/main.py")
    assert read_back["ok"] is True and read_back["content"] == "print(1)\n"


def test_file_edit_patch_semantics(bridge):
    bridge.file_write("a.py", "value = 1\nprint(value)\n")

    edited = bridge.file_edit("a.py", "value = 1", "value = 2")
    assert edited["ok"] is True and "-value = 1" in edited["diff"] and "+value = 2" in edited["diff"]
    assert "value = 2" in bridge.file_read("a.py")["content"]

    assert bridge.file_edit("a.py", "not-there", "x")["error"] == "old_not_found"
    bridge.file_write("dup.py", "x\nx\n")
    assert bridge.file_edit("dup.py", "x", "y")["error"] == "old_ambiguous"


def test_test_run_reports_failure_counts(bridge):
    bridge.file_write("tests/test_sample.py", "def test_ok():\n    assert 1 == 1\n\n\ndef test_bad():\n    assert 1 == 2\n")
    result = bridge.test_run("tests", timeout_s=120)
    assert result["summary"]["passed"] == 1
    assert result["summary"]["failed"] == 1
    assert any("test_bad" in name for name in result["summary"]["failed_tests"])
    assert result["ok"] is False


# --------------------------------------------------------------------------
# W121-04 沙箱边界
# --------------------------------------------------------------------------


def test_path_traversal_and_absolute_and_symlink_denied(bridge, tmp_path):
    # `C:\Windows\win.ini` 只在 **Windows** 上是绝对路径。在 POSIX 上它就是一个普通的
    # 相对文件名，落成 not_found 才是正确行为（不是逃逸），所以按平台挑样本 ——
    # 否则这条用例在 CI 的 Ubuntu runner 上必挂（2026-10-30 实测）。
    bad_paths = ["../secret.txt", "a/../../secret.txt", "/etc/passwd", "~/x"]
    if os.name == "nt":
        bad_paths.insert(2, "C:\\Windows\\win.ini")
    for bad in bad_paths:
        result = bridge.file_read(bad)
        assert result.get("error") in {
            "path_traversal_denied",
            "absolute_path_denied",
            "path_escape_denied",
        }, (bad, result)

    # 链接逃逸：工作区内建一个指向外面的链接（Windows 无权限建 symlink 时退回 junction）
    ws = sandbox.session_workspace("default")
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("secret", encoding="utf-8")
    link = ws / "escape"
    if not _make_escape_link(link, outside_dir):
        pytest.skip("当前环境不支持创建 symlink/junction")
    result = bridge.file_read("escape/secret.txt")
    assert result.get("error") == "path_escape_denied", result


def _make_escape_link(link: Path, target: Path) -> bool:
    """建目录链接（symlink 优先，Windows 退回 junction，都不行返回 False）。

    ⚠️ 必须**验证链接真能穿透到目标**：Windows 上 `os.symlink` 在无开发者模式/权限
    降级时不抛异常却产出**不可解析**的链接 —— 只判 `link.exists()` 会误判成功，
    测试随后以 not_found 假失败（2026-10-10 实测本机即为此类）。
    """
    import subprocess as _sp

    marker = f".probe_{os.getpid()}"
    try:
        (target / marker).write_text("", encoding="utf-8")
    except OSError:
        return False

    def _probe() -> bool:
        return (link / marker).exists()

    try:
        os.symlink(target, link, target_is_directory=True)
        if _probe():
            (target / marker).unlink(missing_ok=True)
            return True
        # 建出来了但不可解析 → 清掉，退回 junction
        Path(link).unlink(missing_ok=True)
    except (OSError, NotImplementedError, AttributeError):
        pass

    if os.name == "nt":
        proc = _sp.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            # cmd 输出是 GBK。不写死编码时它跟随父进程 locale：一旦 pytest 跑在
            # UTF-8 模式（-X utf8）下，reader 线程会 strict utf-8 解码 GBK 字节而抛
            # UnicodeDecodeError（2026-10-22 实测）。只看 returncode，故显式 replace。
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0 and _probe():
            (target / marker).unlink(missing_ok=True)
            return True

    (target / marker).unlink(missing_ok=True)
    return False


def test_shell_allowlist_and_metachar_and_hard_deny(bridge):
    denied = bridge.shell_exec("rm -rf /")
    assert denied.get("error") == "hard_denied"

    not_listed = bridge.shell_exec("whoami")
    assert not_listed.get("error") == "not_allowlisted"

    metachar = bridge.shell_exec("ls; rm -rf /")
    assert metachar.get("error") == "shell_metachar_denied"

    allowed = bridge.shell_exec("python -c \"print('hi')\"")
    assert allowed["ok"] is True and "hi" in allowed["stdout"]


def test_memory_limit_kills_hog(bridge, monkeypatch):
    """内存上限（Windows 走 psutil 看门狗）：超限进程被杀。"""
    pytest.importorskip("psutil")
    monkeypatch.setattr(sandbox, "_limits", lambda: (10.0, 64, 20000))  # 64MB 上限
    result = bridge.code_exec(
        "import time\ndata = bytearray(200 * 1024 * 1024)\ndata[0] = 1\ntime.sleep(3)\nprint(len(data))",
        language="python",
        timeout_s=30,
    )
    # 被看门狗杀掉：没有正常输出、退出码非 0（不是 timeout 而是被 kill）
    assert result.get("exit_code") != 0
    assert "209715200" not in (result.get("stdout") or "")


def test_audit_records_every_execution(bridge, tmp_path):
    bridge.code_exec("print('x')", language="python")
    bridge.shell_exec("ls")
    bridge.shell_exec("whoami")  # 被拒也要记
    bridge.file_write("n.txt", "hi")

    audit_file = tmp_path / "audit" / "code_workspace.ndjson"
    assert audit_file.exists()
    records = [json.loads(line) for line in audit_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    tools = [r.get("tool") for r in records]
    assert "code_exec" in tools and "shell_exec" in tools and "file_write" in tools
    assert any(r.get("denied") == "not_allowlisted" for r in records)


def test_handle_handoff_contract(bridge):
    import asyncio

    ok = json.loads(
        asyncio.run(bridge.handle_handoff({"tool_name": "code_exec", "code": "print('ok')"}))
    )
    assert ok["status"] == "success" and "ok" in ok["data"]["stdout"]

    # MCP dispatch 会把内部字段平铺进同一个 dict，不得被当作工具入参
    dispatched = json.loads(
        asyncio.run(
            bridge.handle_handoff(
                {
                    "tool_name": "code_exec",
                    "code": "print('dispatched')",
                    "_tool_call_id": "call_1",
                    "_original_name": "mcp__code_workspace__code_exec",
                    "_original_args": '{"code": "print(\'dispatched\')"}',
                    "agentType": "mcp",
                    "service_name": "code_workspace",
                }
            )
        )
    )
    assert dispatched["status"] == "success", dispatched
    assert "dispatched" in dispatched["data"]["stdout"]

    denied = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "shell_exec", "command": "rm -rf /"})))
    assert denied["status"] == "error"

    unknown = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "nope"})))
    assert unknown["status"] == "error" and "未知工具" in unknown["message"]

    missing = json.loads(asyncio.run(bridge.handle_handoff({})))
    assert missing["status"] == "error"


# --------------------------------------------------------------------------
# WO-269 T1 / P0-2：子进程环境白名单 + 解释器隔离 + cwd 固定
# --------------------------------------------------------------------------

#: 工单点名的四类形状 + 同义词，全部必须被"凭据命名一票否决"拦住
SECRET_NAME_SHAPES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
    "NOTION_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "APP_SECRET",
    "signing_secret",
    "DB_PASSWORD",
    "POSTGRES_PASSWORD",
    "TLS_PSK",
    "Authorization",
    "SESSION_COOKIE",
    "SSH_PRIVATE_KEY",
)


def test_env_allowlist_is_a_table_not_scattered_literals():
    """白名单表本身可被单测直接断言（工单要求"不要散落在代码里"）。"""
    assert isinstance(sandbox.ENV_ALLOWLIST, frozenset)
    assert {"PATH", "LANG", "TMPDIR"} <= sandbox.ENV_ALLOWLIST
    # 表里不得存在凭据形状的名字 —— 防下一位改配置的人无意间把凭据放进来
    assert [n for n in sandbox.ENV_ALLOWLIST if sandbox.is_secret_env_name(n)] == []
    for shape in SECRET_NAME_SHAPES:
        assert sandbox.is_secret_env_name(shape), shape
    # 不误伤正常变量（"passw" 不匹配 "PATH"）
    for benign in ("PATH", "Path", "LANG", "TMPDIR", "SYSTEMROOT", "HOME", "COMSPEC", "PATHEXT"):
        assert sandbox.is_secret_env_name(benign) is False, benign
    # 隔离参数表也是断言对象（code_exec 用哪几个 flag 被钉住）
    assert sandbox.PYTHON_ISOLATION_FLAGS == ("-I", "-E", "-B", "-X", "utf8")
    # 强制默认值表：白名单只管继承，这两项是沙箱主动设定的（非凭据）
    assert sandbox.ENV_FORCED_DEFAULTS == {"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    assert all(not sandbox.is_secret_env_name(k) for k in sandbox.ENV_FORCED_DEFAULTS)


def test_forced_defaults_applied_even_when_parent_lacks_them(monkeypatch):
    """父进程没有 PYTHONIOENCODING 时也必须给子进程设上 —— 白名单管不了"根本没有"。"""
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    env, _ = sandbox.build_child_env()
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


def test_leak_canary_not_inherited_but_path_still_visible(bridge, monkeypatch):
    """工单验收①：父进程有凭据，子进程读到 None；PATH 仍在（白名单没把正常执行弄死）。"""
    for name in ("OPENAI_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "DB_PASSWORD"):
        monkeypatch.setenv(name, "leak-canary")

    result = bridge.code_exec(
        "import os\n"
        "print(os.environ.get('OPENAI_API_KEY'))\n"
        "print(os.environ.get('GITHUB_TOKEN'))\n"
        "print(os.environ.get('AWS_SECRET_ACCESS_KEY'))\n"
        "print(os.environ.get('DB_PASSWORD'))\n"
        "print('PATH_visible', bool(os.environ.get('PATH')))\n"
    )
    assert result["ok"] is True, result
    lines = result["stdout"].splitlines()
    assert lines[:4] == ["None", "None", "None", "None"], result["stdout"]
    assert lines[4] == "PATH_visible True", result["stdout"]
    assert "leak-canary" not in json.dumps(result, ensure_ascii=False)


def test_shell_exec_also_gets_the_whitelisted_env(bridge, monkeypatch):
    """走白名单的 shell_exec 同样不得继承凭据（argv 由 validate_command 出，env 由 run_process 出）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "leak-canary")
    # 注意不能用 `;`（shell 元字符被拒），这里用 __import__ 避开分号
    result = bridge.shell_exec("python -c \"print(__import__('os').environ.get('OPENAI_API_KEY'))\"")
    assert result["ok"] is True, result
    assert result["stdout"].strip() == "None", result


def test_shell_exec_python_child_still_emits_utf8(bridge):
    """白名单收紧的**反例守卫**：不透传 PYTHONIOENCODING 时，shell_exec 里的 python 会退回
    GBK，父进程按 utf-8 解码成乱码（2026-10-22 实测 `Ĳ`）。
    这条用例保证"闸收紧了但正常用法没被打断"。
    """
    result = bridge.shell_exec("python -c \"print('中文测试')\"")
    assert result["ok"] is True, result
    assert result["stdout"].strip() == "中文测试", result


def test_python_child_runs_isolated(bridge):
    """工单验收②：子进程内 sys.flags.isolated == 1。"""
    result = bridge.code_exec("import sys; print(sys.flags.isolated)")
    assert result["ok"] is True, result
    assert result["stdout"].strip() == "1", result
    # -E / -B / -X utf8 一并钉住（utf8_mode 是 PYTHONIOENCODING 被 -E 废掉后的替代）
    flags = bridge.code_exec("import sys; f=sys.flags; print(f.ignore_environment, f.dont_write_bytecode, f.utf8_mode)")
    assert flags["stdout"].split() == ["1", "1", "1"], flags
    # 中文输出不再变 gbk 乱码（回归钉：曾经靠 PYTHONIOENCODING=utf-8 保证）
    cn = bridge.code_exec("print('中文✓')")
    assert "中文✓" in cn["stdout"], cn


def test_third_party_and_stdlib_imports_survive_isolation(bridge):
    """-I 隐含 -s（用户 site）但不能把 venv 的 site-packages 弄丢，否则工具直接废。"""
    result = bridge.code_exec(
        "import json, re, sqlite3, pathlib\nimport pytest\nprint('ok', pytest.__version__)"
    )
    assert result["ok"] is True, result
    assert result["stdout"].startswith("ok "), result


def test_isolation_drops_cwd_from_sys_path_and_the_documented_remedy(bridge):
    """钉住 -I 的行为变化：工作目录不再自动进 sys.path；官方绕法有效。

    这是工单要求 -I 的**代价**，写进 docs/WO-269-p0-exec-surface.md，不让它变成"意外"。
    """
    bridge.file_write("w269_mod.py", "VALUE = 42\n")
    broken = bridge.code_exec("import w269_mod")
    assert broken["ok"] is False and "ModuleNotFoundError" in broken["stderr"], broken

    fixed = bridge.code_exec(
        "import os, sys\nsys.path.insert(0, os.getcwd())\nimport w269_mod\nprint(w269_mod.VALUE)"
    )
    assert fixed["stdout"].strip() == "42", fixed
    # 文件读写走 cwd 相对路径，不受 sys.path 影响（README 声明的主用法仍可用）
    bridge.file_write("note.txt", "hello\n")
    assert bridge.code_exec("print(open('note.txt').read().strip())")["stdout"].strip() == "hello"


def test_test_run_path_keeps_module_imports_working(bridge, monkeypatch):
    """test_run 不带 -I（只 -E -B -X utf8）：被测模块仍能 import，且环境仍是白名单。"""
    bridge.file_write("tests/w269_helper.py", "VAL = 7\n")
    bridge.file_write(
        "tests/test_w269_helper.py",
        "import sys\n\nimport w269_helper\n\n\n"
        "def test_isolated_flag_off_for_tests():\n"
        "    assert sys.flags.isolated == 0\n\n\n"
        "def test_helper_import_and_no_env_leak():\n"
        "    assert w269_helper.VAL == 7\n"
        "    assert 'OPENAI_API_KEY' not in __import__('os').environ\n",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "leak-canary")
    result = bridge.test_run("tests", timeout_s=180)
    assert result["summary"]["passed"] == 2, result
    assert result["ok"] is True, result


def test_env_extra_cannot_smuggle_secret_names(monkeypatch):
    """build_child_env 两道闸：白名单 ∩ 非秘密命名；env_extra 也没有绕行能力。"""
    monkeypatch.setenv("VENDOR_API_KEY", "canary-value")
    monkeypatch.setenv("NOT_ALLOWLISTED_VAR", "x")
    env, dropped = sandbox.build_child_env(
        {"PATH": "C:\\keep", "OPENAI_API_KEY": "smuggle", "LANG": "zh_CN.UTF-8"}
    )
    assert env["PATH"] == "C:\\keep"
    # 同名大小写变体只留一份（Windows 原本叫 Path）
    assert [k for k in env if k.upper() == "PATH"] == ["PATH"]
    assert env["LANG"] == "zh_CN.UTF-8"
    assert "OPENAI_API_KEY" not in env and "VENDOR_API_KEY" not in env
    assert "NOT_ALLOWLISTED_VAR" not in env
    assert {"OPENAI_API_KEY", "VENDOR_API_KEY", "NOT_ALLOWLISTED_VAR"} <= set(dropped)
    assert not any("canary-value" in v for v in env.values())


def test_secret_veto_works_even_if_allowlist_is_widened(monkeypatch):
    """第二道闸必须**独立**有效：有人把凭据名字误加进白名单，也照样拦。

    只靠"默认拒绝"测不出这道闸 —— 凭据名本来就不在白名单里，否决关不关都拦得住。
    所以这里临时把 ``MY_APP_TOKEN`` 加进 ENV_ALLOWLIST，再证明它仍然进不了子进程环境。
    """
    monkeypatch.setattr(sandbox, "ENV_ALLOWLIST", frozenset(set(sandbox.ENV_ALLOWLIST) | {"MY_APP_TOKEN"}))
    monkeypatch.setenv("MY_APP_TOKEN", "canary-value")
    env, dropped = sandbox.build_child_env({"MY_APP_TOKEN": "smuggle-through-allowlist"})
    assert "MY_APP_TOKEN" not in env
    assert "MY_APP_TOKEN" in dropped
    assert not any("canary" in v for v in env.values())


def test_run_process_refuses_cwd_outside_sandbox(bridge, tmp_path):
    """cwd 固定在沙箱根内：调用方目录 / 沙箱外路径一律拒绝执行（不是拒绝路径，是拒绝起进程）。"""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    denied = sandbox.run_process([sys.executable, "-c", "print(1)"], cwd=outside)
    assert denied.get("error") == "cwd_outside_sandbox", denied
    assert denied.get("exit_code") == 126

    inside = sandbox.run_process([sys.executable, "-c", "print(1)"], cwd=sandbox.session_workspace("default"))
    assert inside["exit_code"] == 0 and inside["stdout"].strip() == "1", inside


def test_audit_records_dropped_count_without_values(bridge, tmp_path, monkeypatch):
    """审计只记被挡掉的变量数量，绝不记名字对应的值。"""
    monkeypatch.setenv("OPENAI_API_KEY", "canary-do-not-log")
    bridge.code_exec("print(1)")

    audit_file = tmp_path / "audit" / "code_workspace.ndjson"
    records = [json.loads(line) for line in audit_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    hit = [r for r in records if r.get("tool") == "code_exec"]
    assert hit and hit[-1]["env_dropped_n"] > 0, hit[-1]
    assert "canary-do-not-log" not in audit_file.read_text(encoding="utf-8")

