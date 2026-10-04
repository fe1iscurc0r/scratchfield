"""LoRa mesh 路由最小模拟（卷102 W102-06 · MIT 可参考，纯 Python 逻辑模拟）。

模拟 lora-mesh 的「路由表 / 逐跳中继 / 去重 / TTL」协议骨架：
节点维护全表路由，报文按 next_hop 逐跳转发，各节点按 (origin, seq) 去重，
每跳 ACK 记录（对照上游 ack 语义），无路由（next_hop=0）与 TTL 耗尽显式丢弃。

源结构对照（nootropicdesign/lora-mesh，LoRaMesh.ino）：
- :11  uint8_t routes[N_NODES] 全量路由表（本探针 routes: dest -> next_hop）
- :105 routes[n-1] = 255 自身路由标记；:107 next_hop 条目写入；:108 next_hop==0 无路由
- :158 发送确认报文；:166 收到下一跳 ACK
本探针为纯逻辑模拟：不实现空口时序/时隙，只验证路由与去重语义。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SELF = 255  # 对照 ino:105 的自身路由标记


@dataclass
class MeshNode:
    """mesh 节点：路由表 + 去重集合 + 收发记录。"""
    node_id: int
    routes: dict[int, int] = field(default_factory=dict)        # dest -> next_hop（对照 ino:11）
    seen: set[tuple[int, int]] = field(default_factory=set)     # (origin, seq) 去重
    delivered: list[tuple[int, int, str]] = field(default_factory=list)  # (origin, seq, payload)

    def route_to(self, dest: int) -> int:
        return self.routes.get(dest, 0)


@dataclass
class MeshNetwork:
    """mesh 网络模拟：逐跳转发 / 每跳 ACK / 去重 / TTL 丢弃的裁决记录。"""

    nodes: dict[int, MeshNode] = field(default_factory=dict)
    hops: list[tuple[int, int]] = field(default_factory=list)          # 每跳 (from, to)
    acks: list[tuple[int, int]] = field(default_factory=list)          # 每跳 (to, from)
    dropped: list[str] = field(default_factory=list)                   # 丢弃原因记录

    def add_node(self, node_id: int) -> MeshNode:
        node = MeshNode(node_id=node_id)
        node.routes[node_id] = SELF
        self.nodes[node_id] = node
        return node

    def install_route(self, src: int, dest: int, next_hop: int) -> None:
        """写入路由条目（对照 ino:107 next_hop 条目）。"""
        self.nodes[src].routes[dest] = next_hop

    def _one_hop(self, from_id: int, to_id: int, origin: int, seq: int,
                 payload: str, ttl: int) -> bool:
        """单跳发送：物理可达（节点存在）即送达，节点侧做去重与落地。"""
        dest_node = self.nodes.get(to_id)
        if dest_node is None:
            self.dropped.append(f"unreachable:{from_id}->{to_id}")
            return False
        self.hops.append((from_id, to_id))
        self.acks.append((to_id, from_id))   # 每跳 ACK（对照 ino:158/166）
        key = (origin, seq)
        if key in dest_node.seen:
            self.dropped.append(f"duplicate:{origin}#{seq}@node{to_id}")
            return True                      # 已送达过：视为重复抑制成功
        dest_node.seen.add(key)
        dest_node.delivered.append((origin, seq, payload))
        return True

    def send(self, src_id: int, dest_id: int, seq: int, payload: str, ttl: int = 5) -> bool:
        """源节点发起：沿路由逐跳转发，返回是否最终送达。"""
        src = self.nodes.get(src_id)
        if src is None:
            self.dropped.append(f"no_src:{src_id}")
            return False
        current = src_id
        guard = 0
        while current != dest_id:
            guard += 1
            if guard > len(self.nodes):
                self.dropped.append("route_loop")
                return False
            node = self.nodes[current]
            next_hop = node.route_to(dest_id)
            if next_hop == 0:
                self.dropped.append(f"no_route:{current}->{dest_id}")   # 对照 ino:108
                return False
            if ttl <= 0:
                self.dropped.append(f"ttl_exhausted:at{current}")
                return False
            ttl -= 1
            if not self._one_hop(current, next_hop, src_id, seq, payload, ttl):
                return False
            current = next_hop
        return True