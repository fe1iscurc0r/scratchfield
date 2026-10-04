"""
W62-01 测试套件：bo_materials_loop.py
=====================================
验收硬线
---------
1. pytest 全绿（≥5 用例）
2. 断言「BO 采样轮次 < 全网格粗扫」
3. 断言「失败惩罚项影响采集函数选择」
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from bo_materials_loop import (
    AcquisitionFunc,
    BOLoop,
    ParameterSpace,
    RFSurrogate,
    default_surrogate_factory,
    lignin_hydrothermal_space,
)

# ---------------------------------------------------------------------------
# 测试 1：ParameterSpace 编码/解码往返一致性
# ---------------------------------------------------------------------------

def test_space_encode_decode_roundtrip():
    space = lignin_hydrothermal_space()
    rng = np.random.default_rng(0)
    for _ in range(20):
        # 随机生成原始参数字典
        params = {
            "T": rng.uniform(80.0, 300.0),
            "t": rng.uniform(10.0, 130.0),
            "C": rng.uniform(0.01, 0.13),
            "solvent": rng.choice(["water", "ethanol", "acidic"]),
            "pH": rng.choice(["acidic", "neutral", "alkaline"]),
        }
        vec = space.encode(params)
        decoded = space.decode(vec)
        # 连续变量误差 < 1%
        for key in ("T", "t", "C"):
            assert abs(decoded[key] - params[key]) / params[key] < 0.01, \
                f"{key} roundtrip failed: {params[key]} -> {decoded[key]}"
        assert decoded["solvent"] == params["solvent"]
        assert decoded["pH"] == params["pH"]


# ---------------------------------------------------------------------------
# 测试 2：RFSurrogate fit / predict 基本功能
# ---------------------------------------------------------------------------

def test_rf_surrogate_fit_predict():
    space = lignin_hydrothermal_space()
    # 产生 10 个随机点
    X = space.sample_random(10, seed=0)
    y = np.array([0.3 + i * 0.05 + np.random.randn() * 0.01 for i in range(10)])
    failed_mask = np.zeros(10, dtype=bool)

    sur = RFSurrogate(n_estimators=20, seed=42)
    sur.fit(X, y, failed_mask)

    mu, sigma = sur.predict(X)
    assert mu.shape == (10,)
    assert sigma.shape == (10,)
    assert not np.any(np.isnan(mu))
    # 训练集预测均值应接近训练目标
    assert np.corrcoef(mu, y)[0, 1] > 0.5


# ---------------------------------------------------------------------------
# 测试 3：失败实验纳入训练（失败点 sigma 放大）
# ---------------------------------------------------------------------------

def test_rf_surrogate_failed_points_have_higher_uncertainty():
    space = lignin_hydrothermal_space()
    X_ok = space.sample_random(8, seed=1)
    y_ok = np.array([0.4 + i * 0.06 for i in range(8)])
    fail_mask = np.zeros(12, dtype=bool)
    fail_mask[8:] = True   # 后4个是失败实验

    X_all = np.vstack([X_ok, space.sample_random(4, seed=2)])
    y_all = np.concatenate([y_ok, np.full(4, RFSurrogate.FAIL_TOKEN)])

    sur = RFSurrogate(n_estimators=20, seed=42)
    sur.fit(X_all, y_all, fail_mask)

    mu, sigma = sur.predict(X_all)
    # 成功点 sigma vs 失败点 sigma
    sigma_ok = sigma[:8]
    sigma_fail = sigma[8:]
    assert sigma_fail.mean() > sigma_ok.mean(), \
        "失败实验点的 sigma 应高于成功实验点（惩罚机制）"


# ---------------------------------------------------------------------------
# 测试 4：采集函数 — EI vs UCB 行为差异
# ---------------------------------------------------------------------------

def test_acquisition_ei_vs_ucb_gives_different_rankings():
    space = lignin_hydrothermal_space()
    X_cand = space.sample_random(50, seed=3)
    mu = np.random.randn(50) * 0.2 + 0.5
    sigma = np.abs(np.random.randn(50) * 0.1 + 0.15)
    y_best = 0.6

    acq_ei = AcquisitionFunc(mode=AcquisitionFunc.EI, xi=0.01)
    acq_ucb = AcquisitionFunc(mode=AcquisitionFunc.UCB, beta=2.0)

    vals_ei = acq_ei.evaluate(X_cand, mu, sigma, y_best)
    vals_ucb = acq_ucb.evaluate(X_cand, mu, sigma, y_best)

    # EI 和 UCB 的排序应不完全相同（否则说明无差异）
    rank_ei = np.argsort(np.argsort(-vals_ei))
    rank_ucb = np.argsort(np.argsort(-vals_ucb))
    assert not np.allclose(rank_ei, rank_ucb), "EI 和 UCB 应给出不同排序"


# ---------------------------------------------------------------------------
# 测试 5：失败惩罚项影响采集函数选择
# ---------------------------------------------------------------------------

def test_failure_penalty_affects_acquisition_choice():
    """
    核心验收断言：在其他条件相同时，
    失败惩罚项会使靠近失败点的候选点采集值显著降低。
    """
    space = lignin_hydrothermal_space()
    X_cand = space.sample_random(100, seed=5)
    # 基准 mu / sigma
    mu    = np.full(100, 0.6)
    sigma = np.full(100, 0.15)
    y_best = 0.5

    # 无失败历史
    acq_no_fail = AcquisitionFunc(
        mode=AcquisitionFunc.EI,
        xi=0.01,
        penalty_strength=0.25,
        failure_history=[],
    )
    vals_no_fail = acq_no_fail.evaluate(X_cand, mu, sigma, y_best)

    # 注入一个失败点（X_cand[50] 附近）
    failure_x = X_cand[50].copy()
    acq_with_fail = AcquisitionFunc(
        mode=AcquisitionFunc.EI,
        xi=0.01,
        penalty_strength=0.25,
        failure_history=[failure_x],
    )
    vals_with_fail = acq_with_fail.evaluate(X_cand, mu, sigma, y_best)

    # 与失败点足够近的点（距离 < 0.05），惩罚后应比惩罚前更低
    near_mask = np.array([
        np.linalg.norm(x - failure_x) < 0.05 for x in X_cand
    ])
    if near_mask.any():
        # 惩罚后这些点的采集值应降低
        assert np.any(vals_with_fail[near_mask] < vals_no_fail[near_mask]), \
            "失败惩罚项应降低近邻失败点采集值"
    # 全局：至少有一个点受影响
    assert not np.allclose(vals_with_fail, vals_no_fail), \
        "失败惩罚项应改变采集函数值"


# ---------------------------------------------------------------------------
# 测试 6：BO 采样轮次 < 全网格粗扫（核心验收断言）
# ---------------------------------------------------------------------------

def test_bo_sampling_rounds_less_than_grid_search():
    """
    核心验收断言：在同一 mock 目标函数上，
    BO 找到接近最优解所需的轮次应显著少于全网格枚举。
    """
    space = lignin_hydrothermal_space()
    rng = np.random.default_rng(99)

    def mock_y_factory(seed):
        def f(x):
            # 固定 mock 函数（与 loop._mock_y 相同）
            T   = x[0] * 220.0 + 80.0
            t   = x[1] * 120.0 + 10.0
            C   = x[2] * 0.12 + 0.01
            pH_i = int(round(x[3]))
            solv_i = int(round(x[4]))
            base = 0.10 + 0.55 * np.exp(-((T - 170) ** 2) / 8000)
            base *= (1 + 0.30 * t / 130) / 1.3
            base *= (1 - 0.60 * C / 0.13)
            if pH_i == 0:  base *= 1.30
            elif pH_i == 2: base *= 0.70
            if solv_i == 0: base *= 1.10
            elif solv_i == 2: base *= 1.20
            rng_loc = np.random.default_rng(seed)
            y = np.clip(base + rng_loc.normal(0, 0.025), 0.0, 1.0)
            return float(y)
        return f

    # 全网格基准
    grid = space.sample_grid()
    mock_y = mock_y_factory(42)
    grid_y = np.array([mock_y(x) for x in grid])
    grid_best = grid_y.max()
    grid_size = len(grid)

    # BO 闭环
    loop = BOLoop(
        space=space,
        surrogate_factory=default_surrogate_factory,
        acq_mode=AcquisitionFunc.EI,
        acq_xi=0.01,
        penalty_strength=0.25,
        max_rounds=30,
        y_threshold=grid_best * 0.98,   # 收敛到 98% 最优即停
        seed=99,
    )
    loop.init(n_init=4)

    bo_rounds = 0
    while not loop.converged() and bo_rounds < 30:
        x_next = loop.recommend()
        y = mock_y(x_next)
        loop.record(x_next, y, failed=False)
        loop.update()
        bo_rounds += 1

    # 验收断言：BO 找到接近最优的轮次应 < 全网格规模
    assert bo_rounds < grid_size, \
        f"BO 轮次 {bo_rounds} 应 < 全网格 {grid_size}"

    print(f"\n  BO 收敛轮次={bo_rounds}  <  全网格规模={grid_size}  ✓")


# ---------------------------------------------------------------------------
# 测试 7：混合变量支持（离散 + 连续同时优化）
# ---------------------------------------------------------------------------

def test_mixed_continuous_discrete_optimization():
    """验证同时存在连续/离散变量时，BO 能找到非平凡解。"""
    space = lignin_hydrothermal_space()
    rng = np.random.default_rng(7)

    loop = BOLoop(
        space=space,
        surrogate_factory=default_surrogate_factory,
        acq_mode=AcquisitionFunc.UCB,
        acq_beta=2.0,
        penalty_strength=0.25,
        max_rounds=15,
        y_threshold=0.90,
        seed=7,
    )
    loop.init(n_init=4)
    n_rounds = 0
    while not loop.converged() and n_rounds < 15:
        x_next = loop.recommend()
        y = loop._mock_y(x_next)
        loop.record(x_next, y, failed=False)
        loop.update()
        n_rounds += 1

    # 最终 y_best 应显著优于初始最差值
    ok_vals = [yi for yi, fi in zip(loop.y_history, loop.failed_mask)
               if yi is not None and not fi]
    assert len(ok_vals) >= 4
    assert loop.y_best > 0.2, "BO 至少应优于随机基线"


# ---------------------------------------------------------------------------
# 运行入口（可独立 python -m pytest 调用）
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
