"""PSK31 解码器（Phase 6 · 31.25 baud BPSK + Varicode）

调制：31.25 baud 二进制相移键控——bit1 相位保持、bit0 相位翻转 180°；
      相位跳变发生在符号边界（窗口内相位恒定），接收端 integrate-and-dump。
编码：Varicode 变长码，字符码字后跟 00 作为字符边界（自同步）。

Varicode 表来源：codec2 项目 varicode_table.h（KA7OEI / G3PLX，源自
Peter Martinez 的《PSK31 Fundamentals》）。256 字节逐字节转录，运行时
按 codec2 编码逻辑（MSB 先行、连续两个 0 截断）重建 码字→字符 映射，
与 C 参考实现保持同源，避免手抄码字出错。

注册：本模块不主动注册，由 decoders/__init__.py 统一导入触发。
"""
from __future__ import annotations

import numpy as np

BAUD = 31.25                 # PSK31 符号率
CARRIER = 1500.0             # 载波（PSK31 习惯 ~1000Hz 附近，任取）
IDLE_BITS = 64               # 空闲前导（连续发 1 = 相位不变）

# ---------------------------------------------------------------- Varicode 表
# 转录自 codec2 varicode_table.h（每字符 2 字节，MSB 先行，第一字节先发）。
# 每项编码中已包含尾随的字符边界 00（encode 时移出到连续两个 0 即截断）。
_VARICODE_BYTES = [
    0b10101010, 0b11000000,  # 0 NUL
    0b10110110, 0b11000000,  # 1 SOH
    0b10111011, 0b01000000,  # 2 STX
    0b11011101, 0b11000000,  # 3 ETX
    0b10111010, 0b11000000,  # 4 EOT
    0b11010111, 0b11000000,  # 5 ENQ
    0b10111011, 0b11000000,  # 6 ACK
    0b10111111, 0b01000000,  # 7 BEL
    0b10111111, 0b11000000,  # 8 BS
    0b11101111, 0b00000000,  # 9 HT
    0b11101000, 0b00000000,  # 10 LF
    0b11011011, 0b11000000,  # 11 VT
    0b10110111, 0b01000000,  # 12 FF
    0b11111000, 0b00000000,  # 13 CR
    0b11011101, 0b01000000,  # 14 SO
    0b11101010, 0b11000000,  # 15 SI
    0b10111101, 0b11000000,  # 16 DLE
    0b10111101, 0b01000000,  # 17 DC1
    0b11101011, 0b01000000,  # 18 DC2
    0b11101011, 0b11000000,  # 19 DC3
    0b11010110, 0b11000000,  # 20 DC4
    0b11011010, 0b11000000,  # 21 NAK
    0b11011011, 0b01000000,  # 22 SYN
    0b11010101, 0b11000000,  # 23 ETB
    0b11011110, 0b11000000,  # 24 CAN
    0b11011111, 0b01000000,  # 25 EM
    0b11101101, 0b11000000,  # 26 SUB
    0b11010101, 0b01000000,  # 27 ESC
    0b11010111, 0b01000000,  # 28 FS
    0b11101110, 0b11000000,  # 29 GS
    0b10111110, 0b11000000,  # 30 RS
    0b11011111, 0b11000000,  # 31 US
    0b10000000, 0b00000000,  # 32 SP
    0b11111111, 0b10000000,  # 33 !
    0b10101111, 0b10000000,  # 34 "
    0b11111010, 0b10000000,  # 35 #
    0b11101101, 0b10000000,  # 36 $
    0b10110101, 0b01000000,  # 37 %
    0b10101110, 0b11000000,  # 38 &
    0b10111111, 0b10000000,  # 39 '
    0b11111011, 0b00000000,  # 40 (
    0b11110111, 0b00000000,  # 41 )
    0b10110111, 0b10000000,  # 42 *
    0b11101111, 0b10000000,  # 43 +
    0b11101010, 0b00000000,  # 44 ,
    0b11010100, 0b00000000,  # 45 -
    0b10101110, 0b00000000,  # 46 .
    0b11010111, 0b10000000,  # 47 /
    0b10110111, 0b00000000,  # 48 0
    0b10111101, 0b00000000,  # 49 1
    0b11101101, 0b00000000,  # 50 2
    0b11111111, 0b00000000,  # 51 3
    0b10111011, 0b10000000,  # 52 4
    0b10101101, 0b10000000,  # 53 5
    0b10110101, 0b10000000,  # 54 6
    0b11010110, 0b10000000,  # 55 7
    0b11010101, 0b10000000,  # 56 8
    0b11011011, 0b10000000,  # 57 9
    0b11110101, 0b00000000,  # 58 :
    0b11011110, 0b10000000,  # 59 ;
    0b11110110, 0b10000000,  # 60 <
    0b10101010, 0b00000000,  # 61 =
    0b11101011, 0b10000000,  # 62 >
    0b10101011, 0b11000000,  # 63 ?
    0b10101111, 0b01000000,  # 64 @
    0b11111010, 0b00000000,  # 65 A
    0b11101011, 0b00000000,  # 66 B
    0b10101101, 0b00000000,  # 67 C
    0b10110101, 0b00000000,  # 68 D
    0b11101110, 0b00000000,  # 69 E
    0b11011011, 0b00000000,  # 70 F
    0b11111101, 0b00000000,  # 71 G
    0b10101010, 0b10000000,  # 72 H
    0b11111110, 0b00000000,  # 73 I
    0b11111110, 0b10000000,  # 74 J
    0b10111110, 0b10000000,  # 75 K
    0b11010111, 0b00000000,  # 76 L
    0b10111011, 0b00000000,  # 77 M
    0b11011101, 0b00000000,  # 78 N
    0b10101011, 0b00000000,  # 79 O
    0b11010101, 0b00000000,  # 80 P
    0b11101110, 0b10000000,  # 81 Q
    0b10101111, 0b00000000,  # 82 R
    0b11011110, 0b00000000,  # 83 S
    0b11011010, 0b00000000,  # 84 T
    0b10101011, 0b10000000,  # 85 U
    0b11011010, 0b10000000,  # 86 V
    0b10101110, 0b10000000,  # 87 W
    0b10111010, 0b10000000,  # 88 X
    0b10111101, 0b10000000,  # 89 Y
    0b10101011, 0b01000000,  # 90 Z
    0b11111011, 0b10000000,  # 91 [
    0b11110111, 0b10000000,  # 92 "\"
    0b11111101, 0b10000000,  # 93 ]
    0b10101111, 0b11000000,  # 94 ^
    0b10110110, 0b10000000,  # 95 _ (underline)
    0b10110111, 0b11000000,  # 96 `
    0b10110000, 0b00000000,  # 97 a
    0b10111110, 0b00000000,  # 98 b
    0b10111100, 0b00000000,  # 99 c
    0b10110100, 0b00000000,  # 100 d
    0b11000000, 0b00000000,  # 101 e
    0b11110100, 0b00000000,  # 102 f
    0b10110110, 0b00000000,  # 103 g
    0b10101100, 0b00000000,  # 104 h
    0b11010000, 0b00000000,  # 105 i
    0b11110101, 0b10000000,  # 106 j
    0b10111111, 0b00000000,  # 107 k
    0b11011000, 0b00000000,  # 108 l
    0b11101100, 0b00000000,  # 109 m
    0b11110000, 0b00000000,  # 110 n
    0b11100000, 0b00000000,  # 111 o
    0b11111100, 0b00000000,  # 112 p
    0b11011111, 0b10000000,  # 113 q
    0b10101000, 0b00000000,  # 114 r
    0b10111000, 0b00000000,  # 115 s
    0b10100000, 0b00000000,  # 116 t
    0b11011100, 0b00000000,  # 117 u
    0b11110110, 0b00000000,  # 118 v
    0b11010110, 0b00000000,  # 119 w
    0b11011111, 0b00000000,  # 120 x
    0b10111010, 0b00000000,  # 121 y
    0b11101010, 0b10000000,  # 122 z
    0b10101101, 0b11000000,  # 123 {
    0b11011101, 0b10000000,  # 124 |
    0b10101101, 0b01000000,  # 125 }
    0b10110101, 0b11000000,  # 126 ~
    0b11101101, 0b01000000,  # 127 (del)
]


def _build_varicode() -> tuple[dict[str, str], dict[str, str]]:
    fwd: dict[str, str] = {}
    rev: dict[str, str] = {}
    for i in range(0, len(_VARICODE_BYTES), 2):
        packed = (_VARICODE_BYTES[i] << 8) | _VARICODE_BYTES[i + 1]
        bits: list[int] = []
        nz = 0
        while nz < 2:                          # 与 codec2 encode 同构：连续两个 0 截断
            b = (packed >> 15) & 1
            packed <<= 1
            bits.append(b)
            nz = nz + 1 if b == 0 else 0
        code = "".join(str(b) for b in bits[:-2])   # 去掉尾随的边界 00
        ch = chr(i // 2)                            # i 是字节索引，字符序 = i/2
        fwd[ch] = code
        rev[code] = ch
    return fwd, rev


VARICODE, VARICODE_REV = _build_varicode()


def varicode_encode(text: str) -> str:
    """文本 → Varicode 位串（每字符码字后接 00 字符边界）。不支持字符→空格。"""
    return "".join(VARICODE.get(ch, VARICODE[" "]) + "00" for ch in text)


def varicode_decode(bits: str) -> str:
    """Varicode 位串 → 文本。遇到 00 结束当前字符；未知码字忽略（容错）。"""
    out: list[str] = []
    code = ""
    i, n = 0, len(bits)
    while i < n:
        if bits[i] == "0":
            if i + 1 < n and bits[i + 1] == "0":
                if code in VARICODE_REV:
                    out.append(VARICODE_REV[code])
                code = ""
                i += 2
            else:
                code += "0"
                i += 1
        else:
            code += "1"
            i += 1
    if code in VARICODE_REV:
        out.append(VARICODE_REV[code])
    return "".join(out)


# ---------------------------------------------------------------- 调制（模拟帧）
def modulate_psk31(bits: str, sample_rate: float = 8000.0,
                   carrier: float = CARRIER) -> np.ndarray:
    """BPSK 调制：bit1 相位保持、bit0 相位翻转；跳变发生在符号边界。"""
    sps = int(round(sample_rate / BAUD))
    out = np.zeros(len(bits) * sps, dtype=complex)
    t = np.arange(sps) / sample_rate
    phase = 0.0
    for i, ch in enumerate(bits):
        if ch == "0":
            phase += np.pi
        out[i * sps:(i + 1) * sps] = np.exp(1j * (2 * np.pi * carrier * t + phase))
    return out


def encode_text_psk31(text: str, sample_rate: float = 8000.0,
                      snr_db: float = 20.0, seed: int = 1) -> np.ndarray:
    """生成 PSK31 模拟帧 IQ：空闲前导(1) + 字符边界(00) + Varicode 编码 + BPSK + 加噪。

    前导与数据之间插入 00 边界：接收端差分解码天然丢弃首符号（t=s[1:]），
    若没有该边界，空闲全 1 与首字符码字头一位合并成无效长码，首字符丢失。
    """
    bits = "1" * IDLE_BITS + "00" + varicode_encode(text)
    iq = modulate_psk31(bits, sample_rate)
    iq /= np.sqrt(np.mean(np.abs(iq) ** 2) + 1e-12)
    rng = np.random.default_rng(seed)
    n = iq.size
    noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * np.sqrt(0.5 * 10 ** (-snr_db / 10))
    return iq + noise


# ---------------------------------------------------------------- 接收
def _recover_bits(bb: np.ndarray, sample_rate: float) -> tuple[str, float]:
    """integrate-and-dump 位定时恢复 + 相邻符号相位差判 bit。

    返回 (bit 串, 幅度一致性 std/mean)。真实 BPSK 窗口积分幅度近似恒定
    （相位翻转只改相位不改幅度），噪声下幅度随机波动——一致性用于拒噪。
    """
    sps = int(round(sample_rate / BAUD))
    if bb.size < 2 * sps:
        raise ValueError("信号太短，无法 PSK31 解码")
    # 位定时：滑窗使每符号积分能量最大（符号边界对齐）
    best_off, best_e = 0, -1.0
    for off in range(sps):
        nw = (bb.size - off) // sps
        if nw < 2:
            continue
        e = float(np.abs(bb[off:off + nw * sps].reshape(nw, sps).sum(axis=1)).sum())
        if e > best_e:
            best_e, best_off = e, off
    nwin = (bb.size - best_off) // sps
    s = bb[best_off:best_off + nwin * sps].reshape(nwin, sps).sum(axis=1)
    mag = np.abs(s)
    consistency = float(np.std(mag) / (np.mean(mag) + 1e-12))
    bits: list[str] = []
    prev = s[0]
    for cur in s[1:]:
        dphi = np.angle(cur * np.conj(prev))
        bits.append("0" if abs(dphi) > np.pi / 2 else "1")
        prev = cur
    return "".join(bits), consistency


CONSISTENCY_LIMIT = 0.35    # 幅度一致性上限：真实 BPSK 远低于此，噪声(Rayleigh≈0.52)绝大多数高于此
MIN_READABILITY = 3         # 最小可读字符数：拒噪声偶发解出的单字母


def _readability(text: str) -> int:
    """启发式打分：可打印且非空白字符越多越像有效文本（用于消极性模糊）。"""
    return sum(1 for c in text if c.isprintable() and not c.isspace())


def decode_psk31(iq: np.ndarray, sample_rate: float, carrier: float = CARRIER,
                 **params) -> str:
    """PSK31 完整解码，返回文本；无法恢复有效文本抛 ValueError。"""
    iq = np.asarray(iq)
    if iq.size < int(round(sample_rate / BAUD)) * 2:
        raise ValueError("信号太短，无法 PSK31 解码")
    t = np.arange(iq.size) / sample_rate
    bb = iq * np.exp(-2j * np.pi * carrier * t)     # 搬移到基带
    texts: list[str] = []
    for flip in (1, -1):                             # 双极性消相位模糊
        bits, consistency = _recover_bits(bb if flip == 1 else np.conj(bb), sample_rate)
        if consistency > CONSISTENCY_LIMIT:          # 幅度随机波动 → 无有效信号
            continue
        texts.append(varicode_decode(bits).strip())
    if not texts:
        raise ValueError("PSK31 未检出有效信号（幅度一致性不足）")
    best = max(texts, key=_readability)
    if _readability(best) < MIN_READABILITY:
        raise ValueError("PSK31 未恢复出有效文本")
    return best
