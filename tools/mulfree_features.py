# -*- coding: utf-8 -*-
"""AC-01 · 无乘法特征提取器（multiplication-free feature extractor）Python 参考正本。

授粉来源（设计参照级，非代码移植）：
  cs.SD 关键词检测论文 "Signal classification in the absence of multiplications"
  ——核心思想：用 dyadic Haar 结构的多分辨率分析（MRA）替代常规滤波器组，
  缩放全部取 2 的幂（移位），系数做符号二值量化，特征提取全程无乘法指令，
  MCU 可直跑。本实现只取该设计思想，为独立整数实现，未引用论文代码/数据。

热路径不变量（可执行验收）：
  特征提取 + 分类全程只用 加/减/算术移位/比较/位运算，无 * / % 乘除指令。
  - Python 侧：tools/test_mulfree.py 的 AST 纯净性用例守卫
  - C++ 侧  ：tools/objdump_mulfree_check.py 对 xtensa-esp32s3 反汇编 grep 守卫

镜像关系（沿用 loracanary 约定）：
  本文件 = Python 正本；firmware/mulfree/mulfree_features.{h,cpp} = C++ 正本；
  草图目录内为镜像副本（pytest 守卫防漂移）。黄金向量由 tools/gen_mulfree_assets.py
  一次生成、两侧同源断言。

应用场景（SX1278 收包分类 demo，详见 firmware/mulfree/README.md）：
  对收到的 LoRa 帧字节流做特征提取 → 汉明最近质心分类：
  类 0 NORMAL（结构化正常帧）/ 类 1 NOISE（短包噪声）/ 类 2 BAD_FRAME（帧体损坏）。
  三类样例均为合成 mock（无真机数据，诚实降级标注）；真机收包路径留接口。
"""
from __future__ import annotations

import random

# ---------------- 常量 ----------------

WINDOW = 32            # Haar 树输入点数（2^5，5 层）
LEVELS = 5
N_DETAIL = WINDOW - 1  # 31 个细节系数
N_ACTIVITY = 8         # 活动位（8 个 4 点窗）
ACT_WIN = WINDOW // N_ACTIVITY   # 4 点/窗
ACT_THRESHOLD = 32     # 活动阈值：窗内 |差分| 最大值 >= 32（2 的幂，比较即可）
SPIKE_THRESHOLD = 32   # 尖峰判定：|差分| >= 32（2 的幂）
SPIKE_BITS = 3         # 尖峰计数三档：>=1 / >=4 / >=16
TAIL_PAD_MIN = 8       # 尾部补零判定：连续零差分 >= 8（短包"保持末字节"延拓痕迹）
FEATURE_BITS = N_DETAIL + 1 + N_ACTIVITY + 2 + SPIKE_BITS + 1  # 46 位特征

# 语义位区（bit[32..45]：活动/长度/帧头/尖峰/补零）与符号位区分界
SEMANTIC_BIT0 = N_DETAIL + 1  # bit0..30 符号 + bit31 均值符号 → 语义区从 bit32 起
# 加权汉明：语义位权 8（<<3），符号位权 1——权重是 2 的幂，加权用移位实现，无乘法。
# 动机：Haar 符号位对 NORMAL/BAD 两类同为"结构化"模式，判别弱；语义位判别强。
SEMANTIC_WEIGHT_SHIFT = 3
SIGN_MASK = (1 << SEMANTIC_BIT0) - 1

CLASS_NAMES = ("NORMAL", "NOISE", "BAD_FRAME")
MAGIC0, MAGIC1 = 0xD0, 0xCC   # LoRaCanary 帧头（复用 SPEC-20 契约）


# ---------------- 核心特征提取（热路径，全程无乘法） ----------------

def haar_tree(samples):
    """dyadic Haar 多分辨率树：avg=(a+b)>>1, diff=(a-b)>>1，仅加减移位。

    输入 WINDOW 个整数样本，返回 (details, final_avg)：
      details: 5 层细节系数元组（16+8+4+2+1 = 31 个，逐层打包）
      final_avg: 最终均值系数（>>1 地板除语义，C++ 算术移位一致，见 .cpp 注记）
    """
    work = list(samples)
    details = []
    n = WINDOW
    while n > 1:
        half = n >> 1
        for i in range(half):
            a = work[i << 1]
            b = work[(i << 1) + 1]
            work[i] = (a + b) >> 1          # 均值：加法 + 右移
            details.append((a - b) >> 1)    # 细节：减法 + 右移
        n = half
    return tuple(details), work[0]


def box_window_sums(samples, win=8):
    """盒式滤波参考形态：不相交 8 点窗求和（前缀和 + 减法，全程加减）。

    保留作 README/测试对照；特征路径实际用 box_window_max（对局部损坏更敏感）。
    """
    run = []
    s = 0
    for x in samples:
        s += x
        run.append(s)
    sums = []
    idx = win - 1
    while idx < len(run):
        prev = run[idx - win] if idx >= win else 0
        sums.append(run[idx] - prev)
        idx += win
    return tuple(sums)


def box_window_max(samples, win=4):
    """分段窗内最大值（比较实现，无乘法）——对局部单点损坏比窗和更敏感。

    返回 len(samples)//win 个窗最大值。损坏帧的翻转只污染一两个差分点，
    4 点窗最大值能精确定位，而 8 点窗和会被稀释。
    """
    return tuple(max(samples[i:i + win]) for i in range(0, len(samples), win))


def _abs_i(x):
    """整数绝对值（条件取反，无乘法）。"""
    return -x if x < 0 else x


def packet_window(buf):
    """特征窗准备（packet_feature_bits / elm_lut 共用）：帧头对齐 + 延拓。

    帧头（D0 CC）存在时取其后 WINDOW 字节（剥离帧头跳变）；无帧头取前
    WINDOW 字节；不足按"保持末字节"延拓；空包全零。
    返回 (ext, has_header, n)：ext 为 WINDOW 点列表。
    """
    n = len(buf)
    has_header = n >= 2 and buf[0] == MAGIC0 and buf[1] == MAGIC1
    off = 2 if has_header else 0
    ext = []
    for i in range(WINDOW):
        j = off + i
        ext.append(buf[j] if j < n else (buf[n - 1] if n > 0 else 0))
    return ext, has_header, n


def abs_diffs_31(ext):
    """一阶差分 + 绝对值（31 点，减法/条件取反）。"""
    return [_abs_i(ext[i + 1] - ext[i]) for i in range(WINDOW - 1)]


def packet_feature_bits(buf):
    """收包字节流 → 46 位特征（bitmask int，bit[k] 置位规则见注释）。

    特征窗口对齐规则见 packet_window；bit 语义：
    bit[0..30]      31 个 Haar 细节系数符号（>=0 → 1）
    bit[31]         最终均值系数符号（>=0 → 1）
    bit[32..39]     活动位：8 个 4 点窗内 |差分| 最大值 >= ACT_THRESHOLD
    bit[40]         长度桶：帧长 >= 32
    bit[41]         帧头：buf[0..1] == D0 CC
    bit[42..44]     尖峰计数三档：|差分|>=SPIKE_THRESHOLD 的个数 >=1 / >=4 / >=16
    bit[45]         尾部补零：连续零差分 >= TAIL_PAD_MIN（短包延拓痕迹）
    """
    n = len(buf)
    ext, has_header, n = packet_window(buf)
    abs_diffs = abs_diffs_31(ext)

    details, final_avg = haar_tree(ext)
    bits = 0
    k = 0
    for d in details:
        if d >= 0:
            bits |= 1 << k
        k += 1
    if final_avg >= 0:
        bits |= 1 << k
    k += 1
    # 活动位：4 点窗内 |差分| 最大值对比幂阈值（比较实现）
    for j, m in enumerate(box_window_max(abs_diffs, ACT_WIN)):
        if m >= ACT_THRESHOLD:
            bits |= 1 << (k + j)
    k += N_ACTIVITY
    # 长度桶 + 帧头（比较）
    if n >= WINDOW:
        bits |= 1 << k
    k += 1
    if has_header:
        bits |= 1 << k
    k += 1
    # 尖峰计数三档（计数 + 比较，无乘法）
    n_spike = 0
    for d in abs_diffs:
        if d >= SPIKE_THRESHOLD:
            n_spike += 1
    if n_spike >= 1:
        bits |= 1 << k
    if n_spike >= 4:
        bits |= 1 << (k + 1)
    if n_spike >= 16:
        bits |= 1 << (k + 2)
    k += SPIKE_BITS
    # 尾部补零位（|差分| 为 0 与差分为 0 等价）
    tail = 0
    for d in reversed(abs_diffs):
        if d != 0:
            break
        tail += 1
    if tail >= TAIL_PAD_MIN:
        bits |= 1 << k
    return bits


def popcount(x):
    """逐位计数（加法/位运算，无乘法）。"""
    cnt = 0
    while x:
        cnt += x & 1
        x >>= 1
    return cnt


def hamming_distance(a, b):
    """汉明距离：异或 + 逐位计数（加法/位运算，无乘法）。"""
    return popcount(a ^ b)


def weighted_distance(a, b):
    """加权汉明：语义位（bit32..41）权 4，符号位权 1。

    权 4 = 左移 2 位，全程移位/加法/位运算，无乘法。
    分类与原型训练统一用本距离。
    """
    x = a ^ b
    return (popcount(x & SIGN_MASK)
            + (popcount(x >> SEMANTIC_BIT0) << SEMANTIC_WEIGHT_SHIFT))


def classify_bits(bits, proto_list):
    """加权汉明最近原型分类（无乘法）：返回 (类别索引, 最小加权距离)。

    proto_list: [(类别索引, 原型特征位), ...]（每类 k 个原型）；
    并列时取表内先出现者（生成器按类 0→2 写表，即最小类索引优先，确定性）。
    """
    best_cls = -1
    best_dist = (FEATURE_BITS + 1) << SEMANTIC_WEIGHT_SHIFT
    for cls, proto in proto_list:
        d = weighted_distance(bits, proto)
        if d < best_dist:
            best_dist = d
            best_cls = cls
    return best_cls, best_dist


def train_centroid(feature_bits_list):
    """单类质心训练：逐位多数表决，count<<1 > n 等价 count > n/2（无除法/乘法）。

    注意：类内方差大的类（如帧体损坏类的尖峰位随机分布）会被多数表决抹平，
    分类器实际改用 medoid 原型（见 train_prototype）——此函数保留作基线对照。
    """
    n = len(feature_bits_list)
    centroid = 0
    for k in range(FEATURE_BITS):
        cnt = 0
        for b in feature_bits_list:
            cnt += (b >> k) & 1
        if (cnt << 1) > n:
            centroid |= 1 << k
    return centroid


def train_prototypes_k(feature_bits_list, k=4):
    """farthest-first k 原型训练：第 1 个取类内 medoid，之后每次加入
    "到已选原型最小加权距离最大"的样本（farthest-first 遍历），直到 k 个。

    全程加权汉明 + 比较，无乘法。类内方差大（损坏位置随机）时比单 medoid
    覆盖好得多；k 个原型 × popcount 在 MCU 上可忽略。
    """
    # medoid 起点（类内加权距离和最小）
    best_i = 0
    best_s = None
    for i, a in enumerate(feature_bits_list):
        s = 0
        for b in feature_bits_list:
            s += weighted_distance(a, b)
        if best_s is None or s < best_s:
            best_s = s
            best_i = i
    chosen = [best_i]
    min_d = [weighted_distance(x, feature_bits_list[best_i])
             for x in feature_bits_list]
    while len(chosen) < k:
        far = 0
        for i in range(len(feature_bits_list)):
            if min_d[i] > min_d[far]:
                far = i
        chosen.append(far)
        for i, x in enumerate(feature_bits_list):
            d = weighted_distance(x, feature_bits_list[far])
            if d < min_d[i]:
                min_d[i] = d
    return [feature_bits_list[i] for i in chosen]


# ---------------- 合成 mock 数据（无真机数据，诚实降级标注） ----------------

def make_mock_packet(cls, rng):
    """按类别合成一个"收到的包"（bytes）。

    类 0 NORMAL    ：D0CC 帧头 + 平滑传感器样字节（相邻字节小幅漂移）
    类 1 NOISE     ：短随机字节流（无帧头）
    类 2 BAD_FRAME ：正常帧体中段随机翻转若干字节（帧头保留）
    全部为合成数据；真机 SX1278 收包形状（RSSI/SNR/前导码）未经实物验证。
    """
    if cls == 0:
        # 传感器斜坡帧：[D0 CC] + 单调缓升载荷，偶发固定 -8 回落（负差分结构，幅度 < 阈值）
        ln = rng.randint(40, 64)
        body = bytearray([MAGIC0, MAGIC1])
        v = rng.randint(16, 80)
        for _ in range(ln - 2):
            if rng.random() < 0.05 and v >= 32:
                v -= 8                       # 固定小幅回落（|差分|=8 < 阈值 32）
            else:
                v += rng.randint(0, 3)       # 缓升
            if v > 255:
                v = 255                      # 饱和平台
            body.append(v)
        return bytes(body)
    if cls == 1:
        ln = rng.randint(12, 24)
        return bytes(rng.randint(0, 255) for _ in range(ln))
    # cls == 2：正常帧 + 载荷区损坏
    pkt = bytearray(make_mock_packet(0, rng))
    n_flip = rng.randint(4, 10)
    for _ in range(n_flip):
        i = rng.randint(2, len(pkt) - 1)
        pkt[i] ^= 0x5A
    return bytes(pkt)


def make_dataset(seed=20260829, per_class=200):
    """生成 (特征位, 类别) 数据集：特征提取本身也是无乘法热路径。"""
    rng = random.Random(seed)
    feats = []
    for cls in (0, 1, 2):
        for _ in range(per_class):
            pkt = make_mock_packet(cls, rng)
            feats.append((packet_feature_bits(pkt), cls))
    return feats, rng


# ---------------- 乘法规对照（基准组，仅测试/基准用，不进固件热路径） ----------------

def float_haar_tree(samples):
    """等复杂度乘法规对照：float Haar（avg/diff 各乘 0.5），供精度/性能对比。"""
    work = [float(x) for x in samples]
    details = []
    n = WINDOW
    while n > 1:
        half = n >> 1
        for i in range(half):
            a = work[i << 1]
            b = work[(i << 1) + 1]
            work[i] = (a + b) * 0.5
            details.append((a - b) * 0.5)
        n = half
    return tuple(details), work[0]


def float_feature_signs(buf):
    """乘法规特征（位语义与 packet_feature_bits 逐位对齐），返回位 bitmask。

    与整数版仅一处实现差异：Haar 缩放用乘法 0.5（float），其余位两条路径同构。
    用于 pytest 等价性用例与 README 精度对照表。
    """
    n = len(buf)
    ext, has_header, n = packet_window(buf)
    details, final_avg = float_haar_tree(ext)
    bits = 0
    k = 0
    for d in details:
        if d >= 0:
            bits |= 1 << k
        k += 1
    if final_avg >= 0:
        bits |= 1 << k
    k += 1
    abs_diffs = abs_diffs_31(ext)
    for j, m in enumerate(box_window_max(abs_diffs, ACT_WIN)):
        if m >= ACT_THRESHOLD:
            bits |= 1 << (k + j)
    k += N_ACTIVITY
    if n >= WINDOW:
        bits |= 1 << k
    k += 1
    if has_header:
        bits |= 1 << k
    k += 1
    n_spike = 0
    for d in abs_diffs:
        if d >= SPIKE_THRESHOLD:
            n_spike += 1
    if n_spike >= 1:
        bits |= 1 << k
    if n_spike >= 4:
        bits |= 1 << (k + 1)
    if n_spike >= 16:
        bits |= 1 << (k + 2)
    k += SPIKE_BITS
    tail = 0
    for d in reversed(abs_diffs):
        if d != 0:
            break
        tail += 1
    if tail >= TAIL_PAD_MIN:
        bits |= 1 << k
    return bits
