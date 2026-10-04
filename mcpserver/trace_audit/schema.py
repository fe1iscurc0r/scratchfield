"""Trace Integrity 审计 —— 记录 schema 定义。

定义「交付物 / 工单 / 记忆条目」三类可审计记录的必需字段与类型约束，
供 audit.py 做 schema-valid 判定。纯 stdlib，只读审计，不修改既有格式。

七项审计标准对应的字段要求：
  1. schema 合法  → REQUIRED_FIELDS 齐全且类型正确
  2. 时间戳齐全   → timestamp 存在且可解析（epoch 秒或 ISO-8601）
  3. id 唯一      → 跨记录 id 不重复（audit.py 判定）
  4. 来源可溯     → source 非空
  5. 回放无缺口   → timestamp 单调可回放、无断链（audit.py 判定）
  6. 边界明确     → type 属于已知边界，或带显式 scope
  7. 责任人明确   → owner 非空
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

# 必需字段（顺序即 schema 定义顺序）
REQUIRED_FIELDS: tuple[str, ...] = ("id", "timestamp", "source", "type", "owner")

# 已知记录边界（type 白名单，可扩展）
KNOWN_TYPES: frozenset[str] = frozenset({
    "workorder",   # 工单
    "delivery",    # 交付物
    "memory",      # 记忆条目
    "report",      # 报告
    "spec",        # 规格 / SPEC
    "log",         # 日志
    "config",      # 配置
})


def parse_timestamp(value: Any) -> float | None:
    """把时间戳统一解析为 epoch 秒（float）；无法解析返回 None。

    接受 int/float（epoch 秒）、纯数字字符串、ISO-8601 字符串。
    bool 是 int 子类，显式排除。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            pass
        try:
            return _dt.datetime.fromisoformat(s).timestamp()
        except (ValueError, TypeError):
            return None
    return None


def field_type_ok(name: str, value: Any) -> bool:
    """字段类型校验：字符串字段须为非空 str，timestamp 须可解析。"""
    if name in ("id", "source", "type", "owner"):
        return isinstance(value, str) and bool(value.strip())
    if name == "timestamp":
        return parse_timestamp(value) is not None
    return True
