"""FT8 弱信号数字模式解码器（Phase 6 · 8-GFSK + LDPC(174,91) + CRC14）

FT8 是 K1JT（Joe Taylor）与 WSJT-X 团队设计的窄带数字模式，用于 HF/VHF
弱信号通联：8-FSK（GFSK 成形）、每 15 s 一个时隙、约 50 Hz 带宽、可低至
约 -24 dB（2.5 kHz 参考带宽）解码。每帧 79 个信道符号：58 个数据符号 +
3 段 7 符号 Costas 同步序列。

协议参数（公开协议规范，来源见各常量处）：
- 键控速率 / 音距 = 12000/1920 = 6.25 Hz（8 音，3 bit/符号）
- 消息：77 bit → 加 14 bit CRC14 → 91 bit → LDPC(174,91) → 174 bit
        → Gray 映射为 58 个 3-bit 符号 → 插入 3×7 Costas → 79 符号
- FEC：LDPC 规则码，校验矩阵由 83 个度-3 校验方程构成
- CRC：多项式 0x2757（WSJT-X lib/crc14.cpp）

注册：本模块不主动注册，由 decoders/__init__.py 统一导入触发。

实现纪律（授粉）：本文档按公开协议规范独立实现。LDPC 生成矩阵、校验方程、
Gray 映射、Costas 序列、CRC 多项式属协议规范数据，为互操作必须逐位一致，
此处如实转录并标注来源（WSJT-X lib/ft8/）；解码流程（谱分析 → Costas 相关
找候选 → 基带提取 → GFSK 解调 → LLR → sum-product LDPC 译码 → CRC 校验）
参考公开协议描述与 VK3JPK 的 ft8.py 教学实现独立重写。
"""
from __future__ import annotations

import numpy as np
import scipy.signal

# --------------------------------------------------------------------------- #
# 协议常量（来源：WSJT-X lib/ft8/ 及公开协议描述）
# --------------------------------------------------------------------------- #

tr_period = 15                                  # 时隙长度（秒）
start_delay = 0.5                               # 帧内信号起始偏移（秒）
baud_rate = 12000 / 1920                        # 键控速率 = 6.25 Hz
freq_shift = baud_rate                          # 音距 = 键控速率
tone_order = 3                                  # 每符号比特数（8 音）
tone_count = 1 << tone_order
gaussian_bandwidth = 2.0

msg_bits = 77

# CRC 多项式（来源：WSJT-X lib/crc14.cpp）
crc_bits = 14
crc_padded_bits = 96
crc_polynomial = 0x2757

# LDPC 生成矩阵（来源：WSJT-X lib/ft8/ldpc_174_91_c_generator.f90）
generator_hex_strings = [
    "8329ce11bf31eaf509f27fc",
    "761c264e25c259335493132",
    "dc265902fb277c6410a1bdc",
    "1b3f417858cd2dd33ec7f62",
    "09fda4fee04195fd034783a",
    "077cccc11b8873ed5c3d48a",
    "29b62afe3ca036f4fe1a9da",
    "6054faf5f35d96d3b0c8c3e",
    "e20798e4310eed27884ae90",
    "775c9c08e80e26ddae56318",
    "b0b811028c2bf997213487c",
    "18a0c9231fc60adf5c5ea32",
    "76471e8302a0721e01b12b8",
    "ffbccb80ca8341fafb47b2e",
    "66a72a158f9325a2bf67170",
    "c4243689fe85b1c51363a18",
    "0dff739414d1a1b34b1c270",
    "15b48830636c8b99894972e",
    "29a89c0d3de81d665489b0e",
    "4f126f37fa51cbe61bd6b94",
    "99c47239d0d97d3c84e0940",
    "1919b75119765621bb4f1e8",
    "09db12d731faee0b86df6b8",
    "488fc33df43fbdeea4eafb4",
    "827423ee40b675f756eb5fe",
    "abe197c484cb74757144a9a",
    "2b500e4bc0ec5a6d2bdbdd0",
    "c474aa53d70218761669360",
    "8eba1a13db3390bd6718cec",
    "753844673a27782cc42012e",
    "06ff83a145c37035a5c1268",
    "3b37417858cc2dd33ec3f62",
    "9a4a5a28ee17ca9c324842c",
    "bc29f465309c977e89610a4",
    "2663ae6ddf8b5ce2bb29488",
    "46f231efe457034c1814418",
    "3fb2ce85abe9b0c72e06fbe",
    "de87481f282c153971a0a2e",
    "fcd7ccf23c69fa99bba1412",
    "f0261447e9490ca8e474cec",
    "4410115818196f95cdd7012",
    "088fc31df4bfbde2a4eafb4",
    "b8fef1b6307729fb0a078c0",
    "5afea7acccb77bbc9d99a90",
    "49a7016ac653f65ecdc9076",
    "1944d085be4e7da8d6cc7d0",
    "251f62adc4032f0ee714002",
    "56471f8702a0721e00b12b8",
    "2b8e4923f2dd51e2d537fa0",
    "6b550a40a66f4755de95c26",
    "a18ad28d4e27fe92a4f6c84",
    "10c2e586388cb82a3d80758",
    "ef34a41817ee02133db2eb0",
    "7e9c0c54325a9c15836e000",
    "3693e572d1fde4cdf079e86",
    "bfb2cec5abe1b0c72e07fbe",
    "7ee18230c583cccc57d4b08",
    "a066cb2fedafc9f52664126",
    "bb23725abc47cc5f4cc4cd2",
    "ded9dba3bee40c59b5609b4",
    "d9a7016ac653e6decdc9036",
    "9ad46aed5f707f280ab5fc4",
    "e5921c77822587316d7d3c2",
    "4f14da8242a8b86dca73352",
    "8b8b507ad467d4441df770e",
    "22831c9cf1169467ad04b68",
    "213b838fe2ae54c38ee7180",
    "5d926b6dd71f085181a4e12",
    "66ab79d4b29ee6e69509e56",
    "958148682d748a38dd68baa",
    "b8ce020cf069c32a723ab14",
    "f4331d6d461607e95752746",
    "6da23ba424b9596133cf9c8",
    "a636bcbc7b30c5fbeae67fe",
    "5cb0d86a07df654a9089a20",
    "f11f106848780fc9ecdd80a",
    "1fbb5364fb8d2c9d730d5ba",
    "fcb86bc70a50c9d02a5d034",
    "a534433029eac15f322e34c",
    "c989d9c7c3d3b8c55d75130",
    "7bb38b2f0186d46643ae962",
    "2644ebadeb44b9467d1f42c",
    "608cc857594bfbb55d69600",
]
generator_matrix = [int(h, base=16) >> 1 for h in generator_hex_strings]
ldpc_parity_bits = len(generator_matrix)
encoded_bits = msg_bits + crc_bits + ldpc_parity_bits

# LDPC 校验方程（来源：WSJT-X lib/ft8/ldpc_174_91_c_reordered_parity.f90）
# 174 行，每行 3 个校验方程下标（1-based Fortran），表示该码字比特参与的校验方程。
bit_terms = np.array([
    16, 45, 73, 25, 51, 62, 33, 58, 78, 1, 44, 45, 2, 7, 61, 3, 6, 54, 4, 35, 48,
    5, 13, 21, 8, 56, 79, 9, 64, 69, 10, 19, 66, 11, 36, 60, 12, 37, 58, 14, 32, 43,
    15, 63, 80, 17, 28, 77, 18, 74, 83, 22, 53, 81, 23, 30, 34, 24, 31, 40, 26, 41, 76,
    27, 57, 70, 29, 49, 65, 3, 38, 78, 5, 39, 82, 46, 50, 73, 51, 52, 74, 55, 71, 72,
    44, 67, 72, 43, 68, 78, 1, 32, 59, 2, 6, 71, 4, 16, 54, 7, 65, 67, 8, 30, 42,
    9, 22, 31, 10, 18, 76, 11, 23, 82, 12, 28, 61, 13, 52, 79, 14, 50, 51, 15, 81, 83,
    17, 29, 60, 19, 33, 64, 20, 26, 73, 21, 34, 40, 24, 27, 77, 25, 55, 58, 35, 53, 66,
    36, 48, 68, 37, 46, 75, 38, 45, 47, 39, 57, 69, 41, 56, 62, 20, 49, 53, 46, 52, 63,
    45, 70, 75, 27, 35, 80, 1, 15, 30, 2, 68, 80, 3, 36, 51, 4, 28, 51, 5, 31, 56,
    6, 20, 37, 7, 40, 82, 8, 60, 69, 9, 10, 49, 11, 44, 57, 12, 39, 59, 13, 24, 55,
    14, 21, 65, 16, 71, 78, 17, 30, 76, 18, 25, 80, 19, 61, 83, 22, 38, 77, 23, 41, 50,
    7, 26, 58, 29, 32, 81, 33, 40, 73, 18, 34, 48, 13, 42, 64, 5, 26, 43, 47, 69, 72,
    54, 55, 70, 45, 62, 68, 10, 63, 67, 14, 66, 72, 22, 60, 74, 35, 39, 79, 1, 46, 64,
    1, 24, 66, 2, 5, 70, 3, 31, 65, 4, 49, 58, 1, 4, 5, 6, 60, 67, 7, 32, 75,
    8, 48, 82, 9, 35, 41, 10, 39, 62, 11, 14, 61, 12, 71, 74, 13, 23, 78, 11, 35, 55,
    15, 16, 79, 7, 9, 16, 17, 54, 63, 18, 50, 57, 19, 30, 47, 20, 64, 80, 21, 28, 69,
    22, 25, 43, 13, 22, 37, 2, 47, 51, 23, 54, 74, 26, 34, 72, 27, 36, 37, 21, 36, 63,
    29, 40, 44, 19, 26, 57, 3, 46, 82, 14, 15, 58, 33, 52, 53, 30, 43, 52, 6, 9, 52,
    27, 33, 65, 25, 69, 73, 38, 55, 83, 20, 39, 77, 18, 29, 56, 32, 48, 71, 42, 51, 59,
    28, 44, 79, 34, 60, 62, 31, 45, 61, 46, 68, 77, 6, 24, 76, 8, 10, 78, 40, 41, 70,
    17, 50, 53, 42, 66, 68, 4, 22, 72, 36, 64, 81, 13, 29, 47, 2, 8, 81, 56, 67, 73,
    5, 38, 50, 12, 38, 64, 59, 72, 80, 3, 26, 79, 45, 76, 81, 1, 65, 74, 7, 18, 77,
    11, 56, 59, 14, 39, 54, 16, 37, 66, 10, 28, 55, 15, 60, 70, 17, 25, 82, 20, 30, 31,
    12, 67, 68, 23, 75, 80, 27, 32, 62, 24, 69, 75, 19, 21, 71, 34, 53, 61, 35, 46, 47,
    33, 59, 76, 40, 43, 83, 41, 42, 63, 49, 75, 83, 20, 44, 48, 42, 49, 57,
]).reshape(encoded_bits, 3)
bit_terms -= 1  # Fortran 1-based → Python 0-based


def _build_parity_equations():
    """由 bit_terms 派生校验方程的各种表示（供 numpy 向量化 sum-product 使用）。"""
    check_terms: list[list[int]] = [[] for _ in range(ldpc_parity_bits)]
    check_flat_terms: list[list[int]] = [[] for _ in range(ldpc_parity_bits)]

    for i, row in enumerate(bit_terms):
        for j, t in enumerate(row):
            check_terms[t].append(i)
            check_flat_terms[t].append(i * 3 + j)

    bit_flat_terms: list[list[int]] = [[] for _ in range(encoded_bits)]
    for i, row in enumerate(check_terms):
        for j, t in enumerate(row):
            bit_flat_terms[t].append(i * 7 + j)
        if j == 5:
            check_terms[i].append(-1)
            check_flat_terms[i].append(-1)

    return (np.array(check_terms), np.array(check_flat_terms),
            np.array(bit_flat_terms))


check_terms, check_flat_terms, bit_flat_terms = _build_parity_equations()
adjusted_check_terms = check_terms + 1
adjusted_check_flat_terms = check_flat_terms + 3
del _build_parity_equations

encoded_bits = msg_bits + crc_bits + ldpc_parity_bits
encoded_symbols = encoded_bits // tone_order

# Gray 映射与 Costas 序列（来源：WSJT-X lib/ft8/genft8.f90）
gray_map = [0, 1, 3, 2, 5, 6, 4, 7]
costas = [3, 1, 4, 0, 6, 5, 2]
costas_offsets = [0, 36, 72]
costas_order = len(costas)
costas_symbols = costas_order * len(costas_offsets)

symbol_offsets = (list(range(costas_order, costas_offsets[1])) +
                  list(range(costas_offsets[1] + costas_order, costas_offsets[2])))
assert encoded_symbols == len(symbol_offsets)

total_symbols = encoded_symbols + costas_symbols


# --------------------------------------------------------------------------- #
# 呼号 / 报告 / 消息编码（pack77 / unpack77）
# --------------------------------------------------------------------------- #

class Callsign:
    """呼号 28 bit 编码管理（标准呼号 / 哈希非标准呼号 / 令牌）。"""

    full_charset = ' 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ/'
    charset_1 = full_charset[:-1]
    charset_2 = full_charset[1:-1]
    charset_3 = full_charset[1:11]
    charset_456 = full_charset[0] + full_charset[11:-1]
    charsets = [charset_1, charset_2, charset_3, charset_456, charset_456, charset_456]

    max_std_calls = 1
    for _charset in charsets:
        max_std_calls *= len(_charset)
    max_non_std_calls = 1 << 22
    max_tokens = (1 << 28) - max_std_calls - max_non_std_calls

    tokens = ['DE', 'QRZ', 'CQ']

    hash_table = {10: {}, 12: {}, 22: {}}
    all_calls = {}

    def __init__(self, call):
        self.call = call
        self.pack28 = Callsign._token_pack(call)
        self.token = self.pack28 is not None
        if self.token:
            self.hash = (None, None, None)
            self.standard = False
            return

        # 非令牌：按呼号处理
        words = call.split()
        if len(words) > 1:
            raise ValueError("Callsign contains spaces")

        # 尝试标准呼号打包
        self.pack28 = Callsign._standard_pack(call)
        self.standard = self.pack28 is not None

        # 校验非标准呼号字符
        if not self.standard:
            l = len(call)
            if l > 11:
                raise ValueError("Callsign more than 10 characters long")
            elif not all(c in Callsign.full_charset for c in call):
                raise ValueError("Callsign contains invalid characters")

        # 计算哈希码（不同长度）并登记进哈希表
        i = 0
        for c in call.ljust(11):
            i = i * len(Callsign.full_charset) + Callsign.full_charset.index(c)
        hash64 = (i * 47055833459) & (2 ** 64 - 1)

        hash22 = hash64 >> 42
        hash12 = hash64 >> 52
        hash10 = hash64 >> 54
        self.hash = (hash10, hash12, hash22)
        Callsign.hash_table[10][hash10] = self
        Callsign.hash_table[12][hash12] = self
        Callsign.hash_table[22][hash22] = self

        # 非标准呼号：28 bit 打包 = 22 bit 哈希 + max_tokens 偏移
        if not self.standard:
            self.pack28 = hash22 + Callsign.max_tokens

        Callsign.all_calls[call] = self

    def __str__(self):
        """返回呼号字符串（非标准哈希呼号加尖括号）。"""
        if (not self.standard) and (not self.token):
            return "<" + self.call + ">"
        return self.call

    def isToken(self):
        """是否为协议令牌（DE/QRZ/CQ...）。"""
        return self.token

    def isStandard(self):
        """是否为非哈希标准呼号。"""
        return self.standard

    @classmethod
    def getHash(cls, code, length=22):
        """按指定长度哈希码取呼号对象（无则 None）。"""
        return cls.hash_table[length].get(code)

    @classmethod
    def unpack28(cls, i):
        """28 bit 打包值 → 呼号对象。"""
        # 令牌
        if i < cls.max_tokens:
            if i < len(cls.tokens):
                return Callsign(cls.tokens[i])
            elif i < len(cls.tokens) + 1000:
                return Callsign("CQ " + str(i - len(cls.tokens)))
            elif i < len(cls.tokens) + 1000 + len(cls.charset_456) ** 4:
                i = i - len(cls.tokens) - 1000
                c = []
                s = len(cls.charset_456)
                for _ in range(4):
                    c.insert(0, cls.charset_456[i % s])
                    i = i // s
                return Callsign("CQ " + "".join(c).strip())
            return None

        # 哈希非标准呼号
        if i < cls.max_tokens + cls.max_non_std_calls:
            hash22 = i - cls.max_tokens
            return cls.hash_table[22].get(hash22)

        # 标准呼号
        i = i - cls.max_tokens - cls.max_non_std_calls
        c = []
        for charset in reversed(cls.charsets):
            size = len(charset)
            c.insert(0, charset[i % size])
            i = i // size
        c = "".join(c).strip()

        # 特殊呼号前缀处理
        if c[0] == "Q":
            c = "3X" + c[1:]
        elif c[:3] == "3D0":
            c = "3DA0" + c[3:]

        if c in cls.all_calls:
            return cls.all_calls[c]
        return Callsign(c)

    @classmethod
    def _standard_pack(cls, call):
        """标准呼号 → 28 bit 打包（非标准返回 None）。"""
        l = len(call)

        # 斯威士兰 3DA0... → 3D0...
        if l > 4 and call[:4] == "3DA0":
            call = "3D0" + call[4:]
            l -= 1
        # 几内亚 3X.. → Q..
        elif l > 2 and call[:2] == "3X" and call[2].isalpha():
            call = "Q" + call[2:]
            l -= 1

        # 找最后一个数字
        last_digit = None
        for i, c in enumerate(call):
            if c.isdigit():
                last_digit = i

        # 数字在第二位则前面补空格
        if last_digit == 1:
            call = " " + call
            l += 1

        if l > 6 or l < 3 or not all(c in charset for charset, c in zip(cls.charsets, call)):
            return None

        i = 0
        for charset, c in zip(cls.charsets, call.ljust(len(cls.charsets))):
            i = i * len(charset) + charset.index(c)
        return i + cls.max_tokens + (1 << 22)

    @classmethod
    def _token_pack(cls, token):
        """令牌 → 28 bit 打包（非令牌返回 None）。"""
        words = token.split()
        if words[0] not in cls.tokens:
            return None

        if len(words) == 1:
            return cls.tokens.index(token)

        if words[0] != "CQ" or len(words) != 2:
            return None

        # CQ nnn
        if words[1].isdecimal():
            v = int(words[1])
            if v < 0 or v > 999:
                return None
            return v + len(cls.tokens)

        # CQ aaaa
        if len(words[1]) > 4 or not all(c in cls.charset_456 for c in words[1]):
            return None
        v = 0
        for c in words[1].ljust(4):
            v = v * len(cls.charset_456) + cls.charset_456.index(c)
        return v + len(cls.tokens) + 1000


class Report:
    """报告父类（网格 / 信号 / 其他 / 序列号）。"""

    max_grid_4 = 180 * 180
    max_serial = 4095
    other_reports = ["", "RRR", "RR73", "73"]
    charset_12 = "ABCDEFGHIJKLMNOPQR"
    charset_34 = "0123456789"
    charset_56 = "abcdefghijklmnopqrstuvwx"
    charsets = [charset_12, charset_12, charset_34, charset_34, charset_56, charset_56]

    def __init__(self, value):
        self.value = value
        self.pack5 = None
        self.pack12 = None
        self.pack15 = None
        self.pack25 = None

    def __str__(self):
        return str(self.value)

    def __eq__(self, other):
        if isinstance(other, Report):
            return self.value == other.value
        return False

    @classmethod
    def unpack15(cls, i):
        if i <= cls.max_grid_4:
            c = []
            for charset in reversed(cls.charsets[:4]):
                size = len(charset)
                c.insert(0, charset[i % size])
                i = i // size
            return LocationReport("".join(c))

        i -= cls.max_grid_4
        if i <= 4:
            return OtherReport(cls.other_reports[i - 1])
        if i <= 65:
            return SignalReport(i - 35)
        return None


class LocationReport(Report):
    """网格定位报告。"""

    def __init__(self, value):
        super().__init__(value)
        l = len(value)
        if l not in [4, 6] or not all(c in charset for charset, c in zip(Report.charsets, value)):
            raise ValueError()

        i = 0
        for charset, c in zip(Report.charsets, value):
            i = i * len(charset) + charset.index(c)
        if l == 4:
            self.pack15 = i
        else:
            self.pack25 = i


class SignalReport(Report):
    """信号报告（-30 ~ +30 dB）。"""

    def __init__(self, value):
        super().__init__(value)
        if not isinstance(value, int) or value < -30 or value > 30:
            raise ValueError()
        self.pack15 = Report.max_grid_4 + 35 + value
        self.pack5 = (value + 30) / 2

    def __str__(self):
        return f"{self.value:=+03d}"


class OtherReport(Report):
    """其他报告（RRR/RR73/73 等）。"""

    def __init__(self, value):
        super().__init__(value)
        if value not in Report.other_reports:
            raise ValueError()
        self.pack15 = Report.max_grid_4 + Report.other_reports.index(value) + 1


class SerialReport(Report):
    """序列号报告。"""

    def __init__(self, value):
        super().__init__(value)
        if not isinstance(value, int) or value > Report.max_serial:
            raise ValueError()
        self.pack12 = value


class RTTYSignal:
    """ARRL RTTY 竞赛信号。"""

    def __init__(self, value):
        if value < 529 or value > 599 or (value % 10) != 9:
            raise ValueError()
        self.value = value
        self.pack3 = (self.value - 509) // 10 - 2

    def __str__(self):
        return str(self.value)

    @classmethod
    def unpack3(cls, bits):
        return cls((bits + 2) * 10 + 509)


class RTTYState:
    """ARRL RTTY 竞赛州/省。"""

    states = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
              "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
              "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
              "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
              "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
              "NB", "NS", "QC", "ON", "MB", "SK", "AB", "BC", "NWT", "NF",
              "LB", "NU", "YT", "PEI", "DC"]

    state_offset = 8001

    def __init__(self, value):
        self.value = value
        if value.isnumeric() and int(value) < self.state_offset:
            self.pack13 = int(value)
        elif value in self.states:
            self.pack13 = self.state_offset + self.states.index(value)
        else:
            raise ValueError()

    def __str__(self):
        if self.pack13 < self.state_offset:
            return f"{self.value:04d}"
        return self.value

    @classmethod
    def unpack13(cls, bits):
        if bits < cls.state_offset:
            return cls(str(bits))
        return cls(cls.states[bits - cls.state_offset])


class Message:
    """FT8 消息基类（77 bit 打包 / 91 bit 含 CRC）。"""

    class MessageError(Exception):
        """消息构造错误超类。"""

    class CRCError(MessageError):
        """CRC 校验失败。"""

    class UnsupportedError(MessageError):
        """不支持的报文类型/子类型。"""

    def __eq__(self, other):
        return str(self) == str(other)

    @staticmethod
    def _crc(msg, chk):
        """计算 FT8 CRC14（msg 为 77 bit 整数，chk 为 14 bit）。"""
        remainder = (msg << (crc_padded_bits - msg_bits)) | chk
        mask = 1 << (crc_padded_bits - 1)
        shifted_poly = ((1 << crc_bits) | crc_polynomial) << (crc_padded_bits - crc_bits - 1)
        for _ in range(crc_padded_bits - crc_bits):
            if remainder & mask:
                remainder ^= shifted_poly
            mask >>= 1
            shifted_poly >>= 1
        return remainder

    def encode(self):
        """消息 → 79 个信道符号（CRC + LDPC + Gray + Costas）。"""
        msg_crc = self.pack77 << 14 | Message._crc(self.pack77, 0)

        parity = 0
        for row in generator_matrix:
            parity = parity << 1
            parity = parity | (bin(row & msg_crc).count("1") % 2)

        codeword = (msg_crc << 83) | parity

        msg_symbols = []
        mask = (1 << 3) - 1
        for _ in range(174 // 3):
            msg_symbols.insert(0, gray_map[codeword & mask])
            codeword = codeword >> 3

        symbols = (costas + msg_symbols[:encoded_symbols // 2]
                   + costas + msg_symbols[encoded_symbols // 2:] + costas)
        return symbols

    @classmethod
    def unpack77(cls, bits):
        """77 bit → 消息对象。"""
        msg_type = bits & 7
        if msg_type == 0:
            msg_subtype = (bits >> 3) & 7
            if msg_subtype == TextMessage.msg_subtype:
                return TextMessage.unpack77(bits)
            elif msg_subtype == TelemetryMessage.msg_subtype:
                return TelemetryMessage.unpack77(bits)
        elif msg_type == StandardMessage.msg_type:
            return StandardMessage.unpack77(bits)
        elif msg_type == EUVHFMessage.msg_type:
            return EUVHFMessage.unpack77(bits)
        elif msg_type == RTTYMessage.msg_type:
            return RTTYMessage.unpack77(bits)
        raise cls.UnsupportedError()

    @classmethod
    def unpack91(cls, bits):
        """91 bit（含 CRC）→ 消息对象（CRC 失败抛 CRCError）。"""
        crc = bits & ((1 << crc_bits) - 1)
        msg = bits >> crc_bits
        if cls._crc(msg, crc):
            raise cls.CRCError()
        return cls.unpack77(msg)


class TextMessage(Message):
    """自由文本消息。"""

    charset = " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ+=./?"
    charset_size = len(charset)
    msg_type = 0
    msg_subtype = 0
    max_msg_size = 13

    def __init__(self, text):
        self.text = text.strip()
        if len(text) > TextMessage.max_msg_size or not all(c in TextMessage.charset for c in text):
            raise ValueError()

        i = 0
        for c in self.text:
            i *= TextMessage.charset_size
            i += TextMessage.charset.index(c)
        self.pack77 = (i << 6) | (TextMessage.msg_subtype << 3) | TextMessage.msg_type

    def __str__(self):
        return f'TextMessage("{self.text}")'

    @classmethod
    def unpack77(cls, bits):
        i = bits >> 6
        c = []
        for _ in range(cls.max_msg_size):
            c.insert(0, cls.charset[i % cls.charset_size])
            i = i // cls.charset_size
        return cls("".join(c).strip())


class TelemetryMessage(Message):
    """遥测消息。"""

    msg_type = 0
    msg_subtype = 5

    def __init__(self, bits):
        self.bits = bits
        self.pack77 = (bits << 6) | (TelemetryMessage.msg_subtype << 3) | TelemetryMessage.msg_type

    def __str__(self):
        return f"TelemetryMessage({hex(self.bits)})"

    @classmethod
    def unpack77(cls, bits):
        return cls(bits >> 6)


class StandardMessage(Message):
    """标准消息（双呼号 + 报告 + 可选 roger）。"""

    msg_type = 1
    field_widths = [28, 1, 28, 1, 1, 15, 3]

    def __init__(self, call_1, call_2, report, roger=False, rover_1=False, rover_2=False):
        self.call_1 = call_1
        self.rover_1 = rover_1
        self.call_2 = call_2
        self.rover_2 = rover_2
        self.roger = roger
        self.report = report
        self.fields = [self.call_1, self.rover_1, self.call_2, self.rover_2, self.roger, self.report]
        field_bits = [call_1.pack28, rover_1, call_2.pack28, rover_2, roger,
                      report.pack15, self.msg_type]
        self.pack77 = 0
        for w, f in zip(self.field_widths, field_bits):
            self.pack77 = (self.pack77 << w) | int(f)

    def __str__(self):
        r = "/R" if self.msg_type == 1 else "/P"
        s = str(self.call_1)
        if self.rover_1:
            s += r
        s += " " + str(self.call_2)
        if self.rover_2:
            s += r
        s += " "
        if self.fields[4]:
            s += "R"
        s += str(self.report)
        return f"{self.__class__.__name__}({s})"

    @classmethod
    def unpack77(cls, bits):
        f = []
        for w in reversed(cls.field_widths):
            f.insert(0, bits & ((1 << w) - 1))
            bits >>= w
        return cls(Callsign.unpack28(f[0]), Callsign.unpack28(f[2]), Report.unpack15(f[5]),
                   f[4] != 0, f[1] != 0, f[3] != 0)


class EUVHFMessage(StandardMessage):
    """EU VHF 竞赛消息。"""

    msg_type = 2

    def __init__(self, call_1, call_2, report, roger=False, portable_1=False, portable_2=False):
        super().__init__(call_1, call_2, report, roger, portable_1, portable_2)


class RTTYMessage(Message):
    """ARRL RTTY 竞赛消息。"""

    msg_type = 3
    field_widths = [1, 28, 28, 1, 3, 13, 3]

    def __init__(self, call_1, call_2, roger, signal, state, thank_you=False):
        if not isinstance(call_1, Callsign):
            raise ValueError()
        self.call_1 = call_1
        if not isinstance(call_2, Callsign):
            raise ValueError()
        self.call_2 = call_2
        if not isinstance(signal, RTTYSignal):
            raise ValueError()
        self.signal = signal
        if not isinstance(roger, bool):
            raise ValueError()
        self.roger = roger
        if not isinstance(state, RTTYState):
            raise ValueError()
        self.state = state
        if not isinstance(thank_you, bool):
            raise ValueError()
        self.thank_you = thank_you

        field_bits = [thank_you, call_1.pack28, call_2.pack28, roger, signal.pack3, state.pack13, self.msg_type]
        self.pack77 = 0
        for w, f in zip(self.field_widths, field_bits):
            self.pack77 = (self.pack77 << w) | int(f)

    def __str__(self):
        s = "TU; " + str(self.call_1) if self.thank_you else str(self.call_1)
        s += " " + str(self.call_2)
        if self.roger:
            s += " R"
        s += " " + str(self.signal)
        s += " " + str(self.state)
        return f"RTTYMessage({s})"

    @classmethod
    def unpack77(cls, bits):
        f = []
        for w in reversed(cls.field_widths):
            f.insert(0, bits & ((1 << w) - 1))
            bits >>= w
        return cls(Callsign.unpack28(f[1]), Callsign.unpack28(f[2]), f[3] != 0, RTTYSignal.unpack3(f[4]),
                   RTTYState.unpack13(f[5]), f[0] != 0)


class Candidate:
    """候选信号（频率 / 时间偏移 / 相关 SNR）。"""

    def __init__(self, freq, offset, sync):
        self.freq = freq
        self.offset = offset
        self.sync = sync


class SpectralAnalysis:
    """对 IQ 样本做谱分析，识别候选 FT8 信号。"""

    spectrogram_bins_per_tone = 2
    spectrogram_steps_per_symbol = 4
    spectrogram_scale_factor = 300.0

    low_frequency = 100
    high_frequency = 2700
    offset_bound = 2.5

    max_candidates = 300
    normalization_percentile = 60
    candidate_threshold = 1.5

    spectrogram_time_step = 1 / baud_rate / spectrogram_steps_per_symbol
    spectrogram_bin_width = freq_shift / spectrogram_bins_per_tone
    spectrum_bin_width = 1 / (tr_period + 1)

    def __init__(self, samples, sample_rate):
        if sample_rate != 12000:
            raise ValueError("FT8 目前仅支持 12000 Hz 采样率")
        self.sample_rate = sample_rate
        self.samples = samples
        self.spectrogram = SpectralAnalysis._calculate_spectrogram(samples, sample_rate)
        # 全零/无能量输入时 baseline 多项式拟合会崩 TypeError，诚实降级为 ValueError
        if not np.any(self.spectrogram > 0):
            raise ValueError("输入信号无能量，无法 FT8 解码")
        self.baseline = SpectralAnalysis._calculate_baseline(self.spectrogram)
        self.complex_spectrum = SpectralAnalysis._calculate_complex_spectrum(samples, sample_rate)
        self.snr_matrix = SpectralAnalysis._correlate_costas_arrays(self.spectrogram)
        self.candidate_list = SpectralAnalysis._find_candidates(self.snr_matrix)

    def noise_baseline(self, freq):
        # np.int 已在 NumPy 1.24+ 移除，改用内置 int（修解码后 SNR 估算必崩）
        index = np.rint((freq - self.low_frequency) / freq_shift * self.spectrogram_bins_per_tone).astype(int)
        return np.power(10.0, 0.1 * self.baseline[index])

    @staticmethod
    def _calculate_spectrogram(samples, sample_rate):
        samples_per_symbol = int(sample_rate / freq_shift)
        dft_length = samples_per_symbol * SpectralAnalysis.spectrogram_bins_per_tone
        overlap_samples = samples_per_symbol - samples_per_symbol // SpectralAnalysis.spectrogram_steps_per_symbol
        # 复数 IQ 输入必须用双边谱：return_onesided 显式置 False（此前靠 scipy 静默切换并告警）
        _, _, s = scipy.signal.spectrogram(samples, sample_rate, "boxcar", samples_per_symbol,
                                           overlap_samples, dft_length, False, False)
        return np.transpose(s)

    @staticmethod
    def _calculate_baseline(spectrogram):
        low_freq_index = int(SpectralAnalysis.low_frequency / freq_shift * SpectralAnalysis.spectrogram_bins_per_tone)
        high_freq_index = int(SpectralAnalysis.high_frequency / freq_shift * SpectralAnalysis.spectrogram_bins_per_tone)
        db = 10.0 * np.log10(np.mean(spectrogram[:, low_freq_index:high_freq_index], axis=0))

        indexes = np.arange(high_freq_index - low_freq_index)
        segments = np.array_split(indexes, 10)

        base_indexes = []
        base_values = []
        for segment in segments:
            segment_values = db[segment]
            base = np.percentile(segment_values, 10)
            selector = segment_values <= base
            base_indexes.append(segment[selector])
            base_values.append(segment_values[selector])

        base_index = np.concatenate(base_indexes)
        base_value = np.concatenate(base_values)

        midpoint = (high_freq_index - low_freq_index) // 2
        base_index -= midpoint
        poly = np.polynomial.polynomial.Polynomial(
            np.polynomial.polynomial.polyfit(base_index, base_value, 4))
        return poly(indexes - midpoint)

    @staticmethod
    def _calculate_complex_spectrum(samples, sample_rate):
        # sample_rate 可能为 float（默认 12000.0），np.fft 的 n 参数必须为 int
        dft_length = int((tr_period + 1) * sample_rate)
        # numpy>=2 的 rfft 不再接受复数输入，改用全谱 FFT
        return np.fft.fft(samples, dft_length)

    @staticmethod
    def _correlate_costas_arrays(spectrogram):
        symbol_step = SpectralAnalysis.spectrogram_steps_per_symbol
        tone_step = SpectralAnalysis.spectrogram_bins_per_tone

        t_matrix = np.zeros((costas_order * symbol_step, costas_order * tone_step))
        for symbol, tone in enumerate(costas):
            t_matrix[symbol * symbol_step, tone * tone_step] = 1.0

        t0_matrix = np.zeros(t_matrix.shape)
        t0_matrix[::symbol_step, ::tone_step] = 1.0

        low_freq_index = int(SpectralAnalysis.low_frequency / freq_shift * tone_step)
        high_freq_index = int(SpectralAnalysis.high_frequency / freq_shift * tone_step)
        high_freq_index += t_matrix.shape[1] - 1
        freq_slice = slice(low_freq_index, high_freq_index)

        low_time_index = int((start_delay - SpectralAnalysis.offset_bound) * baud_rate * symbol_step)
        high_time_index = int((start_delay + SpectralAnalysis.offset_bound) * baud_rate * symbol_step)
        time_steps = high_time_index - low_time_index
        high_time_index += t_matrix.shape[0] - 1

        t = []
        t0 = []
        for offset in costas_offsets:
            low = max(0, low_time_index + offset * symbol_step)
            high = min(spectrogram.shape[0], high_time_index + offset * symbol_step)
            time_slice = slice(low, high)
            t.append(scipy.signal.correlate(spectrogram[time_slice, freq_slice], t_matrix, mode="valid"))
            t0.append(scipy.signal.correlate(spectrogram[time_slice, freq_slice], t0_matrix, mode="valid"))

        time_pad = time_steps - t[0].shape[0]
        t[0] = np.pad(t[0], ((time_pad, 0), (0, 0)), mode="constant")
        t0[0] = np.pad(t0[0], ((time_pad, 0), (0, 0)), mode="constant")
        time_pad = time_steps - t[-1].shape[0]
        t[-1] = np.pad(t[-1], ((0, time_pad), (0, 0)), mode="constant")
        t0[-1] = np.pad(t0[-1], ((0, time_pad), (0, 0)), mode="constant")

        t_sum = t[1] + t[2]
        t0_sum = t0[1] + t0[2]
        # 无信号区域 t0_sum == t_sum → 0/0 = NaN；用 errstate 抑制除零/无效告警，
        # 并置 0（无信号语义），防止 NaN 污染下游 argsort 排序（NaN 升序排末尾，会挤占 top-N 候选区）
        with np.errstate(divide="ignore", invalid="ignore"):
            sync_bc = (costas_order - 1) * t_sum / (t0_sum - t_sum)

            t_sum += t[0]
            t0_sum += t0[0]
            sync_abc = (costas_order - 1) * t_sum / (t0_sum - t_sum)

            return np.nan_to_num(np.fmax(sync_abc, sync_bc), nan=0.0)

    @staticmethod
    def _find_candidates(snr_matrix):
        peak_time_step = np.argmax(snr_matrix, axis=0)
        peak_snr = snr_matrix[peak_time_step, np.arange(snr_matrix.shape[1])]

        sorted_bins = np.argsort(peak_snr)
        normalization_bin = sorted_bins[int(SpectralAnalysis.normalization_percentile * sorted_bins.size / 100)]

        candidate_bins = sorted_bins[-SpectralAnalysis.max_candidates:]
        min_snr = SpectralAnalysis.candidate_threshold * peak_snr[normalization_bin]
        candidate_bins = candidate_bins[peak_snr[candidate_bins] > min_snr]
        # 无候选时诚实降级：返回空数组，由上层统一抛"未检测到有效信号"
        if candidate_bins.size == 0:
            return np.empty((0, 3))

        duplicates = np.amax(np.tril(np.abs(candidate_bins - candidate_bins[np.newaxis].T) == 1), axis=0)
        candidate_bins = candidate_bins[np.logical_not(duplicates)]

        candidate_bins = np.sort(candidate_bins)

        freqs = candidate_bins * SpectralAnalysis.spectrogram_bin_width + SpectralAnalysis.low_frequency
        offsets = peak_time_step[candidate_bins] * SpectralAnalysis.spectrogram_time_step - SpectralAnalysis.offset_bound
        return np.column_stack((freqs, offsets, peak_snr[candidate_bins]))


class FSK:
    """基带 MFSK 参考信号生成。"""

    def __init__(self, symbols, sample_rate, samples_per_symbol):
        signal = np.empty((len(symbols), samples_per_symbol), dtype=np.complex128)
        phi = 0.0
        for i, symbol in enumerate(symbols):
            delta_phi = np.pi * 2.0 * symbol / samples_per_symbol
            for k in range(samples_per_symbol):
                phi += delta_phi
                phi %= np.pi * 2.0
                signal[i, k] = np.cos(phi) + 1.0j * np.sin(phi)
        self.signal = np.reshape(signal, len(symbols) * samples_per_symbol)


class Signal:
    """对候选 FT8 信号做精细解调与译码。"""

    sample_rate = 200
    samples_per_symbol = int(sample_rate / baud_rate)
    demap_max_symbols = 3
    decoder_max_iterations = 200

    freq_step = 0.5
    correction_bound = 5
    symbol_correction_range = np.arange(-correction_bound, correction_bound + 1) * freq_step / freq_shift
    costas_conjugates = np.empty((len(symbol_correction_range), samples_per_symbol * costas_order), dtype=np.complex128)
    correction_signals = np.empty((len(symbol_correction_range), samples_per_symbol * total_symbols), dtype=np.complex128)

    for _i, _correction in enumerate(symbol_correction_range):
        _symbols = np.array(costas) + _correction
        costas_conjugates[_i] = np.conjugate(FSK(_symbols, sample_rate, samples_per_symbol).signal)
        _symbols = np.full(total_symbols, -_correction)
        correction_signals[_i] = FSK(_symbols, sample_rate, samples_per_symbol).signal

    del _i, _correction, _symbols

    demap_max_bits = demap_max_symbols * tone_order
    demap_max_permutations = 1 << demap_max_bits
    demap_one = np.zeros((demap_max_bits, demap_max_permutations), dtype="bool")
    for _i in range(demap_max_bits):
        for _j in range(demap_max_permutations):
            if _j & 1 << _i:
                demap_one[_i, _j] = True
    demap_not_one = np.logical_not(demap_one)
    del _i, _j

    def __init__(self, candidate, analysis):
        self.spectrum, self.freq, self.offset, self.baseband, self.sync = Signal._refine_estimates(candidate, analysis)
        self.msg, self.snr, self.obs, self.llr, self.codeword = Signal._detect(self.baseband, self.freq, analysis)

    def __str__(self):
        return f"{self.snr:4.1f} {self.offset:4.1f} {self.freq:4.0f} {self.msg}"

    @staticmethod
    def _extract_baseband(candidate, analysis):
        bin_width = SpectralAnalysis.spectrum_bin_width
        f = candidate[0]
        start_bin = int(f / bin_width)
        upper_bin = int((f + 8.5 * freq_shift) / bin_width)
        lower_bin = int((f - 1.5 * freq_shift) / bin_width)
        bin_range = upper_bin - lower_bin + 1
        padded_bin_range = int(Signal.sample_rate / bin_width)

        s = np.zeros(padded_bin_range, dtype=analysis.complex_spectrum.dtype)
        window = scipy.signal.windows.tukey(bin_range, 1 / 5)
        s[0:bin_range] = analysis.complex_spectrum[lower_bin:upper_bin + 1] * window
        s = np.roll(s, lower_bin - start_bin)

        return s, np.fft.ifft(s) / 32

    @staticmethod
    def _correlate(baseband, costas_conjugate):
        t = 0.0
        for offset in costas_offsets:
            p = baseband[offset:offset + costas_order * Signal.samples_per_symbol] * costas_conjugate
            s = np.sum(np.reshape(p, (costas_order, Signal.samples_per_symbol)), axis=1)
            t += np.sum(np.abs(s) ** 2)
        return t

    @staticmethod
    def _refine_estimates(candidate, analysis):
        spectrum, baseband = Signal._extract_baseband(candidate, analysis)
        freq = candidate[0]
        offset = candidate[1]

        start_sample = int((start_delay + offset) * Signal.sample_rate)
        total_samples = total_symbols * Signal.samples_per_symbol
        search_bound = Signal.samples_per_symbol // 4

        lowest_sample = start_sample - search_bound
        if lowest_sample < 0:
            baseband = np.pad(baseband, (-lowest_sample, 0), "constant")
            start_sample = search_bound

        highest_sample = start_sample + search_bound + 1 + total_samples
        if highest_sample > baseband.size:
            baseband = np.pad(baseband, (0, highest_sample - baseband.size), "constant")

        search_range = range(start_sample - search_bound, start_sample + search_bound + 1)
        smax = -1.0
        best_sample = start_sample
        for sample in search_range:
            s = Signal._correlate(baseband[sample:sample + total_samples],
                                  Signal.costas_conjugates[Signal.correction_bound])
            if s > smax:
                smax = s
                best_sample = sample

        best_offset = (best_sample / Signal.sample_rate) - start_delay
        truncated_baseband = baseband[best_sample:best_sample + total_samples]

        smax = -1.0
        best_i = Signal.correction_bound
        best_correction = 0.0
        for i, correction in enumerate(Signal.symbol_correction_range):
            s = Signal._correlate(truncated_baseband, Signal.costas_conjugates[i])
            if s > smax:
                smax = s
                best_i = i
                best_correction = correction

        corrected_baseband = truncated_baseband * Signal.correction_signals[best_i]
        corrected_frequency = freq + best_correction * freq_shift

        return spectrum, corrected_frequency, best_offset, corrected_baseband, smax

    @staticmethod
    def _demodulate(baseband):
        _, _, dft = scipy.signal.stft(baseband, fs=200, window="boxcar", nperseg=32, noverlap=0,
                                      boundary=None, return_onesided=False, axis=1)
        dft = dft[:, :tone_count]

        tones = np.argmax(np.abs(dft), axis=1)
        good_tones = 0
        for offset in costas_offsets:
            good_tones += np.sum(tones[offset:offset + costas_order] == costas)

        # 健全性检查：Costas 同步必须命中足够多，否则视为噪声
        if good_tones <= 6:
            raise ValueError("Costas 同步命中不足，疑似噪声")

        return dft

    @staticmethod
    def _demap(obs, num_symbols):
        """M-FSK/M-GFSK 软解映射：把观测 DFT 输出转成每码字比特的 LLR。"""
        llr = np.empty(encoded_bits)
        mask = (1 << tone_order) - 1
        num_bits = (num_symbols + 1) * tone_order
        num_permutations = 1 << num_bits

        for i in range(0, encoded_symbols, num_symbols + 1):
            # 对一组符号的所有 bit 排列求和
            s = np.zeros(num_permutations, dtype="complex128")
            for p in range(num_permutations):
                t = p
                for j in range(num_symbols, -1, -1):
                    tone = gray_map[t & mask]
                    s[p] += obs[symbol_offsets[i] + j, tone]
                    t >>= tone_order

            m = np.abs(s)

            first_bit = i * tone_order
            last_bit = min(first_bit + num_bits, encoded_bits)
            bit_pos = num_bits - 1
            for encoded_bit in range(first_bit, last_bit):
                llr[encoded_bit] = (np.amax(m[Signal.demap_one[bit_pos, :num_permutations]]) -
                                    np.amax(m[Signal.demap_not_one[bit_pos, :num_permutations]]))
                bit_pos -= 1

        llr /= np.std(llr)
        llr *= 2.83  # sqrt(8)（WSJT-X 经验缩放因子）
        return llr

    @staticmethod
    def _sum_product_decoder(demapper_llr):
        """sum-product LDPC 译码：从 LLR 恢复合法码字。"""
        codeword = np.empty(encoded_bits + 1, np.bool)
        codeword[0] = False
        bit_llr = np.empty(encoded_bits)
        bit_in = np.zeros((encoded_bits, 3))
        bit_out = np.zeros((encoded_bits + 1, 3))
        bit_out[0] = 1
        check_in = np.ones((ldpc_parity_bits, 7))
        check_out = np.empty((ldpc_parity_bits, 7))
        selector = 1 - np.identity(7)

        msg = None

        for i in range(Signal.decoder_max_iterations):
            bit_llr[:] = demapper_llr + np.sum(bit_in, axis=1)

            # 硬判决并检查是否已构成合法码字
            codeword[1:] = bit_llr > 0
            bad_bits = np.sum(np.sum(np.take(codeword, adjusted_check_terms), axis=1) % 2)
            if bad_bits == 0:
                bits = 0
                for bit in codeword[1:92]:
                    bits = (bits << 1) | int(bit)
                try:
                    msg = Message.unpack91(bits)
                    break  # CRC 也通过，译码完成
                except Message.CRCError:
                    pass  # CRC 未通过，继续迭代

            bit_out[1:] = np.tanh(-0.5 * (bit_llr[:, np.newaxis] - bit_in))
            np.take(bit_out.flat, adjusted_check_flat_terms, out=check_in)
            np.prod(np.where(selector, check_in[:, np.newaxis, :], 1.0), axis=2, out=check_out)
            np.take(check_out.flat, bit_flat_terms, out=bit_in)
            bit_in[:] = -2.0 * np.arctanh(bit_in)

        return msg, codeword[1:], i, bad_bits

    @staticmethod
    def _get_snr(obs, codeword, freq, analysis):
        """成功译码后，用噪声基线估算信噪比。"""
        msg_symbols = []
        s = 0
        for i, bit in enumerate(codeword):
            s = (s << 1) | int(bit)
            if (i % 3) == 2:
                msg_symbols.append(s)
                s = 0
        symbols = (costas + msg_symbols[:encoded_symbols // 2]
                   + costas + msg_symbols[encoded_symbols // 2:] + costas)

        symbol_range = np.arange(total_symbols)
        signal_pwr = np.sum(np.abs(obs[symbol_range, symbols]) ** 2.0)

        noise_psd = analysis.noise_baseline(freq)
        arg = signal_pwr / (noise_psd * 2500)
        if arg > 0.1:
            snr = max(10.0 * np.log10(arg) - 19, -24.0)
        else:
            snr = -24.0
        return snr

    @staticmethod
    def _detect(baseband, freq, analysis):
        obs = Signal._demodulate(baseband)

        for i in range(Signal.demap_max_symbols):
            llr = Signal._demap(obs, i)
            msg, codeword, iterations, bad_bits = Signal._sum_product_decoder(llr)
            if msg is not None:
                break

        if msg is None:
            raise ValueError("未译出有效 FT8 消息")

        snr = Signal._get_snr(obs, codeword, freq, analysis)
        return msg, snr, obs, llr, codeword


# --------------------------------------------------------------------------- #
# 公有入口（供 decoders/__init__.py 注册包装调用）
# --------------------------------------------------------------------------- #

def decode_ft8(iq: np.ndarray, sample_rate: float = 12000.0,
               **params) -> dict[str, object]:
    """FT8 完整解码，返回 {mode, decodes, snr_db, freq_hz, offset_s, message}。

    解码失败（采样率不符 / 信号过短 / 无候选 / 无有效 LDPC 码字）抛
    ValueError——诚实降级，不编造结果。
    """
    iq = np.asarray(iq)
    if sample_rate != 12000:
        raise ValueError("FT8 目前仅支持 12000 Hz 采样率")
    if iq.size < 192000:
        raise ValueError("信号太短，无法 FT8 解码（需 192000 样本）")

    analysis = SpectralAnalysis(iq, sample_rate)

    decoded = []
    for candidate in analysis.candidate_list:
        try:
            signal = Signal(candidate, analysis)
        except (ValueError, IndexError):
            continue
        decoded.append(signal)

    if not decoded:
        raise ValueError("未检测到有效 FT8 信号")

    best = max(decoded, key=lambda s: s.snr)
    return {
        "mode": "ft8",
        "decodes": [str(s.msg) for s in decoded],
        "snr_db": float(best.snr),
        "freq_hz": float(best.freq),
        "offset_s": float(best.offset),
        "message": str(best.msg),
    }