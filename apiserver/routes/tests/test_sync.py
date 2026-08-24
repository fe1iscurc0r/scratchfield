"""
H-01 验收测试（v2 施工图）：/api/sync 双实例 CRDT 同步端点。

覆盖：
  1. 双实例 20 次随机编辑（写/改/删 45:35:20）→ 各自 POST 增量（独立 instance_id + 独立 clock）
     → GET 按 seq 拉取 → pycrdt 合并 → 双方视图一致且完整率 100%
  2. 同 clock 跨实例不覆盖（v2 核心回归：唯一键 (doc_id, instance_id, clock)）
  3. 增量幂等 upsert（同 (doc_id, instance_id, clock) 重发不增行、seq 不变）
  4. compact 手动合并旧增量后行数收敛、合并结果等价、merged 行带新 seq
  5. 非法 base64 返回 400

运行：python -m pytest apiserver/routes/tests/test_sync.py -q
"""

from __future__ import annotations

import base64
import random
import sqlite3

import pycrdt
import pytest
from fastapi.testclient import TestClient

from apiserver import naga_auth
from apiserver.routes import sync as sync_module

KB_KEY = "kb"
DOC_ID = "kb-notes"
INST_A = "inst-a"
INST_B = "inst-b"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """mock 鉴权 + 数据目录隔离 + 使用真实 app（跳过 lifespan 后台任务）。"""
    # 测试环境可 mock 鉴权：本地免鉴权模式 → 全局中间件直接放行
    monkeypatch.setattr(naga_auth, "is_auth_required", lambda: False)
    # require_local_auth 依赖同样放行（require_auth=False）
    monkeypatch.setattr(naga_auth, "_load_auth_config", lambda: ("admin", "", "", False))
    # SQLite 落临时目录，不污染真实数据目录
    monkeypatch.setattr(sync_module, "get_data_dir", lambda: tmp_path)

    from apiserver.api_server import app

    return TestClient(app)


# ============ 工具 ============


def _make_doc() -> pycrdt.Doc:
    doc = pycrdt.Doc()
    kb = doc.get(KB_KEY, type=pycrdt.Map)
    with doc.transaction():
        for i in range(8):
            e = pycrdt.Map()
            kb[f"note{i}"] = e
            e["title"] = f"标题{i}"
            e["content"] = f"内容{i}"
            e["tags"] = f"tag{i}"
    return doc


def _snapshot(doc: pycrdt.Doc) -> dict:
    kb = doc.get(KB_KEY, type=pycrdt.Map)
    out = {}
    for k, v in kb.items():
        out[k] = v.to_py() if hasattr(v, "to_py") else v
    return out


def _random_edit(doc: pycrdt.Doc, rng: random.Random) -> tuple[str, str]:
    """在 doc 上随机执行一个编辑，返回 (op, key)。写:改:删 = 45:35:20。"""
    kb = doc.get(KB_KEY, type=pycrdt.Map)
    keys = list(kb.keys())
    op = rng.choices(["write", "update", "delete"], weights=[45, 35, 20])[0]
    with doc.transaction():
        if op == "write" or not keys:
            name = f"note-{rng.randint(0, 9999)}"
            e = pycrdt.Map()
            kb[name] = e
            e["title"] = f"新-{rng.randint(0, 999)}"
            e["content"] = f"离线写入-{rng.randint(0, 999)}"
            return "write", name
        if op == "update":
            name = rng.choice(keys)
            v = kb[name]
            if hasattr(v, "to_py"):
                v["content"] = f"改-{rng.randint(0, 999)}"
            else:
                kb[name] = f"改-{rng.randint(0, 999)}"
            return "update", name
        name = rng.choice(keys)
        del kb[name]
        return "delete", name


def _post_update(client: TestClient, doc_id: str, instance_id: str, clock: int, update: bytes) -> dict:
    resp = client.post(
        "/api/sync/update",
        json={
            "doc_id": doc_id,
            "instance_id": instance_id,
            "clock": clock,
            "update_b64": base64.b64encode(update).decode(),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    return body


def _fetch_updates(client: TestClient, doc_id: str, since: int = 0) -> list[dict]:
    resp = client.get("/api/sync/updates", params={"doc_id": doc_id, "since": since})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    return body["updates"]


# ============ 验收测试 ============


def test_two_instance_converge_completeness_100pct(client: TestClient):
    """核心验收：双实例 20 次随机冲突合并，视图一致 + 完整率 100%。

    两实例使用独立 instance_id + 独立 clock 计数器——跨实例同 clock 碰撞
    真实发生，唯一键 (doc_id, instance_id, clock) 必须保证 20 行全落盘。
    """
    rng = random.Random(42)
    doc_a = _make_doc()
    doc_b = _make_doc()
    before = set(_snapshot(doc_a).keys()) | set(_snapshot(doc_b).keys())

    ops: list[tuple[str, str]] = []
    clock_a = 0
    clock_b = 0
    # 每轮随机选一个实例离线编辑，get_update() 导出自上次以来的增量；实例内 clock 独立递增
    for _ in range(20):
        if rng.random() < 0.5:
            target, inst = doc_a, INST_A
            clock_a += 1
            clock = clock_a
        else:
            target, inst = doc_b, INST_B
            clock_b += 1
            clock = clock_b
        op, key = _random_edit(target, rng)
        ops.append((op, key))
        _post_update(client, DOC_ID, inst, clock, target.get_update())

    # 应存活集合 = 初始并集 - 被任一实例显式删除的 key（双方都删=删除生效，不算丢失）
    deleted = {key for op, key in ops if op == "delete"}
    expected = before - deleted

    # 双实例各自拉取全部增量并合并（水位 = 返回最大 seq）
    updates = _fetch_updates(client, DOC_ID, since=0)
    assert len(updates) == 20, "20 条增量全部落盘（同 clock 跨实例不得覆盖）"

    # grep 验收：sync_updates 表真实存在（SQLite 落盘）
    conn = sqlite3.connect(sync_module._db_path())
    table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_updates'").fetchone()
    conn.close()
    assert table is not None, "sync_updates 表必须真实存在"

    # seq 单调递增：水位语义稳定
    seqs = [u["seq"] for u in updates]
    assert seqs == sorted(seqs), "seq 必须按插入序单调"

    def apply_all(doc: pycrdt.Doc) -> None:
        for u in updates:
            doc.apply_update(base64.b64decode(u["update_b64"]))

    apply_all(doc_a)
    apply_all(doc_b)

    snap_a = _snapshot(doc_a)
    snap_b = _snapshot(doc_b)
    assert snap_a == snap_b, "双实例合并后视图必须一致"

    after = set(snap_a.keys())
    lost = expected - after
    completeness = (len(expected) - len(lost)) / len(expected) if expected else 1.0
    assert completeness == 1.0, f"完整率 {completeness * 100:.1f}% != 100%，丢失: {sorted(lost)}"


def test_same_clock_different_instances_not_overwritten(client: TestClient):
    """v2 核心回归：两实例各自 clock=1 的增量必须同时保留（旧版 (doc_id, clock) 会覆盖）。"""
    doc_a = _make_doc()
    doc_b = _make_doc()
    with doc_a.transaction():
        doc_a.get(KB_KEY, type=pycrdt.Map)["only-a"] = "来自A"
    with doc_b.transaction():
        doc_b.get(KB_KEY, type=pycrdt.Map)["only-b"] = "来自B"
    _post_update(client, DOC_ID, INST_A, clock=1, update=doc_a.get_update())
    _post_update(client, DOC_ID, INST_B, clock=1, update=doc_b.get_update())

    updates = _fetch_updates(client, DOC_ID, since=0)
    assert len(updates) == 2, "同 clock 不同实例的两条增量都必须保留，不得互相覆盖"

    fresh = pycrdt.Doc()
    for u in updates:
        fresh.apply_update(base64.b64decode(u["update_b64"]))
    snap = _snapshot(fresh)
    assert snap["only-a"] == "来自A"
    assert snap["only-b"] == "来自B"


def test_update_upsert_idempotent(client: TestClient):
    """同 (doc_id, instance_id, clock) 重发幂等：行数不增、seq 不变。"""
    doc = _make_doc()
    update = doc.get_update()
    _post_update(client, DOC_ID, INST_A, clock=1, update=update)
    first_seq = _fetch_updates(client, DOC_ID, since=0)[0]["seq"]
    # 同 (instance_id, clock) 重发
    _post_update(client, DOC_ID, INST_A, clock=1, update=update)

    updates = _fetch_updates(client, DOC_ID, since=0)
    assert len(updates) == 1, "同 (doc_id, instance_id, clock) 重发不增行"
    assert updates[0]["seq"] == first_seq, "幂等重发不得改变 seq（水位稳定性）"


def test_compact_merges_to_single_update(client: TestClient):
    """compact 手动合并旧增量为单条，且合并结果等价于逐条应用。"""
    doc = _make_doc()
    updates: list[bytes] = []
    for i in range(5):
        with doc.transaction():
            kb = doc.get(KB_KEY, type=pycrdt.Map)
            e = pycrdt.Map()
            kb[f"c{i}"] = e
            e["content"] = f"c{i}"
        updates.append(doc.get_update())
        _post_update(client, DOC_ID, INST_A, clock=i + 1, update=updates[-1])

    before = _fetch_updates(client, DOC_ID, since=0)
    assert len(before) == 5

    resp = client.post("/api/sync/compact", json={"doc_id": DOC_ID})
    assert resp.status_code == 200, resp.text
    compact_body = resp.json()
    assert compact_body["ok"] is True
    assert compact_body["rows"] == 5
    assert compact_body["merged_seq"] is not None

    after = _fetch_updates(client, DOC_ID, since=0)
    assert len(after) == 1, "compact 后收敛为单条"
    assert after[0]["seq"] == compact_body["merged_seq"], "merged 行 seq 与 compact 返回一致"
    assert after[0]["seq"] > before[-1]["seq"], "merged 行获得新的自增 seq（水位单调）"

    # 合并后单条 update 应用结果 == 逐条应用结果
    fresh = pycrdt.Doc()
    fresh.apply_update(base64.b64decode(after[0]["update_b64"]))
    ref = pycrdt.Doc()
    for u in updates:
        ref.apply_update(u)
    assert _snapshot(fresh) == _snapshot(ref)


def test_invalid_base64_rejected(client: TestClient):
    """非法 base64 增量返回 400。"""
    resp = client.post(
        "/api/sync/update",
        json={"doc_id": DOC_ID, "instance_id": INST_A, "clock": 1, "update_b64": "!!!not-base64!!!"},
    )
    assert resp.status_code == 400
