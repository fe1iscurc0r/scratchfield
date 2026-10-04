# -*- coding: utf-8 -*-
"""桌宠 pet-id 隔离 + 事件映射（W65-04 · 每个桌宠独立配置/记忆目录）。

pet-id 目录约定 `pets/<pet-id>/`，事件映射（加载/点击/拖拽 → 动作/表情/台词）。
纯标准库。
"""
from __future__ import annotations

from pathlib import Path

# 事件 → 动作映射（参考结构）
EVENT_ACTION_MAP = {
    "load": "greet",
    "click": "poke",
    "drag": "follow",
    "double_click": "pet",
}


def pet_dir(pet_id: str, base: str = "pets") -> str:
    """每个桌宠独立目录 `pets/<pet-id>/`（POSIX 风格正斜杠，跨平台一致）。"""
    return f"{base}/{pet_id}"


def map_event(event: str) -> str:
    """事件 → 动作（未知名回退 idle）。"""
    return EVENT_ACTION_MAP.get(event, "idle")


class PetProfile:
    """桌宠配置：pet-id 隔离 + 事件映射。"""
    def __init__(self, pet_id: str) -> None:
        self.pet_id = pet_id
        self.dir = pet_dir(pet_id)

    def react(self, event: str) -> dict:
        return {"pet_id": self.pet_id, "event": event, "action": map_event(event)}


if __name__ == "__main__":
    p = PetProfile("tom")
    print("目录:", p.dir, "点击:", p.react("click"))
