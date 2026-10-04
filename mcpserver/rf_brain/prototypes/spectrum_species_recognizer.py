"""R28 · 频谱感知物种识别原型（物理约束注入低信噪比推断）

灵感：digest-g1-2 授粉点② · 论文 2608.18191（ChiroEcho，地理信息扩展分类器）。

思想：低信噪比下，把「频率依赖传播 / 天线方向图」等物理先验注入推断，纠正观测的
频率响应畸变，提升未见条件（距离/信道变化）下的识别率。

原型：多个「信号物种」各有频谱模板 S_s(f)；观测 y = S_s(f)·A(f,θ) + 噪声，其中
A(f,θ)=exp(-θ·f) 是已知的频率依赖衰减（物理模型），θ 为条件（如距离）。
  - 无物理先验：直接匹配 y 与模板 S_s（忽略衰减）→ 条件变化后失配
  - 有物理先验：用已知 A(f,θ) 反卷积纠正 y 后再匹配 → 跨条件鲁棒

对比低 SNR 下的识别准确率（尤其未见条件 θ_test）。

运行：python -m mcpserver.rf_brain.prototypes.spectrum_species_recognizer
"""
from __future__ import annotations

import numpy as np


def make_templates(F: int = 32) -> np.ndarray:
    """3 个物种的频谱模板（低通/带通/高通形状）。"""
    f = np.arange(F) / F
    tpl = np.stack([
        np.exp(-((f - 0.2) / 0.15) ** 2),   # 低通
        np.exp(-((f - 0.5) / 0.1) ** 2),    # 带通
        np.exp(-((f - 0.8) / 0.15) ** 2),   # 高通
    ])
    return tpl / np.linalg.norm(tpl, axis=1, keepdims=True)  # 单位范数模板


def attenuation(F: int, theta: float) -> np.ndarray:
    """频率依赖衰减 A(f,θ)=exp(-θ·f)，物理传播模型。"""
    return np.exp(-theta * np.arange(F) / F)


def observe(species: int, templates: np.ndarray, theta: float, noise_std: float, *,
            seed: int = 0) -> np.ndarray:
    """观测：模板 × 衰减 + 高斯噪声。"""
    rng = np.random.default_rng(seed)
    y = templates[species] * attenuation(templates.shape[1], theta)
    return y + noise_std * rng.standard_normal(templates.shape[1])


def classify_no_physics(y: np.ndarray, templates: np.ndarray) -> int:
    """无物理先验：直接匹配模板（忽略衰减）。"""
    return int(np.argmin([np.linalg.norm(y - t) for t in templates]))


def classify_with_physics(y: np.ndarray, templates: np.ndarray, theta: float) -> int:
    """有物理先验：用衰减模型 A(θ) 预测每个物种在此条件下的观测，再匹配。"""
    A = attenuation(templates.shape[1], theta)
    preds = [A * t for t in templates]  # 物理模型预测的观测
    return int(np.argmin([np.linalg.norm(y - p) for p in preds]))


def accuracy(classify, templates, theta, noise_std, n_trials, *, seed=0):
    rng = np.random.default_rng(seed)
    hits = 0
    for i in range(n_trials):
        sp = rng.integers(0, 3)
        y = observe(sp, templates, theta, noise_std, seed=1000 + i)
        hits += classify(y, templates) == sp
    return hits / n_trials


def main() -> None:
    templates = make_templates()
    theta_test = 4.0
    for noise in (0.1, 0.5, 1.0):
        acc_no = accuracy(lambda y, t: classify_no_physics(y, t), templates, theta_test, noise, 1000)
        acc_ph = accuracy(lambda y, t: classify_with_physics(y, t, theta_test), templates, theta_test, noise, 1000)
        print(f"噪声 σ={noise:<4}  无物理先验 = {acc_no*100:.1f}%   有物理先验 = {acc_ph*100:.1f}%")


if __name__ == "__main__":
    main()
