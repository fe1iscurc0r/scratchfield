"""节点空间分簇：RSSI 可达图上的「阈值 + 跳数」聚类 + 簇健康度 + 不稳定链路。

⚠️ 与 ``mcpserver/rf_brain/rlnc/clustering.py`` 的区别（**不可混用、不可互相替代**）
-----------------------------------------------------------------------------
- **本模块**：按**空间可达性**给**节点**分组 —— 谁的信号能覆盖谁、经几跳可达。
  输入是几何位置 + 射频参数，输出是「簇（哪些节点一组）」。**不涉及编码**。
- ``rf_brain/rlnc/clustering.py``：按**链路可靠度**（EWMA 丢包估计）给**链路**分
  ``high/mid/low`` 三档，并映射编码冗余率。输入是历史收包样本，输出是「冗余率」。

两者是**不同层**，可以串联（本模块定簇 → 簇内用 rf_brain 定冗余），但命名与语义
必须区分：本模块的 ``Cluster`` 是**节点集合**，那个模块的 ``ReliabilityClusterer``
是**链路分档器**。

分簇算法（确定性，无随机）
--------------------------
1. 只在**活节点**之间建可达边（``RSSI ≥ 阈值``）。
2. 按「活邻居度降序、id 升序」排候选簇头（确定性 tie-break）。
3. 每个候选簇头对**尚未认领**的节点做 ``max_hops`` 内 BFS，收编为成员。
4. 被跳过（邻居已全被认领）的节点各自成簇 ⇒ **保证每个活节点都落在某个簇里**。

簇健康度口径
------------
``health = 活成员占比 × 连通度``，其中 ``连通度 = 1/mean_hops``（``mean_hops ≤ 1`` 时取 1）。
**簇头失效 ⇒ health = 0**（簇失去中继，需重选簇头）—— 这是刻意做的保守口径，
不是「活成员占比」那么简单，README 与测试都按此断言。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .node import DEFAULT_FREQ_HZ, DEFAULT_PATH_LOSS_EXPONENT, Node

DEFAULT_MAX_HOPS = 2
# 距阈值不足该裕量即视为「勉强连通」——链路抖动/遮挡就会断
DEFAULT_UNSTABLE_MARGIN_DB = 6.0


@dataclass
class Link:
    """一条可达链路（``a → b`` 与 ``b → a`` 视为同一条，``a < b``）。"""

    a: int
    b: int
    rssi_dbm: float

    def as_dict(self, threshold_dbm: float) -> dict:
        return {
            "a": self.a,
            "b": self.b,
            "rssi_dbm": round(self.rssi_dbm, 3),
            "margin_db": round(self.rssi_dbm - threshold_dbm, 3),
        }


@dataclass(frozen=True)
class Cluster:
    """一个节点簇（成员为节点 id 的升序元组；``hops`` 为成员到簇头的跳数）。"""

    cluster_id: int
    head_id: int
    members: tuple[int, ...]
    hops: dict[int, int] = field(default_factory=dict)
    alive_ids: frozenset[int] = frozenset()
    max_hops: int = DEFAULT_MAX_HOPS

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def alive_members(self) -> tuple[int, ...]:
        return tuple(m for m in self.members if m in self.alive_ids)

    @property
    def head_alive(self) -> bool:
        return self.head_id in self.alive_ids

    def mean_hops(self, alive_ids: frozenset[int] | None = None) -> float:
        """活成员到簇头的平均跳数（无活成员时为 0）。``alive_ids`` 缺省用建簇快照。"""
        live = self.alive_ids if alive_ids is None else alive_ids
        alive_hops = [self.hops[m] for m in self.members if m in live]
        if not alive_hops:
            return 0.0
        return sum(alive_hops) / len(alive_hops)

    def health(self, alive_ids: frozenset[int] | None = None) -> float:
        """簇健康度 = 活成员占比 × 连通度；簇头失效直接 0。

        ``alive_ids`` 缺省用**建簇时的快照**（``build_clusters`` 只会拿活节点建簇，
        所以快照下簇头必然活着）。传入更新的存活性集合即可评估**快照之后**的退化 ——
        例如先分簇、再让节点失活的时间步进实验。
        """
        live = self.alive_ids if alive_ids is None else alive_ids
        if not self.members or self.head_id not in live:
            return 0.0
        alive_ratio = sum(1 for m in self.members if m in live) / len(self.members)
        mean = self.mean_hops(live)
        connectivity = 1.0 if mean <= 1.0 else 1.0 / mean
        return round(alive_ratio * connectivity, 6)

    def as_dict(self) -> dict:
        """工单 §2 任务一.3 要求的形态（``id`` / ``members`` / ``health``）+ 审计用扩展字段。"""
        return {
            "id": self.cluster_id,
            "members": list(self.members),
            "health": self.health(),
            "head": self.head_id,
            "head_alive": self.head_alive,
            "size": self.size,
            "alive_members": list(self.alive_members),
            "mean_hops": round(self.mean_hops(), 3),
            "hops": dict(sorted(self.hops.items())),
        }


def rssi_links(
    nodes: list[Node],
    *,
    threshold_dbm: float,
    freq_hz: float = DEFAULT_FREQ_HZ,
    exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
) -> list[Link]:
    """活节点两两建边：``RSSI ≥ threshold_dbm`` 即连通。返回按 ``(a, b)`` 升序。"""
    alive = [n for n in nodes if n.alive]
    links: list[Link] = []
    for i, na in enumerate(alive):
        for nb in alive[i + 1:]:
            rssi = na.rssi_to(nb, freq_hz=freq_hz, exponent=exponent)
            if rssi >= threshold_dbm:
                a, b = sorted((na.node_id, nb.node_id))
                links.append(Link(a, b, rssi))
    links.sort(key=lambda lk: (lk.a, lk.b))
    return links


def adjacency(links: list[Link]) -> dict[int, set[int]]:
    """由链路表构造无向邻接表（两端都登记）。"""
    adj: dict[int, set[int]] = {}
    for link in links:
        adj.setdefault(link.a, set()).add(link.b)
        adj.setdefault(link.b, set()).add(link.a)
    return adj


def bfs_hops(
    adj: dict[int, set[int]],
    source: int,
    *,
    max_hops: int | None = None,
    allowed: set[int] | None = None,
) -> dict[int, int]:
    """从 ``source`` 出发的 BFS 跳数表（``source`` 自身为 0）。

    - ``max_hops``    : 只返回跳数 ≤ 该值的节点（``None`` 表示不限）。
    - ``allowed``     : 只允许经过/收编这些节点（``None`` 表示不限）。
    """
    hops: dict[int, int] = {source: 0}
    queue: deque[int] = deque([source])
    while queue:
        cur = queue.popleft()
        nxt_hop = hops[cur] + 1
        if max_hops is not None and nxt_hop > max_hops:
            continue
        for nb in sorted(adj.get(cur, ())):
            if nb in hops:
                continue
            if allowed is not None and nb not in allowed:
                continue
            hops[nb] = nxt_hop
            queue.append(nb)
    return hops


def unstable_pairs(
    nodes: list[Node],
    *,
    threshold_dbm: float,
    margin_db: float = DEFAULT_UNSTABLE_MARGIN_DB,
    freq_hz: float = DEFAULT_FREQ_HZ,
    exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
) -> list[dict]:
    """「勉强连通」的链路：``threshold ≤ RSSI < threshold + margin`` —— 抖动即断。"""
    if margin_db < 0.0:
        raise ValueError("margin_db 不能为负")
    return [
        link.as_dict(threshold_dbm)
        for link in rssi_links(
            nodes, threshold_dbm=threshold_dbm, freq_hz=freq_hz, exponent=exponent
        )
        if link.rssi_dbm < threshold_dbm + margin_db
    ]


def build_clusters(
    nodes: list[Node],
    *,
    threshold_dbm: float,
    max_hops: int = DEFAULT_MAX_HOPS,
    freq_hz: float = DEFAULT_FREQ_HZ,
    exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
) -> list[Cluster]:
    """阈值 + 跳数分簇（确定性）。返回按簇头出现顺序排列的簇列表。"""
    if max_hops < 0:
        raise ValueError("max_hops 不能为负")
    alive = [n for n in nodes if n.alive]
    if not alive:
        return []
    adj = adjacency(
        rssi_links(nodes, threshold_dbm=threshold_dbm, freq_hz=freq_hz, exponent=exponent)
    )
    alive_ids = frozenset(n.node_id for n in alive)
    # 候选簇头：活邻居度降序，id 升序（确定性 tie-break）
    order = sorted(alive_ids, key=lambda nid: (-len(adj.get(nid, ())), nid))

    assigned: set[int] = set()
    clusters: list[Cluster] = []
    for head in order:
        if head in assigned:
            continue
        allowed = (alive_ids - assigned) | {head}
        hops = bfs_hops(adj, head, max_hops=max_hops, allowed=allowed)
        members = tuple(sorted(hops))
        assigned.update(members)
        clusters.append(
            Cluster(
                cluster_id=len(clusters),
                head_id=head,
                members=members,
                hops=dict(hops),
                alive_ids=alive_ids,
                max_hops=max_hops,
            )
        )
    return clusters


def cluster_report(
    nodes: list[Node],
    *,
    threshold_dbm: float,
    max_hops: int = DEFAULT_MAX_HOPS,
    margin_db: float = DEFAULT_UNSTABLE_MARGIN_DB,
    freq_hz: float = DEFAULT_FREQ_HZ,
    exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
) -> dict:
    """工单 §2 任务一.3 要求的输出：``{clusters: [...], unstable_pairs: [...]}``（+ ``stats``）。"""
    alive = [n for n in nodes if n.alive]
    clusters = build_clusters(
        nodes,
        threshold_dbm=threshold_dbm,
        max_hops=max_hops,
        freq_hz=freq_hz,
        exponent=exponent,
    )
    pairs = unstable_pairs(
        nodes,
        threshold_dbm=threshold_dbm,
        margin_db=margin_db,
        freq_hz=freq_hz,
        exponent=exponent,
    )
    sizes = [c.size for c in clusters]
    healths = [c.health() for c in clusters]
    covered = {m for c in clusters for m in c.members}
    return {
        "clusters": [c.as_dict() for c in clusters],
        "unstable_pairs": pairs,
        "stats": {
            "nodes": len(nodes),
            "alive": len(alive),
            "cluster_count": len(clusters),
            "largest_cluster": max(sizes) if sizes else 0,
            "mean_cluster_size": round(sum(sizes) / len(sizes), 3) if sizes else 0.0,
            "mean_health": round(sum(healths) / len(healths), 6) if healths else 0.0,
            "unstable_pair_count": len(pairs),
            # 覆盖性：活节点若不在任何簇里即为漏网（算法上不应发生，留作自检）
            "uncovered_alive": sorted(n.node_id for n in alive if n.node_id not in covered),
            "threshold_dbm": threshold_dbm,
            "max_hops": max_hops,
        },
    }


__all__ = [
    "DEFAULT_MAX_HOPS",
    "DEFAULT_UNSTABLE_MARGIN_DB",
    "Cluster",
    "Link",
    "adjacency",
    "bfs_hops",
    "build_clusters",
    "cluster_report",
    "rssi_links",
    "unstable_pairs",
]
