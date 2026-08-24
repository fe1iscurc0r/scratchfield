"""射频大脑 · POCSAG 寻呼解码（HW-03）

参考实现：multimon-ng 的 pocsag.c / bch.c（pagermon 依赖的解码器）。
帧结构（CCIR Radiopaging Code No.1 / POCSAG）：
- 前导码：0xAA（1010…交替）至少 576 bit
- 同步码字：0x7CD215D8（32 bit）
- 每批（batch）＝ 1 同步码字 + 16 数据码字（8 帧 × 2 码字）
- 地址码字（bit31=0）：bit30-13＝18 位地址，bit12-11＝2 位功能码，
  bit10-1＝10 位 BCH 校验，bit0＝偶校验；完整 RIC＝(18位地址<<3)|帧号
- 消息码字（bit31=1）：bit30-11＝20 位消息数据（7-bit ASCII 打包），其余同地址码字
- 空闲码字：0x7A89C197（无消息时填充，兼作消息结束标志）
- BCH(31,21) 生成多项式 g(x)=x^10+x^9+x^8+x^6+x^5+x^3+1（0x769），可纠 2 bit 错
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

POCSAG_SYNC = 0x7CD215D8
POCSAG_IDLE = 0x7A89C197
POCSAG_POLY = 0x769            # g(x)，11 bit（degree=10）
PREAMBLE_BYTES = 72            # 576 bit 前导 = 72 × 0xAA
BATCH_DATA_WORDS = 16          # 每批同步码字之后的数据码字数

_MESSAGE_FLAG = 0x80000000     # bit31=1 → 消息码字


@dataclass
class PocsagMessage:
    """一条解出的寻呼消息。"""
    address: int                # 完整 21 位 RIC
    function: int               # 功能码 0-3
    text: str                   # 字母数字消息正文


# --------------------------------------------------------------------------- #
# BCH(31,21) 编码 / 纠错
# --------------------------------------------------------------------------- #

def _poly_mod(value: int, poly: int) -> int:
    """GF(2) 多项式长除：返回 value mod poly（余数位宽 < poly 的 degree）。"""
    degree = poly.bit_length() - 1
    v = value
    while v and v.bit_length() - 1 >= degree:
        v ^= poly << (v.bit_length() - 1 - degree)
    return v


def bch_encode(data: int) -> int:
    """21 位信息 → 32 位 POCSAG 码字（数据 bit31-11 / BCH bit10-1 / 偶校验 bit0）。"""
    data &= 0x1FFFFF
    codeword = data << 11                 # 数据放到 bit31-11
    parity = _poly_mod(codeword >> 1, POCSAG_POLY)  # m(x)·x^10 mod g(x)，10 位余数（与 multimon-ng bch_pocsag_encode 一致）
    codeword |= parity << 1               # BCH 校验放到 bit10-1
    if bin(codeword).count("1") & 1:      # 偶校验：使 1 的个数为偶数
        codeword |= 1
    return codeword


def _syndrome(codeword: int) -> int:
    """11 位 syndrome：低 10 位 = BCH 余数，bit10 = 偶校验失败标志。"""
    syn = _poly_mod(codeword >> 1, POCSAG_POLY)   # 对 bit31-1 求余
    if bin(codeword).count("1") & 1:              # 奇偶校验失败
        syn |= 0x400
    return syn


def _build_error_table() -> dict[int, int]:
    """syndrome → 错误模式（bitmask）。单 bit 错（bit1-31，含偶校验翻转）
    与双 bit 错（偶校验抵消）的并集。"""
    single = {i: _poly_mod(1 << (i - 1), POCSAG_POLY) for i in range(1, 32)}  # bit 位 1-31 → syndrome
    tbl: dict[int, int] = {}
    for i in range(1, 32):
        syn = single[i] | 0x400            # 单 bit 错必破坏偶校验
        tbl[syn] = 1 << i
    for i in range(1, 32):
        for j in range(i + 1, 32):
            syn = single[i] ^ single[j]    # 双 bit 错偶校验抵消
            tbl.setdefault(syn, (1 << i) | (1 << j))
    return tbl


_ERROR_TABLE = _build_error_table()


def bch_correct(codeword: int) -> tuple[int, int]:
    """纠错。返回 (纠错后的码字, 纠错 bit 数)；不可纠时返回 (原码字, -1)。"""
    syn = _syndrome(codeword)
    if syn == 0:
        return codeword, 0
    error = _ERROR_TABLE.get(syn)
    if error is None:
        return codeword, -1
    return codeword ^ error, bin(error).count("1")


# --------------------------------------------------------------------------- #
# 编码辅助（供测试构造模拟寻呼帧）
# --------------------------------------------------------------------------- #

def _bits_of(value: int, nbits: int) -> list[int]:
    """整数按 MSB-first 展开为 bit 列表。"""
    return [(value >> (nbits - 1 - i)) & 1 for i in range(nbits)]


def _bits_to_int(bits) -> int:
    """MSB-first bit 序列 → 整数。"""
    v = 0
    for b in bits:
        v = (v << 1) | (int(b) & 1)
    return v


def encode_address_codeword(ric: int, function: int, frame: int) -> int:
    """构造地址码字。ric 低 3 位必须等于 frame（帧号 0-7）。"""
    address18 = (ric >> 3) & 0x3FFFF
    # 21 位数据：bit20=地址标志0，bit19-2=18 位地址，bit1-0=功能码
    data = (address18 << 2) | (function & 0x3)
    return bch_encode(data)


def encode_message_codewords(text: str) -> list[int]:
    """把文本按 7-bit ASCII 打包成消息码字序列（每码字 20 位数据）。"""
    data_bits: list[int] = []
    for ch in text:
        v = ord(ch) & 0x7F
        data_bits.extend(_bits_of(v, 7))
    codewords: list[int] = []
    for i in range(0, len(data_bits), 20):
        chunk = data_bits[i:i + 20]
        if len(chunk) < 20:
            chunk += [0] * (20 - len(chunk))        # 末尾补 0
        # 21 位数据：bit20=消息标志1，bit19-0=20 位消息数据
        data = _bits_to_int(chunk) | 0x100000
        codewords.append(bch_encode(data))
    return codewords


def build_frame_bits(ric: int, function: int, text: str) -> list[int]:
    """构造完整模拟寻呼帧：前导 + 一个或多个 batch（同步 + 16 数据码字）。

    消息码字按 POCSAG 惯例可跨 batch 延续：首 batch 的地址码字放在帧号位，
    消息紧随其后；当前 batch 放不下的码字在下一 batch 的同步码字之后继续
    放置（解码侧 decode() 对同步码字只重置 word_index、不中断当前消息），
    直到文本编码完成，其余位置填空闲码字。
    """
    bits: list[int] = []
    for _ in range(PREAMBLE_BYTES):
        bits.extend(_bits_of(0xAA, 8))

    frame = ric & 7
    msg_cws = encode_message_codewords(text)
    mi = 0                                          # 已放置的消息码字数
    first = True
    while True:
        bits.extend(_bits_of(POCSAG_SYNC, 32))
        codewords = [POCSAG_IDLE] * BATCH_DATA_WORDS
        pos = 0
        if first:
            pos = frame * 2                         # 首 batch：地址码字放在帧号位
            codewords[pos] = encode_address_codeword(ric, function, frame)
            pos += 1
        while pos < BATCH_DATA_WORDS and mi < len(msg_cws):
            codewords[pos] = msg_cws[mi]
            mi += 1
            pos += 1
        for cw in codewords:
            bits.extend(_bits_of(cw, 32))
        if mi >= len(msg_cws):
            break
        first = False
    return bits


# --------------------------------------------------------------------------- #
# 解码
# --------------------------------------------------------------------------- #

def _find_sync(bits: list[int], start: int = 0) -> int:
    """在 bit 流中搜索同步码字（允许 BCH 纠错），返回其起始下标或 -1。"""
    n = len(bits)
    for i in range(start, n - 31):
        w = _bits_to_int(bits[i:i + 32])
        if w == POCSAG_SYNC:
            return i
        cw, nerr = bch_correct(w)
        if nerr >= 0 and cw == POCSAG_SYNC:
            return i
    return -1


def _decode_text(data_bits: list[int]) -> str:
    """7-bit ASCII（MSB-first）bit 流 → 文本；遇 NUL(0x00) 截断。

    最后一个消息码字的数据位用 0 填充，会解出多余的 NUL 字符，
    此处按 POCSAG 惯例（消息末尾无长度字段，靠填充位终止）截断。
    """
    chars: list[str] = []
    for i in range(0, len(data_bits) - 6, 7):
        c = _bits_to_int(data_bits[i:i + 7])
        if c == 0:
            break
        chars.append(chr(c))
    return "".join(chars)


def decode(bits) -> list[PocsagMessage]:
    """解析 POCSAG bit 流，返回解出的消息列表（含地址、功能码、正文）。"""
    bits = [int(b) & 1 for b in bits]
    messages: list[PocsagMessage] = []
    pos = _find_sync(bits)
    if pos < 0:
        return messages
    pos += 32

    current: dict | None = None
    word_index = 0                                  # batch 内位置 0-15

    while pos + 32 <= len(bits):
        cw, nerr = bch_correct(_bits_to_int(bits[pos:pos + 32]))
        pos += 32
        if nerr < 0:
            # 不可纠：结束当前消息并重新找同步
            if current is not None:
                messages.append(PocsagMessage(
                    address=current["ric"], function=current["function"],
                    text=_decode_text(current["data_bits"])))
                current = None
            nxt = _find_sync(bits, pos)
            if nxt < 0:
                break
            pos = nxt + 32
            word_index = 0
            continue

        if cw == POCSAG_SYNC:
            word_index = 0                          # 跨批消息不因同步而中断
            continue

        if cw == POCSAG_IDLE:
            if current is not None:
                messages.append(PocsagMessage(
                    address=current["ric"], function=current["function"],
                    text=_decode_text(current["data_bits"])))
                current = None
            word_index += 1
            continue

        if cw & _MESSAGE_FLAG == 0:
            # 地址码字
            if current is not None:
                messages.append(PocsagMessage(
                    address=current["ric"], function=current["function"],
                    text=_decode_text(current["data_bits"])))
                current = None
            function = (cw >> 11) & 0x3
            address18 = (cw >> 13) & 0x3FFFF
            ric = (address18 << 3) | (word_index // 2)
            current = {"ric": ric, "function": function, "data_bits": []}
        else:
            # 消息码字：追加 20 位数据
            if current is not None:
                current["data_bits"].extend(_bits_of(cw >> 11, 20))
        word_index += 1

    if current is not None:
        messages.append(PocsagMessage(
            address=current["ric"], function=current["function"],
            text=_decode_text(current["data_bits"])))
    return messages


# --------------------------------------------------------------------------- #
# 接入 demod_ref：FSK 解调 → POCSAG 解码
# --------------------------------------------------------------------------- #

def demodulate_and_decode(iq: np.ndarray, sample_rate: float, symbol_rate: float) -> list[PocsagMessage]:
    """端到端：IQ 样本 → FSK 符号流（demod_ref）→ POCSAG 帧解析。

    POCSAG 是 2-FSK，符号 0/1 直接对应 bit；symbol_rate 即 POCSAG 位率（512/1200/2400）。
    """
    from mcpserver.rf_brain.demod_ref import demodulate_symbols
    symbols = demodulate_symbols(iq, "FSK", sample_rate, symbol_rate)
    return decode([int(s) for s in symbols])
