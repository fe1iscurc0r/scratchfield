"""EIS 电化学阻抗谱工具组（工单202 任务一）。

    kernel.py  可换核谱反卷积抽象（EIS/DLS/SDR 三域共用数学骨架）
    tools.py   linkk / drt / ecm 三工具
    agent.py   总线接入层（EisAgent）
"""

from .agent import EisAgent

__all__ = ["EisAgent"]
