"""Disposable 原语 —— 还原 Cordis utils.ts 的 DisposableList。

参考：vendor/cordis/src/utils.ts:5-40
- push/unshift 返回精确 disposer（按序号删除，O(1)）
- delete(value) 按值 O(1) 删除
- clear() 返回**逆序**值列表（先注册的后清理）
"""
from __future__ import annotations

from typing import Callable, Dict, Generic, Iterator, List, TypeVar

# 契约 A：所有注册返回精确 disposer，调用即卸载，不抛
Disposable = Callable[[], None]

T = TypeVar("T")


class DisposableList(Generic[T]):
    """有序可弃置集合：O(1) 按值删除 + 逆序清理。

    值必须是可哈希的（函数、对象均可）。同一值重复注册时，
    delete(value) 只移除最后一次注册（与 Cordis WeakMap 行为一致）。
    """

    __slots__ = ("_hi", "_lo", "_map", "_index")

    def __init__(self) -> None:
        self._hi = 0  # push 用递增序号
        self._lo = 0  # unshift 用递减序号
        self._map: Dict[int, T] = {}
        self._index: Dict[T, int] = {}

    def __len__(self) -> int:
        return len(self._map)

    def push(self, value: T) -> Disposable:
        """追加到尾部，返回 O(1) disposer。"""
        self._hi += 1
        return self._insert(self._hi, value)

    def unshift(self, value: T) -> Disposable:
        """插入到头部，返回 O(1) disposer。"""
        self._lo -= 1
        return self._insert(self._lo, value)

    def _insert(self, sn: int, value: T) -> Disposable:
        self._map[sn] = value
        self._index[value] = sn

        def dispose() -> None:
            # 幂等：重复调用是 no-op，不抛
            if self._map.pop(sn, None) is not None:
                self._index.pop(value, None)

        return dispose

    def delete(self, value: T) -> bool:
        """按值 O(1) 删除。找到并删除返回 True，否则 False。"""
        sn = self._index.pop(value, None)
        if sn is None:
            return False
        return self._map.pop(sn, None) is not None

    def clear(self) -> List[T]:
        """清空并返回**逆序**值列表（逆序清理契约）。"""
        values = [self._map[sn] for sn in sorted(self._map)]
        self._map.clear()
        self._index.clear()
        values.reverse()
        return values

    def snapshot(self) -> List[T]:
        """当前值的有序快照（dispatch 期间注册/注销不影响本轮）。"""
        return [self._map[sn] for sn in sorted(self._map)]

    def __iter__(self) -> Iterator[T]:
        return iter(self.snapshot())
