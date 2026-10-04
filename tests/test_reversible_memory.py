"""ReversibleMemory 可逆记忆写入的单元测试。

覆盖 SPEC 验收：
- 写入 3 条 → undo_last 剩 2 → rollback(2) 剩 0
- 逆操作幂等（重复撤销返回 False）
- forget_entity 定向遗忘
- undo 栈上限丢最旧
- 后端缺删除接口时降级 tombstone，不抛异常
- issue #24：tombstone 降级后查询路径过滤已删除记录
"""

from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from summer_memory.reversible import ReversibleMemory  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class FakeBackend:
    """带完整写入/删除接口的假后端，验证 wrapper 记账与逆操作。"""

    def __init__(self):
        self.entries = []

    async def add_conversation_memory(self, user_input, ai_response):
        self.entries.append({"user_input": user_input, "ai_response": ai_response})
        return True

    async def add_memory(self, user_input="", ai_response="", quintuples=None, **kw):
        self.entries.append({"user_input": user_input, "ai_response": ai_response,
                             "quintuples": list(quintuples or [])})
        return True

    async def add_quintuples(self, quintuples):
        self.entries.append({"quintuples": list(quintuples)})
        return True

    async def delete_conversation_memory(self, snapshot):
        return True

    async def delete_memory(self, snapshot):
        return True

    async def delete_quintuples(self, snapshot):
        return True


def test_undo_last_and_rollback():
    rm = ReversibleMemory(FakeBackend())

    async def body():
        assert await rm.add_conversation_memory("u1", "a1") is True
        assert await rm.add_conversation_memory("u2", "a2") is True
        assert await rm.add_conversation_memory("u3", "a3") is True
        assert len(rm) == 3

        assert await rm.undo_last() is True
        assert len(rm) == 2

        assert await rm.rollback(2) == 2
        assert len(rm) == 0

    run(body())


def test_undo_idempotent_returns_false():
    rm = ReversibleMemory(FakeBackend())

    async def body():
        await rm.add_conversation_memory("u", "a")
        assert await rm.undo_last() is True
        # 已无可撤销条目 → 幂等返回 False，不抛异常
        assert await rm.undo_last() is False
        assert await rm.undo_last() is False

    run(body())


def test_forget_entity():
    rm = ReversibleMemory(FakeBackend())

    async def body():
        await rm.add_conversation_memory("关于 X 的记忆内容", "回复 Y")
        await rm.add_memory("另一条无关记忆", "回复 Z")
        assert rm.has_entity("X") is True

        n = await rm.forget_entity("X")
        assert n == 1
        assert rm.has_entity("X") is False
        assert rm.active_count == 1  # 无关记忆仍在

    run(body())


def test_add_memory_and_quintuples_recorded():
    rm = ReversibleMemory(FakeBackend())

    async def body():
        assert await rm.add_memory("q", "s") is True
        assert await rm.add_quintuples([("s", "p", "o", "ctx", "t")]) is True
        assert len(rm) == 2
        assert await rm.rollback(2) == 2
        assert len(rm) == 0

    run(body())


def test_undo_limit_drops_oldest():
    rm = ReversibleMemory(FakeBackend(), undo_limit=3)

    async def body():
        for i in range(5):
            await rm.add_conversation_memory(f"u{i}", f"a{i}")
        assert len(rm) == 3  # 丢最旧两条

    run(body())


def test_missing_delete_degrades_to_tombstone():
    class NoDeleteBackend:
        async def add_conversation_memory(self, user_input, ai_response):
            return True

    rm = ReversibleMemory(NoDeleteBackend())

    async def body():
        await rm.add_conversation_memory("u", "a")
        # 后端无删除接口 → 不抛异常，降级 tombstone
        assert await rm.undo_last() is True
        assert rm.active_count == 0
        assert len(rm.tombstones) == 1

    run(body())


def test_backend_write_false_not_recorded():
    class FailingBackend:
        async def add_conversation_memory(self, user_input, ai_response):
            return False

    rm = ReversibleMemory(FailingBackend())

    async def body():
        assert await rm.add_conversation_memory("u", "a") is False
        assert len(rm) == 0  # 写入失败不 push 逆操作

    run(body())


# ---- issue #24：tombstone 降级后的查询过滤 ----

_Q1 = ("陆墨", "喜欢", "通联", "ctx", "t1")
_Q2 = ("陆墨", "住在", "天选7", "ctx", "t2")


class QueryableNoDeleteBackend:
    """无删除接口但有查询接口的后端：记录永久残留，靠 wrapper 过滤。"""

    def __init__(self, records):
        self.records = list(records)

    async def add_quintuples(self, quintuples):
        return True

    async def add_conversation_memory(self, user_input, ai_response):
        return True

    async def get_relevant_memories(self, query, limit=3):
        return self.records[:limit]

    async def query_memory(self, question):
        return "；".join(" ".join(r[:3]) for r in self.records)


def test_query_filters_tombstoned_quintuples():
    backend = QueryableNoDeleteBackend([_Q1, _Q2])
    rm = ReversibleMemory(backend)

    async def body():
        await rm.add_quintuples([_Q1])
        # 后端无删除接口 → undo 降级 tombstone，记录仍残留在后端
        assert await rm.undo_last() is True
        assert len(rm.tombstones) == 1
        assert backend.records == [_Q1, _Q2]  # 后端确实没删掉

        # 验收：查询结果不包含已 undo 的记录
        result = await rm.get_relevant_memories("陆墨", limit=5)
        assert _Q1 not in result
        assert _Q2 in result

    run(body())


def test_filter_records_supports_tuple_and_dict_shapes():
    backend = QueryableNoDeleteBackend([_Q1])
    rm = ReversibleMemory(backend)

    async def body():
        await rm.add_quintuples([_Q1])
        await rm.undo_last()

        tuple_rows = [_Q1, _Q2]
        dict_rows = [
            {"subject": "陆墨", "predicate": "喜欢", "object": "通联"},
            {"subject": "陆墨", "predicate": "住在", "object": "天选7"},
        ]
        assert rm.filter_records(tuple_rows) == [_Q2]
        kept = rm.filter_records(dict_rows)
        assert len(kept) == 1 and kept[0]["object"] == "天选7"
        assert rm.is_record_tombstoned(_Q1) is True
        assert rm.is_record_tombstoned(_Q2) is False

    run(body())


def test_query_memory_text_polluted_returns_none():
    class TextBackend:
        def __init__(self, text):
            self.text = text

        async def add_conversation_memory(self, user_input, ai_response):
            return True

        async def query_memory(self, question):
            return self.text

    async def body():
        # 后端聚合文本里含被 tombstone 的原文 → 判为污染，保守返回 None
        rm = ReversibleMemory(TextBackend("之前提到：陆墨喜欢通联。"))
        await rm.add_conversation_memory("陆墨喜欢通联", "好的，已记住")
        assert await rm.undo_last() is True
        assert await rm.query_memory("陆墨喜欢什么") is None

        # 干净文本不受影响（无 tombstone 时原样透传）
        rm_clean = ReversibleMemory(TextBackend("陆墨住在天选7。"))
        assert await rm_clean.query_memory("住哪") == "陆墨住在天选7。"

    run(body())


def test_forget_entity_also_filtered_in_query():
    backend = QueryableNoDeleteBackend([_Q1, _Q2])
    rm = ReversibleMemory(backend)

    async def body():
        await rm.add_quintuples([_Q1])
        assert await rm.forget_entity("通联") == 1

        result = await rm.get_relevant_memories("陆墨", limit=5)
        assert _Q1 not in result  # 定向遗忘后查询不返回

    run(body())


def test_successful_backend_delete_leaves_no_filter():
    """后端真删除成功时不登记 tombstone，不误伤后续查询。"""
    rm = ReversibleMemory(FakeBackend())

    async def body():
        await rm.add_quintuples([_Q1])
        assert await rm.undo_last() is True
        assert len(rm.tombstones) == 0
        assert rm.is_record_tombstoned(_Q1) is False

    run(body())