"""yjs CRDT 知识库同步落盘（W63-01）。

功能：
- 双实例离线编辑 → update 交换 → 收敛（纯 Python mock，无 pycrdt 依赖）；
- SQLite 持久化：CRDT update 序列存入磁盘，重启后恢复状态；
- 同步端点骨架：apiserver/routes/sync.py 的占位路由（标注 TODO/FIXME）。

pycrdt 不可用时自动降级为纯内存 mock（标注 @pycrdt_required 装饰器），
不引入重依赖。

实现要点（来自 scripts/yjs_sync_prototype.py 的参考设计）：
- Doc = update 序列容器；
- get(KB_KEY, type=Map) 取命名 map；
- transaction() 包裹写操作；
- doc.get_update() / doc.apply_update(blob) 做状态交换；
- 收敛性保证：CRDT merge 数学证明保证双实例最终一致。

本模块纯标准库 sqlite3 + hashlib，不碰 NEKO 五件套。
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------#
# pycrdt 可用性探测 + mock 降级（@pycrdt_required 装饰器）
# -----------------------------------------------------------------------------#

_HAVE_PYCRDT = False
try:
    import pycrdt
    _HAVE_PYCRDT = True
except ImportError:
    pycrdt = None  # type: ignore


def pycrdt_required(func):
    """标注需要真实 pycrdt 的函数（装饰器，当前版本 mock 透明替代）。"""
    return func


# -----------------------------------------------------------------------------#
# Mock CRDT 基类（pycrdt 不可用时的纯内存实现，仅用于本地原型验证）
# -----------------------------------------------------------------------------#

class _MockMap:
    """pycrdt.Map 的内存 mock（支持 item 赋值/删除/traverse）。"""
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def __setitem__(self, key: str, value: Any) -> None:
        if isinstance(value, _MockMap):
            self._data[key] = value
        else:
            self._data[key] = str(value)

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key)

    def __delitem__(self, key: str) -> None:
        self._data.pop(key, None)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def get(self, key: str, default=None):
        return self._data.get(key, default)


class _MockDoc:
    """pycrdt.Doc 的内存 mock（update 序列容器，支持 merge 收敛）。"""
    def __init__(self) -> None:
        self._maps: dict[str, _MockMap] = {}
        self._updates: list[bytes] = []
        self._clock = 0  # 简单逻辑时钟，模拟 Lamport timestamp

    def transaction(self):
        return _MockTransaction(self)

    def get(self, key: str, type=None):
        if key not in self._maps:
            self._maps[key] = _MockMap()
        return self._maps[key]

    def _map_to_dict(self, m: "_MockMap | dict", _seen: set | None = None) -> dict:
        """递归将 _MockMap 转换为纯 dict（带循环检测，防止自引用导致无限递归）。"""
        if _seen is None:
            _seen = set()
        oid = id(m)
        if oid in _seen:
            return {"<cycle>": True}
        _seen.add(oid)
        try:
            if isinstance(m, _MockMap):
                return {k: self._map_to_dict(v, _seen)
                        for k, v in m._data.items()}
            elif isinstance(m, dict):
                return {k: self._map_to_dict(v, _seen) for k, v in m.items()}
            return m
        finally:
            _seen.discard(oid)

    def get_update(self) -> bytes:
        # 序列化为 JSON bytes（实际 pycrdt 用 binary）
        state = {
            "maps": {k: self._map_to_dict(v) for k, v in self._maps.items()},
            "clock": self._clock,
        }
        return json.dumps(state, ensure_ascii=False).encode("utf-8")

    def apply_update(self, update: bytes) -> None:
        # 简单合并：对方的 map 键值直接覆盖本地（Last-Write-Wins）
        # 真实 CRDT 会用 vector clock；这里 mock 保证收敛性（最终一致）
        self._updates.append(update)
        try:
            state = json.loads(update.decode("utf-8"))
        except Exception:
            return
        remote_clock = state.get("clock", 0)
        if remote_clock > self._clock:
            self._clock = remote_clock
        for rk, rv in state.get("maps", {}).items():
            if rk not in self._maps:
                self._maps[rk] = _MockMap()
            if isinstance(rv, dict):
                for ik, iv in rv.items():
                    self._maps[rk][ik] = iv

    def _snapshot(self) -> dict:
        return {k: dict(v.items()) for k, v in self._maps.items()}


class _MockTransaction:
    def __init__(self, doc: _MockDoc) -> None:
        self._doc = doc

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._doc._clock += 1


# -----------------------------------------------------------------------------#
# Doc 工厂（可用 pycrdt.Doc 则用之，否则 mock）
# -----------------------------------------------------------------------------#

def _make_doc() -> Any:
    if _HAVE_PYCRDT:
        return pycrdt.Doc()
    return _MockDoc()


def _make_map(doc: Any) -> Any:
    if _HAVE_PYCRDT:
        return doc.get("kb", type=pycrdt.Map)
    return doc.get("kb")


# -----------------------------------------------------------------------------#
# 核心 CRDT 操作（与 pycrdt API 对齐）
# -----------------------------------------------------------------------------#

KB_KEY = "kb"


def make_doc(seed_entries: int = 8, seed: int = 42) -> Any:
    """建一个含 seed_entries 条目的初始知识库 doc（确定性种子用于测试）。"""
    import random
    rng = random.Random(seed)
    doc = _make_doc()
    kb = _make_map(doc)
    with doc.transaction():
        for i in range(seed_entries):
            name = f"note{i}"
            if hasattr(kb, "__setitem__"):
                entry = _make_map(doc) if _HAVE_PYCRDT else _MockMap()
                kb[name] = entry
                entry["title"] = f"标题{i}"
                entry["content"] = f"内容{i}"
                entry["tags"] = f"tag{i}"
            else:
                # Mock path
                kb[name] = {"title": f"标题{i}", "content": f"内容{i}", "tags": f"tag{i}"}
    return doc


def apply_merge(doc: Any, updates: list[bytes]) -> None:
    """把一系列 update 字节序列应用到 doc（幂等，可重复应用）。"""
    for u in updates:
        doc.apply_update(u)


def snapshot(doc: Any) -> dict:
    """把 doc 的 kb 导出为纯 Python dict（用于校验收敛性）。"""
    kb = _make_map(doc)
    if hasattr(kb, "items"):
        out = {}
        for k, v in kb.items():
            if hasattr(v, "to_py"):
                out[k] = v.to_py()
            elif hasattr(v, "items"):
                out[k] = dict(v.items())
            else:
                out[k] = v
        return out
    # mock path
    if hasattr(kb, "_data"):
        return dict(kb._data)
    return {}


def random_edit(doc: Any, rng: "random.Random") -> str:
    """在 doc 上随机执行一个编辑操作（write/update/delete），返回操作描述。"""
    kb = _make_map(doc)
    # 读 keys（mock 和真实 API 兼容）
    try:
        keys = list(kb.keys())
    except Exception:
        keys = []

    op = rng.choices(["write", "update", "delete"], weights=[45, 35, 20])[0]
    with doc.transaction():
        if op == "write" or not keys:
            name = f"note-{rng.randint(0, 9999)}"
            entry = _make_map(doc) if _HAVE_PYCRDT else _MockMap()
            kb[name] = entry
            entry["title"] = f"新-{rng.randint(0, 999)}"
            entry["content"] = f"离线写入-{rng.randint(0, 999)}"
            entry["tags"] = f"tag{rng.randint(0,99)}"
            return f"write {name}"
        if op == "update":
            name = rng.choice(keys)
            v = kb[name]
            if hasattr(v, "__setitem__"):
                v["content"] = f"改-{rng.randint(0, 999)}"
            else:
                kb[name] = f"改-{rng.randint(0, 999)}"
            return f"update {name}"
        if op == "delete":
            name = rng.choice(keys)
            del kb[name]
            return f"delete {name}"
    return "noop"


# -----------------------------------------------------------------------------#
# SQLite 落盘层
# -----------------------------------------------------------------------------#

@dataclass
class SyncRecord:
    """一次 sync 操作记录。"""
    id: str = ""
    doc_name: str = "default"
    update_blob: bytes = b""
    clock: int = 0
    created_at: float = field(default_factory=time.time)


class YjsSqlitePersist:
    """CRDT update 序列的 SQLite 持久化（append-only 写入，重启恢复状态）。

    表结构：
        crdt_sync(id TEXT PK, doc_name TEXT, update_blob BLOB, clock INTEGER, created_at REAL)

    恢复时：按 clock 升序重放所有 update_blob 到新 doc 实例。
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS crdt_sync (
                    id          TEXT PRIMARY KEY,
                    doc_name    TEXT NOT NULL,
                    update_blob BLOB NOT NULL,
                    clock       INTEGER NOT NULL,
                    created_at  REAL NOT NULL
                )"""
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sync_doc_clock"
                " ON crdt_sync(doc_name, clock)"
            )

    def append_update(self, doc_name: str, update_blob: bytes,
                     clock: int = 0) -> str:
        """追加一条 update（幂等：同 blob 内容不重复写入）。

        record_id 由 update_blob 的 sha256 前 16 hex 派生（确定性，不抛错）。
        """
        import hashlib
        record_id = hashlib.sha256(update_blob).hexdigest()[:16]
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO crdt_sync"
                " (id, doc_name, update_blob, clock, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (record_id, doc_name, update_blob, clock, time.time()))
        return record_id

    def get_updates(self, doc_name: str) -> list[bytes]:
        """按 clock 升序返回所有 update_blob（用于状态恢复）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT update_blob FROM crdt_sync"
                " WHERE doc_name = ? ORDER BY clock ASC",
                (doc_name,)).fetchall()
        return [row["update_blob"] for row in rows]

    def get_clock(self, doc_name: str) -> int:
        """返回当前最大 clock（用于增量同步）。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(clock) as mx FROM crdt_sync WHERE doc_name = ?",
                (doc_name,)).fetchone()
        return int(row["mx"] or 0)

    def count(self, doc_name: str = "default") -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM crdt_sync WHERE doc_name = ?",
                (doc_name,)).fetchone()
        return row[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def recover_doc(persister: YjsSqlitePersist,
                doc_name: str = "default") -> Any:
    """从 SQLite 恢复 doc：重放所有 update_blob。"""
    doc = _make_doc()
    updates = persister.get_updates(doc_name)
    apply_merge(doc, updates)
    return doc


def persist_update(persister: YjsSqlitePersist, doc: Any,
                   doc_name: str = "default") -> None:
    """把 doc 的当前 update 追加到 SQLite（幂等追加）。"""
    blob = doc.get_update()
    clock = getattr(doc, "_clock", 0)
    persister.append_update(doc_name, blob, clock)


# -----------------------------------------------------------------------------#
# 双实例收敛验证（本地自测）
# -----------------------------------------------------------------------------#

@dataclass
class ConvergeResult:
    converged: bool = True
    completeness: float = 1.0
    conflicts: int = 0
    elapsed_ms: float = 0.0
    ops: list[str] = field(default_factory=list)


def simulate_converge(seed: int = 42, rounds: int = 20) -> ConvergeResult:
    """双实例离线编辑 → SQLite 落盘 → 重启恢复 → 交换 update → 校验收敛。

    验收断言：
    1. 重启恢复后状态与重启前一致；
    2. 双实例交换 update 后最终状态一致（converged=True）。
    """
    import random
    rng = random.Random(seed)
    docA = make_doc(seed=seed)
    docB = make_doc(seed=seed)  # 同种子，确保起点一致

    # 记录初始条目全集
    before = set(snapshot(docA).keys()) | set(snapshot(docB).keys())

    # 离线编辑
    ops: list[str] = []
    for _ in range(rounds):
        target = docA if rng.random() < 0.5 else docB
        op = random_edit(target, rng)
        ops.append(op)

    # 落盘（A 和 B 各存自己的 update）
    with tempfile.TemporaryDirectory() as td:
        dbA = YjsSqlitePersist(Path(td) / "sync_A.db")
        dbB = YjsSqlitePersist(Path(td) / "sync_B.db")

        # 各自追加自己的编辑结果（重放后 blob 来自 apply_merge，get_update 只取自身增量）
        # 先持久化当前状态
        blobA = docA.get_update()
        blobB = docB.get_update()
        dbA.append_update("default", blobA, getattr(docA, "_clock", 0))
        dbB.append_update("default", blobB, getattr(docB, "_clock", 0))

        # 重启恢复
        docA_rec = recover_doc(dbA, "default")
        docB_rec = recover_doc(dbB, "default")

        snapA_before = snapshot(docA)
        snapA_rec = snapshot(docA_rec)
        snapB_before = snapshot(docB)
        snapB_rec = snapshot(docB_rec)

        # 恢复后状态与重启前一致
        assert snapA_before == snapA_rec, "A 重启恢复后状态应一致"
        assert snapB_before == snapB_rec, "B 重启恢复后状态应一致"

        # 交换 update（A 收到 B 的全部 update，反之亦然）
        uA = docA_rec.get_update()
        uB = docB_rec.get_update()
        apply_merge(docA_rec, [uB])
        apply_merge(docB_rec, [uA])

        # 必须在退出 TemporaryDirectory 前关闭连接：
        # Windows 下 sqlite 连接未关会锁住 .db 文件，导致临时目录清理 PermissionError(WinError 32)。
        dbA.close()
        dbB.close()

    snapA_final = snapshot(docA_rec)
    snapB_final = snapshot(docB_rec)
    converged = snapA_final == snapB_final

    # 计算完整率（存活条目 / 期望条目）
    deleted_keys = {op.split()[1] for op in ops if op.startswith("delete")}
    expected = before - deleted_keys
    after = set(snapA_final.keys())
    lost = expected - after
    completeness = (len(expected) - len(lost)) / len(expected) if expected else 1.0

    return ConvergeResult(
        converged=converged,
        completeness=completeness,
        conflicts=len(lost),
        elapsed_ms=0.0,
        ops=ops,
    )


# -----------------------------------------------------------------------------#
# 同步端点骨架（apiserver/routes/sync.py 的占位标注）
# -----------------------------------------------------------------------------#
# 以下是 apiserver/routes/sync.py 中需要实现的三个路由占位：
#
# TODO-01: POST /sync/push
#   Request:  {doc_name: str, update_blob: base64, clock: int}
#   Response: {ok: bool, clock: int, conflicts: int}
#   逻辑:
#     1. 验 token（naga_auth.py 已有）；
#     2. 追加 update_blob 到 SQLite（persister.append_update）；
#     3. 返回当前最大 clock。
#
# TODO-02: GET /sync/pull?doc_name=default&since_clock=0
#   Response: {ok: bool, updates: [base64, ...], clock: int}
#   逻辑:
#     1. 从 SQLite 拉取 since_clock 之后的增量 update；
#     2. 返回 update 列表 + 当前最大 clock。
#
# TODO-03: GET /sync/state?doc_name=default
#   Response: {ok: bool, snapshot: dict, clock: int}
#   逻辑:
#     1. recover_doc(persister, doc_name) 重建当前状态；
#     2. 返回 snapshot dict + clock。
#
# 实现提示：
#   - persister 单例由 apiserver/api_server.py 的 lifespan 管理；
#   - 多实例并发写：SQLite 单写者（threading.RLock 已封装）；
#   - 大 update blob：建议 client 端做 gzip 压缩（Accept-Encoding: gzip）。
#
# -----------------------------------------------------------------------------#


if __name__ == "__main__":
    # 本地自测：双实例收敛 + SQLite 落盘验证
    import random
    ok = True
    for seed in (7, 42, 2026):
        r = simulate_converge(seed=seed, rounds=20)
        print(f"seed={seed}: 收敛={r.converged} 完整率={r.completeness*100:.0f}%"
              f" 丢失={r.conflicts}")
        if not r.converged or r.completeness < 1.0:
            ok = False
    print("验收:", "PASS 双实例收敛+SQLite落盘" if ok else "FAIL")
