"""M33 木质素/纤维素可解释描述符库（化学知识 → 可执行描述符）。

授粉源：round3 digest-g6-2026-08-31.md 2608.27587（Chemical knowledge→descriptors：
化学知识编译为可执行材料预测描述符）。承接 M01（符号回归）——本库输出的描述符
既是「可解释特征」，又是符号回归/物理引导模型的输入。

设计：把一个生物质结构的「化学知识」（官能团/键/聚合度/元素组成）编码为
BiomassStructure，DESCRIPTORS 里每个描述符是一个带化学含义的可计算标量。
供符号回归/ML 预测直接调用。

验收：≥20 个可解释描述符 + 预测案例（见 test_biomass_descriptors.py）。
纯 numpy/标准库，无外部依赖，无 LLM/网络调用。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BiomassStructure:
    """生物质结构的化学知识编码（每单体/每结构单元的计数 + 组成）。"""
    lignin_frac: float = 0.30        # 木质素质量分数
    cellulose_frac: float = 0.45     # 纤维素质量分数
    hemicellulose_frac: float = 0.25 # 半纤维素质量分数
    oh_per_monomer: float = 3.0      # 羟基 / 单体
    methoxy_per_monomer: float = 0.9 # 甲氧基 / 单体（木质素 G/S 信号）
    aromatic_rings: float = 1.0      # 芳香环数（木质素单元）
    carboxyl_per_monomer: float = 0.1
    carbonyl_per_monomer: float = 0.15
    beta_o4_linkages: float = 0.5    # β-O-4 连接数（木质素主要连接）
    glycosidic_bonds: float = 1.0    # 糖苷键数（纤维素/半纤维素）
    degree_polymerization: float = 100.0  # 聚合度 DP
    carbon_wt: float = 0.45          # 元素质量分数
    hydrogen_wt: float = 0.06
    oxygen_wt: float = 0.49
    pyrolysis_temp: float = 6.0      # 热解温度（归一化过程条件，char_yield 等依赖）


# 原子量（元素比描述符用）
_A_C, _A_H, _A_O = 12.011, 1.008, 15.999


def _h_c_ratio(s: BiomassStructure) -> float:
    """H/C 原子比：脱氧/芳香化程度（低 = 更致密、更易成炭）。"""
    return (s.hydrogen_wt / _A_H) / max(s.carbon_wt / _A_C, 1e-9)


def _o_c_ratio(s: BiomassStructure) -> float:
    """O/C 原子比：氧化度（羟基/羧基富集程度）。"""
    return (s.oxygen_wt / _A_O) / max(s.carbon_wt / _A_C, 1e-9)


def _oh_density(s: BiomassStructure) -> float:
    """羟基密度：氢键网络强度 / 亲水性。"""
    return s.oh_per_monomer


def _methoxy_density(s: BiomassStructure) -> float:
    """甲氧基密度：木质素 S/G 单元的甲氧基取代度。"""
    return s.methoxy_per_monomer


def _aromatic_ring_density(s: BiomassStructure) -> float:
    """芳香环密度：木质素刚性/热稳定贡献。"""
    return s.aromatic_rings


def _carboxyl_density(s: BiomassStructure) -> float:
    """羧基密度：酸性 / 离子交换 / 水合位点。"""
    return s.carboxyl_per_monomer


def _carbonyl_density(s: BiomassStructure) -> float:
    """羰基密度：氧化降解位点 / 交联前体。"""
    return s.carbonyl_per_monomer


def _beta_o4_density(s: BiomassStructure) -> float:
    """β-O-4 连接密度：木质素解聚的关键断裂位点。"""
    return s.beta_o4_linkages


def _glycosidic_bond_density(s: BiomassStructure) -> float:
    """糖苷键密度：纤维素/半纤维素骨架连接度。"""
    return s.glycosidic_bonds


def _polymerization_degree(s: BiomassStructure) -> float:
    """聚合度 DP：链长（分子量与力学/溶解性相关）。"""
    return s.degree_polymerization


def _molecular_weight(s: BiomassStructure) -> float:
    """表观分子量 ≈ DP × 平均单体质量（按组成加权）。"""
    mono = (s.cellulose_frac + s.hemicellulose_frac) * 162.0 + s.lignin_frac * 180.0
    return s.degree_polymerization * mono


def _lignin_content(s: BiomassStructure) -> float:
    """木质素含量（质量分数）。"""
    return s.lignin_frac


def _cellulose_content(s: BiomassStructure) -> float:
    """纤维素含量（质量分数）。"""
    return s.cellulose_frac


def _hemicellulose_content(s: BiomassStructure) -> float:
    """半纤维素含量（质量分数）。"""
    return s.hemicellulose_frac


def _holocellulose_content(s: BiomassStructure) -> float:
    """综纤维素含量 = 纤维素 + 半纤维素。"""
    return s.cellulose_frac + s.hemicellulose_frac


def _s_g_ratio(s: BiomassStructure) -> float:
    """S/G 比（紫丁香基/愈创木基）代理：甲氧基每环超出 G 单元（1 个）的部分。"""
    return max(0.0, s.methoxy_per_monomer - 1.0)


def _degree_unsaturation(s: BiomassStructure) -> float:
    """不饱和度（DBE）代理：芳香环 + 羰基贡献。"""
    return s.aromatic_rings * 4.0 + s.carbonyl_per_monomer


def _oxygen_functionality_total(s: BiomassStructure) -> float:
    """氧官能团总量 = 羟基 + 甲氧基 + 羧基 + 羰基。"""
    return (s.oh_per_monomer + s.methoxy_per_monomer
            + s.carboxyl_per_monomer + s.carbonyl_per_monomer)


def _carbon_fraction(s: BiomassStructure) -> float:
    """碳质量分数。"""
    return s.carbon_wt


def _hydrogen_fraction(s: BiomassStructure) -> float:
    """氢质量分数。"""
    return s.hydrogen_wt


def _oxygen_fraction(s: BiomassStructure) -> float:
    """氧质量分数。"""
    return s.oxygen_wt


def _h_bond_donor_density(s: BiomassStructure) -> float:
    """氢键供体密度 = 羟基 + 羧基（每单体）。"""
    return s.oh_per_monomer + s.carboxyl_per_monomer


def _aromatic_carbon_fraction(s: BiomassStructure) -> float:
    """芳香碳比例：芳香环碳 / 总碳（木质素贡献）。"""
    total_c = s.carbon_wt / _A_C
    return min(1.0, (s.aromatic_rings * 6.0) / max(total_c, 1e-9))


def _thermal_stability_proxy(s: BiomassStructure) -> float:
    """热稳定代理：芳香环 + 高聚合度 + 低碳氧比贡献（越高越稳定/越易成炭）。"""
    return s.aromatic_rings + 0.5 * (1.0 - _o_c_ratio(s)) + 0.01 * s.degree_polymerization


def _pyrolysis_temperature(s: BiomassStructure) -> float:
    """热解温度（归一化过程条件，非化学描述符，但为 char_yield 等预测的必要输入）。"""
    return s.pyrolysis_temp


# 描述符注册表：name -> (函数, 说明)。顺序稳定，供符号回归/ML 直接取用。
DESCRIPTORS: dict[str, tuple] = {
    "h_c_ratio": (_h_c_ratio, "H/C 原子比（脱氧/芳香化程度）"),
    "o_c_ratio": (_o_c_ratio, "O/C 原子比（氧化度）"),
    "oh_density": (_oh_density, "羟基密度"),
    "methoxy_density": (_methoxy_density, "甲氧基密度（S/G 信号）"),
    "aromatic_ring_density": (_aromatic_ring_density, "芳香环密度"),
    "carboxyl_density": (_carboxyl_density, "羧基密度"),
    "carbonyl_density": (_carbonyl_density, "羰基密度"),
    "beta_o4_density": (_beta_o4_density, "β-O-4 连接密度"),
    "glycosidic_bond_density": (_glycosidic_bond_density, "糖苷键密度"),
    "polymerization_degree": (_polymerization_degree, "聚合度 DP"),
    "molecular_weight": (_molecular_weight, "表观分子量"),
    "lignin_content": (_lignin_content, "木质素含量"),
    "cellulose_content": (_cellulose_content, "纤维素含量"),
    "hemicellulose_content": (_hemicellulose_content, "半纤维素含量"),
    "holocellulose_content": (_holocellulose_content, "综纤维素含量"),
    "s_g_ratio": (_s_g_ratio, "S/G 比（紫丁香基/愈创木基）"),
    "degree_unsaturation": (_degree_unsaturation, "不饱和度 DBE"),
    "oxygen_functionality_total": (_oxygen_functionality_total, "氧官能团总量"),
    "carbon_fraction": (_carbon_fraction, "碳质量分数"),
    "hydrogen_fraction": (_hydrogen_fraction, "氢质量分数"),
    "oxygen_fraction": (_oxygen_fraction, "氧质量分数"),
    "h_bond_donor_density": (_h_bond_donor_density, "氢键供体密度"),
    "aromatic_carbon_fraction": (_aromatic_carbon_fraction, "芳香碳比例"),
    "thermal_stability_proxy": (_thermal_stability_proxy, "热稳定代理"),
    "pyrolysis_temperature": (_pyrolysis_temperature, "热解温度（过程条件，归一化）"),
}


def compute_descriptors(s: BiomassStructure) -> dict[str, float]:
    """计算全部可解释描述符。"""
    return {name: fn(s) for name, (fn, _) in DESCRIPTORS.items()}


def descriptor_names() -> list[str]:
    return list(DESCRIPTORS.keys())


def fit_char_yield_model(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """最小二乘线性拟合（符号回归的线性基线）：y ≈ X w + b。

    返回 (w, b)；配合 compute_descriptors 的输出即可得到可解释公式。
    """
    Xb = np.concatenate([X, np.ones((X.shape[0], 1))], axis=1)
    w, *_ = np.linalg.lstsq(Xb, y, rcond=None)
    return w[:-1], w[-1]


def symbolic_formula_selection(X: np.ndarray, y: np.ndarray, names: list[str],
                               max_pair: bool = True) -> list[tuple[str, float]]:
    """符号公式筛选（接 M01 符号回归）：枚举单描述符 + 双描述符线性候选式，
    按 R² 降序返回可解释公式。

    返回 [(公式字符串, R²), ...]，最优式在最前——即「从可解释描述符里自动挑出
    能解释目标属性的最简公式」。
    """
    n = X.shape[0]
    ss_tot = float(np.sum((y - y.mean()) ** 2))

    def _r2(yhat: np.ndarray) -> float:
        return 1.0 - float(np.sum((y - yhat) ** 2) / ss_tot)

    candidates: list[tuple[str, float]] = []
    # 单描述符：y ≈ a·x + b（跳过近常数描述符，避免 polyfit 病态）
    for i, name in enumerate(names):
        x = X[:, i]
        if float(np.std(x)) < 1e-12:
            continue
        a, b = np.polyfit(x, y, 1)
        candidates.append((f"{name}", _r2(a * x + b)))
    # 双描述符：y ≈ w0·x_i + w1·x_j + b
    if max_pair:
        for i in range(len(names)):
            if float(np.std(X[:, i])) < 1e-12:
                continue
            for j in range(i + 1, len(names)):
                if float(np.std(X[:, j])) < 1e-12:
                    continue
                Xij = np.column_stack([X[:, i], X[:, j], np.ones(n)])
                w, *_ = np.linalg.lstsq(Xij, y, rcond=None)
                candidates.append((f"{names[i]} + {names[j]}", _r2(Xij @ w)))
    candidates.sort(key=lambda t: -t[1])
    return candidates


def make_synthetic_samples(n: int = 200, seed: int = 0):
    """合成生物质样本（lignin 分数 + 温度 → char_yield，模式与 eln-biomass-case.csv 一致）。"""
    rng = np.random.default_rng(seed)
    X, y = [], []
    for _ in range(n):
        lig = rng.uniform(0.1, 0.5)
        temp = rng.uniform(4.0, 8.0)  # 归一化温度
        s = BiomassStructure(
            lignin_frac=lig, cellulose_frac=(1 - lig) * 0.65,
            hemicellulose_frac=(1 - lig) * 0.35,
            methoxy_per_monomer=1.0 + lig,  # 木质素越多 S/G 越高
            aromatic_rings=1.0 + 2 * lig,  # 木质素芳香环
            degree_polymerization=80 + 200 * lig,
            pyrolysis_temp=temp,           # 过程条件
        )
        # 真值：char_yield 随木质素含量与温度上升（与 ELN 模式一致）+ 噪声
        char = 35.0 * lig + 2.5 * temp + rng.normal(0, 1.5)
        desc = compute_descriptors(s)
        X.append([desc[n] for n in descriptor_names()])
        y.append(char)
    return np.asarray(X), np.asarray(y), descriptor_names()


def run_demo() -> None:
    print(f"[M33] 可解释描述符数量 = {len(DESCRIPTORS)}（验收 ≥20）")
    # 案例 1：单个木质素样本的描述符值
    demo = compute_descriptors(BiomassStructure(lignin_frac=0.35))
    print("[M33] 样例描述符（木质素 0.35）：")
    for k, v in list(demo.items())[:6]:
        print(f"      {k} = {v:.3f}")
    # 案例 2：预测案例（char_yield ← 描述符线性模型）
    X, y, names = make_synthetic_samples()
    w, b = fit_char_yield_model(X, y)
    yhat = X @ w + b
    r2 = 1 - float(np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2))
    print(f"[M33] char_yield 预测 R² = {r2:.3f}")
    top = sorted(zip(names, np.abs(w)), key=lambda t: -t[1])[:3]
    print("[M33] 权重最大的可解释描述符：", [(n, round(abs(wv), 2)) for n, wv in top])
    # 案例 3：符号公式筛选（接 M01 符号回归）
    formulas = symbolic_formula_selection(X, y, names)
    print("[M33] 符号公式筛选 top-3（可解释式 + R²）：")
    for f, fr2 in formulas[:3]:
        print(f"      {f:42s} R²={fr2:.3f}")


if __name__ == "__main__":
    run_demo()
