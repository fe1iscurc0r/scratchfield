"""W124-04 验收：事件溯源 surface 双层（四投影 / 原子验证 / 断档 / 兼容）。

覆盖：四投影取数正确（字段裁剪与脱敏）/ 非法事件拒绝 / seq 单调与断档检测 /
surface → event_store 落盘链路 / bus 持久化走验证 / model 面投影成 LLM 上下文 /
未匹配 topic 走默认面 / 调试端点数据。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import pytest

from apiserver.event_bus import surface as surface_mod
from apiserver.event_bus.event_store import build_envelope


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """surface 单例重置，event_store 用 tmp 路径（不碰用户日志）。"""
    from apiserver.event_bus import event_store as event_store_mod
    from apiserver.event_bus.event_store import EventStore

    real = EventStore(tmp_path / "events.jsonl", enabled=True, buffer_lines=1)
    # 总线落盘走 get_event_store() 单例，必须一并指向 tmp，否则会写进用户日志
    monkeypatch.setattr(event_store_mod, "get_event_store", lambda: real)
    surface = surface_mod.SurfaceStore(store=real, window=100)
    surface_mod.reset_surface_store_for_tests(surface)
    yield surface, real
    surface_mod.reset_surface_store_for_tests(None)


def _env(topic: str, payload: dict, *, source: str = "lumo", seq=None) -> dict:
    env = build_envelope(topic, "emit", payload, source=source)
    if seq is not None:
        env["seq"] = seq
    return env


# ---------------------------------------------------------------------------
# 四投影
# ---------------------------------------------------------------------------


def test_four_surfaces_project_correct_subset(store):
    surface, _real = store
    surface.ingest(_env("lumo.user.input.received", {"text": "帮我看看 utils.py", "session_id": "s1",
                                                     "secret_token": "sk-live-abcdef123456"}))
    surface.ingest(_env("lumo.tool.post-execute", {"tool": "code_exec", "session_id": "s1",
                                                   "ok": False, "exit_code": 1, "duration": 0.2}))
    surface.ingest(_env("lumo.memory.created", {"memory_id": "m1", "layer": "long", "summary": "偏好"}))
    surface.ingest(_env("lumo.tts.start", {"text": "好的", "session_id": "s1"}))

    model = surface.surface("model")
    transcript = surface.surface("transcript")
    replay = surface.surface("replay")
    telemetry = surface.surface("telemetry")

    model_topics = [i["topic"] for i in model]
    assert model_topics == ["lumo.user.input.received", "lumo.tool.post-execute"], "记忆事件不进模型面"
    assert model[0]["payload"]["text"] == "帮我看看 utils.py"
    assert "secret_token" not in model[0]["payload"], "白名单外字段必须裁掉"
    assert model[1]["payload"]["exit_code"] == 1 and model[1]["payload"]["ok"] is False

    assert [i["topic"] for i in transcript] == ["lumo.user.input.received", "lumo.tts.start"]
    assert all("payload" in i and "trace_id" not in i for i in transcript), "transcript 面不带 trace_id"

    assert len(replay) == 4, "replay 面保留全量"
    assert all("id" in i and "payload" in i for i in replay)
    assert replay[0]["payload"]["secret_token"] == "sk-live-abcdef123456", "replay 面原样（调试用）"

    telemetry_topics = [i["topic"] for i in telemetry]
    assert "lumo.scheduler.tick" not in telemetry_topics and len(telemetry) == 4
    assert all("payload" in i for i in telemetry)


def test_default_rule_and_unknown_topic(store):
    surface, _real = store
    surface.ingest(_env("custom.unknown.topic", {"anything": 1}))
    assert surface.surface("model") == [], "未匹配 topic 不进模型面"
    assert len(surface.surface("replay")) == 1
    assert surface.surface("telemetry")[0]["payload"] == {}, "默认规则不投影 payload 字段"
    assert surface_mod.rule_for("lumo.task.created")["payload_fields"].count("goal") == 1
    with pytest.raises(ValueError):
        surface_mod.project([], "不存在的面")


def test_session_filter_and_model_messages(store):
    surface, _real = store
    surface.ingest(_env("lumo.user.input.received", {"text": "A 会话", "session_id": "s-a"}))
    surface.ingest(_env("lumo.user.input.received", {"text": "B 会话", "session_id": "s-b"}))

    only_a = surface.surface("model", session_id="s-a")
    assert len(only_a) == 1 and only_a[0]["payload"]["text"] == "A 会话"

    messages = surface.model_messages(session_id="s-a")
    assert messages and messages[0]["role"] == "system"
    assert "〔事件面（surface_model）〕" in messages[0]["content"]
    assert "A 会话" in messages[0]["content"] and "B 会话" not in messages[0]["content"]
    assert surface.model_messages(session_id="nobody") == []


# ---------------------------------------------------------------------------
# 原子验证与断档
# ---------------------------------------------------------------------------


def test_invalid_events_rejected(store):
    surface, _real = store
    assert surface.ingest({"topic": "x"}) is False, "缺必填字段应拒"
    assert surface.ingest({"id": "1", "topic": "t", "source": "s", "trace_id": "tr"}) is False, "缺 timestamp"
    assert surface.ingest({"id": "1", "topic": "t", "source": "s", "trace_id": "tr",
                           "timestamp": 1.0, "seq": "abc"}) is False, "seq 非法"
    assert surface.rejected == 3 and surface.accepted == 0
    assert surface.last_reject_reason == "bad_seq"
    assert surface.surface("replay") == [], "非法事件不入盘"

    assert surface.ingest(_env("lumo.task.created", {"task_id": "t1", "status": "running"})) is True
    assert surface.accepted == 1 and surface.events()[0]["seq"] == 1, "顺序号由 surface 分配"


def test_seq_monotonic_and_gap_detection(store):
    surface, _real = store
    assert surface.ingest(_env("lumo.task.created", {"task_id": "t1"}, seq=1)) is True
    assert surface.ingest(_env("lumo.task.created", {"task_id": "t2"}, seq=1)) is False, "重复序号应拒"
    assert surface.ingest(_env("lumo.task.created", {"task_id": "t3"}, seq=2)) is True
    assert surface.gaps == 0

    surface.ingest(_env("lumo.task.created", {"task_id": "t9"}, seq=9))  # 跳到 9 → 断档
    assert surface.gaps == 1
    stats = surface.stats()
    assert stats["rejected"] == 1 and stats["gaps"] == 1 and stats["accepted"] == 3


def test_surface_persists_to_event_store(store):
    surface, real = store
    surface.ingest(_env("lumo.task.created", {"task_id": "t1", "goal": "做点事"}))
    assert real.flush(timeout=5.0) is True, "先落盘再回放"
    replayed = list(real.replay(topic="lumo.task.created"))
    assert replayed and replayed[0]["payload"]["task_id"] == "t1"
    assert replayed[0].get("seq") == 1, "顺序号随信封一起落盘"


def test_bus_persistence_goes_through_validation(store, monkeypatch):
    """总线持久化走 surface：合法事件入盘、非法事件被拒且不影响分发。"""
    from apiserver.event_bus.bus import InProcessEventBus

    surface, real = store
    bus = InProcessEventBus()
    seen: list = []
    bus.on("lumo.task.created", lambda e: seen.append(e))

    bus.emit("lumo.task.created", {"task_id": "t-bus", "goal": "总线事件"})
    assert seen, "分发不受持久化影响"
    assert real.flush(timeout=5.0) is True
    assert any(str((e.get("payload") or {}).get("task_id")) == "t-bus" for e in real.replay())
    assert surface.accepted >= 1

    # surface 抛错时退回直接落盘（不影响主路径）
    monkeypatch.setattr(surface_mod.SurfaceStore, "ingest",
                        lambda self, env: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.emit("lumo.task.created", {"task_id": "t-fallback"})
    assert len(seen) == 2
    assert real.flush(timeout=5.0) is True
    assert any(str((e.get("payload") or {}).get("task_id")) == "t-fallback" for e in real.replay())


def test_dump_surface_and_stats(store):
    surface, _real = store
    surface.ingest(_env("lumo.tool.post-execute", {"tool": "code_exec", "ok": True, "duration": 0.1}))
    payload = surface_mod.dump_surface("model", limit=10)
    assert payload["surface"] == "model" and payload["count"] == 1
    assert payload["items"][0]["payload"]["tool"] == "code_exec"
    bad = surface_mod.dump_surface("nope")
    assert bad["error"] == "unknown_surface" and "model" in bad["surfaces"]
    stats = surface_mod.surface_stats()
    assert stats["surfaces"] == ["model", "transcript", "replay", "telemetry", "router"]
    assert stats["store"]["accepted"] >= 1
