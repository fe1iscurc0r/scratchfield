"""WSPR 弱信号传播报告解码器（Phase 6 · 4-FSK + K=32 卷积码）

WSPR（Weak Signal Propagation Reporter）是 K1JT（Joe Taylor）设计的
窄带数字信标协议：约 6 Hz 带宽、可低至 -28 dB（2.5 kHz 参考带宽）解码，
每 2 分钟一个时隙（偶 UTC 分钟后 1 秒起发，持续约 110.6 s）。

协议参数（公开协议规范，来源标注见各常量处）：
- 消息：50 bit = 28 bit 呼号 + 15 bit 网格 + 7 bit 功率
- FEC：非递归卷积码，约束长度 K=32，速率 r=1/2
        生成多项式 G1=0xF2D05351、G2=0xE4613C47
- 交织：8-bit 位反转置换（仅取 <162 的位置，共 162 个）
- 同步：162 bit 伪随机同步向量，与数据 bit 合并成 2 bit 符号
        symbol = (data << 1) | sync（data 为 MSB，sync 为 LSB）
- 调制：连续相位 4-FSK，音距 = 键控速率 = 12000/8192 ≈ 1.4648 Hz
- 符号数：162 = (50 + K - 1) * 2

注册：本模块不主动注册，由 decoders/__init__.py 统一导入触发。

实现纪律（授粉）：本文档按公开协议规范独立实现，仅参考协议描述，
未逐字拷贝 WSJT-X / WsprryPi 源码（同步向量与多项式属于协议规范数据，
为互操作必须一致，此处如实转录并标注来源）。
"""
from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------- #
# 协议常量（来源：WSPR 公开协议规范 / G4JNT 编码过程描述）
# --------------------------------------------------------------------------- #

# 162 bit 伪随机同步向量（协议规范固定值，来源：WSPR 协议公开文档）
SYNC_VECTOR: tuple[int, ...] = (
    1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0,
    0, 0, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 0, 1, 1, 0, 1, 0,
    0, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 1, 0, 1, 0,
    0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 0, 1, 1, 1,
    0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0,
    0, 0,
)

# 卷积码生成多项式（K=32, r=1/2，非递归）
POLY: tuple[int, int] = (0xF2D05351, 0xE4613C47)

# 有效功率档位（dBm，19 档）。其他值按协议规则取整到最近有效值。
VALID_POWERS: tuple[int, ...] = (
    0, 3, 7, 10, 13, 17, 20, 23, 27, 30, 33, 37, 40, 43, 47, 50, 53, 57, 60,
)

# 键控速率 / 音距（Hz）：12000 / 8192
TONE_SPACING = 12000.0 / 8192.0          # ≈ 1.46484375 Hz
SYMBOL_RATE = TONE_SPACING                # 符号率 = 音距
N_SYMBOLS = 162                           # 信道符号数
SAMPLE_RATE = 12000.0                     # 内部采样率（符号周期 = 8192 样本）
SYMBOL_SAMPLES = 8192                     # 每符号样本数 @12kHz
BASE_FREQ = 1500.0                        # 基音（音频偏移，恰好落在 FFT bin 1024）
# 校验：1500 / TONE_SPACING = 1024，正好整数 bin，4 个音点对齐 FFT 分辨率
_F0_BIN = int(round(BASE_FREQ * SYMBOL_SAMPLES / SAMPLE_RATE))

# 交织表：8-bit 位反转置换（仅取 <162 的位置）。perm[i] = 卷积符号 i 的目标位置。


def _bitrev8(x: int) -> int:
    """8-bit 位反转。"""
    r = 0
    for j in range(8):
        r = ((x >> j) & 1) | (r << 1)
    return r


def _build_interleave_table() -> tuple[int, ...]:
    perm: list[int] = []
    k = 0
    while len(perm) < N_SYMBOLS:
        j0 = _bitrev8(k)
        if j0 < N_SYMBOLS:
            perm.append(j0)
        k += 1
    return tuple(perm)


_INTERLEAVE_TABLE = _build_interleave_table()


def _parity(x: int) -> int:
    """整数 x 的 1 比特数量奇偶校验（mod 2）。"""
    return x.bit_count() & 1


def _round_power(p: int) -> int:
    """把功率四舍五入到最近的 WSPR 有效档位。"""
    corr = (0, -1, 1, 0, -1, 2, 1, 0, -1, 1)
    return max(0, min(60, p + corr[p % 10]))


# --------------------------------------------------------------------------- #
# 消息打包 / 解包（呼号 28 bit · 网格 15 bit · 功率 7 bit）
# --------------------------------------------------------------------------- #

def _char_val_prefix(c: str) -> int:
    """呼号前缀字符 → 36 进制值：数字 0-9 → 0-9，字母 A-Z → 10-35，空格 → 36。"""
    if c.isdigit():
        return ord(c) - ord("0")
    if c == " ":
        return 36
    return ord(c) - ord("A") + 10


def _char_val_suffix(c: str) -> int:
    """呼号后缀字符 → 27 进制值：字母 A-Z → 0-25，空格 → 26。"""
    if c == " ":
        return 26
    return ord(c) - ord("A")


def _pack_callsign(call: str) -> int:
    """标准呼号（Type 1，无前缀/后缀）→ 28 bit 整数。

    编码公式（公开协议规范）：
        N = ch1·36·10·27³ + ch2·10·27³ + ch3·27³ + ch4·27² + ch5·27 + ch6
    ch1/ch2 为前缀（36 进制，空位=36），ch3 为数字，ch4..ch6 为后缀（27 进制，空位=26）。
    """
    call = call.upper().strip()
    # 找到呼号前缀中最后一个数字的位置（呼号格式：前缀字母/数字 + 数字 + 后缀字母）
    i = 2 if (len(call) > 2 and call[2].isdigit()) else \
        1 if (len(call) > 1 and call[1].isdigit()) else 0
    if not (i < len(call) and call[i].isdigit()):
        raise ValueError(f"无效呼号（缺少数字字段）: {call!r}")
    rest = call[i + 1:]  # 数字后的后缀字符

    def cval(s: str, idx: int) -> int:
        return _char_val_prefix(s[idx]) if idx < len(s) else 36

    n1 = cval(call, i - 2) if i >= 2 else 36
    n1 = 36 * n1 + (cval(call, i - 1) if i >= 1 else 36)
    n1 = 10 * n1 + (ord(call[i]) - ord("0"))
    n1 = 27 * n1 + (_char_val_suffix(rest[0]) if len(rest) > 0 else 26)
    n1 = 27 * n1 + (_char_val_suffix(rest[1]) if len(rest) > 1 else 26)
    n1 = 27 * n1 + (_char_val_suffix(rest[2]) if len(rest) > 2 else 26)
    return n1


def _unpack_callsign(n1: int) -> str:
    """28 bit 整数 → 标准呼号（Type 1）。"""
    ch6 = n1 % 27
    n1 //= 27
    ch5 = n1 % 27
    n1 //= 27
    ch4 = n1 % 27
    n1 //= 27
    ch3 = n1 % 10
    n1 //= 10
    ch2 = n1 % 36
    n1 //= 36
    # 最高位 ch1 值域 0..36（36 = 空位），37 个值恰好铺满 2^28 编码空间，
    # 必须用整除取商；若取模 36 会把 36 折叠成 0，导致短呼号多出假 '0' 前缀
    ch1 = n1

    def prefix_ch(v: int) -> str:
        if v == 36:
            return ""
        if v < 10:
            return str(v)
        return chr(ord("A") + v - 10)

    def suffix_ch(v: int) -> str:
        return "" if v == 26 else chr(ord("A") + v)

    return (prefix_ch(ch1) + prefix_ch(ch2) + str(ch3)
            + suffix_ch(ch4) + suffix_ch(ch5) + suffix_ch(ch6))


def _pack_grid(grid: str) -> int:
    """4 字符 Maidenhead 网格（如 "FN20"）→ 15 bit 整数。

    编码（公开协议规范）：
        N = 180·(179 - 10·g0 - g2) + 10·g1 + g3
    g0/g1 为字段字母（A=0..R=17），g2/g3 为子字段数字。
    """
    g = grid.upper()
    if len(g) < 4:
        raise ValueError(f"网格至少 4 字符: {grid!r}")
    g0 = ord(g[0]) - ord("A")
    g1 = ord(g[1]) - ord("A")
    g2 = ord(g[2]) - ord("0")
    g3 = ord(g[3]) - ord("0")
    if not (0 <= g0 <= 17 and 0 <= g1 <= 17 and 0 <= g2 <= 9 and 0 <= g3 <= 9):
        raise ValueError(f"无效网格: {grid!r}")
    return 180 * (179 - 10 * g0 - g2) + 10 * g1 + g3


def _unpack_grid(ng: int) -> str:
    """15 bit 整数 → 4 字符 Maidenhead 网格。"""
    low = ng % 180
    g1, g3 = low // 10, low % 10
    hi = 179 - (ng // 180)
    g0, g2 = hi // 10, hi % 10
    return f"{chr(ord('A') + g0)}{chr(ord('A') + g1)}{g2}{g3}"


def pack_message(callsign: str, grid: str, power_dbm: int) -> list[int]:
    """呼号 + 网格 + 功率 → 50 bit 消息（MSB 先行）。"""
    n1 = _pack_callsign(callsign)
    n2 = (_pack_grid(grid) << 7) | (_round_power(power_dbm) + 64)
    bits: list[int] = []
    for i in range(27, -1, -1):
        bits.append((n1 >> i) & 1)
    for i in range(21, -1, -1):
        bits.append((n2 >> i) & 1)
    assert len(bits) == 50
    return bits


def unpack_message(bits: list[int]) -> dict[str, object]:
    """50 bit 消息 → {callsign, grid, power_dbm}。"""
    if len(bits) < 50:
        raise ValueError(f"消息长度不足 50 bit: {len(bits)}")
    n1 = 0
    for b in bits[:28]:
        n1 = (n1 << 1) | b
    n2 = 0
    for b in bits[28:50]:
        n2 = (n2 << 1) | b
    ng = n2 >> 7
    power = (n2 & 0x7F) - 64
    return {
        "callsign": _unpack_callsign(n1),
        "grid": _unpack_grid(ng),
        "power_dbm": power,
    }


# --------------------------------------------------------------------------- #
# 卷积编码 / 交织
# --------------------------------------------------------------------------- #

def _convolve(bits: list[int]) -> list[int]:
    """K=32 r=1/2 非递归卷积编码：81 bit → 162 bit（每输入 bit 输出 2 bit）。"""
    nstate = 0
    out: list[int] = []
    for bit in bits:
        nstate = ((nstate << 1) | bit) & 0xFFFFFFFF
        out.append(_parity(nstate & POLY[0]))
        out.append(_parity(nstate & POLY[1]))
    return out


def _interleave(conv: list[int]) -> list[int]:
    """位反转交织 162 个卷积 bit → 按交织表重排。"""
    out = [0] * N_SYMBOLS
    for i, j0 in enumerate(_INTERLEAVE_TABLE):
        out[j0] = conv[i]
    return out


def _deinterleave(data_bits: list[int]) -> list[int]:
    """去交织（交织的逆变换）。"""
    out = [0] * N_SYMBOLS
    for i, j0 in enumerate(_INTERLEAVE_TABLE):
        out[i] = data_bits[j0]
    return out


def encode_symbols(callsign: str, grid: str, power_dbm: int) -> list[int]:
    """完整编码：消息 → 卷积 → 交织 → 与同步向量合并 → 162 个符号（0-3）。"""
    msg = pack_message(callsign, grid, power_dbm)
    # 50 bit + 31 个 0 尾比特 = 81 bit
    conv = _convolve(msg + [0] * 31)
    data_bits = _interleave(conv)
    return [(data_bits[i] << 1) | SYNC_VECTOR[i] for i in range(N_SYMBOLS)]


# --------------------------------------------------------------------------- #
# 调制（4-FSK 连续相位）
# --------------------------------------------------------------------------- #

def modulate_wspr(symbols: list[int], sample_rate: float = SAMPLE_RATE,
                  base_freq: float = BASE_FREQ) -> np.ndarray:
    """162 个符号（0-3）→ 连续相位 4-FSK IQ 信号。"""
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"WSPR 调制仅支持 {SAMPLE_RATE} Hz 采样率")
    sps = int(round(sample_rate / SYMBOL_RATE))
    freq = np.repeat([base_freq + s * TONE_SPACING for s in symbols], sps)
    phase = 2 * np.pi * np.cumsum(freq) / sample_rate
    return np.exp(1j * phase).astype(complex)


def encode_wspr_text(callsign: str, grid: str, power_dbm: int,
                     snr_db: float = 20.0, seed: int = 1,
                     sample_rate: float = SAMPLE_RATE,
                     base_freq: float = BASE_FREQ) -> np.ndarray:
    """生成 WSPR 模拟帧 IQ（含加噪）——合成信号闭环测试用。"""
    symbols = encode_symbols(callsign, grid, power_dbm)
    iq = modulate_wspr(symbols, sample_rate, base_freq)
    iq /= np.sqrt(np.mean(np.abs(iq) ** 2) + 1e-12)
    rng = np.random.default_rng(seed)
    n = iq.size
    noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * np.sqrt(
        0.5 * 10 ** (-snr_db / 10))
    return iq + noise


# --------------------------------------------------------------------------- #
# 接收：4-FSK 解调 → 去交织 → 维特比解码 → 消息解析
# --------------------------------------------------------------------------- #

def _demod_symbols(iq: np.ndarray, sample_rate: float,
                   base_freq: float = BASE_FREQ) -> list[int]:
    """对 IQ 信号逐符号 FFT 判频，返回 162 个符号（0-3）。"""
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"WSPR 解调仅支持 {SAMPLE_RATE} Hz 采样率")
    sps = int(round(sample_rate / SYMBOL_RATE))
    if iq.size < N_SYMBOLS * sps:
        raise ValueError(f"信号太短，无法 WSPR 解码（需 {N_SYMBOLS * sps} 样本）")
    iq = np.asarray(iq)[:N_SYMBOLS * sps].reshape(N_SYMBOLS, sps)
    symbols: list[int] = []
    # 4 个音点恰好在 FFT bin 上（基音 bin = _F0_BIN，音距 = 1 bin）
    win = np.hanning(sps)
    for frame in iq:
        # numpy>=2 的 rfft 不再接受复数输入，改用全谱 FFT（音点都在正频率侧）
        spec = np.abs(np.fft.fft(frame * win, n=sps))
        tones = spec[_F0_BIN:_F0_BIN + 4]
        symbols.append(int(np.argmax(tones)))
    return symbols


def _viterbi_decode(conv_bits: list[int], m_states: int = 2048) -> list[int]:
    """列表维特比（M-algorithm 状态裁剪）解码卷积码 → 81 bit 数据。

    输入 162 个硬判决卷积 bit；返回 81 bit（前 50 为消息，后 31 为尾比特）。
    K=32 全状态 = 2^31 不可行，故每步保留度量最优的 m_states 个幸存路径。
    """
    if len(conv_bits) < N_SYMBOLS:
        raise ValueError(f"卷积 bit 不足: {len(conv_bits)}")
    # 幸存路径：state -> (metric, path_bits)
    survivors: dict[int, tuple[int, list[int]]] = {0: (0, [])}
    for step in range(81):
        r0 = conv_bits[2 * step]
        r1 = conv_bits[2 * step + 1]
        new: dict[int, tuple[int, list[int]]] = {}
        for state, (metric, path) in survivors.items():
            for b in (0, 1):
                ns = ((state << 1) | b) & 0xFFFFFFFF
                o0 = _parity(ns & POLY[0])
                o1 = _parity(ns & POLY[1])
                bm = (o0 ^ r0) + (o1 ^ r1)   # 汉明距离
                nm = metric + bm
                if ns not in new or nm < new[ns][0]:
                    new[ns] = (nm, path + [b])
        if len(new) > m_states:
            new = dict(sorted(new.items(), key=lambda kv: kv[1][0])[:m_states])
        survivors = new
        if not survivors:
            raise ValueError("维特比解码路径为空")
    best = min(survivors.values(), key=lambda kv: kv[0])
    return best[1]


def decode_wspr(iq: np.ndarray, sample_rate: float = SAMPLE_RATE,
                base_freq: float = BASE_FREQ, **params) -> dict[str, object]:
    """WSPR 完整解码，返回 {mode, callsign, grid, snr_db, freq_hz, decodes}。

    解码失败（信号过弱 / 无法恢复合法消息）抛 ValueError——诚实降级，不编造。
    """
    iq = np.asarray(iq)
    if iq.size < N_SYMBOLS * int(round(sample_rate / SYMBOL_RATE)):
        raise ValueError("信号太短，无法 WSPR 解码")

    symbols = _demod_symbols(iq, sample_rate, base_freq)

    # 用同步向量做一次粗略校验：解出的 sync bit 与已知同步向量匹配率
    sync_match = sum(1 for i in range(N_SYMBOLS)
                     if (symbols[i] & 1) == SYNC_VECTOR[i]) / N_SYMBOLS
    if sync_match < 0.55:
        raise ValueError(f"WSPR 同步向量匹配率过低（{sync_match:.2f}），疑似噪声")

    data_bits = [(symbols[i] >> 1) & 1 for i in range(N_SYMBOLS)]
    conv = _deinterleave(data_bits)
    decoded = _viterbi_decode(conv)
    msg_bits = decoded[:50]

    info = unpack_message(msg_bits)
    info["mode"] = "wspr"
    info["snr_db"] = round(float(sync_match * 100 - 50), 1) if False else None
    # 用同步匹配率折算一个粗略 SNR 指标（供展示，非物理精测）
    info["snr_db"] = round(float((sync_match - 0.5) * 2 * 30.0), 1)
    info["freq_hz"] = base_freq
    info["decodes"] = [f"{info['callsign']} {info['grid']} {info['power_dbm']}dBm"]

    # 合法性校验：呼号 / 网格 / 功率必须在协议允许范围内
    p = info["power_dbm"]
    if not (isinstance(p, int) and 0 <= p <= 60):
        raise ValueError(f"WSPR 解出非法功率: {p!r}")
    if not info["callsign"].strip():
        raise ValueError("WSPR 解出空呼号")
    return info
