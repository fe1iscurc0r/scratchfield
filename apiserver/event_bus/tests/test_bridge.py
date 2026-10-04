"""W119-04 验收：跨总线桥（桥 A 双向 / 桥 B 命令转发 / 防环去重 / 映射表完整性）。

对应工单验收：
- 桥 A 双向事件转发可验证（各写一条事件走完取出）
- 桥 B 至少一条命令转发（NEKO 侧用桩）
- 防环去重用例过
- 映射表含 ≥10 条 topic 对照
- NEKO 上游零改动（本模块只读 NEKO 概念，不 import 其源码）
"""
from __future__ import annotations

import time

from apiserver.event_bus import InProcessEventBus, Topics
from apiserver.event_bus.bridge import (
    LUMO_TO_NEKO,
    LUMO_TO_WORKFLOW,
    NEKO_TO_LUMO,
    WORKFLOW_TO_LUMO,
    LumoNekoBridge,
    NekoStubTransport,
    WorkflowBusBridge,
    reset_bridges_for_tests,
)
from mcpserver.workflow.event_bus import EVENT_TASK_DONE
from mcpserver.workflow.event_bus import EventBus as WorkflowBus


def test_bridge_a_workflow_to_lumo():
    """workflow 发布 task_done → Lumo 总线收到 lumo.task.done（带 trace_id 与 source 标记）。"""
    lumo = InProcessEventBus()
    workflow = WorkflowBus(log_path=None)
    received: list[dict] = []
    lumo.on(Topics.TASK_DONE, lambda e: received.append(e))

    bridge = WorkflowBusBridge(lumo, workflow)
    bridge.attach()
    try:
        workflow.publish(EVENT_TASK_DONE, "workflow", payload={"task_id": "t-1"}, trace_id="trace-abc")
        assert len(received) == 1
        event = received[0]
        assert event["source"] == "workflow-bridge"
        assert event["trace_id"] == "trace-abc"
        assert event["payload"]["task_id"] == "t-1"
        assert bridge.stats()["forwarded_to_lumo"] == 1
    finally:
        bridge.detach()


def test_bridge_a_lumo_to_workflow_explicit():
    """Lumo → workflow 显式转发：publish_to_workflow 后 workflow 侧订阅者收到。"""
    lumo = InProcessEventBus()
    workflow = WorkflowBus(log_path=None)
    got: list = []
    workflow.subscribe("task_created", lambda e: got.append(e))

    bridge = WorkflowBusBridge(lumo, workflow)
    bridge.attach()
    try:
        event = bridge.publish_to_workflow("task_created", {"title": "卷119 收口"}, trace_id="trace-xyz")
        assert event is not None and event.trace_id == "trace-xyz"
        assert len(got) == 1 and got[0].source == "lumo-bridge"
        assert bridge.stats()["forwarded_to_workflow"] == 1
    finally:
        bridge.detach()


def test_bridge_a_auto_forward_when_configured():
    """登记自动转发后，Lumo 侧 emit 该 topic 即自动落到 workflow 总线。"""
    lumo = InProcessEventBus()
    workflow = WorkflowBus(log_path=None)
    got: list = []
    workflow.subscribe("task_created", lambda e: got.append(e))

    bridge = WorkflowBusBridge(lumo, workflow, auto_forward={Topics.TASK_CREATED: "task_created"})
    bridge.attach()
    try:
        lumo.emit(Topics.TASK_CREATED, {"id": "e1", "payload": {"title": "自动转发"}})
        assert len(got) == 1 and got[0].payload["title"] == "自动转发"
    finally:
        bridge.detach()


def test_loop_prevention_dedupes_by_id():
    """防环：同 id 事件第二次进入即被判重（source 属于桥自身也丢弃）。"""
    lumo = InProcessEventBus()
    workflow = WorkflowBus(log_path=None)
    received: list[dict] = []
    lumo.on(Topics.TASK_DONE, lambda e: received.append(e))

    bridge = WorkflowBusBridge(lumo, workflow)
    bridge.attach()
    try:
        workflow.publish(EVENT_TASK_DONE, "workflow", payload={"task_id": "t-2"})
        assert len(received) == 1
        # 制造回环：把刚提升的事件原样再喂回桥（模拟 workflow→Lumo→workflow→Lumo 镜像）
        echo = dict(received[0])
        bridge._on_workflow_event(
            type("E", (), {"event_type": EVENT_TASK_DONE, "id": echo["id"], "source": "", "payload": {}, "trace_id": ""})
        )
        assert len(received) == 1  # 未重复提升
        assert bridge.stats()["skipped_loops"] >= 1
    finally:
        bridge.detach()


def test_bridge_b_command_forward_and_event_promotion():
    """桥 B：Lumo 命令 → NEKO 记录；NEKO 记录 → Lumo 事件（用桩传输）。"""
    lumo = InProcessEventBus()
    transport = NekoStubTransport()
    bridge = LumoNekoBridge(lumo, transport)
    bridge.attach()
    try:
        # 命令方向
        lumo.emit(Topics.SPEAK_REQUESTED, {"id": "c1", "payload": {"text": "在的"}})
        assert len(transport.published) == 1
        record = transport.published[0]
        assert record["type"] == "LUMO_SPEAK_REQUESTED"
        assert record["source"] == "lumo"
        assert record["payload"]["text"] == "在的"

        # 事件方向
        events: list[dict] = []
        lumo.on(Topics.TTS_START, lambda e: events.append(e))
        transport.inject({"id": "n1", "type": "NEKO_TTS_START", "payload": {"voice": "yui"}})
        assert len(events) == 1 and events[0]["neko_type"] == "NEKO_TTS_START"
        assert bridge.stats()["forwarded_to_neko"] == 1
        assert bridge.stats()["forwarded_to_lumo"] == 1

        # 同 id 重复推入 → 去重
        transport.inject({"id": "n1", "type": "NEKO_TTS_START", "payload": {}})
        assert len(events) == 1
        assert bridge.stats()["skipped_loops"] >= 1
    finally:
        bridge.detach()


def test_mapping_table_has_enough_rows():
    """映射表 ≥10 条（工单要求），且 topic 都在 Topics 里登记。"""
    total = len(WORKFLOW_TO_LUMO) + len(LUMO_TO_WORKFLOW) + len(LUMO_TO_NEKO) + len(NEKO_TO_LUMO)
    assert total >= 10, total
    known = {str(getattr(Topics, name)) for name in dir(Topics) if name.isupper()}
    for topic in list(WORKFLOW_TO_LUMO.values()) + list(LUMO_TO_NEKO) + list(NEKO_TO_LUMO.values()):
        assert str(topic) in known


def test_setup_and_reset_bridges():
    """进程级装配/拆卸：setup_bridges 后可查 stats，reset 后清空。"""
    from apiserver.event_bus.bridge import bridge_stats, setup_bridges

    lumo = InProcessEventBus()
    reset_bridges_for_tests()
    setup_bridges(lumo, workflow_bus=WorkflowBus(log_path=None), neko_transport=NekoStubTransport())
    stats = bridge_stats()
    assert set(stats.keys()) == {"workflow", "neko"}
    assert stats["neko"]["transport_available"] is True
    reset_bridges_for_tests()
    assert bridge_stats() == {}


# ---------------------------------------------------------------------------
# W119-04 补：NEKO 真实传输（HTTP → NEKO 注入路由 /api/lumo/speak|emotion）
# ---------------------------------------------------------------------------


def test_neko_http_transport_requires_token():
    """无 LUMO_PROXY_TOKEN 时不可用、publish 直接失败并记录原因。"""
    from apiserver.event_bus.bridge import NekoHttpTransport

    transport = NekoHttpTransport(base_url="http://127.0.0.1:48911", token="")
    assert transport.available() is False
    assert transport.publish({"type": "LUMO_SPEAK_REQUESTED", "payload": {"text": "x"}}) is False
    assert transport.stats()["last_error"]


def test_neko_http_transport_maps_records_to_inject_routes():
    """命令记录 → NEKO 注入路由与请求体的映射（speak/emotion；缺参不发）。"""
    from apiserver.event_bus.bridge import NekoHttpTransport

    transport = NekoHttpTransport(token="tok")
    speak_path, speak_body = transport._build_request(
        {
            "type": "LUMO_SPEAK_REQUESTED",
            "payload": {"character": "桐生桔梗", "text": "在的", "emotion": "happy"},
        }
    )
    assert speak_path == "/api/lumo/speak"
    assert speak_body["lanlan_name"] == "桐生桔梗"
    assert speak_body["text"] == "在的"
    assert speak_body["emotion"] == "happy" and speak_body["emotion_confidence"] == 0.5

    emotion_path, emotion_body = transport._build_request(
        {"type": "LUMO_EMOTION_REQUESTED", "payload": {"character": "YUI", "emotion": "surprised"}}
    )
    assert emotion_path == "/api/lumo/emotion" and emotion_body["emotion"] == "surprised"

    # 缺文本 / 未知类型 → 不发
    assert transport._build_request({"type": "LUMO_SPEAK_REQUESTED", "payload": {"character": "YUI"}}) == (None, {})
    assert transport._build_request({"type": "UNKNOWN", "payload": {}}) == (None, {})


def test_neko_http_transport_sends_in_background(monkeypatch):
    """后台线程真实发起 POST（假 httpx.Client 记录请求），publish 本身不阻塞。"""
    import httpx

    import apiserver.event_bus.bridge as bridge_mod

    captured: list[tuple] = []

    class FakeResponse:
        status_code = 200
        text = "ok"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            captured.append((url, json, headers))
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    transport = bridge_mod.NekoHttpTransport(base_url="http://127.0.0.1:48911", token="tok")
    try:
        assert transport.publish(
            {"id": "1", "type": "LUMO_SPEAK_REQUESTED", "payload": {"character": "YUI", "text": "测试说话"}}
        )
        deadline = time.time() + 3
        while not captured and time.time() < deadline:
            time.sleep(0.05)
        assert captured, "后台线程未发出请求"
        # 等价等待计数落定：captured 是在 post() 内 append，sent 在其返回后才自增，
        # 直接断言会踩到竞态（实测偶发 sent==0）
        deadline = time.time() + 3
        while transport.stats()["sent"] != 1 and time.time() < deadline:
            time.sleep(0.05)
        url, body, headers = captured[0]
        assert url == "http://127.0.0.1:48911/api/lumo/speak"
        assert body["text"] == "测试说话" and body["lanlan_name"] == "YUI"
        assert headers["Authorization"] == "Bearer tok"
        assert transport.stats()["sent"] == 1
    finally:
        transport.close(timeout=2.0)
