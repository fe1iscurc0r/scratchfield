"""
AgentServer 公共工具函数
"""

from datetime import time as dt_time


def is_time_in_range(now: dt_time, start: dt_time, end: dt_time) -> bool:
    """判断时间 now 是否在 [start, end] 范围内，支持跨午夜

    Args:
        now: 当前时间
        start: 范围起始时间
        end: 范围结束时间

    Returns:
        True 表示 now 在 [start, end] 范围内
    """
    if start < end:
        return start <= now <= end
    elif start > end:
        # 跨午夜，如 22:00-06:00
        return now >= start or now <= end
    else:
        # start == end: 显式定义为零宽区间（仅精确命中该时刻），避免走跨午夜分支恒为 True
        return now == start
