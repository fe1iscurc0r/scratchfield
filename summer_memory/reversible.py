"""可逆记忆写入（ReversibleMemory）。

非侵入 wrapper：包装 ``GRAGMemoryManager`` / ``RemoteMemoryClient``，
每次写入成功后在 undo 栈 push 一条逆操作（记录"写了什么"的快照），
支持撤销最近一条、批量回滚、定向遗忘某实体关联的全部记忆。

原则（对应论文"可逆效应"）：
- 零侵入：不改动 ``GRAGMemoryManager`` / ``memory_client.py`` 本体。
- undo 栈上限默认 50 步，超出丢最旧（"遗忘是适应性"）。
- 逆操作幂等：无可撤销条目时返回 False，不抛异常。
- 降级路径：后端缺"单条删除"接口时走 tombstone 标记删除，查询时过滤。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 逆操作按写入类型映射到后端删除方法名
_DELETE_METHOD = {
    "conversation": "delete_conversation_memory",
    "memory": "delete_memory",
    "quintuples": "delete_quintuples",
}


@dataclass
class UndoOp:
    """一次写入的逆操作记录（逆累加器 φ）。

    ``snapshot`` 记录写入时"写了什么"；``active`` 表示该条目当前是否仍生效；
    被撤销/遗忘后置 False，并写入 tombstone 指纹供查询过滤。
    """

    kind: str  # 'conversation' | 'memory' | 'quintuples'
    snapshot: Dict[str, Any]
    active: bool = True
    tombstones: List[str] = field(default_factory=list)

    def entities(self) -> Tuple[str, ...]:
        """从快照中提取用于定向遗忘匹配的关键词/实体。"""
        out: List[str] = []
        for key in ("user_input", "ai_response"):
            v = self.snapshot.get(key)
            if isinstance(v, str) and v:
                out.append(v)
        for q in self.snapshot.get("quintuples", []) or []:
            if isinstance(q, (tuple, list)) and len(q) >= 4:
                # 五元组 (subject, predicate, object, context, time)
                out.append(str(q[0]))
                out.append(str(q[2]))
        return tuple(dict.fromkeys(out))

    def fingerprint(self) -> str:
        return f"{self.kind}:{self.snapshot!r}"


class ReversibleMemory:
    """可逆记忆写入包装器。

    参数:
        backend: 底层记忆后端（通常为 ``GRAGMemoryManager``）。
        remote: 可选，``RemoteMemoryClient``；当 backend 缺少 ``add_memory`` /
            ``add_quintuples`` 时回退到 remote。
        undo_limit: undo 栈上限（默认 50），超出丢最旧。
    """

    def __init__(self, backend: Any, remote: Any = None, undo_limit: int = 50):
        self._backend = backend
        self._remote = remote
        self._undo_limit = max(1, int(undo_limit))
        self._stack: List[UndoOp] = []
        self._tombstones: set = set()  # 降级删除的指纹集合
        # 降级删除（后端无删除接口/删除失败）后记录仍残留在后端，
        # 这里登记被 tombstone 的内容特征，查询路径据此过滤（issue #24）
        self._tombstoned_quintuples: set = set()  # (subject, predicate, object) 归一化键
        self._tombstoned_texts: set = set()  # 被删对话文本（user_input/ai_response）

    # ------------------------------------------------------------------ 写入

    async def add_conversation_memory(self, user_input: str, ai_response: str) -> bool:
        fn = getattr(self._backend, "add_conversation_memory", None)
        if fn is None:
            return False
        ok = self._ok(await fn(user_input, ai_response))
        if ok:
            self._push(UndoOp("conversation", {
                "user_input": user_input, "ai_response": ai_response}))
        return ok

    async def add_memory(self, user_input: str = "", ai_response: str = "",
                         quintuples: Optional[List] = None, **kw) -> bool:
        fn = getattr(self._backend, "add_memory", None)
        if fn is None:
            fn = getattr(self._remote, "add_memory", None)
        if fn is None:
            return False
        ok = self._ok(await fn(user_input=user_input, ai_response=ai_response,
                               quintuples=quintuples, **kw))
        if ok:
            self._push(UndoOp("memory", {
                "user_input": user_input, "ai_response": ai_response,
                "quintuples": list(quintuples or [])}))
        return ok

    async def add_quintuples(self, quintuples: List) -> bool:
        fn = getattr(self._backend, "add_quintuples", None)
        if fn is None:
            fn = getattr(self._remote, "add_quintuples", None)
        if fn is None:
            return False
        ok = self._ok(await fn(quintuples))
        if ok:
            self._push(UndoOp("quintuples", {"quintuples": list(quintuples)}))
        return ok

    # ------------------------------------------------------------------ 撤销

    async def undo_last(self) -> bool:
        """撤销最近一条仍生效的写入。无可撤销条目时返回 False（幂等）。"""
        op = self._top_active()
        if op is None:
            return False
        await self._apply_inverse(op)
        op.active = False
        return True

    async def rollback(self, n: int) -> int:
        """回滚 n 步，返回实际回滚条数。"""
        count = 0
        for _ in range(max(0, int(n))):
            if not await self.undo_last():
                break
            count += 1
        return count

    async def forget_entity(self, entity) -> int:
        """定向遗忘某实体关联的全部生效记忆，返回遗忘条数。"""
        entity = str(entity)
        count = 0
        for op in self._stack:
            if op.active and any(entity in s for s in op.entities()):
                await self._apply_inverse(op)
                op.active = False
                count += 1
        return count

    # ------------------------------------------------------------------ 查询

    def has_entity(self, entity) -> bool:
        """该实体是否仍存在生效关联记忆（被遗忘后返回 False）。"""
        entity = str(entity)
        return any(op.active and any(entity in s for s in op.entities())
                   for op in self._stack)

    def is_record_tombstoned(self, record) -> bool:
        """单条记录是否已被 tombstone（降级删除）标记。

        支持五元组 tuple/list（取前三元 S/P/O）与 dict（subject/predicate/object
        或 s/p/o 键）两种形态；归一化后与降级删除时登记的内容键比对。
        """
        key = self._record_key(record)
        if key is not None:
            return key in self._tombstoned_quintuples
        if isinstance(record, str):
            return self._is_text_tombstoned(record)
        return False

    def filter_records(self, records) -> List:
        """过滤记录列表，剔除已被 undo/rollback/forget tombstone 的条目。"""
        if not isinstance(records, list):
            return records
        return [r for r in records if not self.is_record_tombstoned(r)]

    async def query_memory(self, question: str, **kw):
        """查询代理：透传后端/远端 query_memory，过滤 tombstone 残留内容。

        后端返回聚合文本时，若整段文本包含被 tombstone 的原文则判为污染，
        保守返回 None（宁可少给，不可回灌已删除记忆）。
        """
        fn = getattr(self._backend, "query_memory", None)
        if fn is None:
            fn = getattr(self._remote, "query_memory", None)
        if fn is None:
            return None
        try:
            result = await fn(question, **kw)
        except TypeError:
            # 后端签名不吃额外 kwargs（如 GRAGMemoryManager.query_memory(question)）
            result = await fn(question)
        return self._filter_payload(result)

    async def get_relevant_memories(self, query: str, limit: int = 3) -> List:
        """查询代理：透传后端 get_relevant_memories 并过滤 tombstone 记录。

        向后端多要 tombstone 数量的缓冲条，避免过滤后不足 limit。
        """
        fn = getattr(self._backend, "get_relevant_memories", None)
        if fn is None:
            fn = getattr(self._remote, "get_relevant_memories", None)
        if fn is None:
            return []
        limit = max(0, int(limit))
        fetch = limit + len(self._tombstoned_quintuples)
        try:
            records = await fn(query, fetch)
        except TypeError:
            records = await fn(query)
        return self.filter_records(records or [])[:limit]

    async def query_by_keywords(self, keywords: List[str], limit: int = 10):
        """查询代理：透传 remote.query_by_keywords，过滤返回里的 tombstone 记录。"""
        fn = getattr(self._backend, "query_by_keywords", None)
        if fn is None:
            fn = getattr(self._remote, "query_by_keywords", None)
        if fn is None:
            return None
        return self._filter_payload(await fn(keywords, limit=limit))

    def _filter_payload(self, payload):
        """任意查询返回体过滤：dict 挖常见列表字段，list 逐条过滤，str 查文本污染。"""
        if isinstance(payload, dict):
            for key in ("quintuples", "results", "items", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    payload[key] = self.filter_records(value)
                elif isinstance(value, str) and self._is_text_tombstoned(value):
                    payload[key] = None
            return payload
        if isinstance(payload, list):
            return self.filter_records(payload)
        if isinstance(payload, str):
            return None if self._is_text_tombstoned(payload) else payload
        return payload

    def _is_text_tombstoned(self, text: str) -> bool:
        if not text or not self._tombstoned_texts:
            return False
        return any(t in text for t in self._tombstoned_texts)

    @staticmethod
    def _record_key(record) -> Optional[Tuple[str, str, str]]:
        """五元组记录 → (S, P, O) 归一化键；无法识别的形态返回 None。"""
        if isinstance(record, (tuple, list)) and len(record) >= 3:
            return (str(record[0]).strip(), str(record[1]).strip(), str(record[2]).strip())
        if isinstance(record, dict):
            subject = record.get("subject") or record.get("s")
            predicate = record.get("predicate") or record.get("p")
            obj = record.get("object") or record.get("o")
            if subject is not None and predicate is not None and obj is not None:
                return (str(subject).strip(), str(predicate).strip(), str(obj).strip())
        return None

    def _register_tombstoned_content(self, op: UndoOp) -> None:
        """降级删除时登记被 tombstone 的内容特征，供查询路径过滤。"""
        for q in op.snapshot.get("quintuples", []) or []:
            key = self._record_key(q)
            if key is not None:
                self._tombstoned_quintuples.add(key)
        for key_name in ("user_input", "ai_response"):
            text = op.snapshot.get(key_name)
            if isinstance(text, str) and text.strip():
                self._tombstoned_texts.add(text)

    def active_entries(self) -> List[Dict[str, Any]]:
        """返回全部生效写入的快照（已撤销/遗忘的不含）。"""
        return [op.snapshot for op in self._stack if op.active]

    @property
    def active_count(self) -> int:
        return sum(1 for op in self._stack if op.active)

    @property
    def tombstones(self) -> set:
        """降级删除指纹集合（后端缺删除接口时写入）。"""
        return set(self._tombstones)

    def __len__(self) -> int:
        return self.active_count

    # ------------------------------------------------------------------ 内部

    def _push(self, op: UndoOp) -> None:
        self._stack.append(op)
        if len(self._stack) > self._undo_limit:
            self._stack.pop(0)

    def _top_active(self) -> Optional[UndoOp]:
        for op in reversed(self._stack):
            if op.active:
                return op
        return None

    async def _apply_inverse(self, op: UndoOp) -> bool:
        """应用逆操作：先尝试后端删除，缺接口则降级为 tombstone 标记删除。"""
        delete_name = _DELETE_METHOD.get(op.kind)
        deleted = False
        if delete_name:
            fn = getattr(self._backend, delete_name, None)
            if fn is None:
                fn = getattr(self._remote, delete_name, None)
            if fn is not None:
                try:
                    deleted = self._ok(await fn(op.snapshot))
                except Exception as e:  # 后端删除失败不抛异常，降级 tombstone
                    logger.warning("后端删除 %s 失败: %s，降级 tombstone", delete_name, e)
                    deleted = False
        if not deleted:
            fp = op.fingerprint()
            self._tombstones.add(fp)
            op.tombstones.append(fp)
            # 记录实际残留在后端的内容特征，查询时过滤（issue #24）
            self._register_tombstoned_content(op)
        return True

    @staticmethod
    def _ok(resp: Any) -> bool:
        """兼容 bool 与 {'success': ...} 两种返回形态。"""
        if isinstance(resp, dict):
            if "success" in resp:
                return bool(resp["success"])
            return True
        return bool(resp)