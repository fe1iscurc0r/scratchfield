"""memory_write_gate 测试（P1-3 原型）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from memory_write_gate import MemoryWriteGate


def test_authorized_write_allowed():
    g = MemoryWriteGate(secret=b"s")
    tok = g.mint("k", "v", "user")
    assert g.write("k", "v", "user", tok) is True
    assert g.retrieve("k") == "v"


def test_forged_write_denied():
    g = MemoryWriteGate(secret=b"s")
    assert g.write("k", "evil", "user", "0" * 64) is False
    assert g.retrieve("k") is None


def test_audit_records_stages():
    g = MemoryWriteGate(secret=b"s")
    tok = g.mint("k", "v", "user")
    g.write("k", "v", "user", tok)
    g.write("k", "evil", "user", "0" * 64)
    stages = {r["stage"] for r in g.audit}
    assert "write" in stages
    # 一次授权一次拒绝
    assert [r["authorized"] for r in g.audit] == [True, False]
