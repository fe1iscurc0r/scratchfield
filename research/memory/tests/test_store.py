"""授粉-C2 验收：SQLite 四表建齐 + synchronize_messages 前缀增量幂等。"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), *([os.pardir] * 3)))
sys.path.insert(0, REPO_ROOT)

from research.memory import MemoryStore, SessionMessage


def _msg(mid: str, role: str = "human", content: str = "hi") -> SessionMessage:
    return SessionMessage(role=role, content=content, message_id=mid)


class TestC2MemoryStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test_memory.db")
        self.store = MemoryStore(db_path=self.db_path)
        self.store.create_session("s1", model_name="test-model", workflow_type="single")

    def tearDown(self):
        # WAL 模式会留下 -wal/-shm 文件，Windows 上直接 rmtree 会被文件锁拦住：
        # 先 checkpoint 并切回 DELETE 日志模式，确保无残留句柄再清理
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("PRAGMA journal_mode=DELETE")
        self._tmp.cleanup()

    def test_four_tables_created(self):
        """验收：四表建齐（sessions/messages/tasks/events）。"""
        with closing(sqlite3.connect(self.db_path)) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        for required in ("sessions", "messages", "tasks", "events"):
            self.assertIn(required, tables)

    def test_sync_same_message_idempotent(self):
        """验收核心：同一条消息重复同步不产生重复行。"""
        msgs = [_msg("m1")]
        self.store.synchronize_messages("s1", msgs)
        self.store.synchronize_messages("s1", msgs)
        self.store.synchronize_messages("s1", msgs)
        stored = self.store.get_messages("s1")
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].message_id, "m1")

    def test_sync_prefix_appends_suffix_only(self):
        """前缀成立时只补尾部，不重写已有行。"""
        self.store.synchronize_messages("s1", [_msg("m1"), _msg("m2")])
        added = self.store.synchronize_messages(
            "s1", [_msg("m1"), _msg("m2"), _msg("m3"), _msg("m4")]
        )
        self.assertEqual(added, 2)
        ids = [m.message_id for m in self.store.get_messages("s1")]
        self.assertEqual(ids, ["m1", "m2", "m3", "m4"])

    def test_sync_divergent_history_rebuilds(self):
        """历史分叉（非前缀）时删除重建，以权威转录为准。"""
        self.store.synchronize_messages("s1", [_msg("m1"), _msg("m2")])
        self.store.synchronize_messages("s1", [_msg("m1"), _msg("m2-rewrite")])
        ids = [m.message_id for m in self.store.get_messages("s1")]
        self.assertEqual(ids, ["m1", "m2-rewrite"])

    def test_sync_updates_query_count(self):
        msgs = [_msg("m1"), _msg("m2", role="ai"), _msg("m3")]
        self.store.synchronize_messages("s1", msgs)
        with closing(sqlite3.connect(self.db_path)) as conn:
            count = conn.execute(
                "SELECT query_count FROM sessions WHERE session_id='s1'"
            ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_tasks_lifecycle(self):
        """tasks 表：登记 TaskSpec → 更新状态 → 可查询。"""
        from research.execution import TaskSpec

        spec = TaskSpec(task_id="t1", task_type="shell", command="echo ok")
        self.store.add_task("t1", "s1", task_type="shell", spec=spec)
        task = self.store.get_task("t1")
        self.assertEqual(task["status"], "pending")
        self.assertIn("echo ok", task["spec_json"])
        self.assertNotIn("callable", task["spec_json"])  # callable 不可序列化，需剔除

        self.store.update_task_status("t1", "completed", result="ok")
        task = self.store.get_task("t1")
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"], "ok")

    def test_add_task_duplicate_idempotent(self):
        self.store.add_task("t1", "s1")
        self.store.add_task("t1", "s1")  # 重复登记不报 UNIQUE 冲突
        with closing(sqlite3.connect(self.db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        self.assertEqual(count, 1)

    def test_events_roundtrip(self):
        self.store.add_event("s1", "task_started", {"task_id": "t1"})
        self.store.add_event("s1", "task_finished", None)
        events = self.store.get_events("s1")
        self.assertEqual([e["event_type"] for e in events], ["task_started", "task_finished"])
        self.assertIn("t1", events[0]["payload"])

    def test_cascade_delete(self):
        """删会话级联清空子表（FK ON DELETE CASCADE 生效）。"""
        self.store.save_messages("s1", [_msg("m1")])
        self.store.add_task("t1", "s1")
        self.store.add_event("s1", "ping")
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("DELETE FROM sessions WHERE session_id='s1'")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
