"""message_ledger 测试（A26 验收：丢包节点信用下降 + 重路由决策生效）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from message_ledger import DOWNGRADE_THRESHOLD, MessageLedger


def _settle_many(ledger, sender, n_ack, n_timeout):
    idx = 0
    for _ in range(n_ack):
        mid = f"{sender}-{idx}"
        ledger.submit(mid, sender)
        ledger.confirm(mid)
        idx += 1
    for _ in range(n_timeout):
        mid = f"{sender}-{idx}"
        ledger.submit(mid, sender)
        ledger.timeout(mid)
        idx += 1


def test_ack_node_credit_rises():
    ledger = MessageLedger()
    _settle_many(ledger, "good", n_ack=10, n_timeout=0)
    assert ledger.credit_of("good") > 0.9
    assert not ledger.downgraded("good")


def test_droppy_node_credit_falls_below_threshold():
    ledger = MessageLedger()
    _settle_many(ledger, "droppy", n_ack=2, n_timeout=8)
    assert ledger.credit_of("droppy") < DOWNGRADE_THRESHOLD
    assert ledger.downgraded("droppy")


def test_reroute_decision_takes_effect():
    ledger = MessageLedger()
    _settle_many(ledger, "good", n_ack=10, n_timeout=0)
    _settle_many(ledger, "droppy", n_ack=2, n_timeout=8)
    relays = [("relay-a", 0.9), ("relay-b", 0.7)]

    assert ledger.routing_decision("good", relays)["mode"] == "direct"
    drop_decision = ledger.routing_decision("droppy", relays)
    assert drop_decision["mode"] == "relay"
    assert drop_decision["relay"] == "relay-a"  # 选可靠性最高中继


def test_unknown_message_settle_is_ignored():
    ledger = MessageLedger()
    ledger.confirm("nonexistent")  # 不报错、不改变任何信用
    assert ledger.credit_of("nobody") == 0.5


def test_audit_history_recorded_and_filterable():
    ledger = MessageLedger()
    ledger.submit("m1", "good")
    ledger.confirm("m1")
    ledger.submit("m2", "droppy")
    ledger.timeout("m2")

    assert len(ledger.audit_records()) == 2
    good = ledger.audit_records("good")
    droppy = ledger.audit_records("droppy")
    assert len(good) == 1 and good[0]["ack"] is True
    assert len(droppy) == 1 and droppy[0]["ack"] is False
    # 结算后信用与账本当前信用一致（可审计闭合）
    assert abs(good[0]["credit_after"] - ledger.credit_of("good")) < 1e-9
    assert abs(droppy[0]["credit_after"] - ledger.credit_of("droppy")) < 1e-9
