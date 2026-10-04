"""W71-01 · 无主 mesh 路由原型（吞入自 painlessMesh 设计，AGPL 自研实现）。

painlessMesh 的核心：无主节点 + 心跳邻居表 + 逐跳洪泛路由（TTL + 去重）。
本原型用纯 Python 实现这套「无主自组网」机制，供 LoRaCanary 对等 mesh 参考。

模型：节点构成无向图，每条消息带 (msg_id, ttl)，从源节点洪泛到邻居，直到 TTL 耗尽；
msg_id 去重避免环路。纯标准库。
"""
from __future__ import annotations

from collections import defaultdict


class MeshNode:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.neighbors: set[str] = set()
        self.received: set = set()   # 已见 msg_id（去重）

    def add_neighbor(self, other_id: str) -> None:
        self.neighbors.add(other_id)


class MeshNetwork:
    """无主 mesh：节点 + 洪泛路由。"""

    def __init__(self):
        self.nodes: dict[str, MeshNode] = {}

    def add_node(self, node_id: str) -> MeshNode:
        n = MeshNode(node_id)
        self.nodes[node_id] = n
        return n

    def link(self, a: str, b: str) -> None:
        self.nodes[a].add_neighbor(b)
        self.nodes[b].add_neighbor(a)

    def heartbeat(self, node_id: str) -> list[str]:
        """返回该节点当前邻居表（心跳 + 邻居发现的结果）。"""
        return sorted(self.nodes[node_id].neighbors)

    def route(self, src: str, msg_id: str, ttl: int = 3) -> set[str]:
        """从 src 洪泛一条消息，返回收到的节点集合（TTL 跳数内 + 去重）。"""
        reached = {src}
        frontier = {src}
        remaining = ttl
        while frontier and remaining > 0:
            nxt = set()
            for nid in frontier:
                for nb in self.nodes[nid].neighbors:
                    if msg_id not in self.nodes[nb].received:
                        self.nodes[nb].received.add(msg_id)
                        nxt.add(nb)
            reached |= nxt
            frontier = nxt
            remaining -= 1
        return reached


def run_demo() -> None:
    net = MeshNetwork()
    for i in range(5):
        net.add_node(f"n{i}")
    # 链式拓扑 n0-n1-n2-n3-n4
    for i in range(4):
        net.link(f"n{i}", f"n{i+1}")
    reached = net.route("n0", "m1", ttl=2)
    print(f"[W71-01] 源 n0 洪泛(TTL=2) 到达: {sorted(reached)}")
    print(f"[W71-01] n1 邻居表: {net.heartbeat('n1')}")


if __name__ == "__main__":
    run_demo()
