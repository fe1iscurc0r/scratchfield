"""permission_kernel 测试（P1-2 原型）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from permission_kernel import PermissionKernel


def test_whitelisted_action_allowed():
    k = PermissionKernel()
    k.grant("file_io", "read")
    assert k.run("file_io", "read", lambda: 42) == 42


def test_unwhitelisted_action_denied():
    k = PermissionKernel()
    assert k.run("shell", "exec", lambda: "BAD") is None
    assert k.violations and k.violations[0]["result"] == "denied"


def test_allow_is_deterministic():
    k = PermissionKernel()
    k.grant("a", "b")
    assert k.allow("a", "b") is True
    assert k.allow("a", "c") is False


def test_runtime_guard_records_violations():
    k = PermissionKernel()
    k.run("net", "upload", lambda: "x")
    k.run("net", "upload", lambda: "x")
    assert len(k.violations) == 2
