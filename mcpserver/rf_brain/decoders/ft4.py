"""FT4 弱信号数字模式解码器（骨架 · 4-GFSK + LDPC(174,91) + CRC14）

FT4 是 FT8 的 7.5 秒时隙同族变体，为竞赛（contest）场景设计：换句速度更快、
带宽略宽（约 90 Hz）。与 FT8 **共享完全相同的消息层**——77 bit 消息 + CRC14
+ LDPC(174,91) → 174 bit 码字；差异仅在物理层调制与同步：

- FT8：8-GFSK（3 bit/符号，音距 6.25 Hz），79 符号，3×7 符号 Costas
- FT4：4-GFSK（2 bit/符号，音距 23.4375 Hz），105 符号，4 音 Costas

实现纪律（授粉）：
- 消息/CRC14/LDPC 层与 ft8.py 完全一致，直接复用 ft8 的 Message 类族与生成
  矩阵（单源真相，避免两处维护漂移），不复制代码。
- 物理层调制为 FT4 独有：本骨架实现「编码侧」——协议常量 + 174 bit 码字 +
  87 数据符号（2-bit Gray 4-GFSK）；**解调链（Costas 同步搜索 + LDPC 译码）
  未实现**，诚实降级不编造解码结果，待真机/对 WSJT-X lib/ft4/ 源验证后补全。
- 同步序列（Costas 数组排布）为协议规范数据，此处提供已知值并标注「待核」。

来源：QEX《The FT4 and FT8 Communication Protocols》（公开论文）+ WSJT-X
（GPL-3.0，参考设计，不逐字拷贝——保持 ft8.py 的独立实现路径）。
"""
from __future__ import annotations

from . import ft8

# --------------------------------------------------------------------------- #
# 物理层常量（FT4 独有，来源：QEX 论文 + WSJT-X lib/ft4/）
# --------------------------------------------------------------------------- #
baud_rate = 24000 / 1024                 # 键控速率 ≈ 23.4375 Hz
freq_shift = baud_rate                   # 音距 = 键控速率
tone_order = 2                           # 每符号比特数（4 音）
tone_count = 1 << tone_order             # 4
gray_map = [0, 1, 3, 2]                  # 2-bit Gray（4-GFSK）
slot_seconds = 7.5                       # 时隙（FT8 的一半）

# 消息层（与 FT8 完全一致，引用 ft8 的常量避免漂移）
msg_bits = ft8.msg_bits                  # 77
crc_bits = ft8.crc_bits                  # 14
ldpc_parity_bits = ft8.ldpc_parity_bits  # 83
encoded_bits = ft8.encoded_bits          # 174
encoded_symbols = encoded_bits // tone_order  # 87（174 bit / 2 bit 每符号）
total_symbols = 105                      # 87 数据 + 18 同步

# 同步序列（4 音 Costas，待核：完整排布需对 WSJT-X lib/ft4/ 源）
# FT4 用 4 符号 Costas 数组（区别于 FT8 的 7 符号）。
costas_0 = [0, 1, 3, 2]                 # 待核
costas_1 = [2, 3, 1, 0]                 # 待核


def _encode_codeword(msg: "ft8.Message") -> int:
    """77 bit 消息 → CRC14 → LDPC(174,91) → 174 bit 码字（与 ft8 完全一致）。

    复用 ft8 的生成矩阵与 CRC，仅重写「拼装」这一小段；与 ft8.Message.encode
    里内嵌的同一段算法逐位等价，供测试交叉校验。
    """
    msg_crc = msg.pack77 << crc_bits | ft8.Message._crc(msg.pack77, 0)
    parity = 0
    for row in ft8.generator_matrix:
        parity = (parity << 1) | (bin(row & msg_crc).count("1") % 2)
    return (msg_crc << ldpc_parity_bits) | parity


def encode_data_symbols(msg: "ft8.Message") -> list[int]:
    """消息 → 87 个数据符号（4-GFSK 2-bit Gray，不含同步序列）。

    编码侧唯一确定的部分：174 bit 码字按 2 bit/符号映射为 87 个信道数据符号。
    完整 105 符号帧还需插入 18 个同步符号，其排布见下（待核，不在此拼装）。
    """
    codeword = _encode_codeword(msg)
    symbols: list[int] = []
    mask = (1 << tone_order) - 1  # 0b11
    for _ in range(encoded_symbols):
        symbols.insert(0, gray_map[codeword & mask])
        codeword >>= tone_order
    return symbols


def decode_ft4(iq, sample_rate: float = 24000.0, **params):
    """FT4 解码（骨架占位）：解调链未实现，诚实降级不编造结果。

    编码侧（协议常量 + 174 bit 码字 + 87 数据符号）已落地；4-GFSK 解调 +
    Costas 同步搜索 + LDPC 译码链路需真机/对 WSJT-X lib/ft4/ 源验证后补全。
    抛 ValueError 使注册包装统一转 success=False（与 ft8 坏输入降级一致）。
    """
    raise ValueError(
        "FT4 解调链未实现（骨架）：仅提供编码侧与协议常量，"
        "解码需真机/对 WSJT-X lib/ft4/ 源验证后补全，不编造解码结果"
    )
