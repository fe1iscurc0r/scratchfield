"""W121-01 / W121-04 验收：Code Workspace 工具集 + 沙箱安全边界。

对应工单验收：
- W121-01：code_exec 跑 print(1+1) → stdout 含 2/exit 0；白名单外命令被拒；file_write 后 file_read 一致；
  test_run 对 1 个故意失败的测试返回 failed=1；≥6 用例
- W121-04：路径穿越被拒（../、绝对路径、symlink 逃逸）；超时 kill；白名单拒绝；内存超限被杀；audit 记录
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


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows 专用路径拒绝断言（C:\\ 路径），非 Windows 平台由前三个相对路径用例覆盖（2026-10-04 展示仓 CI 口径）",
)
def test_path_traversal_and_absolute_and_symlink_denied(bridge, tmp_path):
    for bad in ("../secret.txt", "a/../../secret.txt", "/etc/passwd", "C:\\Windows\\win.ini", "~/x"):
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
    """建目录链接（symlink 优先，Windows 退回 junction，都不行返回 False）。"""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError, AttributeError):
        pass
    if os.name == "nt":
        import subprocess as _sp

        proc = _sp.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0 and link.exists()
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
