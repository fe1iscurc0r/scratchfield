"""R31 · 材料指纹频谱库原型（THz 材料响应指纹识别）

灵感：digest-g5-3a 授粉点② · 论文 2608.22958 相关（MXene THz 发射 + 量子流体动力学
框架）。THz 波段材料 EM 响应与其能带结构显式链接，可做成「材料指纹特征库」，
供 SDR 频谱比对（材料识别 / 成分分析）。

原型：
  - MaterialFingerprint 特征 schema（dataclass）
  - 合成若干材料 THz 吸收谱（各有特征吸收带）
  - match：观测谱与库内指纹做相关性匹配 → 识别材料

运行：python -m mcpserver.rf_brain.prototypes.material_fingerprint_lib
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class MaterialFingerprint:
    """材料指纹 schema：THz 吸收谱特征。"""
    name: str
    freq_thz: np.ndarray                      # 频率轴（THz）
    absorbance: np.ndarray                    # 吸收谱（归一化）
    peak_freqs_thz: list[float] = field(default_factory=list)   # 特征吸收带中心
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"name": self.name, "peak_freqs_thz": self.peak_freqs_thz,
                "metadata": self.metadata}


def synthesize_material(name: str, peak_freqs: list[float], *, n: int = 200,
                        seed: int = 0) -> MaterialFingerprint:
    """合成一种材料的 THz 吸收谱：特征吸收带（高斯峰）+ 底噪。"""
    rng = np.random.default_rng(seed)
    freq = np.linspace(0.1, 3.0, n)          # 0.1-3 THz
    spec = np.zeros(n)
    for p in peak_freqs:
        spec += np.exp(-((freq - p) / 0.1) ** 2)  # 高斯吸收带
    spec += 0.02 * rng.standard_normal(n)
    spec = spec / (spec.max() + 1e-12)
    return MaterialFingerprint(name, freq, spec, list(peak_freqs), {"band": "THz"})


def build_library(seed: int = 0) -> list[MaterialFingerprint]:
    """构建材料指纹库（3 种材料，各有特征吸收带）。"""
    return [
        synthesize_material("MXene-Ti3C2", [0.8, 1.6], seed=seed),
        synthesize_material("石墨烯", [1.2, 2.4], seed=seed + 1),
        synthesize_material("硅", [0.4, 2.8], seed=seed + 2),
    ]


def match(observed: np.ndarray, library: list[MaterialFingerprint]) -> str:
    """观测谱与库内指纹做相关性匹配，返回最匹配材料名。"""
    def corr(a, b):
        return float(np.corrcoef(a, b)[0, 1])
    return max(library, key=lambda m: corr(observed, m.absorbance)).name


def observe(material: MaterialFingerprint, noise: float = 0.3, *, seed: int = 0) -> np.ndarray:
    """模拟观测：材料谱 + 高斯噪声。"""
    rng = np.random.default_rng(seed)
    return material.absorbance + noise * rng.standard_normal(material.absorbance.size)


def main() -> None:
    lib = build_library()
    print("材料指纹库：")
    for m in lib:
        print(f"  {m.name:<14} 特征吸收带 = {m.peak_freqs_thz} THz")
    for m in lib:
        acc = np.mean([match(observe(m, noise=0.3, seed=10 + i), lib) == m.name
                       for i in range(50)])
        print(f"{m.name} 识别准确率 = {acc * 100:.0f}%")


if __name__ == "__main__":
    main()
