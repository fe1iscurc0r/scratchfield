"""link_reliability 原型测试（SPEC-20 v1.6 验收：EWMA/XOR 正确性）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from link_reliability import (
    THRESH_MEDIUM,
    THRESH_STRONG,
    group_for,
    recover,
    redundancy_count,
    update_reliability,
    xor_redundancy,
)


def test_ewma_all_ack_converges_to_1():
    r = 0.5
    for _ in range(100):
        r = update_reliability(r, True)
    assert r > 0.999


def test_ewma_all_lost_converges_to_0():
    r = 0.5
    for _ in range(100):
        r = update_reliability(r, False)
    assert r < 0.001


def test_ewma_mixed_reflects_history():
    # 10 次全成功后 1 次失败：R 应小幅下降但不至于跌破 B
    r = 0.0
    for _ in range(10):
        r = update_reliability(r, True)
    assert r > THRESH_STRONG
    r = update_reliability(r, False)
    assert THRESH_MEDIUM <= r < THRESH_STRONG


def test_group_boundaries():
    assert group_for(0.8) == "A"
    assert group_for(0.79) == "B"
    assert group_for(0.5) == "B"
    assert group_for(0.49) == "C"
    assert redundancy_count("A") == 0
    assert redundancy_count("B") == 1
    assert redundancy_count("C") == 2


def test_xor_roundtrip_lose_one_of_two():
    p1 = b"\x01\x02\x03"
    p2 = b"\x10\x20\x30"
    x = xor_redundancy([p1, p2])
    rec = recover([p1, None], x)
    assert rec == p2


def test_xor_roundtrip_lose_one_of_three():
    p1 = b"\x01\x02"
    p2 = b"\x03\x04"
    p3 = b"\x05\x06"
    x = xor_redundancy([p1, p2, p3])
    assert recover([None, p2, p3], x) == p1
    assert recover([p1, None, p3], x) == p2
    assert recover([p1, p2, None], x) == p3


def test_xor_unequal_length_padding():
    p1 = b"\x01"
    p2 = b"\x02\x03"
    x = xor_redundancy([p1, p2])
    rec = recover([None, p2], x)
    assert rec == b"\x01\x00"  # 短帧补 0


def test_recover_requires_exactly_one_missing():
    p1 = b"\x01"
    p2 = b"\x02"
    x = xor_redundancy([p1, p2])
    try:
        recover([None, None], x)
        assert False, "应抛 ValueError"
    except ValueError:
        pass
