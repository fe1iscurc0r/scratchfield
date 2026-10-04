# -*- coding: utf-8 -*-
"""JLC-EDA 寄生控制链第一宿主落地（W66-06 · API 通道骨架 + 双通道指挥层）。

依据 docs/JLC-EDA-寄生控制链-SPEC-v1.md §4.1：API 通道骨架（EasyEDA Pro 官方
eda.* 扩展 API 的类型化操作封装）+ 复刻目标选型（AntiHunter DIGI）+ 双通道指挥层
（屏幕控制 + 软件接入共用一个指挥层）。纯标准库，mock 降级。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 复刻目标选型（按 SPEC 建议）
REPLICA_TARGET = {
    "node": "AntiHunter DIGI",
    "reason": "物料最贴近，双通道（屏幕+API）可复用",
}

# 类型化操作目录（EasyEDA Pro eda.* 封装的骨架）
TYPED_ACTIONS = ("place_symbol", "route_track", "export_gerber", "drf_check")


@dataclass
class EDACommander:
    """双通道指挥层：屏幕控制 + 软件接入（API）共用一个指挥层。"""
    api_available: bool = False
    executed: list[str] = field(default_factory=list)

    def typed_action(self, action: str, **kwargs) -> dict:
        """API 通道：类型化操作封装；API 不可用则 mock 降级。"""
        if action not in TYPED_ACTIONS:
            return {"ok": False, "reason": f"未支持动作 {action}"}
        if not self.api_available:
            return {"ok": True, "mock": True, "action": action, "args": kwargs}
        self.executed.append(action)
        return {"ok": True, "action": action, "args": kwargs}


def replica_target_plan() -> dict:
    """复刻目标选型依据 + 双通道架构。"""
    return {
        "replica": REPLICA_TARGET,
        "dual_channel": "屏幕控制通道 + 软件接入(API)通道，共用一个 EDACommander 指挥层",
    }


if __name__ == "__main__":
    c = EDACommander(api_available=False)
    print(c.typed_action("place_symbol", ref="R1"))
    print(replica_target_plan()["dual_channel"])
