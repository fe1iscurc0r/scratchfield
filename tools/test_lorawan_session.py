"""W71-11 LoRaWAN 会话管理测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from lorawan_session import SessionRegistry


def test_join_allocates_unique_dev_addr():
    reg = SessionRegistry()
    s1 = reg.join("DEV001", "K1")
    s2 = reg.join("DEV002", "K2")
    assert s1["dev_addr"] != s2["dev_addr"]


def test_join_idempotent():
    reg = SessionRegistry()
    s1 = reg.join("DEV001", "K1")
    s2 = reg.join("DEV001", "K1")
    assert s1["dev_addr"] == s2["dev_addr"]      # 重复入网返回同一会话


def test_route_uplink_by_dev_addr():
    reg = SessionRegistry()
    s = reg.join("DEV001", "K1")
    assert reg.route_uplink(s["dev_addr"], "hello") == ("DEV001", "hello")


def test_unknown_dev_addr_rejected():
    reg = SessionRegistry()
    assert reg.route_uplink("FFFFFFFF", "x") is None
    assert not reg.has_dev_addr("FFFFFFFF")
