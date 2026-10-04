# -*- coding: utf-8 -*-
"""OTA-ELM · PC 端零梯度轻量推理训练骨架（01-01）。

范式：极限学习机（Extreme Learning Machine, ELM）
  - 随机隐层投影 W/b 一次生成、不再更新；
  - 输出层 β 用伪逆（np.linalg.pinv）闭式解，无梯度反向传播；
  - 节点只做推理：定点矩阵乘 + LUT 激活，无浮点超越函数（exp/pow 仅用于
    离线生成查表，见 build_sigmoid_lut / build_exp_neg_lut）。

定位：在 PC 端用 numpy 训练一次、导出 int8 定点表，供 ESP32-S3 固件
  （firmware/elm_classifier/）以及任意支持 int8 乘加的处理器（如 IC-705 侧
  软件解调链）复用。特征层一律用物理量（SNR/包络/谱形），跨硬件可测可比；
  训练前按训练集做逐特征 z-score 标准化（mean/std 一并导出，推理侧复现）。

依赖：仅 numpy（无 torch/tf，无 LLM 调用）。

模型导出格式 EBIN v1（小端）：
  ┌────────┬──────────────┬────────────────────────────────────────────┐
  │ 偏移   │ 长度(字节)    │ 字段                                        │
  ├────────┼──────────────┼────────────────────────────────────────────┤
  │  0     │ 4            │ magic "ELM1" (0x45 0x4C 0x4D 0x31)          │
  │  4     │ 1            │ n_features (u8)                             │
  │  5     │ 2            │ n_hidden (u16 LE)                           │
  │  7     │ 1            │ n_outputs (u8)                              │
  │  8     │ 1            │ act_code (u8, 0x01=LUT sigmoid)             │
  │  9     │ 1            │ n_classes (u8, 恒等于 n_outputs，冗余校验)   │
  │ 10     │ 1            │ numeric_classes (u8, 1=数值类标签/0=字符串)  │
  │ 11     │ 4            │ s_x (f32 LE, 标准化输入量化尺度)             │
  │ 15     │ 4            │ s_w1 (f32 LE, 隐层权重量化尺度)              │
  │ 19     │ 4            │ s_pre (f32 LE, 预激活量化尺度=LUT 输入域)    │
  │ 23     │ 4            │ s_h (f32 LE, 恒 1/254)                      │
  │ 27     │ 4            │ s_b (f32 LE, 输出权重量化尺度)               │
  │ 31     │ 4            │ s_logit (f32 LE, logit 量化尺度)            │
  │ 35     │ 4            │ M1 (i32 LE, 第 1 层定点重量化乘子)           │
  │ 39     │ 4            │ S1 (i32 LE, 第 1 层定点重量化移位)           │
  │ 43     │ 4            │ M2 (i32 LE, 第 2 层定点重量化乘子)           │
  │ 47     │ 4            │ S2 (i32 LE, 第 2 层定点重量化移位)           │
  │ 51     │ nf*4         │ x_mean (f32 LE × nf，逐特征均值)             │
  │ 51+4nf │ nf*4         │ x_std  (f32 LE × nf，逐特征标准差)           │
  │ …      │ 256          │ SIG_LUT[i8 × 256]（sigmoid 激活查表）        │
  │ …      │ 512          │ EN_LUT[i16 LE × 256]（softmax 指数查表）     │
  │ …      │ nf*nh        │ W1_q[i8, 行主序 i*nh+j]                     │
  │ …      │ nh*4         │ B1_q[i32 LE × nh]（第 1 层偏置）             │
  │ …      │ nh*no        │ B_q[i8, 行主序 j*no+k]                      │
  │ …      │ no*4         │ OFF[i32 LE × no]（sigmoid 中心偏移折叠项）   │
  │ …      │ 变长         │ 类名：no × (u8 长度 + UTF-8 字节)            │
  └────────┴──────────────┴────────────────────────────────────────────┘
  定点推理语义见 QuantizedELM._predict_quantized() 与 README，PC 仿真与固件
  elm_infer.cpp 逐位对齐（同为 int64 累加 + 算术移位 + LUT）。

参考（思想层面，独立实现，不复制源码）：
  - G.-B. Huang, Q.-Y. Zhu, C.-K. Siew, "Extreme learning machine:
    theory and applications", Neurocomputing 70 (2006).（ELM 伪逆闭式解）
  - TensorFlow Lite Micro 定点重量化（multiplier/shift）思想（Apache-2.0）。
  - 超表面查表非线性思想：固定非线性搬到软件 = LUT 激活（本线自主做法）。
"""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# 常量与特征定义
# ---------------------------------------------------------------------------

# 特征层：8 个「物理量」特征，跨硬件可测可比（ESP32/SX1278 与 IC-705 通用）。
# 单位与量纲固定，训练/推理两侧必须严格对齐（见 README §特征工程）。
FEATURE_NAMES = [
    "env_mean",      # 0 包络均值（dBm 级，减去参考后无量纲）
    "env_std",       # 1 包络标准差（无量纲，波动强度）
    "env_skew",      # 2 包络偏度（无量纲）
    "env_kurt",      # 3 包络峭度（无量纲）
    "spec_peak_pos", # 4 谱峰位置（相对中心频偏，归一化 -1~+1）
    "spec_bw",       # 5 归一化占用带宽（0~1）
    "snr_db",        # 6 估计信噪比（dB）
    "rise_time",     # 7 归一化包络上升沿时间（0~1）
]
N_FEATURES = len(FEATURE_NAMES)

ACT_LUT_SIGMOID = 0x01  # EBIN act_code：LUT 化 sigmoid

# s_pre 的下限：防止全零/极小预激活时 LUT 输入域退化为 0（1 LSB = 1/32）。
_PRE_LSB_FLOOR = 1.0 / 32.0

_SIG_LUT_CACHE: dict[float, np.ndarray] = {}
_EN_LUT_CACHE: dict[float, np.ndarray] = {}


# ---------------------------------------------------------------------------
# LUT 构造（离线，允许浮点超越函数；固件侧不出现）
# ---------------------------------------------------------------------------

def build_sigmoid_lut(s_pre: float) -> np.ndarray:
    """构造 int8 sigmoid 查表。

    索引 i∈[0,255] ↔ 预激活 int8 q = i-128，真实值 v = q*s_pre。
    输出 int8 表项 = round((sigmoid(v)-0.5)*254)，落在 [-127,127]，
    即隐层输出 h 以「h = 0.5 + h_q/254」编码（s_h = 1/254 恒成立）。

    说明：固件只查表，不调用 exp；本函数仅离线执行一次。
    """
    key = round(s_pre, 12)
    if key in _SIG_LUT_CACHE:
        return _SIG_LUT_CACHE[key]
    q = np.arange(256, dtype=np.float64) - 128
    v = q * s_pre
    sig = _stable_sigmoid(v)
    lut = np.clip(np.round((sig - 0.5) * 254.0), -127, 127).astype(np.int8)
    _SIG_LUT_CACHE[key] = lut
    return lut


def build_exp_neg_lut(s_logit: float) -> np.ndarray:
    """构造 softmax 指数查表 EN[d] = round(32767*exp(-d*s_logit))，d∈[0,255]。

    真实差值 Δlogit = d*s_logit，表项 int16，最大 32767（EN[0]）。
    固件用整数求和 S=ΣEN，概率（千分比）= EN*1000/S，全程无浮点。
    """
    key = round(s_logit, 12)
    if key in _EN_LUT_CACHE:
        return _EN_LUT_CACHE[key]
    d = np.arange(256, dtype=np.float64)
    lut = np.clip(np.round(32767.0 * np.exp(-d * s_logit)), 0, 32767).astype(np.int16)
    _EN_LUT_CACHE[key] = lut
    return lut


def _stable_sigmoid(v: np.ndarray) -> np.ndarray:
    """数值稳定 sigmoid。"""
    v = np.asarray(v, dtype=np.float64)
    return np.where(v >= 0, 1.0 / (1.0 + np.exp(-v)), np.exp(v) / (1.0 + np.exp(v)))


# ---------------------------------------------------------------------------
# 定点工具
# ---------------------------------------------------------------------------

def best_mult_shift(ratio: float) -> tuple[int, int]:
    """把正实数 ratio 近似为 (M / 2^S)，M 为 int32 正数、S∈[0,31]。

    使 M 尽量接近 2^31 且逼近误差最小（TFLite 风格定点重量化）。
    返回 (M, S)。ratio<=0 时报错（语义上不允许）。
    """
    if ratio <= 0:
        raise ValueError(f"定点重量化要求 ratio>0，得到 {ratio}")
    best_m, best_s, best_err = 0, 0, float("inf")
    for s in range(32):
        m = ratio * (1 << s)
        if m < 1.0:
            continue
        m_round = round(m)
        if m_round >= (1 << 31):
            break  # 再大越界 int32
        err = abs(m_round / (1 << s) - ratio)
        if err < best_err:
            best_m, best_s, best_err = m_round, s, err
    if best_m == 0:
        raise ValueError(f"无法为 ratio={ratio} 找到合法 (M,S)")
    return best_m, best_s


def requant(acc: np.ndarray, mult: int, shift: int) -> np.ndarray:
    """定点重量化：y = (acc*mult + (1<<(shift-1))) >> shift（算术移位，四舍五入）。

    与固件 elm_infer.cpp 的 requant64 逐位一致：int64 累加后右移。
    numpy 的 >> 对负数实现为算术移位（floor 除法），两侧一致。
    """
    half = 1 << (shift - 1) if shift > 0 else 0
    return (acc.astype(np.int64) * np.int64(mult) + half) >> shift


def quantize_int8(x: np.ndarray, scale: float) -> np.ndarray:
    """浮点 → int8：q = clamp(floor(x*scale + 0.5), -128, 127)。

    与固件 elm_quantize 一致（floor(v*scale+0.5)，向 +∞ 取整）。
    """
    q = np.floor(x * scale + 0.5)
    return np.clip(q, -128, 127).astype(np.int8)


def _safe_scale(a: np.ndarray) -> float:
    """对称量化尺度 127/max|a|，全零时回退 1.0。"""
    m = float(np.abs(a).max())
    return 127.0 / m if m > 1e-12 else 1.0


# ---------------------------------------------------------------------------
# ELM 训练器
# ---------------------------------------------------------------------------

class ELM:
    """极限学习机：随机隐层投影 + 伪逆输出层。二分类/多分类均可。

    Parameters
    ----------
    n_hidden : 隐层神经元数（随机投影维度）。
    projection : "normal"（正态）或 "uniform"（均匀）随机投影。
    activation : "sigmoid" / "relu" / "lut_sigmoid"。
        lut_sigmoid 用 int8 查表 sigmoid 的等价浮点形式训练，使 β 直接适配
        固件会执行到的量化激活（训练与部署共用同一 s_pre 与 LUT，保证一致）。
    seed : 随机种子（可复现）。
    ridge : 岭回归系数 λ>0 时 β=(HᵀH+λI)⁻¹HᵀY，否则 β=pinv(H)Y。

    输入特征在 fit 时按训练集做逐特征 z-score 标准化（mean/std 存于对象，
    推理/导出时复现），避免大动态范围特征（如 dBm 级包络均值）主导随机投影。
    """

    def __init__(self, n_hidden: int = 64, projection: str = "normal",
                 activation: str = "lut_sigmoid", seed: int | None = None,
                 ridge: float = 0.0):
        if projection not in ("normal", "uniform"):
            raise ValueError("projection 必须是 'normal' 或 'uniform'")
        if activation not in ("sigmoid", "relu", "lut_sigmoid"):
            raise ValueError("activation 必须是 'sigmoid'/'relu'/'lut_sigmoid'")
        if n_hidden < 1:
            raise ValueError("n_hidden 必须 ≥1")
        self.n_hidden = int(n_hidden)
        self.projection = projection
        self.activation = activation
        self.seed = seed
        self.ridge = float(ridge)
        self.rng = np.random.default_rng(seed)

        self.W: np.ndarray | None = None   # (n_features, n_hidden)
        self.b: np.ndarray | None = None   # (n_hidden,)
        self.beta: np.ndarray | None = None  # (n_hidden, n_outputs)
        self.classes_: np.ndarray | None = None
        self.x_mean: np.ndarray | None = None  # (n_features,)
        self.x_std: np.ndarray | None = None   # (n_features,)
        self.s_pre: float | None = None   # 预激活量化尺度（lut_sigmoid 用）

    # -- 激活函数（浮点，训练用；lut_sigmoid 复刻量化语义）----------------
    def _activate(self, z: np.ndarray) -> np.ndarray:
        if self.activation == "sigmoid":
            return _stable_sigmoid(np.clip(z, -500, 500))
        if self.activation == "relu":
            return np.maximum(z, 0.0)
        # lut_sigmoid：与固件完全一致的量化 sigmoid（共用 self.s_pre）
        assert self.s_pre is not None, "lut_sigmoid 需要 fit() 先确定 s_pre"
        lut = build_sigmoid_lut(self.s_pre)
        q = quantize_int8(z, 1.0 / self.s_pre)
        return 0.5 + lut[q.astype(np.int64) + 128].astype(np.float64) / 254.0

    def _standardize(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        if self.x_mean is None or self.x_std is None:
            raise RuntimeError("模型尚未 fit，无标准化参数")
        return (X - self.x_mean) / self.x_std

    # -- 训练 -----------------------------------------------------------
    def fit(self, X: np.ndarray, y: np.ndarray) -> "ELM":
        """训练：标准化 → 随机投影 → 伪逆闭式解。

        X: (n_samples, n_features)；y: 整型标签（任意类标签，自动 one-hot）。
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        if X.ndim != 2 or X.shape[1] != N_FEATURES:
            raise ValueError(f"X 必须为 (n, {N_FEATURES})，得到 {X.shape}")
        if y.ndim != 1 or len(y) != X.shape[0]:
            raise ValueError("y 必须为长度 n 的一维标签")

        self.classes_ = np.unique(y)
        n_out = len(self.classes_)
        idx = np.searchsorted(self.classes_, y)
        Y = np.zeros((X.shape[0], n_out), dtype=np.float64)
        Y[np.arange(X.shape[0]), idx] = 1.0

        # 逐特征标准化（训练集统计）
        self.x_mean = X.mean(axis=0)
        self.x_std = np.maximum(X.std(axis=0), 1e-6)
        Xs = self._standardize(X)

        nf = X.shape[1]
        nh = self.n_hidden
        if self.projection == "normal":
            self.W = self.rng.standard_normal((nf, nh))
            self.b = self.rng.standard_normal(nh)
        else:  # uniform（Xavier 均匀区间）
            bound = math.sqrt(6.0 / (nf + nh))
            self.W = self.rng.uniform(-bound, bound, (nf, nh))
            self.b = self.rng.uniform(-bound, bound, nh)

        pre = Xs @ self.W + self.b
        # 预激活量化尺度：由实际分布决定，训练/导出/推理共用同一值
        self.s_pre = float(max(float(np.abs(pre).max()) / 120.0, _PRE_LSB_FLOOR))
        H = self._activate(pre)

        if self.ridge > 0:
            beta = np.linalg.solve(H.T @ H + self.ridge * np.eye(nh), H.T @ Y)
        else:
            beta = np.linalg.pinv(H) @ Y
        self.beta = beta
        return self

    # -- 推理（浮点）----------------------------------------------------
    def _logits(self, X: np.ndarray) -> np.ndarray:
        Xs = self._standardize(X)
        H = self._activate(Xs @ self.W + self.b)
        return H @ self.beta

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """软最大概率（浮点，PC 参考值）。"""
        z = self._logits(X)
        z = z - z.max(axis=1, keepdims=True)  # 稳定 softmax
        e = np.exp(np.clip(z, -500, 500))
        return e / e.sum(axis=1, keepdims=True)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """硬分类：返回类别标签（self.classes_ 的原始取值）。"""
        return self.classes_[np.argmax(self._logits(X), axis=1)]

    def score(self, X: np.ndarray, y: np.ndarray) -> float:
        """准确率 0~1。"""
        return float(np.mean(self.predict(X) == np.asarray(y)))

    # -- int8 定点导出 ---------------------------------------------------
    def export_int8(self, calib_X: np.ndarray) -> "QuantizedELM":
        """把训练好的 ELM 导出为 int8 定点模型（供固件查表推理）。"""
        if self.W is None or self.beta is None or self.s_pre is None:
            raise RuntimeError("请先 fit() 再导出")
        calib_X = np.asarray(calib_X, dtype=np.float64)
        if calib_X.shape[1] != N_FEATURES:
            raise ValueError(f"标定集必须 (n, {N_FEATURES})")
        return QuantizedELM.from_float(self, calib_X)


# ---------------------------------------------------------------------------
# int8 定点推理模型（PC 仿真，与固件逐位一致）
# ---------------------------------------------------------------------------

class QuantizedELM:
    """int8 定点 ELM 推理器：PC 侧仿真固件 elm_infer.cpp 的整数路径。

    保存全部量化表与尺度；predict() 走与固件完全相同的整数运算，
    用于一致性测试与导出。无浮点超越函数（仅构造 LUT 时一次性离线计算）。
    """

    def __init__(self, *, n_hidden, n_outputs, classes, x_mean, x_std,
                 s_x, s_w1, s_pre, s_h, s_b, s_logit, M1, S1, M2, S2,
                 sig_lut, en_lut, W1_q, B1_q, B_q, OFF):
        self.n_hidden = n_hidden
        self.n_outputs = n_outputs
        self.classes = np.asarray(classes)
        self.x_mean = np.asarray(x_mean, dtype=np.float64)
        self.x_std = np.asarray(x_std, dtype=np.float64)
        self.s_x, self.s_w1 = s_x, s_w1
        self.s_pre, self.s_h = s_pre, s_h
        self.s_b, self.s_logit = s_b, s_logit
        self.M1, self.S1, self.M2, self.S2 = M1, S1, M2, S2
        self.sig_lut = np.asarray(sig_lut, dtype=np.int8)
        self.en_lut = np.asarray(en_lut, dtype=np.int16)
        self.W1_q = np.asarray(W1_q, dtype=np.int8)
        self.B1_q = np.asarray(B1_q, dtype=np.int32)
        self.B_q = np.asarray(B_q, dtype=np.int8)
        self.OFF = np.asarray(OFF, dtype=np.int32)

    # -- 构造（从浮点 ELM）-----------------------------------------------
    @classmethod
    def from_float(cls, elm: "ELM", calib_X: np.ndarray) -> "QuantizedELM":
        if elm.activation != "lut_sigmoid":
            raise ValueError("固件仅实现 LUT sigmoid，请用 activation='lut_sigmoid' 训练")
        nf = calib_X.shape[1]
        nh = elm.n_hidden
        n_out = len(elm.classes_)

        # 与训练一致的标准化 + 同一 s_pre（保证 LUT 语义一致）
        Xs = (calib_X - elm.x_mean) / elm.x_std
        s_pre = elm.s_pre

        # 尺度：逐张量对称量化（zero_point=0）
        s_x = _safe_scale(Xs)                        # 标准化输入
        s_w1 = _safe_scale(elm.W)                    # 隐层权重
        s_h = 1.0 / 254.0                            # 恒成立（sigmoid LUT 定义）
        s_b = _safe_scale(elm.beta)                  # 输出权重

        # 量化表
        W1_q = quantize_int8(elm.W, s_w1)
        # acc1 = Σ x_q·W1_q + B1_q 的 LSB 尺度 = 1/(s_x*s_w1)，
        # 故偏置需放大：B1_q = round(b * s_x * s_w1)（不是除法！）
        B1_q = np.clip(np.floor(elm.b * (s_x * s_w1) + 0.5),
                       -(2 ** 31 - 1), 2 ** 31 - 1).astype(np.int32)
        B_q = quantize_int8(elm.beta, s_b)
        # sigmoid 中心偏移折叠项：OFF[k] = 127*Σ_j B_q[j,k]（推导见 README）
        OFF = (127 * B_q.sum(axis=0)).astype(np.int32)

        # logit 尺度：自适应，防止 argmax 饱和碰撞（在标定集上取 max|logit|）
        zf = elm._activate(Xs @ elm.W + elm.b) @ elm.beta
        s_logit = max(float(np.abs(zf).max()) / 120.0, _PRE_LSB_FLOOR) if zf.size else _PRE_LSB_FLOOR
        s_logit = float(s_logit)

        # 定点重量化乘子/移位
        # 第 1 层：acc1 的 LSB 尺度 = 1/(s_x*s_w1)，目标尺度 s_pre，
        #          故 ratio = (1/(s_x*s_w1)) / s_pre = 1/(s_x*s_w1*s_pre)
        M1, S1 = best_mult_shift(1.0 / (s_x * s_w1 * s_pre))
        # 第 2 层：zq 真实值 = logit，其 LSB 尺度 = s_h / s_b（推导见 README）
        M2, S2 = best_mult_shift((s_h / s_b) / s_logit)

        sig_lut = build_sigmoid_lut(s_pre)
        en_lut = build_exp_neg_lut(s_logit)

        return cls(n_hidden=nh, n_outputs=n_out, classes=elm.classes_,
                   x_mean=elm.x_mean, x_std=elm.x_std,
                   s_x=s_x, s_w1=s_w1, s_pre=s_pre, s_h=s_h, s_b=s_b,
                   s_logit=s_logit, M1=M1, S1=S1, M2=M2, S2=S2,
                   sig_lut=sig_lut, en_lut=en_lut, W1_q=W1_q, B1_q=B1_q,
                   B_q=B_q, OFF=OFF)

    # -- 定点推理（与固件 elm_run 逐位一致）-------------------------------
    def _predict_quantized(self, X: np.ndarray):
        """返回 (class_labels, probs_permille)。全部整数运算。"""
        X = np.asarray(X, dtype=np.float64)
        Xs = (X - self.x_mean) / self.x_std
        x_q = quantize_int8(Xs, self.s_x)  # (n, nf)

        # 第 1 层：int64 累加
        acc1 = (x_q.astype(np.int64) @ self.W1_q.astype(np.int64)
                + self.B1_q.astype(np.int64))          # (n, nh)
        hp_q = np.clip(requant(acc1, self.M1, self.S1), -128, 127).astype(np.int8)
        h_q = self.sig_lut[hp_q.astype(np.int64) + 128]  # (n, nh) int8

        # 第 2 层：int64 累加 + 中心偏移折叠
        zq = (h_q.astype(np.int64) @ self.B_q.astype(np.int64)
              + self.OFF.astype(np.int64))              # (n, n_out)
        l8 = np.clip(requant(zq, self.M2, self.S2), -128, 127).astype(np.int32)

        # softmax LUT（整数）
        lmax = l8.max(axis=1, keepdims=True)
        d = np.clip((lmax - l8).astype(np.int64), 0, 255)
        E = self.en_lut[d]                              # (n, n_out) int16
        S = E.sum(axis=1, keepdims=True).astype(np.int64)
        permille = (E.astype(np.int64) * 1000) // np.maximum(S, 1)  # 千分比
        clazz = self.classes[np.argmax(l8, axis=1)]     # 平局取索引小者
        return clazz, permille.astype(np.int32)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._predict_quantized(X)[0]

    def predict_proba_permille(self, X: np.ndarray) -> np.ndarray:
        """int8 定点 softmax 概率（千分比 0~1000，行和≈1000）。"""
        return self._predict_quantized(X)[1]

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.predict_proba_permille(X).astype(np.float64) / 1000.0

    def score(self, X: np.ndarray, y: np.ndarray) -> float:
        return float(np.mean(self.predict(X) == np.asarray(y)))

    # -- 导出 ------------------------------------------------------------
    def save_ebin(self, path: str | Path) -> None:
        """写出 EBIN v1 二进制模型文件（格式见模块 docstring）。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        class_bytes = [bytes([len(c)]) + c.encode("utf-8")
                       for c in map(str, self.classes)]
        # 类标签是否为数值（1=数值，0=字符串），往返还原 dtype 用
        numeric = 1 if np.issubdtype(self.classes.dtype, np.integer) else 0
        blob = struct.pack(
            "<4sBHBBBBffffffiiii",  # magic + dims + act/保留位 + 6 尺度 + M1S1M2S2
            b"ELM1", N_FEATURES, self.n_hidden, self.n_outputs,
            ACT_LUT_SIGMOID, self.n_outputs, numeric,
            self.s_x, self.s_w1, self.s_pre, self.s_h, self.s_b, self.s_logit,
            self.M1, self.S1, self.M2, self.S2,
        )
        blob += self.x_mean.astype(np.float32).tobytes()
        blob += self.x_std.astype(np.float32).tobytes()
        blob += self.sig_lut.astype(np.int8).tobytes()
        blob += self.en_lut.astype(np.int16).tobytes()
        blob += self.W1_q.astype(np.int8).tobytes()     # 行主序 (nf, nh)
        blob += self.B1_q.astype(np.int32).tobytes()
        blob += self.B_q.astype(np.int8).tobytes()      # 行主序 (nh, no)
        blob += self.OFF.astype(np.int32).tobytes()
        blob += b"".join(class_bytes)
        path.write_bytes(blob)

    @classmethod
    def load_ebin(cls, path: str | Path) -> "QuantizedELM":
        """读取 EBIN v1，做 magic/维度校验后还原对象。"""
        data = Path(path).read_bytes()
        (magic, nf, nh, no, act_code, n_classes, numeric,
         s_x, s_w1, s_pre, s_h, s_b, s_logit,
         M1, S1, M2, S2) = struct.unpack("<4sBHBBBBffffffiiii", data[:51])
        if magic != b"ELM1":
            raise ValueError(f"magic 错误：{magic!r}（期望 b'ELM1'）")
        if act_code != ACT_LUT_SIGMOID:
            raise ValueError(f"不支持 act_code=0x{act_code:02X}")
        if nf != N_FEATURES or no != n_classes:
            raise ValueError(f"维度校验失败 nf={nf} no={no} n_classes={n_classes}")
        off = 51
        x_mean = np.frombuffer(data, np.float32, nf, off); off += nf * 4
        x_std = np.frombuffer(data, np.float32, nf, off); off += nf * 4
        sig_lut = np.frombuffer(data, np.int8, 256, off); off += 256
        en_lut = np.frombuffer(data, np.int16, 256, off); off += 256 * 2
        W1_q = np.frombuffer(data, np.int8, nf * nh, off).reshape(nf, nh)
        off += nf * nh
        B1_q = np.frombuffer(data, np.int32, nh, off); off += nh * 4
        B_q = np.frombuffer(data, np.int8, nh * no, off).reshape(nh, no)
        off += nh * no
        OFF = np.frombuffer(data, np.int32, no, off); off += no * 4
        names = []
        for _ in range(no):
            ln = data[off]; off += 1
            names.append(data[off:off + ln].decode("utf-8")); off += ln
        classes = np.array([int(s) for s in names] if numeric else names)
        return cls(n_hidden=nh, n_outputs=no, classes=np.asarray(classes),
                   x_mean=x_mean, x_std=x_std,
                   s_x=s_x, s_w1=s_w1, s_pre=s_pre, s_h=s_h, s_b=s_b,
                   s_logit=s_logit, M1=M1, S1=S1, M2=M2, S2=S2,
                   sig_lut=sig_lut, en_lut=en_lut, W1_q=W1_q, B1_q=B1_q,
                   B_q=B_q, OFF=OFF)

    def to_c_header(self, path: str | Path) -> str:
        """生成 C 头文件（固件编译期嵌入模型，零运行时解析）。返回文本。"""
        nh, no = self.n_hidden, self.n_outputs
        nf = N_FEATURES
        # 输入预量化系数：x_q = floor(x*A + B + 0.5)，A = s_x/std, B = -mean*s_x/std
        x_a = self.s_x / self.x_std
        x_b = -self.x_mean * x_a

        def c_array(name, dtype, vals, per_line=16):
            body = ""
            for i in range(0, len(vals), per_line):
                chunk = ", ".join(str(int(v)) if "int" in dtype else repr(float(v))
                                  for v in vals[i:i + per_line])
                body += f"\n    {chunk},"
            return f"static const {dtype} {name}[] = {{{body.rstrip(',')}\n}};"

        lines = []
        lines.append("/* 由 tools/elm_train.py 自动生成，勿手改。")
        lines.append(" * OTA-ELM int8 定点模型（EBIN v1 对应的 C 嵌入表）。")
        lines.append(" * 生成：python tools/elm_train.py（numpy，无 LLM 依赖）")
        lines.append(" * 语义与定点推理步骤见 firmware/elm_classifier/README.md。")
        lines.append(" */")
        lines.append("#ifndef ELM_MODEL_H")
        lines.append("#define ELM_MODEL_H")
        lines.append("#include <stdint.h>")
        lines.append("")
        lines.append(f"#define ELM_N_FEATURES {nf}")
        lines.append(f"#define ELM_N_HIDDEN   {nh}")
        lines.append(f"#define ELM_N_OUTPUTS  {no}")
        lines.append("")
        lines.append("/* 输入预量化系数：x_q = floor(x*A + B + 0.5)（double，非超越函数） */")
        lines.append(c_array("ELM_X_A", "double", x_a))
        lines.append(c_array("ELM_X_B", "double", x_b))
        lines.append("")
        lines.append("/* 标准化统计（文档/参考） */")
        lines.append(c_array("ELM_X_MEAN", "double", self.x_mean))
        lines.append(c_array("ELM_X_STD", "double", self.x_std))
        lines.append("")
        lines.append("/* 定点重量化参数（推理全程整数） */")
        lines.append(c_array("ELM_M1", "int32_t", [self.M1]))
        lines.append(c_array("ELM_S1", "int32_t", [self.S1]))
        lines.append(c_array("ELM_M2", "int32_t", [self.M2]))
        lines.append(c_array("ELM_S2", "int32_t", [self.S2]))
        lines.append("")
        lines.append("/* 类名（下标 = 输出列） */")
        lines.append('static const char* const ELM_CLASS_NAMES[] = { '
                     + ", ".join(f'"{c}"' for c in self.classes) + " };")
        lines.append("")
        lines.append("/* sigmoid 激活 LUT：index = hpre_q + 128，值 = (sigmoid-0.5)*254 */")
        lines.append(c_array("ELM_SIG_LUT", "int8_t", self.sig_lut.flatten()))
        lines.append("")
        lines.append("/* softmax 指数衰减 LUT：index = d = l8max - l8，表项见 build_exp_neg_lut */")
        lines.append(c_array("ELM_EN_LUT", "int16_t", self.en_lut.flatten()))
        lines.append("")
        lines.append("/* 第 1 层权重 W1_q[i*ELM_N_HIDDEN + j]，int8 */")
        lines.append(c_array("ELM_W1_Q", "int8_t", self.W1_q.flatten()))
        lines.append("")
        lines.append("/* 第 1 层偏置 B1_q[j]（int32，尺度 = s_x*s_w1） */")
        lines.append(c_array("ELM_B1_Q", "int32_t", self.B1_q.flatten()))
        lines.append("")
        lines.append("/* 第 2 层权重 B_q[j*ELM_N_OUTPUTS + k]，int8（尺度 = s_b） */")
        lines.append(c_array("ELM_B_Q", "int8_t", self.B_q.flatten()))
        lines.append("")
        lines.append("/* sigmoid 中心偏移折叠项 OFF[k] = 127*Σ_j B_q[j,k]（int32） */")
        lines.append(c_array("ELM_OFF", "int32_t", self.OFF.flatten()))
        lines.append("")
        lines.append("#endif /* ELM_MODEL_H */")
        text = "\n".join(lines) + "\n"
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return text


# ---------------------------------------------------------------------------
# 合成频谱特征数据集（演示：信号类别 A/B/C）
# ---------------------------------------------------------------------------

def make_demo_dataset(n_per_class: int = 240, seed: int = 42,
                      train_ratio: float = 0.75):
    """合成三类信号（A/B/C）的 8 维物理量特征，模拟不同 SF/带宽的包络统计。

    类别语义（诚实标注为合成，非实测）：
      A = SF7/BW125 型（快 chirp）：短上升沿、宽占用带宽、高 SNR、正偏度
      B = SF9/BW125 型（中 chirp）：各项居中
      C = SF12/BW125 型（慢 chirp/深弱）：长上升沿、窄带宽、低 SNR、负偏度
    返回 (X_train, y_train, X_test, y_test, class_names)。
    """
    rng = np.random.default_rng(seed)
    centers = {
        "A": np.array([-85.0, 6.0, 0.8, 3.2, 0.15, 0.28, 14.0, 0.08]),
        "B": np.array([-92.0, 4.0, 0.2, 2.8, 0.00, 0.12, 7.0, 0.22]),
        "C": np.array([-98.0, 2.5, -0.3, 2.5, -0.10, 0.05, 0.0, 0.50]),
    }
    spreads = {
        "A": np.array([2.0, 1.0, 0.25, 0.4, 0.06, 0.05, 2.5, 0.03]),
        "B": np.array([2.0, 0.9, 0.25, 0.4, 0.06, 0.04, 2.5, 0.04]),
        "C": np.array([2.0, 0.7, 0.25, 0.4, 0.05, 0.02, 2.5, 0.06]),
    }
    X, y = [], []
    for name in ["A", "B", "C"]:
        c, s = centers[name], spreads[name]
        X.append(c + s * rng.standard_normal((n_per_class, N_FEATURES)))
        y.extend([name] * n_per_class)
    X = np.vstack(X)
    y = np.array(y)  # 字符串标签 "A"/"B"/"C"（np.unique 字典序 = A<B<C）

    perm = rng.permutation(len(y))
    X, y = X[perm], y[perm]
    n_train = int(len(y) * train_ratio)
    return (X[:n_train], y[:n_train], X[n_train:], y[n_train:],
            ["A", "B", "C"])


# ---------------------------------------------------------------------------
# 演示入口（python tools/elm_train.py）
# ---------------------------------------------------------------------------

def run_demo(n_per_class: int = 240, n_hidden: int = 64, seed: int = 42,
             out_ebin: str | Path = "elm_demo_model.ebin",
             out_header: str | Path | None = None) -> dict:
    """训练 → 量化 → 一致性评估 → 导出，返回关键指标 dict（供测试断言）。"""
    repo_root = Path(__file__).resolve().parents[1]
    out_ebin = Path(out_ebin)
    if not out_ebin.is_absolute():
        out_ebin = repo_root / "tools" / out_ebin

    Xtr, ytr, Xte, yte, names = make_demo_dataset(n_per_class, seed)
    model = ELM(n_hidden=n_hidden, projection="normal",
                activation="lut_sigmoid", seed=seed)
    model.fit(Xtr, ytr)

    acc_f = model.score(Xte, yte)

    q = model.export_int8(Xtr)  # 用训练集标定量化尺度
    pred8 = q.predict(Xte)
    acc8 = float(np.mean(pred8 == yte))

    # 一致性：argmax 一致率 + softmax 近似误差（千分比 → 概率）
    agree = float(np.mean(pred8 == model.predict(Xte)))
    p_f = model.predict_proba(Xte)
    p8 = q.predict_proba(Xte)
    approx_err = float(np.max(np.abs(p8 - p_f)))
    conf = q.predict_proba_permille(Xte)
    conf_argmax = conf[np.arange(conf.shape[0]), np.argmax(conf, axis=1)]
    assert conf_argmax.min() >= 0 and conf_argmax.max() <= 1000

    q.save_ebin(out_ebin)
    header_path = None
    if out_header is not None:
        header_path = Path(out_header)
        if not header_path.is_absolute():
            header_path = repo_root / out_header
        q.to_c_header(header_path)

    print("=" * 60)
    print("OTA-ELM 演示 · ESP32-S3 LoRa 轻量推理（01-01）")
    print("=" * 60)
    print(f"隐层神经元   : {n_hidden}（{model.projection} 随机投影, {model.activation} 激活）")
    print(f"数据         : 合成频谱特征 {n_per_class * 3} 样本 / 3 类（A/B/C）")
    print(f"训练样本     : {Xtr.shape[0]}   测试样本 : {Xte.shape[0]}")
    print(f"特征维度     : {N_FEATURES}（物理量：SNR/包络/谱形）")
    print("-" * 60)
    print(f"浮点模型准确率   : {acc_f * 100:.2f}%")
    print(f"int8 定点准确率  : {acc8 * 100:.2f}%")
    print(f"浮点/int8 argmax 一致率 : {agree * 100:.2f}%")
    print(f"softmax LUT 近似误差(最大) : {approx_err:.4f}（标注阈值 ≤0.05）")
    print("-" * 60)
    print(f"模型文件   : {out_ebin}")
    if header_path:
        print(f"C 头文件   : {header_path}（固件编译期嵌入）")
    print(f"类别标签   : {names}")
    print("导出完成。固件烧录见 firmware/elm_classifier/README.md")
    return {"acc_float": acc_f, "acc_int8": acc8, "argmax_agreement": agree,
            "softmax_max_abs_err": approx_err, "ebin": str(out_ebin),
            "header": str(header_path) if header_path else None}


def main() -> None:
    ap = argparse.ArgumentParser(description="OTA-ELM PC 端训练 + int8 导出")
    ap.add_argument("--n-per-class", type=int, default=240)
    ap.add_argument("--n-hidden", type=int, default=64)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-ebin", default="elm_demo_model.ebin")
    ap.add_argument("--out-header", default="firmware/elm_classifier/elm_model.h")
    args = ap.parse_args()
    run_demo(args.n_per_class, args.n_hidden, args.seed,
             args.out_ebin, args.out_header)


if __name__ == "__main__":
    main()
