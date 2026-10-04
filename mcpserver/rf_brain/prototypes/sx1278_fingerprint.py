"""R18 · SX1278 物理层指纹原型（RF 前端固有特征做设备信任根）

灵感：digest-g3-1 授粉点① · 论文 2608.18642（IriSig-Spoof，卫星 RF 指纹 97.75%）。

RF 前端的制造级差异（晶振偏移 / I/Q 不平衡）具有唯一性与鲁棒性，可作不可克隆的
设备信任根。本原型用合成信号演示三个特征的提取、稳定性与判别力：

  - F1 载波频率偏移（晶振 ppm 差异，相位漂移率估计）
  - F2 I/Q 增益失配（实虚部能量比）
  - F3 I/Q 相位失配（实虚部相关）

流程：为每个「设备」生成固有参数 → 发射含损伤的单音 → 提取特征 → 近邻识别；
量化类内散布 vs 类间距离（稳定性）与识别准确率。

（功放非线性 AM-AM 压缩需双音/功率扫描测量，见 docs/sx1278-puf-设计.md §2，本原型以
晶振偏移 + I/Q 失配三个可闭环特征演示判别力。）

运行：python -m mcpserver.rf_brain.prototypes.sx1278_fingerprint
"""
from __future__ import annotations

import numpy as np


def synthesize_device_params(n_devices: int, *, seed: int = 0) -> np.ndarray:
    """每台设备的固有指纹参数 [freq_offset_hz, iq_gain, iq_phase]。"""
    rng = np.random.default_rng(seed)
    return np.column_stack([
        rng.normal(0.0, 8.0, n_devices),     # 晶振频偏 Hz（相对 1kHz 载波）
        rng.normal(1.0, 0.03, n_devices),    # I/Q 增益失配
        rng.normal(0.0, 0.05, n_devices),    # I/Q 相位失配（rad）
    ])


def transmit(params: np.ndarray, n_samples: int, *, sr: float = 1e6,
             meas_noise: float = 1e-3, seed: int = 0) -> np.ndarray:
    """该设备发射一个含损伤的单音（复基带）。

    params: (freq_offset_hz, iq_gain, iq_phase)
    返回复信号：I/Q 失衡 + 晶振频偏 + 测量噪声。
    """
    rng = np.random.default_rng(seed)
    f_off, g, phi = params
    t = np.arange(n_samples) / sr
    x = np.exp(1j * 2 * np.pi * (1000.0 + f_off) * t)   # 单音 + 频偏
    # I/Q 不平衡：I 增益 g、Q 相位 φ
    y = g * np.real(x) + 1j * np.imag(x) * np.exp(1j * phi)
    return y + meas_noise * (rng.standard_normal(n_samples) + 1j * rng.standard_normal(n_samples))


def extract_features(sig: np.ndarray, *, sr: float = 1e6) -> np.ndarray:
    """提取三特征 [频偏Hz, I/Q增益比, I/Q相位失配]。"""
    n = sig.size
    # F1 频偏：相位差分平均 → 瞬时频率
    inst = np.angle(sig[1:] * np.conj(sig[:-1]))
    f_est = float(np.mean(inst)) * sr / (2 * np.pi)
    f_off = f_est - 1000.0
    # F2 I/Q 增益比
    iq_gain = float(np.mean(np.real(sig) ** 2) / (np.mean(np.imag(sig) ** 2) + 1e-12))
    # F3 I/Q 相位失配：实虚部归一化相关（相位失配引入相关）
    I = np.real(sig) - np.mean(np.real(sig))
    Q = np.imag(sig) - np.mean(np.imag(sig))
    iq_phase = float(np.mean(I * Q) / (np.std(I) * np.std(Q) + 1e-12))
    return np.array([f_off, iq_gain, iq_phase])


def identify(features: np.ndarray, templates: np.ndarray) -> int:
    """近邻识别：返回最接近的设备模板下标。"""
    return int(np.argmin(np.linalg.norm(templates - features, axis=1)))


def main() -> None:
    n_devices = 8
    params = synthesize_device_params(n_devices)
    templates, test_feats, test_labels = [], [], []
    for d in range(n_devices):
        feats = [extract_features(transmit(params[d], 8192, seed=1000 + d + r))
                 for r in range(5)]
        templates.append(np.mean(feats, axis=0))
        for r in range(20):
            test_feats.append(extract_features(transmit(params[d], 8192, seed=2000 + d * 100 + r)))
            test_labels.append(d)
    templates = np.array(templates)
    intra = [np.linalg.norm(templates[l] - test_feats[i]) for i, l in enumerate(test_labels)]
    inter = [np.linalg.norm(templates[a] - templates[b])
             for a in range(n_devices) for b in range(a + 1, n_devices)]
    acc = np.mean([identify(f, templates) == l for f, l in zip(test_feats, test_labels)])
    print(f"类内平均距离 = {np.mean(intra):.4f}   类间平均距离 = {np.mean(inter):.4f}")
    print(f"判别比（类间/类内） = {np.mean(inter) / (np.mean(intra) + 1e-12):.1f}×")
    print(f"识别准确率 = {acc * 100:.1f}%")


if __name__ == "__main__":
    main()
