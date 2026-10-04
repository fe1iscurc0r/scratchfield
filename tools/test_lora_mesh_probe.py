"""lora_mesh_probe 验收硬线（卷102 W102-06）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lora_mesh_probe import SELF, MeshNetwork  # noqa: E402


def test_three_node_relay_routing():
    """三节点链 A→B→C：路由表逐跳转发到达，每跳 ACK 留痕。"""
    net = MeshNetwork()
    for n in (1, 2, 3):
        net.add_node(n)
    assert net.nodes[1].route_to(1) == SELF      # 自身路由标记
    net.install_route(1, 3, 2)                    # A 到 C 走 B（对照路由表条目）
    net.install_route(1, 2, 2)
    net.install_route(2, 3, 3)
    ok = net.send(1, 3, seq=7, payload="ping")
    assert ok is True
    assert (1, 7, "ping") in net.nodes[3].delivered
    assert net.hops[0] == (1, 2) and net.hops[1] == (2, 3)
    assert net.acks == [(2, 1), (3, 2)]


def test_duplicate_suppression():
    """(origin, seq) 重复包被中继节点抑制，不二次落地。"""
    net = MeshNetwork()
    for n in (1, 2):
        net.add_node(n)
    net.install_route(1, 2, 2)
    assert net.send(1, 2, seq=9, payload="x") is True
    assert net.send(1, 2, seq=9, payload="x") is True
    assert len(net.nodes[2].delivered) == 1     # 只落地一次
    assert any(d.startswith("duplicate:") for d in net.dropped)


def test_ttl_and_no_route_drops():
    """TTL 耗尽与无路由（next_hop=0）均显式丢弃并有原因记录。"""
    net = MeshNetwork()
    for n in (1, 2):
        net.add_node(n)
    net.install_route(1, 2, 2)
    assert net.send(1, 2, seq=1, payload="x", ttl=0) is False
    assert net.dropped[-1].startswith("ttl_exhausted")
    # 无路由：1 想发给 2 但路由条目缺失
    net2 = MeshNetwork()
    net2.add_node(1)
    net2.add_node(2)
    assert net2.send(1, 2, seq=2, payload="y") is False
    assert net2.dropped[-1].startswith("no_route:")
    assert net2.send(1, 99, seq=3, payload="z") is False  # 目标不存在亦不崩溃