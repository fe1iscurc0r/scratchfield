"""SF-Cluster 挫折模式感知的能量景观导航（M23 · 陆墨材料采样）。

依据 docs/paper-round2-2026-08-30/digests/授粉点-统一.md 中 g7-1 授粉点 2：
「SF-Cluster 用局部能量挫折模式引导 MSA 二次采样，突破序列相似性限制」→
把「基于能量地貌特征而非序列相似性」的采样策略迁移到材料合成参数搜索：

- 能量景观：二维势能面（多个高斯阱 = 亚稳态，阱间鞍点/壁垒 = 挫折区域）
- 挫折模式感知采样：抖动网格粗采样（分层覆盖）→ 低能点聚类（识别盆地/亚稳态
  候选）→ 每簇质心廉价下降收敛到亚稳态 → 盆地之间记录能量壁垒（挫折）
- 输出：定位到的亚稳态（局部极小）+ 合成参数搜索建议（按能量/壁垒排序）

验收（SPEC M23）：
  1. 二维势能面案例定位 ≥3 个亚稳态
  2. 搜索效率较随机采样提升：步数降 ≥2×（用同一案例对照 random_baseline_steps）

纯标准库，主机侧参考实现。运行：
  python tools/energy_landscape_nav.py
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# 领域默认边界（合成参数 x/y 的归一化范围）
DEFAULT_BOUNDS = (-3.0, 3.0)

# 「定位到亚稳态」的判定半径：落在真值极小点该半径内即算命中
LOCATE_RADIUS = 0.3


@dataclass
class GaussianWell:
    """单个高斯势阱（对应一个亚稳态）。"""
    x: float
    y: float
    depth: float  # >0，阱越深越稳定
    sigma: float = 0.5

    def energy_at(self, x: float, y: float) -> float:
        r2 = (x - self.x) ** 2 + (y - self.y) ** 2
        return -self.depth * math.exp(-r2 / (2.0 * self.sigma ** 2))


@dataclass
class MetastableState:
    """定位到的亚稳态（局部极小）。"""
    x: float
    y: float
    energy: float
    barrier: float = 0.0  # 通往全局最小方向的最近壁垒高度（挫折程度）


@dataclass
class EnergyLandscape:
    """二维势能面 = 若干高斯阱 + 线性斜坡（打破对称）。"""

    wells: list[GaussianWell]
    ramp: tuple[float, float] = (0.05, 0.03)  # 线性斜坡系数，制造非对称
    bounds: tuple[float, float] = DEFAULT_BOUNDS
    _evals: int = field(default=0, init=False)

    def potential(self, x: float, y: float) -> float:
        self._evals += 1
        v = sum(w.energy_at(x, y) for w in self.wells)
        v += self.ramp[0] * x + self.ramp[1] * y
        return v

    def gradient(self, x: float, y: float, h: float = 1e-4) -> tuple[float, float]:
        """中心差分梯度（数值，2 次势能评估）。"""
        gx = (self.potential(x + h, y) - self.potential(x - h, y)) / (2 * h)
        gy = (self.potential(x, y + h) - self.potential(x, y - h)) / (2 * h)
        return gx, gy

    @property
    def true_minima(self) -> list[tuple[float, float]]:
        """真值亚稳态位置（高斯阱中心近似为局部极小；斜坡扰动可忽略）。"""
        return [(w.x, w.y) for w in self.wells]

    def nearest_minimum(self, x: float, y: float) -> int:
        """返回距 (x,y) 最近的真值极小点下标。"""
        best_i, best_d = -1, math.inf
        for i, (mx, my) in enumerate(self.true_minima):
            d = math.hypot(x - mx, y - my)
            if d < best_d:
                best_i, best_d = i, d
        return best_i


def demo_landscape() -> EnergyLandscape:
    """演示用四阱势能面：4 个亚稳态，深度各异，阱间形成壁垒。"""
    wells = [
        GaussianWell(-2.0, -2.0, depth=1.20),
        GaussianWell(2.0, -2.0, depth=1.00),
        GaussianWell(-2.0, 2.0, depth=0.85),
        GaussianWell(2.0, 2.0, depth=1.05),
    ]
    return EnergyLandscape(wells=wells)


def local_minimize(
    landscape: EnergyLandscape,
    x0: float,
    y0: float,
    lr: float = 0.2,
    tol: float = 0.05,
    max_steps: int = 25,
) -> MetastableState:
    """从初值做中心差分梯度下降，收敛到局部极小（亚稳态）。

    每步 2 次势能评估（中心差分）。lr 取小值避免高斯阱内过冲振荡；tol 取宽松值：
    我们只需要足够接近真值极小（LOCATE_RADIUS 内）即可，不必压到机器精度。
    """
    x, y = x0, y0
    for _ in range(max_steps):
        gx, gy = landscape.gradient(x, y)
        if math.hypot(gx, gy) < tol:
            break
        x -= lr * gx
        y -= lr * gy
    return MetastableState(x=x, y=y, energy=landscape.potential(x, y))


def sf_cluster_navigate(
    landscape: EnergyLandscape,
    grid_n: int = 6,
    jitter: float = 0.2,
    exploit_top: int = 6,
    cluster_radius: float = 0.9,
    seed: int | None = 0,
) -> tuple[list[MetastableState], int]:
    """挫折模式感知采样导航。

    步骤（对应 SF-Cluster 的「低能挫折模式引导二次采样」）：
      1. 粗采样：抖动网格（分层覆盖，保证每个盆地有种子，避免纯随机的盲区）
      2. 低能聚类：取 exploit_top 个最低能点，按 cluster_radius 合并成盆地簇
      3. 每簇质心做廉价下降，收敛到亚稳态并去重
    返回（定位到的亚稳态列表, 已消耗的势能评估次数）。
    """
    rng = random.Random(seed)
    lo, hi = landscape.bounds
    span = hi - lo

    # 1) 抖动网格粗采样：分层覆盖，比纯随机更省评估就能触达每个盆地
    step = span / (grid_n - 1)
    samples: list[tuple[float, float, float]] = []
    for i in range(grid_n):
        for j in range(grid_n):
            x = lo + i * step + rng.uniform(-jitter, jitter) * step
            y = lo + j * step + rng.uniform(-jitter, jitter) * step
            x = min(hi, max(lo, x))
            y = min(hi, max(lo, y))
            samples.append((landscape.potential(x, y), x, y))

    # 2) 低能点聚类（贪心单链：按能量升序取点、合并邻近簇）
    samples.sort()
    clusters: list[list[tuple[float, float]]] = []
    for _, x, y in samples[:exploit_top]:
        placed = False
        for cl in clusters:
            cx = sum(p[0] for p in cl) / len(cl)
            cy = sum(p[1] for p in cl) / len(cl)
            if math.hypot(x - cx, y - cy) <= cluster_radius:
                cl.append((x, y))
                placed = True
                break
        if not placed:
            clusters.append([(x, y)])

    # 3) 每簇质心 → 廉价下降 → 去重
    found: list[MetastableState] = []
    seen: set[int] = set()
    for cl in clusters:
        cx = sum(p[0] for p in cl) / len(cl)
        cy = sum(p[1] for p in cl) / len(cl)
        ms = local_minimize(landscape, cx, cy)
        idx = landscape.nearest_minimum(ms.x, ms.y)
        if idx in seen:
            continue
        if math.hypot(ms.x - landscape.true_minima[idx][0], ms.y - landscape.true_minima[idx][1]) <= LOCATE_RADIUS:
            seen.add(idx)
            ms.barrier = _estimate_barrier(landscape, ms)
            found.append(ms)

    found.sort(key=lambda m: m.energy)
    return found, landscape._evals


def _estimate_barrier(landscape: EnergyLandscape, ms: MetastableState) -> float:
    """估计该亚稳态到全局最小方向的最近壁垒高度（沿连线扫描最高势能 - 本底）。

    启发式：在亚稳态与全局最小（最深阱）之间线性插值扫少量点，取最高势能作为
    通往该方向的壁垒。用于「挫折程度」排序，非精确 MEP（最小能量路径）。
    """
    gi = max(range(len(landscape.wells)), key=lambda i: landscape.wells[i].depth)
    gx, gy = landscape.true_minima[gi]
    peak = -math.inf
    for t in range(1, 9):
        f = t / 9.0
        x = ms.x + (gx - ms.x) * f
        y = ms.y + (gy - ms.y) * f
        peak = max(peak, landscape.potential(x, y))
    return max(0.0, peak - ms.energy)


def random_baseline_steps(
    landscape: EnergyLandscape,
    target: int = 3,
    seed: int | None = 0,
    max_steps: int = 100_000,
) -> int:
    """随机采样基线：均匀撒点，统计「定位到 target 个不同亚稳态」所需步数。

    判定：某采样点落在真值极小点 LOCATE_RADIUS 半径内即命中该亚稳态。
    返回命中 target 个不同亚稳态所需的总势能评估次数。
    """
    rng = random.Random(seed)
    lo, hi = landscape.bounds
    span = hi - lo
    hit: set[int] = set()
    steps = 0
    while steps < max_steps:
        x = lo + span * rng.random()
        y = lo + span * rng.random()
        steps += 1
        landscape.potential(x, y)
        idx = landscape.nearest_minimum(x, y)
        if idx not in hit:
            mx, my = landscape.true_minima[idx]
            if math.hypot(x - mx, y - my) <= LOCATE_RADIUS:
                hit.add(idx)
                if len(hit) >= target:
                    return steps
    return steps


def synthesis_suggestions(states: list[MetastableState]) -> list[str]:
    """把定位到的亚稳态转成合成参数搜索建议。"""
    out = []
    for i, s in enumerate(states, 1):
        if i == 1:
            stab = "全局最小（最稳定）"
        else:
            stab = "稳定" if s.barrier >= 0.5 else "亚稳（壁垒低）"
        out.append(
            f"#{i} 参数(x={s.x:.2f}, y={s.y:.2f}) 能量={s.energy:.3f} "
            f"通往全局最小壁垒≈{s.barrier:.3f} → {stab}，优先围绕该点做细粒度合成扫描"
        )
    return out


def frustration_map(landscape: EnergyLandscape, grid_n: int = 41) -> dict:
    """把「挫折模式」落成可计算的二维图（纯标准库，无 numpy）。

    返回：
      - V: 势能面（grid_n × grid_n）
      - basin: 每个网格点归属的亚稳态下标（最近真值极小点）
      - frustration: 挫折度 = 该点势能 − 归属盆地极小点的势能
          → 盆地底部 ≈ 0（稳定）；盆地之间的鞍点/壁垒区显著 > 0（挫折）
      - minima: 真值极小点列表

    「挫折区域」即 frustration 高的网格带（能量壁垒/竞争梯度区），
    可直接用于指导合成参数搜索：避开壁垒、沿盆地底部细化扫描。
    """
    lo, hi = landscape.bounds
    step = (hi - lo) / (grid_n - 1)
    minima_e = [landscape.potential(mx, my) for mx, my in landscape.true_minima]

    V = [[0.0] * grid_n for _ in range(grid_n)]
    basin = [[0] * grid_n for _ in range(grid_n)]
    frustration = [[0.0] * grid_n for _ in range(grid_n)]

    for i in range(grid_n):
        x = lo + i * step
        for j in range(grid_n):
            y = lo + j * step
            V[i][j] = landscape.potential(x, y)
            b = landscape.nearest_minimum(x, y)
            basin[i][j] = b
            frustration[i][j] = V[i][j] - minima_e[b]

    return {
        "grid": (grid_n, grid_n),
        "bounds": landscape.bounds,
        "V": V,
        "basin": basin,
        "frustration": frustration,
        "minima": landscape.true_minima,
    }


def main() -> int:
    landscape = demo_landscape()

    nav_states, nav_evals = sf_cluster_navigate(landscape)
    print(f"[导航] 定位 {len(nav_states)} 个亚稳态，消耗 {nav_evals} 次势能评估")
    for line in synthesis_suggestions(nav_states):
        print("  " + line)

    # 对照：随机采样基线（重跑独立景观，避免评估计数污染）
    base_landscape = demo_landscape()
    random_evals = random_baseline_steps(base_landscape, target=len(nav_states))
    speedup = random_evals / max(nav_evals, 1)
    print(f"[对照] 随机采样定位 {len(nav_states)} 个亚稳态需 {random_evals} 次评估")
    print(f"[效率] 导航/随机 = {speedup:.1f}×（验收要求 ≥2×）")
    return 0 if (len(nav_states) >= 3 and speedup >= 2.0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
