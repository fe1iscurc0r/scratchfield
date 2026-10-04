# -*- coding: utf-8 -*-
"""event_protocol + workorder_split_rules 测试（W64-02/04 验收）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workorder_split_rules import RawTask, order_non_blocking_first, split_workorders

from mcpserver.event_protocol import Event, StateMachine, deserialize, serialize

# ---- W64-02 事件协议 ----

def test_event_serialize_roundtrip():
    e = Event("t1", "exec_done", status="done", output_ref="out://1")
    e.sig = e.compute_sig()
    assert deserialize(serialize(e)).to_dict() == e.to_dict()


def test_state_machine_legal_transitions():
    sm = StateMachine()
    assert sm.transition("running") is True
    assert sm.transition("done") is True
    assert sm.transition("running") is False  # done 无出边


def test_state_machine_blocked_path():
    sm = StateMachine()
    sm.transition("running")
    assert sm.transition("blocked") is True
    assert sm.transition("running") is True  # blocked 可回到 running


# ---- W64-04 工单拆分 ----

def test_dedup_gate_blocks_duplicate():
    tasks = [RawTask("a", "实现频谱缓存"), RawTask("b", "实现频谱缓存")]
    orders = split_workorders(tasks)
    assert len(orders) == 1  # 去重门拦截重复


def test_blocking_marked_and_not_first():
    tasks = [RawTask("a", "实现频谱缓存"), RawTask("c", "接入解调链", deps=["a"])]
    orders = order_non_blocking_first(split_workorders(tasks))
    assert orders[0].id == "a"  # 非阻塞在前
    assert orders[-1].blocking is True


def test_review_gate_on_short_timeout():
    tasks = [RawTask("d", "写测试", timeout_s=30)]
    orders = split_workorders(tasks)
    assert orders[0].needs_review is True
