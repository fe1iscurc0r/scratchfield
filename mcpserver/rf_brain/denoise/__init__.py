"""时窗 Noise2Noise 自监督盲去噪 + reservoir 漂移补偿（D-01/D-02 · DELTA 线）

旁路模块：不触碰 rf_brain 主流程（feature_extractor / spectrum / demod_ref 只读引用），
纯 numpy 实现，为 ESP32-S3 MCU 移植留余地（小模型参数量 / 固定随机种子可复现）。

子模块:
  synthetic  合成信号与噪声生成（正弦/扫频/脉冲 × 高斯/椒盐/射频包络，无标签训练对）
  n2n        Noise2Noise 小 MLP 去噪（train / denoise）
  eval        去噪前后 SNR / 波形对比指标表
  reservoir  Echo State Network 简化版（固定随机 reservoir + 岭回归读出层）
  drift      漂移模拟 + RC 补偿流程（读出层自适应更新）
  bench      漂移前后指标对比 + 去噪→RC 端到端
  demo       自测/演示入口（--simulate 接收 spectrum 包络做演示去噪）
"""
from __future__ import annotations

__all__ = ["synthetic", "n2n", "eval", "reservoir", "drift", "bench", "demo"]
