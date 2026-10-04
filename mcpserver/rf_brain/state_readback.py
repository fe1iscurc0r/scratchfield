"""W63-06 跨层状态读回确认原语

目标：检测「广播信任」模式下的隐式状态不一致。

术语：
- 广播信任（broadcast trust）：A 层写入状态后假设所有层已收到，不验证
- 读回确认（readback confirmation）：B 层从自身视角读取状态，与 A 层声明值对比，不一致则告警

典型应用场景：
- 决策层（rule_engine）声明当前调制方式 → 执行层（sensor/demod）读回确认
- 决策层声明频率/带宽 → 执行层读回确认
- 任意双向层间状态对齐

核心接口：
- LayerStateStore      : 单层状态存储（支持声明值 + 读回值分离）
- ReadbackConfirm      : 跨层读回确认器
- BroadcastTrustPolicy : 广播信任策略（不验证，直接信任）
- confirm()            : 执行读回确认，返回 (ok, diff)
- diagnose()           : 诊断广播信任 vs 读回确认的不一致检测能力
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
class LayerRole(Enum):
    """层角色：决策层（DECISION）或执行层（EXECUTION）。"""
    DECISION = auto()   # 决策层 — rule_engine
    EXECUTION = auto()  # 执行层 — sensor/demod backend


@dataclass
class StateSnapshot:
    """某层的单条状态快照。"""
    role: LayerRole
    key: str
    value: Any
    seq: int = 0           # 版本序列号（单调递增）


@dataclass
class ReadbackResult:
    """读回确认结果。"""
    key: str
    declared_by: LayerRole     # A 层声明的值
    readback_by: LayerRole    # B 层读回的值
    declared_value: Any
    readback_value: Any
    ok: bool                  # 是否一致
    diff_description: str = ""


# --------------------------------------------------------------------------- #
# 单层状态存储
# --------------------------------------------------------------------------- #
class LayerStateStore:
    """单层状态存储：维护本层声明的状态键值。

    与其他层的「读回副本」隔离——每个层只管自己的视角。
    """

    def __init__(self, role: LayerRole, description: str = ""):
        self.role = role
        self.description = description
        self._declared: Dict[str, Any] = {}      # 本层声明的值
        self._readback: Dict[str, StateSnapshot] = {}  # 从其他层读回的值
        self._seq: Dict[str, int] = {}           # 每个 key 的序列号

    def declare(self, key: str, value: Any) -> StateSnapshot:
        """A 层声明状态（写入自己的视角）。"""
        seq = self._seq.get(key, 0) + 1
        self._seq[key] = seq
        self._declared[key] = value
        return StateSnapshot(role=self.role, key=key, value=value, seq=seq)

    def readback(self, from_role: LayerRole, key: str, value: Any, seq: int = 0) -> None:
        """B 层记录从 A 层读回的状态值。"""
        self._readback[key] = StateSnapshot(
            role=from_role, key=key, value=value, seq=seq
        )

    def get_declared(self, key: str) -> Tuple[Any, int]:
        """返回 A 层声明的值和序列号。"""
        return self._declared.get(key), self._seq.get(key, 0)

    def get_readback(self, key: str) -> StateSnapshot | None:
        """返回 B 层读回的值快照（若无则 None）。"""
        return self._readback.get(key)


# --------------------------------------------------------------------------- #
# 读回确认策略
# --------------------------------------------------------------------------- #
class ReadbackConfirm:
    """跨层读回确认器。

    用法：
        confirm = ReadbackConfirm()

        # 决策层声明调制方式为 OOK
        confirm.declare(LayerRole.DECISION, "modulation", "OOK")

        # 执行层读回确认（从执行层视角）
        confirm.readback_and_confirm(
            reader_role=LayerRole.EXECUTION,
            declarer_role=LayerRole.DECISION,
            key="modulation",
            readback_value="GFSK",   # 执行层实际读到的是 GFSK（不一致！）
        )
    """

    def __init__(self):
        self._stores: Dict[LayerRole, LayerStateStore] = {
            LayerRole.DECISION: LayerStateStore(LayerRole.DECISION, "决策层"),
            LayerRole.EXECUTION: LayerStateStore(LayerRole.EXECUTION, "执行层"),
        }

    def declare(self, role: LayerRole, key: str, value: Any) -> StateSnapshot:
        """A 层声明状态。"""
        return self._stores[role].declare(key, value)

    def readback_and_confirm(
        self,
        reader_role: LayerRole,
        declarer_role: LayerRole,
        key: str,
        readback_value: Any,
    ) -> ReadbackResult:
        """B 层从自身视角读回 A 层的状态，与声明值对比。

        返回 ReadbackResult：ok=False 表示不一致（应告警）。
        """
        declarer_store = self._stores[declarer_role]
        declared_value, seq = declarer_store.get_declared(key)

        reader_store = self._stores[reader_role]
        reader_store.readback(declarer_role, key, readback_value, seq=seq)

        # 对比
        ok = _values_equal(declared_value, readback_value)
        diff_desc = "" if ok else (
            f"声明值={declared_value!r} vs 读回值={readback_value!r}"
        )

        return ReadbackResult(
            key=key,
            declared_by=declarer_role,
            readback_by=reader_role,
            declared_value=declared_value,
            readback_value=readback_value,
            ok=ok,
            diff_description=diff_desc,
        )

    def bulk_confirm(
        self,
        reader_role: LayerRole,
        declarer_role: LayerRole,
        readback_pairs: List[Tuple[str, Any]],
    ) -> List[ReadbackResult]:
        """批量读回确认（一次验证多条状态）。"""
        results = []
        for key, readback_value in readback_pairs:
            results.append(
                self.readback_and_confirm(reader_role, declarer_role, key, readback_value)
            )
        return results

    def has_mismatch(self, results: List[ReadbackResult]) -> bool:
        """判断是否有任何不一致。"""
        return any(not r.ok for r in results)


# --------------------------------------------------------------------------- #
# 广播信任策略（对照）
# --------------------------------------------------------------------------- #
class BroadcastTrustPolicy:
    """广播信任策略：只管写，不管验证。

    对比用：体现「不做读回确认」时的不一致检测盲区。

    模型：声明 → 广播总线（所有层收到相同值，但不验证）
    → 执行层以为收到了，实际上没有机制确认是否一致
    """

    def __init__(self):
        # 共享广播总线：key → value（所有层看到同一份）
        self._bus: Dict[str, Any] = {}

    def declare(self, role: LayerRole, key: str, value: Any) -> None:
        """A 层声明状态（广播出去，信任所有层已收到）。"""
        self._bus[key] = value

    def read(self, role: LayerRole, key: str, default: Any = None) -> Any:
        """B 层读取状态（从广播总线，不验证是否与声明一致）。

        这里 role 参数保留接口签名，但读的是总线，不区分角色。
        """
        return self._bus.get(key, default)


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _values_equal(a: Any, b: Any) -> bool:
    """比较两个值是否相等（支持 numpy 数组）。"""
    if a is None or b is None:
        return a is b
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        try:
            return bool(np.all(a == b))
        except Exception:
            return False
    try:
        return bool(a == b)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# 诊断：展示广播信任 vs 读回确认的差异
# --------------------------------------------------------------------------- #
def diagnose(
    key: str,
    decision_value: Any,
    sensor_readback_value: Any,
) -> Dict[str, Any]:
    """诊断单条状态：广播信任 vs 读回确认的检测能力对比。

    返回：
        - broadcast_trust_result : 广播信任读到啥（无验证）
        - readback_confirm_result : 读回确认是否检出不一致
        - missed_by_broadcast : 广播信任是否漏检
    """
    # 广播信任
    bcast = BroadcastTrustPolicy()
    bcast.declare(LayerRole.DECISION, key, decision_value)
    bcast_read = bcast.read(LayerRole.EXECUTION, key, default=None)

    # 读回确认
    confirm = ReadbackConfirm()
    confirm.declare(LayerRole.DECISION, key, decision_value)
    rb_result = confirm.readback_and_confirm(
        reader_role=LayerRole.EXECUTION,
        declarer_role=LayerRole.DECISION,
        key=key,
        readback_value=sensor_readback_value,
    )

    return {
        "key": key,
        "decision_declared": decision_value,
        "sensor_readback": sensor_readback_value,
        "broadcast_trust_value": bcast_read,
        "readback_confirm_ok": rb_result.ok,
        "readback_confirm_diff": rb_result.diff_description,
        # 关键指标：广播信任是否漏掉不一致
        "broadcast_missed": not rb_result.ok and _values_equal(
            bcast_read, decision_value
        ),
    }
