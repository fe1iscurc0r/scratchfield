"""ReasonCode 枚举 — multica Admission 词表落地。

铁律（multica S4）：
- 代码在决策源头生成，绝不从错误字符串反推。
- 语义稳定、可本地化、不泄露隐私信息。

三组语义：
1. 成功路径：queued / coalesced / deferred
2. 拒绝路径：invocation_not_allowed / target_unavailable / runtime_offline /
   runtime_unusable / already_active / self_trigger_suppressed
3. blocked 子分类：可等（等待能解决）vs 不可等（等待无意义，需人修）
   - 可等：runtime_offline（机器离线）→ 排队即可；blocked_wait_external /
     blocked_wait_permission
   - 不可等：runtime_unusable（CLI 不可执行）→ 等待无意义；blocked_env /
     blocked_dead_end / blocked_attribution
"""

from __future__ import annotations

from enum import Enum


class ReasonCode(str, Enum):
    # ── 成功路径 ──
    QUEUED = "queued"                 # 已入队，等待调度
    COALESCED = "coalesced"           # 与既有非终态任务合并，不再重复派发
    DEFERRED = "deferred"             # 已延迟，等待满足前置条件

    # ── 拒绝路径 ──
    INVOCATION_NOT_ALLOWED = "invocation_not_allowed"   # 该状态不允许此调用
    TARGET_UNAVAILABLE = "target_unavailable"           # 目标/负责人不可达
    RUNTIME_OFFLINE = "runtime_offline"                 # 机器离线（可等）
    RUNTIME_UNUSABLE = "runtime_unusable"               # CLI 不可执行（不可等）
    ALREADY_ACTIVE = "already_active"                   # 已有活跃任务
    SELF_TRIGGER_SUPPRESSED = "self_trigger_suppressed" # 自触发抑制

    # ── blocked 子分类 ──
    BLOCKED_WAIT_EXTERNAL = "blocked_wait_external"     # 缺硬件/缺真机/等上游（可等）
    BLOCKED_WAIT_PERMISSION = "blocked_wait_permission" # 缺许可/需法务核（可等）
    BLOCKED_ENV = "blocked_env"                         # 工具链不可用（不可等）
    BLOCKED_DEAD_END = "blocked_dead_end"               # 方案不可行/上游归档（不可等）
    BLOCKED_ATTRIBUTION = "blocked_attribution"         # 无法归因，fail-closed（不可等）


# 可等（等待能解决，任务保留排队）
WAITABLE_BLOCKED: frozenset[ReasonCode] = frozenset({
    ReasonCode.RUNTIME_OFFLINE,
    ReasonCode.BLOCKED_WAIT_EXTERNAL,
    ReasonCode.BLOCKED_WAIT_PERMISSION,
})

# 不可等（等待无意义，需人先修环境 / 取消工单）
NON_WAITABLE_BLOCKED: frozenset[ReasonCode] = frozenset({
    ReasonCode.RUNTIME_UNUSABLE,
    ReasonCode.BLOCKED_ENV,
    ReasonCode.BLOCKED_DEAD_END,
    ReasonCode.BLOCKED_ATTRIBUTION,
})

# 全部可充当 blocked 理由的 code（子分类 + 拒绝路径中的 runtime_* 对）
BLOCKED_CODES: frozenset[ReasonCode] = WAITABLE_BLOCKED | NON_WAITABLE_BLOCKED


def is_blocked_code(code: str | ReasonCode | None) -> bool:
    """判断一个 reason code 是否可作为 blocked 的合法理由。"""
    try:
        return ReasonCode(code) in BLOCKED_CODES
    except ValueError:
        return False


def is_waitable(code: str | ReasonCode | None) -> bool:
    """可等 vs 不可等：等待是否能解决问题。"""
    try:
        return ReasonCode(code) in WAITABLE_BLOCKED
    except ValueError:
        return False


def waitability(code: str | ReasonCode | None) -> str:
    """返回 'waitable' / 'non_waitable' 分类标签。"""
    return "waitable" if is_waitable(code) else "non_waitable"
