"""issue #17: /api/lumo/speak 队列余量预检，根治部分成功语义。

speak 带 emotion 时需要入队 2 条消息；旧行为先入 emotion 再试 speak，
speak 触发 429 时前端已切表情却没声音/字幕。修复后在**任何消息入队前**
预检余量，不足直接 429，队列状态保持原样。

兄弟模块 shared_state / system_router.emotion 用 sys.modules stub 替代，
避免拉起 main_server 全量状态与 LLM 客户端依赖。
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

TOKEN = "test-lumo-proxy-token"
CHAR = "lumian"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

_NEKO_ROOT = Path(__file__).resolve().parents[2]


def _load_router_module(monkeypatch) -> types.ModuleType:
    """文件级加载 lumo_inject_router，用假父包绕过真 main_routers/__init__
    （它会连带拉 pages_router 等重量模块）。"""
    holder_pkg = types.ModuleType("main_routers")
    holder_pkg.__path__ = [str(_NEKO_ROOT / "main_routers")]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "main_routers", holder_pkg)

    spec = importlib.util.spec_from_file_location(
        "main_routers.lumo_inject_router",
        _NEKO_ROOT / "main_routers" / "lumo_inject_router.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "main_routers.lumo_inject_router", module)
    spec.loader.exec_module(module)
    return module


class _SyncPutQueue(asyncio.Queue):
    """镜像生产 _SyncMessageQueue（app/main_server/character_runtime.py）：
    put 同步别名 put_nowait，满时同步抛 QueueFull。"""

    def put(self, item):  # type: ignore[override]
        self.put_nowait(item)


@pytest.fixture()
def client(monkeypatch):
    holder: dict = {}

    shared_stub = types.ModuleType("main_routers.shared_state")
    shared_stub._state = {}  # unit conftest 的 _reset_shared_state 会快照它
    shared_stub.get_sync_message_queue = lambda: holder["queues"]
    shared_stub.get_session_manager = lambda: {}
    monkeypatch.setitem(sys.modules, "main_routers.shared_state", shared_stub)

    system_stub = types.ModuleType("main_routers.system_router")
    monkeypatch.setitem(sys.modules, "main_routers.system_router", system_stub)
    emotion_stub = types.ModuleType("main_routers.system_router.emotion")
    emotion_stub._normalize_emotion_label = lambda label, confidence: label
    monkeypatch.setitem(sys.modules, "main_routers.system_router.emotion", emotion_stub)

    monkeypatch.setenv("LUMO_PROXY_TOKEN", TOKEN)

    lumo_router = _load_router_module(monkeypatch)

    app = FastAPI()
    app.include_router(lumo_router.router)

    def _set_queue(maxsize: int, prefilled: int) -> asyncio.Queue:
        q: asyncio.Queue = _SyncPutQueue(maxsize=maxsize)
        for _ in range(prefilled):
            q.put_nowait({"type": "json", "data": {"type": "filler"}})
        holder["queues"] = {CHAR: q}
        return q

    with TestClient(app) as test_client:
        test_client.set_queue = _set_queue  # type: ignore[attr-defined]
        yield test_client


def test_emotion_plus_speak_rejected_before_enqueue_when_headroom_short(client):
    """余量只够 1 条时，带 emotion 的 speak（需 2 槽）必须整体 429，
    且 emotion 不许先入队（部分成功的根）。"""
    q = client.set_queue(maxsize=2, prefilled=1)

    resp = client.post(
        "/api/lumo/speak",
        json={"lanlan_name": CHAR, "text": "你好", "emotion": "happy"},
        headers=AUTH,
    )

    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "1"
    # 核心断言：队列没有多出 emotion 消息，保持预检前的 1 条
    assert q.qsize() == 1


def test_emotion_plus_speak_enqueues_both_when_room(client):
    q = client.set_queue(maxsize=2, prefilled=0)

    resp = client.post(
        "/api/lumo/speak",
        json={"lanlan_name": CHAR, "text": "你好", "emotion": "happy"},
        headers=AUTH,
    )

    assert resp.status_code == 200
    assert q.qsize() == 2  # emotion + speak 都入队


def test_plain_speak_passes_with_single_free_slot(client):
    """不带 emotion 只需 1 槽：余量 1 时不应被误拒。"""
    q = client.set_queue(maxsize=2, prefilled=1)

    resp = client.post(
        "/api/lumo/speak",
        json={"lanlan_name": CHAR, "text": "你好"},
        headers=AUTH,
    )

    assert resp.status_code == 200
    assert q.qsize() == 2


def test_unknown_character_still_404(client):
    client.set_queue(maxsize=2, prefilled=0)

    resp = client.post(
        "/api/lumo/speak",
        json={"lanlan_name": "ghost", "text": "你好"},
        headers=AUTH,
    )

    assert resp.status_code == 404


def test_unbounded_queue_bypasses_precheck(client):
    """生产现状：_SyncMessageQueue() 无界（maxsize=0），预检不拦截，
    行为与修复前完全一致（不误伤现有部署）。"""
    q = client.set_queue(maxsize=0, prefilled=0)

    resp = client.post(
        "/api/lumo/speak",
        json={"lanlan_name": CHAR, "text": "你好", "emotion": "happy"},
        headers=AUTH,
    )

    assert resp.status_code == 200
    assert q.qsize() == 2
