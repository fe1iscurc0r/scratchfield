"""rf_brain · 分布式频谱仲裁 自测（pytest）。

运行：python -m pytest mcpserver/rf_brain/test_spectrum_arbitration.py -q
覆盖：
  - 权重衰减：半衰期处权重减半，过时声明自动降权；
  - 仲裁：新近 × 来源可信度裁决，高可信但过时的声明输给新鲜声明；
  - 空声明 / 单声明边界；
  - 端到端模拟：多节点带滞后/噪声/可信度差异的声明冲突，仲裁结果与
    最新真实状态一致率 ≥ 0.9（验收指标）。
"""
from __future__ import annotations

import numpy as np

from mcpserver.rf_brain.spectrum_arbitration import (
    Claim,
    arbitrate,
    consistency,
    weight,
)


def test_weight_half_life():
    c = Claim(node="n1", freq=433.0e6, state=1, t=0.0, trust=1.0)
    assert weight(c, now=0.0, half_life=30.0) == 1.0     # 新鲜：权重=trust
    assert abs(weight(c, now=30.0, half_life=30.0) - 0.5) < 1e-9  # 一个半衰期减半
    assert abs(weight(c, now=60.0, half_life=30.0) - 0.25) < 1e-9  # 两个半衰期 1/4


def test_stale_loses_to_fresh():
    # 高可信（0.98）但过时 60s 的声明 vs 低可信（0.6）但新鲜 1s 的声明
    freq = 433.0e6
    now = 1000.0
    stale = Claim(node="trusted_old", freq=freq, state=0, t=now - 60, trust=0.98)
    fresh = Claim(node="new", freq=freq, state=1, t=now - 1, trust=0.6)
    r = arbitrate([stale, fresh], freq, now, half_life=30.0)
    assert r.winner == 1                      # 新鲜声明胜出
    # 过时声明权重已被衰减到低于新鲜声明
    assert weight(stale, now, 30.0) < weight(fresh, now, 30.0)


def test_consensus_stacking():
    # 多个新近节点同状态共识增强，压倒单个高可信过时声明
    freq = 433.0e6
    now = 500.0
    claims = [
        Claim("a", freq, 1, now - 2, 0.7),
        Claim("b", freq, 1, now - 3, 0.7),
        Claim("c", freq, 1, now - 4, 0.7),
        Claim("z", freq, 0, now - 90, 0.99),  # 单个高可信但极过时
    ]
    r = arbitrate(claims, freq, now, half_life=30.0)
    assert r.winner == 1
    assert r.confidence > 0.5


def test_decay_changes_verdict():
    """对照：衰减开/关决定「过时高可信」是否压过「新近低可信」。

    证明过时降权（staleness decay）是真正起作用的机制，而非装饰：
      - 有衰减：新近低可信(0.5, 1s) 的正确声明胜出；
      - 无衰减：过时高可信(0.95, 60s) 的错误声明压倒新近声明 → 错误裁决。
    """
    freq = 433.0e6
    now = 1000.0
    correct = Claim("fresh_low", freq, 1, now - 1, 0.5)     # 新近、正确、低可信
    wrong = Claim("stale_high", freq, 0, now - 60, 0.95)    # 过时、错误、高可信

    r_on = arbitrate([correct, wrong], freq, now, half_life=30.0)
    assert r_on.winner == 1          # 有衰减：新近声明胜出 → 正确

    r_off = arbitrate([correct, wrong], freq, now, half_life=float("inf"))
    assert r_off.winner == 0         # 无衰减：高可信过时声明压倒 → 错误


def test_empty_and_single():
    freq = 433.0e6
    r = arbitrate([], freq, 100.0)
    assert r.winner is None and r.confidence == 0.0

    one = Claim("a", freq, 1, 99.0, 0.8)
    r = arbitrate([one], freq, 100.0)
    assert r.winner == 1 and r.confidence == 1.0


def test_simulation_consistency():
    """端到端：节点声明冲突 → 仲裁与最新真实状态一致率 ≥ 0.9。"""
    rng = np.random.default_rng(20260831)
    n_freqs = 20
    n_queries = 200
    half_life = 30.0
    freqs = 433.0e6 + np.arange(n_freqs) * 25e3

    # 节点配置：trust / lag(秒) / 独立状态误报率
    # 最后一个节点「高可信但长期滞后」——无衰减时会压倒全场，有衰减应被正确降权。
    node_trust = np.array([0.95, 0.90, 0.85, 0.75, 0.65, 0.98])
    node_lag = np.array([1.0, 2.0, 4.0, 12.0, 25.0, 60.0])
    node_err = np.array([0.0, 0.0, 0.02, 0.05, 0.08, 0.0])

    # 每频点真实状态：初始态 + 翻转时间序列（分段常数，翻转间隔 20~80s）
    init_state = rng.integers(0, 2, size=n_freqs)
    flips = []
    for _ in range(n_freqs):
        t = 0.0
        ts = []
        while t < 4000.0:
            t += rng.uniform(20.0, 80.0)
            ts.append(t)
        flips.append(np.asarray(ts))

    def truth(fi: int, t: float) -> int:
        s = int(init_state[fi])
        for ft in flips[fi]:
            if t >= ft:
                s = 1 - s
            else:
                break
        return s

    decisions = []
    ground = []
    query_times = rng.uniform(500.0, 3500.0, size=n_queries)
    for now in query_times:
        for fi in range(n_freqs):
            freq = float(freqs[fi])
            claims = []
            for n in range(len(node_trust)):
                obs_t = now - node_lag[n]
                if obs_t < 0:
                    continue
                st = truth(fi, obs_t)
                if node_err[n] > 0 and rng.random() < node_err[n]:
                    st = 1 - st
                claims.append(Claim(node=f"n{n}", freq=freq, state=st,
                                    t=float(obs_t), trust=float(node_trust[n])))
            decisions.append(arbitrate(claims, freq, now, half_life))
            ground.append(truth(fi, now))  # 与 decisions 逐条对齐的真实状态

    rate = consistency(decisions, ground)
    # 验收：≥ 0.9
    assert rate >= 0.9, f"consistency too low: {rate:.3f}"
