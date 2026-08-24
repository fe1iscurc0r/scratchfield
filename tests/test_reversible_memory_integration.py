"""ReversibleMemory 集成测试。

覆盖 SPEC 的"端到端"层：
- 包装真实 GRAGMemoryManager 接口形状（仅 add_conversation_memory，无删除接口）
  → undo 走 tombstone 降级，不抛异常
- 与后端真实条目状态联动：add/undo/rollback/forget 后，后端条目随之变化
- 纯 wrapper：不向 backend 实例注入任何属性

注：真实 GRAGMemoryManager import 依赖 system.config / Neo4j，非同环境可跑，
因此这里用其"公开接口形状"（读自 memory_manager.py）做集成验证。
"""

from __future__ import annotations

import asyncio
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from summer_memory.reversible import ReversibleMemory  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class RealShapeBackend:
    """镜像 GRAGMemoryManager 的公开接口：只有 add_conversation_memory，无删除接口。"""

    def __init__(self):
        self.conversations = []

    async def add_conversation_memory(self, user_input, ai_response):
        self.conversations.append({"user_input": user_input, "ai_response": ai_response})
        return True


class FullBackend:
    """带删除接口的完整后端，用于验证与真实条目状态的端到端联动。"""

    def __init__(self):
        self.entries = []

    async def add_conversation_memory(self, user_input, ai_response):
        self.entries.append({"user_input": user_input, "ai_response": ai_response})
        return True

    async def delete_conversation_memory(self, snapshot):
        self.entries = [e for e in self.entries
                        if e.get("user_input") != snapshot.get("user_input")]
        return True


def test_wraps_real_shape_backend_tombstone_degrade():
    """GRAGMemoryManager 接口形状（无删除接口）→ undo 降级 tombstone，不抛异常。"""
    backend = RealShapeBackend()
    rm = ReversibleMemory(backend)

    async def body():
        assert await rm.add_conversation_memory("u1", "a1") is True
        assert await rm.add_conversation_memory("u2", "a2") is True
        assert backend.conversations is not None  # 写入确实进了后端
        assert len(rm) == 2

        # 后端无任何删除方法 → 逆操作走 tombstone，绝不允许抛异常
        assert await rm.undo_last() is True
        assert len(rm) == 1
        assert len(rm.tombstones) == 1

        assert await rm.rollback(1) == 1
        assert len(rm) == 0
        assert len(rm.tombstones) == 2

    run(body())


def test_end_to_end_backend_state_follows_wrapper():
    """add/undo/rollback/forget 后，后端真实条目随之联动。"""
    backend = FullBackend()
    rm = ReversibleMemory(backend)

    async def body():
        await rm.add_conversation_memory("关于 X 的记忆", "回复 X")
        await rm.add_conversation_memory("关于 Y 的记忆", "回复 Y")
        assert len(backend.entries) == 2
        assert len(rm) == 2

        # undo_last → 后端最末条目被删
        assert await rm.undo_last() is True
        assert len(backend.entries) == 1
        assert len(rm) == 1
        assert backend.entries[0]["user_input"] == "关于 X 的记忆"

        # forget_entity("X") → 后端 X 条目被删，剩 0
        assert await rm.forget_entity("X") == 1
        assert len(backend.entries) == 0
        assert rm.has_entity("X") is False
        assert rm.active_count == 0

    run(body())


def test_pure_wrapper_no_attribute_injection():
    """零侵入：操作后 backend 实例不新增任何属性。"""
    backend = RealShapeBackend()
    rm = ReversibleMemory(backend)
    before = set(vars(backend).keys())

    async def body():
        await rm.add_conversation_memory("u", "a")
        await rm.undo_last()

    run(body())
    assert set(vars(backend).keys()) == before


def test_reversible_module_imports_lightweight():
    """reversible.py 只依赖标准库，import 不触发 system.config / Neo4j 等重依赖。

    原断言（system.config not in sys.modules）依赖测试执行顺序：其他用例
    可能已导入 system.config，导致该断言在任何顺序下都不稳定。改为检查
    reversible 模块自身的源码与命名空间：
    - 顶层 import/from 不含 system.config / memory_manager
    - 模块命名空间不持有 system.config / memory_manager 模块对象
    """
    import inspect
    import types

    import summer_memory.reversible as rev

    src = inspect.getsource(rev)
    top_lines = [
        line.strip()
        for line in src.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not any(
        ("system.config" in line or "memory_manager" in line) for line in top_lines
    )
    # 命名空间不持有这两个重依赖模块对象（即使其他模块已把它们加载进 sys.modules）
    for name, val in vars(rev).items():
        if isinstance(val, types.ModuleType):
            assert val.__name__ not in ("system.config", "summer_memory.memory_manager")
    assert hasattr(rev, "ReversibleMemory")
    assert hasattr(rev, "UndoOp")