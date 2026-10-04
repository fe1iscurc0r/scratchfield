# -*- coding: utf-8 -*-
"""AC-02 · OTA-ELM 查表推理（ESP32-S3 轻量推理）Python 参考正本。

授粉来源（设计参照级，非代码移植）：
  arXiv 2608.27137（OTA-ELM + 非线性超表面）——核心思想：
  (1) ELM 单隐层：输入权重固定随机（不训练），仅输出权重解析求解（岭回归），
      无梯度反向传播，训练/部署成本极低，适合资源受限设备；
  (2) 超表面的固定非线性响应可"预先测量/计算成查找表"→ MCU 侧把激活函数
      tanh 预计算为 256 项 8-bit LUT，推理时查表替代三角函数计算。
  本实现只取该设计思想，为独立实现，未引用论文代码/数据。

任务（与 AC-01 衔接的频谱特征分类）：对收包字节流的 |差分| 序列做 8 个
4 点窗能量和（粗粒度"频谱"描述子）→ 三类收包分类（NORMAL/NOISE/BAD_FRAME，
mock 合成数据沿用 mulfree_features.make_mock_packet，诚实标注）。

双路径推理（同权重、同输入语义）：
  float 路径：x_real → tanh(Wx+b) → 岭回归输出层（参考实现）
  LUT 路径  ：Q 定点 x_q → 整数 MAC → LUT[idx] 查表激活 → Q 定点输出层
精度验收：LUT 版与 float 版测试精度差 ≤5%（工单验收线）。

推理热路径不变量（可执行验收）：
  LUT 推理函数只用 加/减/移位/比较/查表/整数乘法（int MAC 允许乘法——
  AC-01 的"无乘法"约束只针对特征提取器；本单的卖点是 LUT 替代 tanh 计算）。
"""
from __future__ import annotations

import math
import random
import timeit

from mulfree_features import (
    CLASS_NAMES,
    MAGIC0,
    MAGIC1,
    WINDOW,
    abs_diffs_31,
    make_mock_packet,
    packet_window,
)

# ---------------- 常量（与生成的 C++ 头逐项一致） ----------------

FEATURE_DIM = 8          # 4 窗能量 + 尖峰计数 + 均值字节 + 帧长 + 帧头
HIDDEN = 32              # 隐层节点数
CLASS_N = 3

X_SCALE_BITS = 7         # x 定点：x_q = round(x_real · 2^7)（int16 承载）
W_SCALE_BITS = 8         # 输入权重定点：w_q = round(w · 2^8)（int16）
OUT_SCALE_BITS = 8       # 输出权重定点：wout_q = round(wout · 2^8)（int16）
H_SCALE = 127            # 隐层输出 int8：h_real = h_q / 127

LUT_N = 256              # tanh 查找表项数（8-bit 索引）
LUT_U_STEP_BITS = 5      # u_real = idx / 2^5（覆盖 ±4.0，tanh 已饱和）
LUT_OUT_MAX = 127

TRAIN_SEED_W = 20260902      # 输入权重随机种子（固定随机，不训练——ELM 要义）
TRAIN_SEED_DATA = 20260829   # 训练集种子（复用 AC-01 mock 生成器）
TEST_SEED_DATA = 20260830
PER_CLASS_TRAIN = 200
PER_CLASS_TEST = 50
RIDGE_LAMBDA = 1e-3

# ---------------- 特征（收包 → 8 维） ----------------

def elm_features_real(buf):
    """收包字节流 → 8 维特征（float 实数语义）。

    f0..f3  4 个 8 点窗 |差分| 能量和 /16（0..127.5，粗粒度"频谱"能量）
    f4      尖峰计数（|差分|>=32）/4（0..7.75）
    f5      窗内均值字节 Σext/64（0..127.5）
    f6      帧长（0..255）
    f7      帧头旗标（0/1）
    窗口对齐/延拓语义复用 mulfree_features.packet_window（与 AC-01 同源）。
    特征提取本身只用 加/减/移位/比较（量化到定点才引入乘法常数）。
    """
    ext, has_header, n = packet_window(buf)
    absd = abs_diffs_31(ext)
    feats = []
    for j in range(4):
        base = j * 8
        s = 0
        for i in range(8):
            if base + i < WINDOW - 1:
                s += absd[base + i]
        feats.append(s / 16.0)
    n_spike = 0
    for d in absd:
        if d >= 32:
            n_spike += 1
    feats.append(n_spike / 4.0)
    feats.append(sum(ext) / 64.0)
    feats.append(float(min(n, 255)))
    feats.append(1.0 if has_header else 0.0)
    return feats


def quantize_x(feats):
    """x_q = round(x_real · 2^7)，int16 语义（Q7 定点，不限于 ±1）。"""
    return [max(-32768, min(32767, int(round(f * (1 << X_SCALE_BITS)))))
            for f in feats]


# ---------------- ELM 训练（纯 stdlib：岭回归解析解，无反向传播） ----------------

def _draw_weights(rng):
    """固定随机输入权重 W(H×D) 与偏置 b(H)：ELM 要义——只随机一次不训练。"""
    W = [[rng.uniform(-1.0, 1.0) for _ in range(FEATURE_DIM)]
         for _ in range(HIDDEN)]
    b = [rng.uniform(-0.3, 0.3) for _ in range(HIDDEN)]
    return W, b


def _quantize_weights(W, b):
    """w_q = round(w·2^8)（int16 语义）；LUT 路径与 float 路径共用同一组
    实数权重的定点化身——两条路径的差异只在激活与输出层的数值形态。"""
    W_q = [[max(-32768, min(32767, int(round(w * (1 << W_SCALE_BITS)))))
            for w in row] for row in W]
    b_q = [max(-32768, min(32767, int(round(v * (1 << W_SCALE_BITS)))))
           for v in b]
    return W_q, b_q


def _solve_ridge(A, Y, lam):
    """岭回归解析解 Wout = (AᵀA + λI)⁻¹ AᵀY（Gauss-Jordan，纯 stdlib）。

    A: N×M，Y: N×C → 返回 Wout: C×M（Wout[c][j]）。ELM 的"训练"仅此一步
    （无梯度迭代，授粉点要义）。
    """
    n, m = len(A), len(A[0])
    c = len(Y[0])
    ata = [[sum(A[k][i] * A[k][j] for k in range(n)) for j in range(m)]
           for i in range(m)]
    for i in range(m):
        ata[i][i] += lam
    aty = [[sum(A[k][i] * Y[k][j] for k in range(n)) for j in range(c)]
           for i in range(m)]
    # Gauss-Jordan：对 [AᵀA | AᵀY] 做行变换，右块即为解（按列对应类别）
    aug = [ata[i] + aty[i] for i in range(m)]
    total = m + c
    for col in range(m):
        piv = max(range(col, m), key=lambda r: abs(aug[r][col]))
        aug[col], aug[piv] = aug[piv], aug[col]
        pv = aug[col][col]
        aug[col] = [v / pv for v in aug[col]]
        for r in range(m):
            if r != col and aug[r][col] != 0:
                f = aug[r][col]
                aug[r] = [aug[r][j] - f * aug[col][j] for j in range(total)]
    return [[aug[j][m + cix] for j in range(m)] for cix in range(c)]


def _forward_hidden_float(x, W, b):
    """float 隐层：h = tanh(Wx+b)（参考实现，真 tanh）。"""
    return [math.tanh(sum(W[j][i] * x[i] for i in range(FEATURE_DIM)) + b[j])
            for j in range(HIDDEN)]


def _forward_hidden_int(x_q, W_q, b_q):
    """LUT 隐层：整数 MAC → 移位 → 查表（推理热路径）。

    acc 实数语义 = Σ w·x + b（w/2^8 · x/2^7 → acc/2^15）；
    idx = clamp(acc >> 10, -128, 127) → u = idx/2^5 覆盖 ±4.0（tanh 饱和区）。
    """
    out = []
    for j in range(HIDDEN):
        acc = b_q[j] << X_SCALE_BITS            # b = b_q/2^8 → acc 域 = b·2^15 = b_q<<7
        for i in range(FEATURE_DIM):
            acc += W_q[j][i] * x_q[i]
        idx = acc >> LUT_U_STEP_BITS
        if idx < -128:
            idx = -128
        if idx > 127:
            idx = 127
        out.append(TANH_LUT[idx + 128])
    return out


def build_tanh_lut():
    """预计算 256 项 tanh LUT（8-bit 输出 Q7：h_real = h_q/127）。

    超表面→LUT 的 MCU 映射：固定非线性响应一次性预计算，推理时零计算。
    """
    lut = []
    for j in range(LUT_N):
        u = (j - 128) / (1 << LUT_U_STEP_BITS)
        v = max(-1.0, min(1.0, math.tanh(u)))
        lut.append(max(-LUT_OUT_MAX, min(LUT_OUT_MAX, int(round(v * H_SCALE)))))
    return lut


TANH_LUT = build_tanh_lut()   # 模块级常量表（与生成器导出的 C++ 表逐项一致）


def lut_error_table():
    """LUT 量化误差表（README 用）：逐项 |LUT/127 - tanh(u)| 的 max/mean，
    以及 LUT 节点间的连续误差界（半步长估计）。"""
    errs = []
    for j in range(LUT_N):
        u = (j - 128) / (1 << LUT_U_STEP_BITS)
        errs.append(abs(TANH_LUT[j] / H_SCALE - math.tanh(u)))
    errs.sort()
    mean = sum(errs) / LUT_N
    return {
        "max_abs": errs[-1],
        "mean_abs": mean,
        "p99_abs": errs[int(LUT_N * 0.99) - 1],
        "u_step": 1.0 / (1 << LUT_U_STEP_BITS),
        "saturation_u": 127 / (1 << LUT_U_STEP_BITS),
        "theoretical_bound": 0.5 / (1 << LUT_U_STEP_BITS) + 0.5 / H_SCALE,
    }


# ---------------- 双路径推理 ----------------

def infer_float(feats, W, b, Wout):
    """float 全路径推理（参考实现）：返回 3 类 logits。"""
    h = _forward_hidden_float(feats, W, b)
    h.append(1.0)   # 偏置列
    return [sum(Wout[c][j] * h[j] for j in range(HIDDEN + 1))
            for c in range(CLASS_N)]


def infer_lut(x_q, W_q, b_q, Wout_q):
    """LUT 全路径推理（MCU 热路径）：返回 3 类整数 logits。

    输出层：h_qq = [h_q...] + [127]（偏置列实数 1.0 的定点化身），
    logit 实数 = Σ wout_q·h_qq / (2^8 · 127)，argmax 语义下无需除法。
    """
    h = _forward_hidden_int(x_q, W_q, b_q)
    h.append(H_SCALE)
    logits = []
    for c in range(CLASS_N):
        s = 0
        for j in range(HIDDEN + 1):
            s += Wout_q[c][j] * h[j]
        logits.append(s)
    return logits


def argmax3(logits):
    best = 0
    for c in range(1, len(logits)):
        if logits[c] > logits[best]:
            best = c
    return best


# ---------------- 端到端：训练 + 评估 + 资产导出 ----------------

def train_elm(seed_w=TRAIN_SEED_W, seed_train=TRAIN_SEED_DATA,
              per_class=PER_CLASS_TRAIN):
    """ELM 训练：固定随机输入权重 → 双路径隐层 → 各自岭回归输出层。

    两条路径各自求最优输出权重（各路径 = 完整管线，公平比较端到端量化影响）。
    返回 (W, b, Wout_float, Wout_q, W_q, b_q)。
    """
    W, b = _draw_weights(random.Random(seed_w))
    W_q, b_q = _quantize_weights(W, b)

    data, _ = _dataset(seed_train, per_class)
    A_f, A_i, Y = [], [], []
    for pkt, cls in data:
        feats = elm_features_real(pkt)
        h_f = _forward_hidden_float(feats, W, b)
        A_f.append(h_f + [1.0])
        h_i = _forward_hidden_int(quantize_x(feats), W_q, b_q)
        A_i.append([v / H_SCALE for v in h_i] + [1.0])
        onehot = [0.0] * CLASS_N
        onehot[cls] = 1.0
        Y.append(onehot)
    Wout_f = _solve_ridge(A_f, Y, RIDGE_LAMBDA)
    Wout_i = _solve_ridge(A_i, Y, RIDGE_LAMBDA)
    Wout_q = [[max(-32767, min(32767, int(round(v * (1 << OUT_SCALE_BITS)))))
               for v in row] for row in Wout_i]
    return W, b, Wout_f, Wout_q, W_q, b_q


def _dataset(seed, per_class):
    rng = random.Random(seed)
    out = []
    for cls in (0, 1, 2):
        for _ in range(per_class):
            out.append((make_mock_packet(cls, rng), cls))
    return out, rng


def evaluate(W, b, Wout_f, Wout_q, W_q, b_q, seed=TEST_SEED_DATA,
             per_class=PER_CLASS_TEST):
    """双路径测试集评估：精度、混淆矩阵、逐类精度、精度差（工单 ≤5% 线）。"""
    data, _ = _dataset(seed, per_class)
    conf_f = [[0] * CLASS_N for _ in range(CLASS_N)]
    conf_l = [[0] * CLASS_N for _ in range(CLASS_N)]
    hit_f = hit_l = 0
    for pkt, cls in data:
        feats = elm_features_real(pkt)
        pf = argmax3(infer_float(feats, W, b, Wout_f))
        pl = argmax3(infer_lut(quantize_x(feats), W_q, b_q, Wout_q))
        hit_f += pf == cls
        hit_l += pl == cls
        conf_f[cls][pf] += 1
        conf_l[cls][pl] += 1
    acc_f, acc_l = hit_f / len(data), hit_l / len(data)
    per_f = [conf_f[c][c] / max(1, sum(conf_f[c])) for c in range(CLASS_N)]
    per_l = [conf_l[c][c] / max(1, sum(conf_l[c])) for c in range(CLASS_N)]
    return {
        "n": len(data),
        "acc_float": acc_f, "acc_lut": acc_l,
        "acc_delta": abs(acc_f - acc_l),
        "confusion_float": conf_f, "confusion_lut": conf_l,
        "per_class_float": per_f, "per_class_lut": per_l,
    }


def benchmark_host(feats=None, n=5000):
    """CPython 主机参考基准：LUT 路径 vs float 路径 ns/样本（非固件实测）。"""
    if feats is None:
        rng = random.Random(1)
        pkt = make_mock_packet(0, rng)
        feats = elm_features_real(pkt)
    x_q = quantize_x(feats)
    W, b = _draw_weights(random.Random(TRAIN_SEED_W))
    W_q, b_q = _quantize_weights(W, b)
    t_l = timeit.timeit(lambda: infer_lut(x_q, W_q, b_q, [[1] * (HIDDEN + 1)] * CLASS_N), number=n) / n
    t_f = timeit.timeit(lambda: infer_float(feats, W, b, [[1.0] * (HIDDEN + 1)] * CLASS_N), number=n) / n
    return {"ns_per_sample_lut": t_l * 1e9, "ns_per_sample_float": t_f * 1e9}
