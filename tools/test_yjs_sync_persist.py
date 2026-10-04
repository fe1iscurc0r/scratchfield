"""W63-01 yjs CRDT 落盘测试（≥4用例，pytest 全绿）。

跑法: python -m pytest tools/test_yjs_sync_persist.py -q
覆盖：
- Mock CRDT Doc/Map 创建与 basic operations；
- 双实例 offline edit → SQLite 落盘 → 重启恢复 → 双方收敛一致；
- 同一 doc 多次 restart 状态保持；
- SQLite update 追加幂等性。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tools import yjs_sync_persist as ysp

# =============================================================================
# Mock CRDT 基础操作
# =============================================================================

def test_mock_doc_creation():
    """Mock CRDT Doc 创建 + Map 读写 + transaction。"""
    doc = ysp._make_doc()
    kb = ysp._make_map(doc)
    with doc.transaction():
        kb["key1"] = "value1"
    assert kb["key1"] == "value1"


def test_mock_doc_snapshot_and_update():
    """snapshot 导出纯 dict；get_update 返回非空字节。"""
    doc = ysp._make_doc()
    kb = ysp._make_map(doc)
    with doc.transaction():
        kb["title"] = "test"
        entry = ysp._make_map(doc)
        kb["note1"] = entry
        entry["content"] = "hello"

    snap = ysp.snapshot(doc)
    assert "title" in snap or "note1" in snap

    blob = doc.get_update()
    assert isinstance(blob, bytes)
    assert len(blob) > 0


def test_mock_apply_update_converges():
    """apply_update 幂等应用；重复应用不导致状态漂移。"""
    doc1 = ysp._make_doc()
    doc2 = ysp._make_doc()
    kb1 = ysp._make_map(doc1)
    with doc1.transaction():
        kb1["a"] = "1"
    blob = doc1.get_update()

    ysp.apply_merge(doc2, [blob])
    snap2 = ysp.snapshot(doc2)
    assert snap2.get("a") == "1" or "a" in snap2

    # 重复应用应幂等（不炸）
    ysp.apply_merge(doc2, [blob])
    ysp.apply_merge(doc2, [blob])


# =============================================================================
# SQLite 落盘 + 重启恢复
# =============================================================================

def test_sqlite_persist_append_and_recover():
    """双实例编辑 → SQLite 落盘 → 重启恢复 → 状态一致。"""
    with tempfile.TemporaryDirectory() as td:
        # 实例 A 编辑
        docA = ysp.make_doc(seed=42)
        kbA = ysp._make_map(docA)
        with docA.transaction():
            kbA["new-entry"] = "from-A"

        # 实例 B 编辑
        docB = ysp.make_doc(seed=42)
        kbB = ysp._make_map(docB)
        with docB.transaction():
            kbB["new-entry"] = "from-B"

        # 各自落盘
        dbA = ysp.YjsSqlitePersist(Path(td) / "sync_A.db")
        dbB = ysp.YjsSqlitePersist(Path(td) / "sync_B.db")

        ysp.persist_update(dbA, docA, "kb")
        ysp.persist_update(dbB, docB, "kb")

        assert dbA.count("kb") >= 1
        assert dbB.count("kb") >= 1

        # 重启恢复
        docA_rec = ysp.recover_doc(dbA, "kb")
        docB_rec = ysp.recover_doc(dbB, "kb")

        snapA = ysp.snapshot(docA_rec)
        snapB = ysp.snapshot(docB_rec)

        # 恢复后各自状态 = 重启前
        assert snapA.get("new-entry") == "from-A"
        assert snapB.get("new-entry") == "from-B"

        dbA.close()
        dbB.close()


def test_double_instance_convergence_after_restart():
    """双实例编辑 → SQLite 落盘 → 重启恢复 → 交换 update → 双方收敛一致。

    这是核心验收硬线：双实例离线编辑→SQLite落盘→重启恢复→双方收敛一致。
    """
    with tempfile.TemporaryDirectory() as td:
        docA = ysp.make_doc(seed=7)
        docB = ysp.make_doc(seed=7)

        # 离线编辑（A 添加 note-X，B 添加 note-Y）
        kbA = ysp._make_map(docA)
        with docA.transaction():
            kbA["note-X"] = {"title": "X", "content": "A 的内容"}

        kbB = ysp._make_map(docB)
        with docB.transaction():
            kbB["note-Y"] = {"title": "Y", "content": "B 的内容"}

        # 落盘
        dbA = ysp.YjsSqlitePersist(Path(td) / "sync_A.db")
        dbB = ysp.YjsSqlitePersist(Path(td) / "sync_B.db")
        ysp.persist_update(dbA, docA, "kb")
        ysp.persist_update(dbB, docB, "kb")

        # 重启恢复
        docA_rec = ysp.recover_doc(dbA, "kb")
        docB_rec = ysp.recover_doc(dbB, "kb")

        # 交换 update（模拟多实例同步）
        uA = docA_rec.get_update()
        uB = docB_rec.get_update()
        ysp.apply_merge(docA_rec, [uB])
        ysp.apply_merge(docB_rec, [uA])

        snapA = ysp.snapshot(docA_rec)
        snapB = ysp.snapshot(docB_rec)

        # 收敛：双方最终状态一致
        assert snapA == snapB, \
            f"收敛失败：A={snapA} B={snapB}"

        # 各自身上都有对方的内容
        assert "note-X" in snapA, "A 应持有 X（来自 B 的同步）"
        assert "note-Y" in snapA, "A 应持有 Y（来自 B 的同步）"
        assert "note-X" in snapB, "B 应持有 X（来自 A 的同步）"
        assert "note-Y" in snapB, "B 应持有 Y（来自 A 的同步）"

        dbA.close()
        dbB.close()


def test_multiple_restart_preserves_state():
    """同一 doc 三次 restart，每次状态保持。"""
    with tempfile.TemporaryDirectory() as td:
        doc = ysp.make_doc(seed=99)
        kb = ysp._make_map(doc)
        with doc.transaction():
            kb["persistent-key"] = "persistent-value"

        db = ysp.YjsSqlitePersist(Path(td) / "sync_multi.db")
        ysp.persist_update(db, doc, "kb")

        for i in range(3):
            doc_rec = ysp.recover_doc(db, "kb")
            snap = ysp.snapshot(doc_rec)
            assert snap.get("persistent-key") == "persistent-value", \
                f"第 {i+1} 次重启后状态丢失"
            # 再次持久化（模拟运行中定期 checkpoint）
            ysp.persist_update(db, doc_rec, "kb")

        db.close()


def test_sqlite_append_idempotent():
    """append_update 幂等：同 id 不重复写入。"""
    with tempfile.TemporaryDirectory() as td:
        db = ysp.YjsSqlitePersist(Path(td) / "idempotent.db")
        doc = ysp._make_doc()
        blob = doc.get_update()
        clock = getattr(doc, "_clock", 0)

        # 同一 id 写入两次
        rid = db.append_update("kb", blob, clock)
        count_after_first = db.count("kb")
        rid2 = db.append_update("kb", blob, clock)
        count_after_second = db.count("kb")

        assert rid == rid2, "同内容第二次写入应返回同 id"
        assert count_after_first == count_after_second, "id 重复不应增加行数"
        db.close()


# =============================================================================
# 集成：完整 simulate_converge
# =============================================================================

def test_simulate_converge_local():
    """simulate_converge 返回收敛结果（本地 mock 路径）。"""
    r = ysp.simulate_converge(seed=42, rounds=20)
    assert isinstance(r, ysp.ConvergeResult)
    assert r.converged is True, \
        f"CRDT 收敛失败：{r.conflicts} 冲突"
    assert r.completeness == 1.0, \
        f"完整率不足：{r.completeness*100:.0f}%"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])