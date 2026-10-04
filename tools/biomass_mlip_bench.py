"""W59-02 · 生物质分子势基准（承接 M08 DPA4C / M09 UBio-MolFM 分子势路线）。

来源：docs/biomass-mlip-benchmark-方案.md（M32 方案转原型）。
目标：给生物质体系建一个「专用基准」——选代表性分子、构造小样本能量-构型数据、
定义基准协议（能量 MAE / 力 MAE / 推理时长），并用一个 numpy 可跑的基线 MLIP 对照。

本原型（简化 + 诚实标注）：
  - 分子：5 个代表性生物质相关分子（葡萄糖/纤维二糖/愈创木酚/丁香酚/木糖）；
  - 数据：每分子沿一个「关键键长」坐标扫描的 Morse 势能 + 解析力（合成 surrogate，
    真实 DFT 能量/力可替换此数据，见 data/biomass_mlip/ 说明）；
  - 基线 MLIP：核岭回归（RBF 核），力 = 数值梯度；对照「均值基线」；
  - 输出：模型 × 分子 → 能量 MAE / 力 MAE 表格到 stdout。

验收：pytest 全绿（≥4 用例）+ 基准脚本输出表格（模型 × 分子 → 能量 MAE / 力 MAE）。
纯 numpy + 标准库，无外部依赖。
"""
from __future__ import annotations

import os
import time

import numpy as np

# 代表性生物质相关分子 + 合成 Morse 参数 (D, a, r0)——真实体系可替换为 DFT 扫描
MOLECULES = ["葡萄糖", "纤维二糖", "愈创木酚", "丁香酚", "木糖"]
MORSE = {
    "葡萄糖": (0.50, 4.0, 1.00),
    "纤维二糖": (0.60, 4.5, 1.10),
    "愈创木酚": (0.40, 5.0, 0.90),
    "丁香酚": (0.45, 5.2, 0.95),
    "木糖": (0.55, 4.2, 1.05),
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "biomass_mlip")


def morse_energy(r: np.ndarray, D: float, a: float, r0: float) -> np.ndarray:
    """Morse 势能：E(r) = D·(1 - e^{-a(r-r0)})²。"""
    x = 1.0 - np.exp(-a * (r - r0))
    return D * x * x


def morse_force(r: np.ndarray, D: float, a: float, r0: float) -> np.ndarray:
    """Morse 解析力：F(r) = -dE/dr = -2aD·(1-e^{-a(r-r0)})·e^{-a(r-r0)}。"""
    x = np.exp(-a * (r - r0))
    return -2.0 * a * D * (1.0 - x) * x


def generate_dataset(n: int = 40, seed: int = 0, save: bool = True) -> dict[str, tuple]:
    """每分子生成 n 个构型（键长 r 扫描 + 能量/力 + 噪声），可选落盘到 data/biomass_mlip/。"""
    rng = np.random.default_rng(seed)
    os.makedirs(DATA_DIR, exist_ok=True)
    data = {}
    for name in MOLECULES:
        D, a, r0 = MORSE[name]
        r = r0 + rng.uniform(-0.3, 0.3, size=n)
        e = morse_energy(r, D, a, r0) + rng.normal(0, 0.01, size=n)
        f = morse_force(r, D, a, r0) + rng.normal(0, 0.05, size=n)
        data[name] = (r, e, f)
        if save:
            np.savetxt(os.path.join(DATA_DIR, f"{name}.csv"),
                       np.column_stack([r, e, f]), delimiter=",",
                       header="r,E,F", comments="")
    return data


def load_dataset(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """从 data/biomass_mlip/<name>.csv 读取 (r, E, F)。"""
    arr = np.loadtxt(os.path.join(DATA_DIR, f"{name}.csv"), delimiter=",", skiprows=1)
    return arr[:, 0], arr[:, 1], arr[:, 2]


class KernelRidge:
    """核岭回归（RBF 核）：解 (K + λI)α = y，numpy 可跑。"""

    def __init__(self, sigma: float = 0.15, lam: float = 1e-6):
        self.sigma = sigma
        self.lam = lam
        self.X_tr = None
        self.alpha = None

    def _kernel(self, X: np.ndarray, Z: np.ndarray) -> np.ndarray:
        X = np.asarray(X).ravel()
        Z = np.asarray(Z).ravel()
        sq = X[:, None] ** 2 + Z[None, :] ** 2 - 2.0 * X[:, None] * Z[None, :]
        return np.exp(-sq / (2.0 * self.sigma ** 2))

    def fit(self, X: np.ndarray, y: np.ndarray) -> "KernelRidge":
        self.X_tr = np.asarray(X).ravel()
        K = self._kernel(self.X_tr, self.X_tr) + self.lam * np.eye(len(self.X_tr))
        self.alpha = np.linalg.solve(K, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._kernel(np.asarray(X).ravel(), self.X_tr) @ self.alpha


def force_from_energy(model: KernelRidge, r: np.ndarray, h: float = 1e-3) -> np.ndarray:
    """力的数值梯度：F ≈ -(E(r+h) - E(r-h)) / 2h。"""
    ep = model.predict(r + h)
    em = model.predict(r - h)
    return -(ep - em) / (2.0 * h)


def benchmark() -> list[tuple[str, str, float, float, float]]:
    """跑基准：KRR 基线 vs 均值基线，输出 模型×分子→能量 MAE/力 MAE 行。

    返回行列表 [(模型, 分子, 能量MAE, 力MAE, 推理时长ms)]。
    """
    generate_dataset(seed=0, save=True)
    rows = []
    for name in MOLECULES:
        r, e, f = load_dataset(name)
        split = int(len(r) * 0.7)
        r_tr, e_tr = r[:split], e[:split]
        r_te, e_te, f_te = r[split:], e[split:], f[split:]

        # 基线：KRR
        t0 = time.perf_counter()
        krr = KernelRidge(sigma=0.15).fit(r_tr, e_tr)
        e_pred = krr.predict(r_te)
        f_pred = force_from_energy(krr, r_te)
        t_krr = (time.perf_counter() - t0) * 1e3
        e_mae_k = float(np.mean(np.abs(e_pred - e_te)))
        f_mae_k = float(np.mean(np.abs(f_pred - f_te)))
        rows.append(("KRR基线", name, e_mae_k, f_mae_k, t_krr))

        # 对照：均值基线（能量=训练均值，力=0）
        e_mean = float(np.mean(e_tr))
        e_mae_m = float(np.mean(np.abs(e_mean - e_te)))
        f_mae_m = float(np.mean(np.abs(0.0 - f_te)))
        rows.append(("均值基线", name, e_mae_m, f_mae_m, 0.0))

    # 打印表格
    print("[W59-02] 模型 × 分子 → 能量 MAE (eV) / 力 MAE (eV/Å) / 推理 (ms)")
    print(f"  {'模型':<8} {'分子':<8} {'能量MAE':>9} {'力MAE':>9} {'推理ms':>9}")
    for model, name, emae, fmae, tms in rows:
        print(f"  {model:<8} {name:<8} {emae:>9.4f} {fmae:>9.4f} {tms:>9.2f}")
    return rows


def run_demo() -> None:
    benchmark()


if __name__ == "__main__":
    run_demo()
