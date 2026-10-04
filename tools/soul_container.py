# -*- coding: utf-8 -*-
"""airi 灵魂容器 + 分层提示参考（W65-06 · soul/style/rules 分层 + depth_prompt）。

depth_prompt 一个字段切换闲聊/工作模式；灵魂容器格式结构化（soul/style/rules）。
纯标准库。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SoulContainer:
    """灵魂容器：人格结构化（soul/style/rules 分层）。"""
    soul: str = ""
    style: str = ""
    rules: list[str] = field(default_factory=list)
    depth_prompt: str = "chat"  # chat / work

    @classmethod
    def from_dict(cls, d: dict) -> "SoulContainer":
        return cls(
            soul=d.get("soul", ""),
            style=d.get("style", ""),
            rules=list(d.get("rules", [])),
            depth_prompt=d.get("depth_prompt", "chat"),
        )

    def set_mode(self, mode: str) -> bool:
        """切换模式（chat/work）。"""
        if mode not in ("chat", "work"):
            return False
        self.depth_prompt = mode
        return True

    def prompt(self) -> str:
        """按当前模式生成分层提示。"""
        prefix = "闲聊模式" if self.depth_prompt == "chat" else "工作模式"
        return f"[{prefix}] {self.soul} | 风格:{self.style} | 规则:{';'.join(self.rules)}"


if __name__ == "__main__":
    s = SoulContainer.from_dict({"soul": "温柔助手", "style": "简洁", "rules": ["不说脏话"], "depth_prompt": "chat"})
    print(s.prompt())
    s.set_mode("work")
    print(s.prompt())
