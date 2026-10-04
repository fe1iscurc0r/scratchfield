#!/usr/bin/env python3
"""PARAFAC 测向最小验证（卷155 任务A.2）。

纯 numpy 实现：**合成阵列信号 → 三阶张量 → PARAFAC(ALS) 分解 → DOA 估计**。
无硬件依赖、无 scipy 依赖，`--simulate` 即可自测。

张量构造（与文献里的 PARAFAC-DOA 同构）：
    天线 m 与参考天线 0 的互相关，按「时延 τ」与「子块 n」展开 → Y[m, τ, n]
    Y[m, τ, n] ≈ Σ_k A[m,k] · B[τ,k] · C[n,k]
其中 A 的第 k 列就是第 k 个源的空间特征（ULA 相位斜线），由相位斜率反解 sinθ_k。

用法：
    python tools/parafac_doa_sim.py --simulate                 # 默认双源自测
    python tools/parafac_doa_sim.py --simulate --sources 3      # 指定源数
    python tools/parafac_doa_sim.py --simulate --snr-db 0       # 指定信噪比
    python tools/parafac_doa_sim.py --sweep-snr                 # 扫 SNR，看误差随 SNR 收敛
"""

from __future__ import annotations

import argparse
import sys

try:
    import numpy as np
except ModuleNotFoundError:  # 不静默降级：把「缺什么 + 怎么补」直接打出来
    sys.stderr.write(
        "[parafac_doa_sim] 缺少依赖 numpy，脚本无法运行。任选其一：\n"
        "  · 用仓内虚拟环境（推荐，已带 numpy）：\n"
        "      .venv/Scripts/python.exe tools/parafac_doa_sim.py --simulate\n"
        "  · 或为当前解释器安装（装前按供应链铁律核对包真实存在）：\n"
        "      python3 -m pip install numpy\n"
    )
    raise SystemExit(2) from None

# ── 系统参数（可被命令行覆盖） ──
DEFAULTS = {
    "antennas": 10,     # 阵列总阵元数 M
    "sources": 2,       # 源数 K
    "snapshots": 1024,  # 总快拍数 T
    "lags": 6,          # 时延维度长度
    "shifts": 4,        # 空间平滑子阵移位数 S（第三模）
    "snr_db": 20.0,     # 信噪比
    "als_iters": 400,   # ALS 迭代上限
    "als_tol": 1e-10,   # ALS 收敛阈值
    "restarts": 8,      # 多起点次数（取拟合残差最小者）
    "seed": 0,
}


def steering_ula(m: int, theta_deg: np.ndarray, half_wavelength: bool = True) -> np.ndarray:
    """ULA 阵列流形。间距 = 半波长时，相邻阵元相位差 = π·sinθ。"""
    m_idx = np.arange(m)[:, None]
    return np.exp(1j * np.pi * m_idx * np.sin(np.deg2rad(theta_deg))[None, :]) / np.sqrt(m)


def synthesize(cfg: dict, theta_true: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """合成接收数据 X[M, T]：x_m(t) = Σ_k a_m(θ_k)·s_k(t) + n_m(t)。

    ★ 源必须是**时间相关的**（AR(1)）：若源是时间白噪声，时延维 τ>0 的互相关恒为 0，
    张量在 τ 维退化成 rank-1，PARAFAC 无法分离多个源（实测过这个坑）。
    各源取不同 AR 系数 ⇒ 时延维给对方程供了可分性（这正是 PARAFAC-DOA 依赖的多样性）。
    """
    rng = np.random.default_rng(cfg["seed"])
    M, T, K = cfg["antennas"], cfg["snapshots"], cfg["sources"]

    # AR(1) 源：s_k(t) = ρ_k·s_k(t-1) + w(t)，各源 ρ 不同
    rho = np.linspace(0.85, 0.55, K)
    S = np.zeros((K, T), dtype=complex)
    w = (rng.standard_normal((K, T)) + 1j * rng.standard_normal((K, T))) / np.sqrt(2)
    for k in range(K):
        for t in range(1, T):
            S[k, t] = rho[k] * S[k, t - 1] + w[k, t]
    S /= np.std(S, axis=1, keepdims=True)          # 各源功率归一

    A = steering_ula(M, theta_true)
    X = A @ S

    # 按目标 SNR 加噪（信号功率已知，噪声独立复高斯）
    sig_pow = np.mean(np.abs(X) ** 2)
    noise_pow = sig_pow / (10 ** (cfg["snr_db"] / 10.0))
    N = (rng.standard_normal(X.shape) + 1j * rng.standard_normal(X.shape)) * np.sqrt(noise_pow / 2)
    return X + N, S


def build_tensor(X: np.ndarray, lags: int, shifts: int) -> np.ndarray:
    """X[M, T] → Y[Ms, lags, S]（空间平滑构造，固定全局参考阵元 0）。

    Y[m, τ, s] = (1/T) Σ_t X[s+m, t] · conj(X[0, t+τ])

    期望值 = Σ_k (1/M)·e^{jπ(s+m-1)sinθ_k}·ρ_k^τ —— 对 (m, s) 里只通过 (s+m) 进入，
    于是**三模各自带逐源多样性**：
        A[m,k] ∝ e^{jπ m sinθ_k}   B[τ,k] ∝ ρ_k^τ   C[s,k] ∝ e^{jπ s sinθ_k}
    Kruskal 条件 k_A+k_B+k_C ≥ 2K+1 对 K 个不同角度成立 ⇒ 分解**唯一**。

    ★ 为什么不用「时间子块」当第三模（踩过的坑）：
    块的互相关期望与块号无关（只差估计噪声）⇒ 第三模近似 rank-1 ⇒ 非唯一，
    分解结果可以是任意混合，DOA 估计随机乱跳（实测 10 个种子 RMSE 从 1.9° 到 15°）。
    空间平滑给出的是**确定性的逐源相位多样性**，这才让 PARAFAC 有解可言。
    """
    M, T = X.shape
    Ms = M - shifts + 1
    Y = np.zeros((Ms, lags, shifts), dtype=complex)
    ref = X[0, :]                                    # 固定全局参考阵元
    for s in range(shifts):
        sub = X[s:s + Ms, :]                         # 子阵 s：阵元 s..s+Ms-1
        for tau in range(lags):
            a_ = sub[:, : T - tau]
            b_ = ref[tau:]
            Y[:, tau, s] = (a_ * np.conj(b_)[None, :]).mean(axis=1)
    return Y


def parafac_als(Y: np.ndarray, rank: int, iters: int, tol: float, seed: int = 0,
                restarts: int = 4):
    """三阶 PARAFAC 分解（复值 ALS，多起点选优）：Y ≈ Σ_r a_r ∘ b_r ∘ c_r。

    ★ 为什么必须多起点：CP-ALS 对随机初值敏感，单起点常落进坏局部极小
      （实测：单起点时不同随机种子 RMSE 从 1.9° 到 15° 不等）。
      多起点跑几遍、取**拟合残差最小**的解，是 CP 分解的标准工程做法。

    返回 (A[Ms,rank], B[lags,rank], C[S,rank], 相对拟合误差)。
    """
    best = None
    for r in range(max(1, restarts)):
        res = _als_single(Y, rank, iters, tol, seed=seed + 1000 * r)
        if best is None or res[3] < best[3]:
            best = res
    return best


def _als_single(Y: np.ndarray, rank: int, iters: int, tol: float, seed: int = 0):
    """单起点 ALS（内部函数）。返回 (A, B, C, 相对拟合误差)。"""
    rng = np.random.default_rng(seed)
    M, L, N = Y.shape
    A = rng.standard_normal((M, rank)) + 1j * rng.standard_normal((M, rank))
    B = rng.standard_normal((L, rank)) + 1j * rng.standard_normal((L, rank))
    C = rng.standard_normal((N, rank)) + 1j * rng.standard_normal((N, rank))

    def khatri_rao(P, Q):
        """列向 Khatri-Rao 积：(P ⊙ Q)[i*rows(Q) + j, r] = P[i,r]·Q[j,r]。

        ★ 参数顺序必须与「C-order 展平后的列索引」一致，否则最小二乘解全错：
          Y1 = Y.reshape(M, L*N)          → 列索引 = l*N + n  ⇒ 需要 kr(B, C)
          Y2 = transpose(1,0,2).reshape(L, M*N) → 列索引 = m*N + n ⇒ 需要 kr(A, C)
          Y3 = transpose(2,0,1).reshape(N, M*L) → 列索引 = m*L + l ⇒ 需要 kr(A, B)
        （踩过：写成 kr(C,B)/kr(C,A)/kr(B,A) 时，即便用真值初始化，单步更新也会把残差打到 ~1.0）
        """
        return (P[:, None, :] * Q[None, :, :]).reshape(P.shape[0] * Q.shape[0], -1)

    # 三向展开（mode-1/2/3 unfold）
    Y1 = Y.reshape(M, -1)                                  # [M, L*N]，列索引 l*N+n
    Y2 = np.transpose(Y, (1, 0, 2)).reshape(L, -1)         # [L, M*N]，列索引 m*N+n
    Y3 = np.transpose(Y, (2, 0, 1)).reshape(N, -1)         # [N, M*L]，列索引 m*L+l

    prev = None
    for _ in range(iters):
        A = Y1 @ np.linalg.pinv(khatri_rao(B, C)).T
        B = Y2 @ np.linalg.pinv(khatri_rao(A, C)).T
        C = Y3 @ np.linalg.pinv(khatri_rao(A, B)).T
        for X_ in (A, B, C):                                # 列归一化，避免尺度漂移
            nrm = np.linalg.norm(X_, axis=0, keepdims=True)
            X_ /= np.where(nrm == 0, 1, nrm)
        # 拟合残差
        Yhat = np.einsum("mr,tr,nr->mtn", A, B, C)
        err = np.linalg.norm(Y - Yhat) / max(np.linalg.norm(Y), 1e-30)
        if prev is not None and abs(prev - err) < tol:
            break
        prev = err
    return A, B, C, float(err)


def _phase_slope_to_deg(col: np.ndarray) -> float:
    """一列空间特征 → DOA（度）：相邻元素相位差均值 / π → arcsin。"""
    dphi = np.angle(col[1:] * np.conj(col[:-1]))           # 公共相位自动抵消
    return float(np.rad2deg(np.arcsin(np.clip(float(np.mean(dphi)) / np.pi, -1.0, 1.0))))


def doa_from_factors(A: np.ndarray, C: np.ndarray,
                     theta_hint: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """从两个空间因子反解 DOA 并取均值。

    空间平滑构造下 **A（阵元维）与 C（子阵移位维）都是 e^{jπ(·)sinθ} 型**，
    两路估计互相独立 ⇒ 取均值降方差，且两者的**一致性本身就是拟合质量的自检信号**
    （若两路差很多，说明分解没落到真解上）。

    返回 (est_均值, est_A, est_C)，均已按真值顺序配对。
    """
    est_a = np.array([_phase_slope_to_deg(A[:, k]) for k in range(A.shape[1])], dtype=float)
    est_c = np.array([_phase_slope_to_deg(C[:, k]) for k in range(C.shape[1])], dtype=float)
    est = 0.5 * (est_a + est_c)
    if theta_hint is not None and len(est) > 1:
        est, est_a, est_c = (match_to_truth(theta_hint, e) for e in (est, est_a, est_c))
    return est, est_a, est_c


def match_to_truth(theta_true: np.ndarray, est: np.ndarray) -> np.ndarray:
    """贪心最近邻配对：把估计角度按真值顺序摆好，便于逐源比对（不改动估计值）。"""
    remaining = list(range(len(est)))
    ordered = []
    for t in theta_true:
        j = min(remaining, key=lambda i: abs(est[i] - t))
        remaining.remove(j)
        ordered.append(est[j])
    return np.array(ordered)


def run_once(cfg: dict, theta_true: np.ndarray, verbose: bool = True) -> dict:
    X, _ = synthesize(cfg, theta_true)
    Y = build_tensor(X, cfg["lags"], cfg["shifts"])
    A, B, C, fit_err = parafac_als(Y, cfg["sources"], cfg["als_iters"], cfg["als_tol"], cfg["seed"],
                                   restarts=cfg.get("restarts", 8))
    est, est_a, est_c = doa_from_factors(A, C, theta_true)
    rmse = float(np.sqrt(np.mean((est - theta_true) ** 2)))
    if verbose:
        print(f"[DOA] 真值   : {np.array2string(theta_true, precision=2)}")
        print(f"[DOA] PARAFAC 估计: {np.array2string(est, precision=2)}")
        print(f"[DOA] 双路自检: 阵元维 {np.array2string(est_a, precision=2)} / 子阵维 {np.array2string(est_c, precision=2)}"
              f"  （两者应接近；差很多说明分解没落到真解）")
        print(f"[DOA] RMSE   : {rmse:.3f}°   张量拟合相对误差: {fit_err:.4f}   SNR={cfg['snr_db']}dB  源数={cfg['sources']}")
        for i, (t, e) in enumerate(zip(theta_true, est, strict=False), 1):
            print(f"[DOA]   源{i}: 真值 {t:+.2f}° → 估计 {e:+.2f}°  误差 {abs(e - t):.3f}°")
    return {"theta_true": theta_true, "theta_est": est, "rmse": rmse, "fit_err": fit_err}


def main() -> int:
    ap = argparse.ArgumentParser(description="PARAFAC 测向最小验证（numpy only）")
    ap.add_argument("--simulate", action="store_true", help="合成数据自测（默认行为）")
    ap.add_argument("--sources", type=int, default=DEFAULTS["sources"])
    ap.add_argument("--antennas", type=int, default=DEFAULTS["antennas"])
    ap.add_argument("--snapshots", type=int, default=DEFAULTS["snapshots"])
    ap.add_argument("--snr-db", type=float, default=DEFAULTS["snr_db"])
    ap.add_argument("--lags", type=int, default=DEFAULTS["lags"])
    ap.add_argument("--shifts", type=int, default=DEFAULTS["shifts"], help="空间平滑子阵移位数")
    ap.add_argument("--als-iters", type=int, default=DEFAULTS["als_iters"])
    ap.add_argument("--restarts", type=int, default=DEFAULTS["restarts"], help="ALS 多起点次数")
    ap.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    ap.add_argument("--max-rmse", type=float, default=5.0, help="自检阈值（度），超过则以非零码退出")
    ap.add_argument("--sweep-snr", action="store_true", help="扫 SNR，输出 RMSE 收敛表")
    args = ap.parse_args()

    cfg = dict(DEFAULTS)
    cfg.update(sources=args.sources, antennas=args.antennas, snapshots=args.snapshots,
               snr_db=args.snr_db, lags=args.lags, shifts=args.shifts,
               als_iters=args.als_iters, restarts=args.restarts, seed=args.seed)

    # 真值角度：等间隔张开，保证 K 个源在 [-60°, 60°] 内可分
    if cfg["sources"] == 2:
        theta_true = np.array([-20.0, 25.0])
    else:
        theta_true = np.linspace(-30.0, 30.0, cfg["sources"])

    if args.sweep_snr:
        print("[DOA] SNR 扫描（每档 10 次独立试验的 RMSE 均值±标准差，单位：度）")
        rmses = []
        for snr in (-5.0, 0.0, 5.0, 10.0, 20.0, 30.0):
            vals = []
            for t in range(10):
                c = dict(cfg, snr_db=snr, seed=1000 + t)
                vals.append(run_once(c, theta_true, verbose=False)["rmse"])
            m, s = float(np.mean(vals)), float(np.std(vals))
            rmses.append(m)
            print(f"[DOA]   SNR={snr:>5.1f}dB  RMSE={m:6.3f} ± {s:5.3f}")
        print(f"[DOA] 趋势：低噪→高噪 RMSE {rmses[0]:.3f}° → {rmses[-1]:.3f}°"
              f"（{'下降 ✓' if rmses[-1] <= rmses[0] else '未下降 —— 需检查'}）")
        return 0

    # 默认（含 --simulate）走单次自测，并做**自检断言**（防止将来改动再次引入退化）
    res = run_once(cfg, theta_true, verbose=True)
    if res["rmse"] > args.max_rmse:
        print(f"[DOA] 自检失败：RMSE {res['rmse']:.3f}° > 阈值 {args.max_rmse}°", file=sys.stderr)
        return 1
    print(f"[DOA] 自检通过：RMSE {res['rmse']:.3f}° ≤ 阈值 {args.max_rmse}°"
          f"（注：张量拟合误差反映 CP 模型与含噪相关张量的固有失配，不是收敛判据）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
