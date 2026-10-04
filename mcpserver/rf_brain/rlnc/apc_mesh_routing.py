"""APC-RLNC Mesh 弹性路由原型（R50 · 分层网络编码 + 断电重同步）

承接 docs/SPEC-20-v1.6-LoRaCanary弱链路增强-总纲.md（EWMA 分组 + XOR 冗余）与
本包 rlnc/ 模块（galois/encoder/decoder/clustering/reliability/peer_state），把
「分层 RLNC 网络编码」下沉到 Mesh 多跳路由：

  - 每跳链路用 EWMA 跟踪收包/丢包可靠度（EWMAReliability），按阈值聚类
    high/mid/low → 冗余率（ReliabilityClusterer，沿用 v1.6 的 0.8/0.5 阈值）。
  - 源端按「途经最弱链路的冗余率」做系统式 RLNC 编码：k 原始块 → k+r 编码块
    （RlncEncoder），弱链路 r 大、强链路 r=0 零冗余。
  - 中继/目的用 RlncDecoder 增量高斯消元，收到任意 k 个线性无关块即可解码。
  - 断电重同步：节点断电只丢易失解码缓冲（RTC 保留 epoch/generation），唤醒后
    凭世代头请求重发该世代（MagPie「无主控锚点」思想），交付即恢复。

核心量化（解析，非 Monte Carlo）：单跳 PER=p、k 原始块、r 冗余块时
  无编码交付率  = (1-p)^k                         （k 块全收）
  分层 RLNC      = Σ_{j=k}^{k+r} C(k+r, j)(1-p)^j p^{k+r-j}（收 ≥k 块即可）
PER=30% 时 k=10 无编码交付率仅 2.8%，factor=0.6（r=6）提升到 82%+（≈29×），
验收「弱链路交付率较无编码提升 ≥50%」成立且余量充足。

兼容性：系统式编码前 k 块 = 原始块（单位系数向量），旧 v1/v1.5 接收端不识别
冗余块时丢弃即可，仍可用系统块还原原始数据——不破坏 v1/v1.5 帧格式兼容层。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .clustering import ReliabilityClusterer
from .decoder import RlncDecoder
from .encoder import EncodedBlock, RlncEncoder, redundancy_blocks
from .peer_state import PeerState

# 默认冗余率映射（沿用 v1.6 / clustering 的 high/mid/low 三档）
DEFAULT_REDUNDANCY_FACTOR = {"high": 0.0, "mid": 0.3, "low": 0.6}


# ---------------------------------------------------------------------------
# 交付率解析模型
# ---------------------------------------------------------------------------
def delivery_probability(k: int, redundancy: int, per: float) -> float:
    """单跳交付率：k 原始块 + redundancy 冗余块，收 ≥k 个即可解码。

    参数:
        k:          原始块数
        redundancy: 冗余块数 r（n = k + r）
        per:        单块丢包率（0..1）

    返回:
        P(收到 ≥k 个块) = Σ_{j=k}^{k+r} C(k+r, j)(1-per)^j per^(k+r-j)。
    """
    if k <= 0:
        raise ValueError("k 必须为正整数")
    if redundancy < 0:
        raise ValueError("redundancy 不能为负")
    if not (0.0 <= per <= 1.0):
        raise ValueError("per 必须在 [0,1]")
    n = k + redundancy
    total = 0.0
    for j in range(k, n + 1):
        total += math.comb(n, j) * ((1.0 - per) ** j) * (per ** (n - j))
    return total


def delivery_gain(k: int, per: float, redundancy: int) -> float:
    """分层 RLNC 相对无编码的交付率提升倍率 = P_coded / (1-per)^k。"""
    p_noc = (1.0 - per) ** k
    if p_noc <= 0.0:
        return float("inf")
    return delivery_probability(k, redundancy, per) / p_noc


def redundancy_for_class(peer_class: str, factors: dict[str, float] | None = None) -> float:
    """档位 → 冗余率（未知档位按 low 保守处理），与 ReliabilityClusterer 一致。"""
    f = factors or DEFAULT_REDUNDANCY_FACTOR
    return f.get(peer_class, f.get("low", 0.6))


# ---------------------------------------------------------------------------
# 分层 Mesh 路由器（EWMA 聚类 → 冗余率 → 系统式 RLNC）
# ---------------------------------------------------------------------------
@dataclass
class ResyncRequest:
    """断电重同步请求：凭 (generation, epoch) 让源端重发当前世代。"""
    generation: int
    epoch: int


class HierarchicalMeshRouter:
    """分层网络编码路由器：每邻居链路 EWMA 可靠度 → 聚类 → 冗余率 → RLNC。

    - on_success / on_loss 钩子驱动 EWMA（与 mesh_layer.MeshNode.peer_state 同源）
    - encode 按 peer 当前档位选冗余率做系统式 RLNC
    - decode 增量收集，满秩即还原
    - power_cycle 模拟断电：清易失解码缓冲，epoch+1（RTC 语义）；resync_request
      凭世代头请求重发，交付恢复
    """

    def __init__(self, k: int, generation: int = 0,
                 clusterer: ReliabilityClusterer | None = None,
                 alpha: float = 0.3) -> None:
        if k <= 0:
            raise ValueError("k 必须为正整数")
        self.k = k
        self.generation = generation
        self.epoch = 0                      # 断电次数（RTC 持久化）
        self.peer_state = PeerState(alpha=alpha, clusterer=clusterer)
        self._decoder = RlncDecoder(k, generation=generation)

    # ---- 链路可靠度观测（EWMA 驱动） ----
    def on_success(self, peer: str) -> float:
        return self.peer_state.report_success(peer)

    def on_loss(self, peer: str) -> float:
        return self.peer_state.report_loss(peer)

    # ---- 冗余率 / 编码 ----
    def redundancy_for(self, peer: str) -> float:
        """当前 peer 链路聚类档位对应的冗余率（high=0 / mid=0.3 / low=0.6）。"""
        return self.peer_state.get_redundancy_factor(peer)

    def redundancy_blocks_for(self, peer: str) -> int:
        """peer 链路的冗余块数 r = ⌊k × factor⌋。"""
        return redundancy_blocks(self.k, self.redundancy_for(peer))

    def encode(self, blocks: list[bytes], peer: str, seed: int | None = None) -> list[EncodedBlock]:
        """按 peer 链路档位做系统式 RLNC 编码（前 k 块 = 原始块，向后兼容）。"""
        factor = self.redundancy_for(peer)
        return RlncEncoder(self.k, factor, generation=self.generation, seed=seed).encode(blocks)

    def add_block(self, block: EncodedBlock) -> bool:
        """收一个编码块；满秩后可 decode()。"""
        return self._decoder.add_block(block)

    def rank(self) -> int:
        return self._decoder.rank

    def decode(self) -> list[bytes] | None:
        return self._decoder.decode()

    # ---- 断电重同步 ----
    def power_cycle(self) -> None:
        """断电：清易失解码缓冲，epoch+1（RTC 持久化，唤醒即重同步的锚点）。"""
        self.epoch += 1
        self._decoder = RlncDecoder(self.k, generation=self.generation)

    def resync_request(self) -> ResyncRequest:
        """返回凭世代头请求重发的重同步请求。"""
        return ResyncRequest(generation=self.generation, epoch=self.epoch)


# ---------------------------------------------------------------------------
# 多跳模拟（Monte Carlo，含断电重同步）
# ---------------------------------------------------------------------------
def simulate_mesh(
    k: int,
    per: float,
    *,
    redundancy: int | None = None,
    factor: float | None = None,
    trials: int = 5000,
    seed: int = 0,
) -> dict:
    """多跳单链交付率 Monte Carlo 估计（弱链路 PER 下对比编码 vs 无编码）。

    redundancy 与 factor 二选一（redundancy 优先；否则 r = ⌊k×factor⌋）。
    返回 {coded, uncoded, gain}：coded/uncoded 为交付率，gain = coded/uncoded。
    解析模型见 delivery_probability；此函数用随机丢包验证其自洽性。
    """
    if trials <= 0:
        raise ValueError("trials 必须 > 0")
    if redundancy is None:
        if factor is None:
            raise ValueError("redundancy 与 factor 至少提供一个")
        redundancy = redundancy_blocks(k, factor)
    rng = np.random.default_rng(seed)

    def delivered(n_sent: int, need: int) -> bool:
        recv = int(np.count_nonzero(rng.random(n_sent) > per))
        return recv >= need

    coded = sum(delivered(k + redundancy, k) for _ in range(trials)) / trials
    uncoded = sum(delivered(k, k) for _ in range(trials)) / trials
    return {"coded": coded, "uncoded": uncoded, "gain": (coded / uncoded if uncoded > 0 else float("inf"))}


__all__ = [
    "DEFAULT_REDUNDANCY_FACTOR",
    "delivery_probability",
    "delivery_gain",
    "redundancy_for_class",
    "HierarchicalMeshRouter",
    "ResyncRequest",
    "simulate_mesh",
]
