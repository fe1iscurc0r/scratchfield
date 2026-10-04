"""R09 · 信道字典原子验证器（共享物理响应排序）

灵感：digest-g1-2 授粉点① · 论文 2608.20441（Shared Physics Responses）。

问题：信道字典学习产出的原子里，哪些对应真实物理过程（多径/衰落），哪些只是
拟合噪声的数据伪影？只验证「数据重建误差」无法区分二者（伪影也能重建训练数据）。

方法：为每个原子计算**共享物理诊断**——功率谱、延迟扩展、相干带宽，然后与
「共享物理响应锚」比对排序：
  - 真实多径原子：功率按指数衰减集中在早期抽头（物理 Rayleigh 指数 PDP），
    延迟扩展有界，谱相干；
  - 数据伪影原子：白噪声/随机尖峰，能量均匀散布，延迟扩展大或谱平坦。

打分 = 原子的功率延迟剖面 |h|² 与指数衰减模板（共享物理响应锚）的归一化内积，
物理原子得分高、伪影得分低，据此筛选原子。

运行：python -m mcpserver.rf_brain.prototypes.channel_atom_validator
"""
from __future__ import annotations

import numpy as np


def physical_multipath(L: int, rng: np.random.Generator, *, tau_mean: float = 6.0) -> np.ndarray:
    """真实物理多径：少数抽头，功率指数衰减（Rayleigh 指数 PDP）。"""
    h = np.zeros(L, dtype=float)
    for d in (0, 2, 5, 9, 14, 20):
        if d < L:
            amp = rng.rayleigh() * np.exp(-d / tau_mean)
            h[d] = amp
    return h


def artifact(L: int, rng: np.random.Generator, *, kind: str = "noise") -> np.ndarray:
    """数据伪影：白噪声（谱平坦、无物理结构）或随机尖峰。"""
    if kind == "noise":
        return rng.standard_normal(L)
    if kind == "spike":
        h = np.zeros(L, dtype=float)
        for d in rng.integers(0, L, size=3):
            h[d] = rng.uniform(0.5, 1.0)
        return h
    raise ValueError(kind)


def synthesize_dictionary(n_true: int, n_artifact: int, L: int, *, seed: int = 0):
    """合成字典：n_true 个物理原子 + n_artifact 个伪影原子，返回 (atoms, labels)。"""
    rng = np.random.default_rng(seed)
    atoms = [physical_multipath(L, rng) for _ in range(n_true)]
    labels = [True] * n_true
    for i in range(n_artifact):
        atoms.append(artifact(L, rng, kind="noise" if i % 2 == 0 else "spike"))
        labels.append(False)
    return np.array(atoms), np.array(labels)


def pdp(atom: np.ndarray) -> np.ndarray:
    """功率延迟剖面 |h|²（归一化）。"""
    p = np.abs(atom) ** 2
    s = p.sum()
    return p / s if s > 0 else p


def shared_physics_anchor(atoms: np.ndarray, *, tau_mean: float = 6.0) -> np.ndarray:
    """共享物理响应锚 = 指数衰减模板 e^{-n/τ̄}（归一化）。"""
    L = atoms.shape[1]
    tpl = np.exp(-np.arange(L) / tau_mean)
    return tpl / tpl.sum()


def delay_spread(atom: np.ndarray) -> float:
    """RMS 延迟扩展（抽头）。"""
    p = pdp(atom)
    tau = np.arange(p.size)
    mean_tau = float(np.dot(tau, p))
    return float(np.sqrt(np.dot((tau - mean_tau) ** 2, p)))


def coherence_bandwidth(atom: np.ndarray) -> float:
    """相干带宽 ≈ 1/(5·τ_rms)（以抽头为单位的倒数）。"""
    d = delay_spread(atom)
    return 1.0 / (5.0 * d) if d > 0 else float("inf")


def physical_score(atom: np.ndarray, anchor: np.ndarray) -> float:
    """与共享物理响应锚的归一化内积（余弦相似度）。"""
    p = pdp(atom)
    return float(np.dot(p, anchor) / (np.linalg.norm(p) * np.linalg.norm(anchor) + 1e-12))


def rank_atoms(atoms: np.ndarray, anchor: np.ndarray) -> np.ndarray:
    """按物理一致性降序返回原子下标。"""
    scores = np.array([physical_score(a, anchor) for a in atoms])
    return np.argsort(scores)[::-1]


def top_k_precision(order: np.ndarray, labels: np.ndarray, k: int) -> float:
    """top-k 里物理原子的占比。"""
    return float(labels[order[:k]].mean())


def main() -> None:
    n_true, n_artifact, L = 20, 40, 64
    atoms, labels = synthesize_dictionary(n_true, n_artifact, L)
    anchor = shared_physics_anchor(atoms)
    order = rank_atoms(atoms, anchor)
    for k in (20, 30, 40):
        print(f"top-{k} 物理原子占比 = {top_k_precision(order, labels, k)*100:.1f}%")


if __name__ == "__main__":
    main()
