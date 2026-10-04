"""M32 生物质分子势基准 · 可执行基准脚本（uMOF 标准化评测方法参照）。

授粉源：round3 digest-g6-2026-08-31.md 2608.28100（uMOF：通用数据库 + 基准 +
ML 原子间势标准化评测）。配合 docs/biomass-mlip-benchmark-方案.md，把方案里的
评测指标落地成可运行的 scorecard：给定「候选势预测」与「DFT 参考」，输出统一指标。

指标（与方案 §2 一一对应）：
  energy_rmse / force_rmse / lattice_rel_error / hbond_rmse /
  bond_break_order_acc / stability_score / extrapolation_rmse

纯 numpy，无外部依赖；无真实 DFT 数据时用合成 mock 演示（诚实标注）。
"""
from __future__ import annotations

import numpy as np


def energy_rmse(pred_eV: np.ndarray, ref_eV: np.ndarray, n_atoms: int = 1) -> float:
    """能量误差（meV/atom）：预测总能 vs DFT 参考的 RMSE。"""
    return float(np.sqrt(np.mean(((pred_eV - ref_eV) * 1000.0 / n_atoms) ** 2)))


def force_rmse(pred_forces: np.ndarray, ref_forces: np.ndarray) -> float:
    """力误差（meV/Å）：原子受力分量的 RMSE。"""
    return float(np.sqrt(np.mean((pred_forces - ref_forces) ** 2)) * 1000.0)


def lattice_rel_error(pred_lattice: np.ndarray, ref_lattice: np.ndarray) -> float:
    """晶胞参数相对误差（%）：|pred-ref|/ref 均值。"""
    return float(np.mean(np.abs(pred_lattice - ref_lattice) / np.abs(ref_lattice)) * 100.0)


def hbond_rmse(pred_hb: np.ndarray, ref_hb: np.ndarray) -> float:
    """氢键几何误差（Å）：键长/角度的 RMSE（生物质特有：糖苷键/羟基）。"""
    return float(np.sqrt(np.mean((pred_hb - ref_hb) ** 2)))


def bond_break_order_acc(pred_rank: np.ndarray, ref_rank: np.ndarray) -> float:
    """键断裂顺序一致率：预测 vs 参考的断裂温度排序（Kendall τ 归一化到 0~1）。"""
    pred_rank = np.asarray(pred_rank, dtype=float)
    ref_rank = np.asarray(ref_rank, dtype=float)
    if len(pred_rank) < 2:
        return 1.0
    # 成对一致率（秩相关）：对每对 (i<j)，符号一致则 +1
    n = 0
    agree = 0
    for i in range(len(ref_rank)):
        for j in range(i + 1, len(ref_rank)):
            n += 1
            if (pred_rank[i] - pred_rank[j]) * (ref_rank[i] - ref_rank[j]) >= 0:
                agree += 1
    return agree / n


def stability_score(force_rmse_val: float, threshold_meV_ang: float = 200.0) -> float:
    """MD 稳定性代理：力误差远小于阈值则稳定（0~1，越高越稳）。"""
    return float(np.clip(1.0 - force_rmse_val / threshold_meV_ang, 0.0, 1.0))


def extrapolation_rmse(pred_eV_ood: np.ndarray, ref_eV_ood: np.ndarray, n_atoms: int = 1) -> float:
    """外推鲁棒性（meV/atom）：训练集外构型的能量 RMSE。"""
    return float(np.sqrt(np.mean(((pred_eV_ood - ref_eV_ood) * 1000.0 / n_atoms) ** 2)))


def score(pred: dict, ref: dict, n_atoms: int = 1) -> dict[str, float]:
    """统一 scorecard：把候选势预测 vs 参考打成一串可横向比较的指标。

    pred/ref 字段：energy_eV, forces, lattice, hbond, bond_rank, energy_eV_ood。
    """
    return {
        "energy_rmse_meV_atom": energy_rmse(pred["energy_eV"], ref["energy_eV"], n_atoms),
        "force_rmse_meV_ang": force_rmse(pred["forces"], ref["forces"]),
        "lattice_rel_error_pct": lattice_rel_error(pred["lattice"], ref["lattice"]),
        "hbond_rmse_ang": hbond_rmse(pred["hbond"], ref["hbond"]),
        "bond_break_order_acc": bond_break_order_acc(pred["bond_rank"], ref["bond_rank"]),
        "stability_score": stability_score(force_rmse(pred["forces"], ref["forces"])),
        "extrapolation_rmse_meV_atom": extrapolation_rmse(pred["energy_eV_ood"], ref["energy_eV_ood"], n_atoms),
    }


def _make_reference(n: int = 50, seed: int = 0) -> dict:
    """合成「DFT 参考」（mock：真实 DFT 数据可替换此处）。"""
    rng = np.random.default_rng(seed)
    return {
        "energy_eV": rng.normal(-100.0, 2.0, size=n),       # 每构型总能
        "forces": rng.normal(0.0, 0.1, size=(n, 30)),        # 30 个受力分量
        "lattice": np.array([8.35, 10.4, 7.9]) + rng.normal(0, 0.02, size=(n, 3)),
        "hbond": rng.normal(1.85, 0.1, size=n),              # 氢键键长
        "bond_rank": np.array([0, 1, 2, 3]),                 # β-O-4<C-C<糖苷<C-O 断裂顺序
        "energy_eV_ood": rng.normal(-99.0, 2.5, size=n),     # 外推构型
    }


def _perturb(ref: dict, noise: float, bias: float = 0.0, seed: int = 1) -> dict:
    """生成一个「候选势」预测：参考 + 噪声 + 偏置（模拟不同势的精度）。"""
    rng = np.random.default_rng(seed)
    return {
        "energy_eV": ref["energy_eV"] + bias + rng.normal(0, noise, size=ref["energy_eV"].shape),
        "forces": ref["forces"] + rng.normal(0, noise, size=ref["forces"].shape),
        "lattice": ref["lattice"] + rng.normal(0, noise, size=ref["lattice"].shape),
        "hbond": ref["hbond"] + rng.normal(0, noise, size=ref["hbond"].shape),
        "bond_rank": ref["bond_rank"] + rng.normal(0, noise, size=ref["bond_rank"].shape),
        "energy_eV_ood": ref["energy_eV_ood"] + rng.normal(0, noise, size=ref["energy_eV_ood"].shape),
    }


def run_demo() -> None:
    ref = _make_reference()
    good = _perturb(ref, noise=0.02, seed=1)   # 高精度候选势
    bad = _perturb(ref, noise=0.5, bias=1.0, seed=2)  # 低精度候选势

    s_good = score(good, ref, n_atoms=64)
    s_bad = score(bad, ref, n_atoms=64)
    print("[M32] 基准 scorecard（合成 mock，真实 DFT 可替换）：")
    for k in s_good:
        print(f"      {k:28s}  good={s_good[k]:8.3f}  bad={s_bad[k]:8.3f}")
    assert s_good["energy_rmse_meV_atom"] < s_bad["energy_rmse_meV_atom"]
    print("[M32] 基准能正确区分好/坏候选势 ✓")


if __name__ == "__main__":
    run_demo()
