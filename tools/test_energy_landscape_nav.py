"""energy_landscape_nav 测试（M23 验收：定位 ≥3 亚稳态 + 效率较随机 ≥2×）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from energy_landscape_nav import (
    LOCATE_RADIUS,
    EnergyLandscape,
    GaussianWell,
    demo_landscape,
    frustration_map,
    local_minimize,
    random_baseline_steps,
    sf_cluster_navigate,
)


def test_locates_at_least_three_metastable_states():
    states, _ = sf_cluster_navigate(demo_landscape())
    assert len(states) >= 3


def test_efficiency_at_least_2x_over_random():
    nav_states, nav_evals = sf_cluster_navigate(demo_landscape(), seed=0)
    random_evals = random_baseline_steps(demo_landscape(), target=len(nav_states), seed=0)
    assert nav_evals * 2 <= random_evals, (
        f"效率不足：导航 {nav_evals} 次 vs 随机 {random_evals} 次（要求 ≥2×）"
    )


def test_local_minimize_converges_to_well():
    L = demo_landscape()
    ms = local_minimize(L, -1.8, -1.8)
    mx, my = L.true_minima[L.nearest_minimum(ms.x, ms.y)]
    assert (ms.x - mx) ** 2 + (ms.y - my) ** 2 <= LOCATE_RADIUS ** 2


def test_potential_is_lowest_at_deepest_well():
    L = demo_landscape()
    vals = {i: L.potential(*L.true_minima[i]) for i in range(len(L.wells))}
    gi = min(vals, key=vals.get)
    assert gi == 0  # 阱 0（depth 1.2）在斜坡下仍为全局最小


def test_frustration_map_basin_bottom_near_zero():
    m = frustration_map(demo_landscape(), grid_n=41)
    V, frust = m["V"], m["frustration"]
    gn = m["grid"][0]
    # 全局最低势能点应是某盆地底部，挫折度接近 0
    best = min(range(gn * gn), key=lambda k: V[k // gn][k % gn])
    bi, bj = best // gn, best % gn
    assert frust[bi][bj] < 0.1


def test_frustration_map_highlights_barrier_region():
    m = frustration_map(demo_landscape(), grid_n=41)
    V, frust = m["V"], m["frustration"]
    gn = m["grid"][0]
    # 中心 (0,0) 是四阱之间的壁垒区（grid 中心 index = 20）
    c = gn // 2
    center_frust = frust[c][c]
    # 盆地底部（V 最小点）的挫折
    best = min(range(gn * gn), key=lambda k: V[k // gn][k % gn])
    bi, bj = best // gn, best % gn
    assert center_frust > 0.8, f"中心壁垒挫折应显著（实得 {center_frust:.3f}）"
    assert center_frust > frust[bi][bj]
