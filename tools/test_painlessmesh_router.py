"""W71-01 无主 mesh 路由测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from painlessmesh_router import MeshNetwork


def _chain(n=5):
    net = MeshNetwork()
    for i in range(n):
        net.add_node(f"n{i}")
    for i in range(n - 1):
        net.link(f"n{i}", f"n{i+1}")
    return net


def test_ttl_limits_hop():
    net = _chain(5)
    reached = net.route("n0", "m1", ttl=1)
    assert reached == {"n0", "n1"}           # 仅 1 跳邻居


def test_ttl_covers_chain():
    net = _chain(5)
    reached = net.route("n0", "m2", ttl=4)
    assert reached == {f"n{i}" for i in range(5)}   # 全链可达


def test_dedup_no_loop():
    net = MeshNetwork()
    for i in range(3):
        net.add_node(f"n{i}")
    net.link("n0", "n1"); net.link("n1", "n2"); net.link("n0", "n2")  # 三角环
    reached = net.route("n0", "m3", ttl=5)
    assert reached == {"n0", "n1", "n2"}     # 环不产生重复/死循环


def test_heartbeat_neighbors():
    net = _chain(3)
    assert net.heartbeat("n1") == ["n0", "n2"]
