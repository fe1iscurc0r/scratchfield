"""网络拓扑生成器：``grid`` / ``random`` / ``lora_deployment``。

三种拓扑的用途
--------------
- ``grid``            : 规则网格。分簇结果**可手算校验**（簇边界与跳数都是确定值），
  适合做回归基线。
- ``random``          : 区域内均匀随机。适合做蒙特卡洛（``dashboard`` 的弹性曲线用它）。
- ``lora_deployment`` : **合成样例**，形态参考 LoRaCanary 一类「单网关 + 分散节点」部署
  （网关居中，其余节点按若干扇区向外分布，近密远疏）。

⚠️ ``lora_deployment`` 是**人工设定的合成形态**，不是实测坐标 —— 本仓没有 LoRaCanary
的真实布点数据（``firmware/dcp_lora/`` 只有固件，无布点表）。若日后拿到实测坐标，
应新增 ``from_waypoints()`` 入口，而不是修改本函数（保持合成样例的口径可追溯）。

频道参数（``freq_hz`` / ``path_loss_exponent``）挂在 ``Topology`` 上而不是 ``Node`` 上 ——
它们是**信道属性**，同一次仿真里对全网一致；``Node`` 只持有**自身**的射频属性（发射功率/天线增益）。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .node import DEFAULT_FREQ_HZ, DEFAULT_PATH_LOSS_EXPONENT, DEFAULT_TX_POWER_DBM, Node

GRID = "grid"
RANDOM = "random"
LORA_DEPLOYMENT = "lora_deployment"
TOPOLOGY_KINDS = (GRID, RANDOM, LORA_DEPLOYMENT)

DEFAULT_MARGIN_RATIO = 0.05
# lora_deployment：扇区数 ≈ 每 8 个节点 1 个，最少 1 个
LORA_NODES_PER_LOBE = 8
# 网关到最外圈的半径占区域短边的比例
LORA_MAX_RADIUS_RATIO = 0.42


@dataclass
class Topology:
    """一次生成的拓扑快照（节点 + 区域尺寸 + 信道参数）。"""

    kind: str
    width: float
    height: float
    nodes: list[Node] = field(default_factory=list)
    freq_hz: float = DEFAULT_FREQ_HZ
    path_loss_exponent: float = DEFAULT_PATH_LOSS_EXPONENT

    @property
    def size(self) -> int:
        return len(self.nodes)

    @property
    def alive_nodes(self) -> list[Node]:
        return [n for n in self.nodes if n.alive]

    def positions(self) -> list[tuple[float, float]]:
        return [n.position for n in self.nodes]

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "width": self.width,
            "height": self.height,
            "size": self.size,
            "alive": len(self.alive_nodes),
            "freq_hz": self.freq_hz,
            "path_loss_exponent": self.path_loss_exponent,
        }


def _axis_positions(count: int, span: float, margin_ratio: float) -> list[float]:
    """在 ``span`` 内均匀铺 ``count`` 个坐标（含两侧留白）。"""
    if count <= 0:
        return []
    if count == 1:
        return [span / 2.0]
    margin = span * margin_ratio
    step = (span - 2.0 * margin) / (count - 1)
    return [margin + i * step for i in range(count)]


def grid_topology(
    n: int,
    *,
    width: float,
    height: float,
    margin_ratio: float = DEFAULT_MARGIN_RATIO,
    tx_power_dbm: float = DEFAULT_TX_POWER_DBM,
    freq_hz: float = DEFAULT_FREQ_HZ,
    path_loss_exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
) -> Topology:
    """规则网格拓扑：行列数最接近正方形的排布，居中铺满。"""
    if n <= 0:
        raise ValueError("节点数必须为正")
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    xs = _axis_positions(cols, width, margin_ratio)
    ys = _axis_positions(rows, height, margin_ratio)
    nodes: list[Node] = []
    for idx in range(n):
        row, col = divmod(idx, cols)
        nodes.append(
            Node(node_id=idx, x=xs[col], y=ys[row], tx_power_dbm=tx_power_dbm)
        )
    return Topology(
        kind=GRID,
        width=width,
        height=height,
        nodes=nodes,
        freq_hz=freq_hz,
        path_loss_exponent=path_loss_exponent,
    )


def random_topology(
    n: int,
    *,
    width: float,
    height: float,
    seed: int | None = None,
    tx_power_dbm: float = DEFAULT_TX_POWER_DBM,
    freq_hz: float = DEFAULT_FREQ_HZ,
    path_loss_exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
) -> Topology:
    """区域内均匀随机拓扑（同一 ``seed`` 可复现）。"""
    if n <= 0:
        raise ValueError("节点数必须为正")
    rng = random.Random(seed)
    nodes = [
        Node(
            node_id=i,
            x=rng.uniform(0.0, width),
            y=rng.uniform(0.0, height),
            tx_power_dbm=tx_power_dbm,
        )
        for i in range(n)
    ]
    return Topology(
        kind=RANDOM,
        width=width,
        height=height,
        nodes=nodes,
        freq_hz=freq_hz,
        path_loss_exponent=path_loss_exponent,
    )


def lora_deployment_topology(
    n: int,
    *,
    width: float,
    height: float,
    seed: int | None = None,
    tx_power_dbm: float = DEFAULT_TX_POWER_DBM,
    freq_hz: float = DEFAULT_FREQ_HZ,
    path_loss_exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
) -> Topology:
    """单网关 + 分散节点的**合成**部署样例（网关 id=0 居中，其余按扇区向外分布）。"""
    if n <= 0:
        raise ValueError("节点数必须为正")
    rng = random.Random(seed)
    cx, cy = width / 2.0, height / 2.0
    max_radius = min(width, height) * LORA_MAX_RADIUS_RATIO
    nodes = [Node(node_id=0, x=cx, y=cy, tx_power_dbm=tx_power_dbm)]
    remaining = n - 1
    lobes = max(1, math.ceil(remaining / LORA_NODES_PER_LOBE))
    base_angle = rng.uniform(0.0, 2.0 * math.pi)
    for i in range(remaining):
        lobe = i % lobes
        # 扇区中心角 + 扇区内抖动（±0.6 rad），避免扇区之间糊成一片
        angle = base_angle + 2.0 * math.pi * lobe / lobes + rng.uniform(-0.6, 0.6)
        # sqrt(u) 使节点在圆盘上近似均匀；再乘径向后撤量做近密远疏
        radius = max_radius * math.sqrt(rng.uniform(0.0, 1.0)) * rng.uniform(0.35, 1.0)
        nodes.append(
            Node(
                node_id=i + 1,
                x=min(max(cx + radius * math.cos(angle), 0.0), width),
                y=min(max(cy + radius * math.sin(angle), 0.0), height),
                tx_power_dbm=tx_power_dbm,
            )
        )
    return Topology(
        kind=LORA_DEPLOYMENT,
        width=width,
        height=height,
        nodes=nodes,
        freq_hz=freq_hz,
        path_loss_exponent=path_loss_exponent,
    )


def generate(
    kind: str,
    n: int,
    *,
    width: float,
    height: float,
    seed: int | None = None,
    tx_power_dbm: float = DEFAULT_TX_POWER_DBM,
    freq_hz: float = DEFAULT_FREQ_HZ,
    path_loss_exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
) -> Topology:
    """按 ``kind`` 生成拓扑；未知 ``kind`` 直接抛 ``ValueError``（不静默回退默认值）。"""
    common = {
        "width": width,
        "height": height,
        "tx_power_dbm": tx_power_dbm,
        "freq_hz": freq_hz,
        "path_loss_exponent": path_loss_exponent,
    }
    if kind == GRID:
        return grid_topology(n, **common)
    if kind == RANDOM:
        return random_topology(n, seed=seed, **common)
    if kind == LORA_DEPLOYMENT:
        return lora_deployment_topology(n, seed=seed, **common)
    raise ValueError(f"未知拓扑类型 {kind!r}，可选 {TOPOLOGY_KINDS}")


__all__ = [
    "DEFAULT_MARGIN_RATIO",
    "GRID",
    "LORA_DEPLOYMENT",
    "LORA_MAX_RADIUS_RATIO",
    "LORA_NODES_PER_LOBE",
    "RANDOM",
    "TOPOLOGY_KINDS",
    "Topology",
    "generate",
    "grid_topology",
    "lora_deployment_topology",
    "random_topology",
]
