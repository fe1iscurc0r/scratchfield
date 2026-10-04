"""邻居可靠度表：收包/丢包更新 EWMA，聚类档位与冗余率对上层暴露。

MeshNode 集成入口：收包成功 → report_success(last_hop)，定向帧丢包 → report_loss(next_hop)；
上层通过 get_peer_class / get_redundancy_factor 查询聚类结果驱动编码冗余。
"""
from __future__ import annotations

from .clustering import ReliabilityClusterer
from .reliability import EWMAReliability


class PeerState:
    """一组邻居链路的 EWMA 可靠度 + 动态聚类结果。"""

    def __init__(self, alpha: float = 0.3,
                 clusterer: ReliabilityClusterer | None = None) -> None:
        self.alpha = alpha
        self.clusterer = clusterer or ReliabilityClusterer()
        self._peers: dict[str, EWMAReliability] = {}

    def report_success(self, peer: str) -> float:
        """收包成功上报 → 返回该邻居新可靠度。"""
        return self._get(peer).on_success()

    def report_loss(self, peer: str) -> float:
        """丢包上报 → 返回该邻居新可靠度。"""
        return self._get(peer).on_loss()

    def report(self, peer: str, success: bool) -> float:
        """通用上报入口。"""
        return self._get(peer).on_success() if success else self._get(peer).on_loss()

    def get_reliability(self, peer: str) -> float:
        """查询邻居可靠度；未见过的邻居回退默认 1.0（假设初始可靠）。"""
        return self._peers[peer].reliability if peer in self._peers else 1.0

    def get_peer_class(self, peer: str) -> str:
        """聚类结果暴露：邻居链路可靠度档位（high/mid/low）。"""
        return self.clusterer.classify(self.get_reliability(peer))

    def get_redundancy_factor(self, peer: str) -> float:
        """聚类结果暴露：邻居链路对应的编码冗余率。"""
        return self.clusterer.redundancy_for(self.get_peer_class(peer))

    def query(self, peer: str) -> dict:
        """查询单邻居全量信息：可靠度/丢包率/样本数/档位/冗余率。"""
        e = self._peers.get(peer)
        rel = e.reliability if e else 1.0
        cls = self.clusterer.classify(rel)
        return {
            "peer": peer,
            "reliability": rel,
            "loss_rate": 1.0 - rel,
            "samples": e.samples if e else 0,
            "lost_count": e.lost_count if e else 0,
            "class": cls,
            "redundancy_factor": self.clusterer.redundancy_for(cls),
        }

    def cluster_all(self) -> dict[str, str]:
        """全邻居重分组：{peer: class}。"""
        return self.clusterer.cluster({p: e.reliability for p, e in self._peers.items()})

    def peers(self) -> list[str]:
        return list(self._peers)

    def __len__(self) -> int:
        return len(self._peers)

    def _get(self, peer: str) -> EWMAReliability:
        if peer not in self._peers:
            self._peers[peer] = EWMAReliability(alpha=self.alpha)
        return self._peers[peer]


__all__ = ["PeerState"]
