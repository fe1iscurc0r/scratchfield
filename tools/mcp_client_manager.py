# -*- coding: utf-8 -*-
"""MCP 客户端管理面参考实现（W65-05 · server 状态机 + shortId 映射）。

参考 5ire manager 模式（不抄代码）：server 状态机（激活/停用/连接中）+ 实时状态
查询 + 双缓存 + shortId 映射。纯标准库。
"""
from __future__ import annotations

from dataclasses import dataclass, field

SERVER_STATES = ("inactive", "connecting", "active")
TRANSITIONS = {
    "inactive": {"connecting"},
    "connecting": {"active", "inactive"},
    "active": {"inactive"},
}


@dataclass
class MCPClientManager:
    """server 状态机 + shortId 唯一映射。"""
    servers: dict[str, str] = field(default_factory=dict)   # name -> state
    _short_ids: dict[str, str] = field(default_factory=dict)  # shortId -> name
    _counter: int = 0

    def register(self, name: str) -> str:
        """登记 server，返回唯一 shortId。"""
        self.servers[name] = "inactive"
        self._counter += 1
        sid = f"s{self._counter}"
        self._short_ids[sid] = name
        return sid

    def transition(self, name: str, to: str) -> bool:
        cur = self.servers.get(name)
        if cur is None or to not in TRANSITIONS.get(cur, set()):
            return False
        self.servers[name] = to
        return True

    def resolve(self, short_id: str) -> str | None:
        return self._short_ids.get(short_id)

    def is_short_id_unique(self) -> bool:
        names = set(self._short_ids.values())
        return len(names) == len(self._short_ids)


if __name__ == "__main__":
    m = MCPClientManager()
    sid = m.register("filesystem")
    m.transition("filesystem", "connecting")
    m.transition("filesystem", "active")
    print("shortId:", sid, "resolve:", m.resolve(sid), "state:", m.servers["filesystem"])
