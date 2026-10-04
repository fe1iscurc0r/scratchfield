"""rf_brain · 分布式频谱仲裁（digest-gx-4c 过期约束授粉）。

授粉源：digest-gx-4c-2026-08-30.md「Agent 继承记忆中过期约束致决策失效」。
同构迁移：多 Agent 记忆中残留的「过期约束」与分布式频谱感知中「过时占用声明」
是同一类问题——旧状态未失效时会被误当现状，导致冲突/错误决策。

设计（无需中心节点）：
  - 每份频谱占用声明带 provenance（时间戳 t + 来源节点 node + 来源可信度 trust）；
  - 过时声明按半衰期指数自动降权（新近性）；
  - 同一频点的多份声明冲突时，按「新近性 × 来源可信度」加权投票裁决；
  - 每个节点本地运行同一套仲裁逻辑，输入自己收到的声明即可得到一致裁决。

可信度 trust 可由 A26 DreamLedger 信用文件滚动更新（确认/超时记账），本模块只
消费 trust，不负责记账。纯计算，无 LLM/网络调用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np


@dataclass
class Claim:
    """一份频谱占用声明（provenance 完备）。"""
    node: str        # 来源节点 id
    freq: float      # 中心频率 Hz
    state: int       # 占用状态：0=空闲，1=占用（可扩展为信道分配 id / 功率档）
    t: float         # 声明时间戳（epoch 秒）
    trust: float     # 来源可信度 0..1


@dataclass
class ArbitrationResult:
    """单频点仲裁结果。"""
    freq: float
    winner: int | None          # 胜出状态；无声明时为 None
    confidence: float              # 胜出权重占比 0..1
    weights: dict = field(default_factory=dict)  # state -> 累计权重（可观测/审计）


def weight(claim: Claim, now: float, half_life: float = 30.0) -> float:
    """声明权重 = 来源可信度 × 新近性衰减（半衰期指数）。

    age=0 时权重=trust；age=half_life 时权重=trust/2；以此类推。
    """
    age = max(0.0, now - claim.t)
    staleness = 0.5 ** (age / half_life) if half_life > 0 else 1.0
    return claim.trust * staleness


def weights_array(claims: Iterable[Claim], now: float,
                  half_life: float = 30.0) -> np.ndarray:
    """向量化计算一组声明的权重（numpy）。"""
    arr = [(c.trust, max(0.0, now - c.t)) for c in claims]
    if not arr:
        return np.empty(0, dtype=float)
    trust, age = np.array([a[0] for a in arr]), np.array([a[1] for a in arr])
    staleness = np.power(0.5, age / half_life) if half_life > 0 else np.ones_like(age)
    return trust * staleness


def arbitrate(claims: Iterable[Claim], freq: float, now: float,
              half_life: float = 30.0) -> ArbitrationResult:
    """对同一频点的声明集合做加权投票仲裁。

    胜出状态 = 累计权重最大的状态；conf = 胜出权重 / 总权重。
    多节点同一状态权重叠加（共识增强），新近 + 可信的声明自然压倒过时声明。
    """
    acc: dict[int, float] = {}
    for c in claims:
        if c.freq != freq:
            continue
        acc[c.state] = acc.get(c.state, 0.0) + weight(c, now, half_life)

    if not acc:
        return ArbitrationResult(freq=freq, winner=None, confidence=0.0, weights={})

    winner = max(acc, key=acc.get)
    total = float(sum(acc.values()))
    confidence = acc[winner] / total if total > 0 else 0.0
    return ArbitrationResult(freq=freq, winner=winner, confidence=confidence,
                             weights=dict(acc))


def arbitrate_band(claims: Iterable[Claim], freqs: Iterable[float], now: float,
                   half_life: float = 30.0) -> list[ArbitrationResult]:
    """对整个频段逐频点仲裁（复用 arbitrate 的单频点逻辑）。"""
    return [arbitrate(claims, f, now, half_life) for f in freqs]


def consistency(decisions: Iterable[ArbitrationResult],
                ground_truth: Iterable[int]) -> float:
    """仲裁结果与最新真实状态的一致率（验收指标，0..1）。

    ground_truth 须与 decisions 等长、按顺序对齐（每个仲裁决策对应一个
    「该时刻该频点的真实状态」）。这样同一频点在不同时刻的多次仲裁才能
    各自与对应时刻的真实状态比对。
    """
    n = 0
    hit = 0
    for d, gt in zip(decisions, ground_truth):
        if d.winner is None:
            continue
        n += 1
        if d.winner == gt:
            hit += 1
    return hit / n if n > 0 else 0.0
