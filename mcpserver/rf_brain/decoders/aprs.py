"""APRS / AX.25 解码器（Phase 6 · AFSK1200 / Bell 202）

发送链路（模拟帧生成，自洽闭环）：
    HAM 文本 → AX.25 UI 帧（地址+控制+PID+信息+FCS-16）
             → bit stuffing（连续 5 个 1 后插 0）→ HDLC 0x7E 成帧
             → NRZI 编码（bit0 翻转 / bit1 保持）→ Bell 202 FSK（Mark 1200 / Space 2200）

接收链路：
    FM 鉴频（相位差分）→ 符号采样 → NRZI 解码（双极性消相位模糊）
    → 0x7E 帧同步 → de-stuff → FCS-16 校验（CRC==0xF0B8）→ AX.25 字段解析 → 文本

注册：本模块不主动注册，由 decoders/__init__.py 统一导入触发。
"""
from __future__ import annotations

import numpy as np

MARK_FREQ = 1200.0          # Bell 202 Mark（逻辑 1）
SPACE_FREQ = 2200.0         # Bell 202 Space（逻辑 0）
BAUD = 1200.0               # AFSK1200 数据率
FCS_MAGIC = 0xF0B8          # CRC-CCITT 校验剩余数（AX.25 标准）

_FLAG = 0x7E
_FLAG_BITS = "01111110"


# ---------------------------------------------------------------- FCS-16
def crc_ccitt(data: bytes) -> int:
    """CRC-CCITT（X^16+X^12+X^5+1，LSB 先行），初值 0xFFFF。"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc


# ---------------------------------------------------------------- AX.25 打包
def _ax25_address(callsign: str, ssid: int, last: bool) -> bytes:
    """AX.25 地址字段：6 字符字节（ASCII<<1）+ 1 个 SSID 字节。"""
    cs = callsign.upper().ljust(6, " ")[:6]
    body = bytes(ord(c) << 1 for c in cs)
    ssid_byte = ((ssid & 0x0F) << 1) | 0x60
    if last:
        ssid_byte |= 0x80          # 最后地址标志
    return body + bytes([ssid_byte])


def build_ax25_frame(dest: str, source: str, info: bytes) -> bytes:
    """AX.25 UI 帧（含 flag 与 stuffing），返回 HDLC 字节流。

    帧 = 0x7E + 目的(7) + 源(7) + 控制(0x03 UI) + PID(0xF0) + 信息 + FCS-16 + 0x7E
    """
    payload = (_ax25_address(dest, 0, False)
               + _ax25_address(source, 0, True)
               + bytes([0x03, 0xF0])          # 控制=UI，PID=无第 3 层
               + info)
    fcs = (~crc_ccitt(payload)) & 0xFFFF          # AX.25：FCS 为余数补码，低字节先发
    body = payload + bytes([fcs & 0xFF, (fcs >> 8) & 0xFF])
    return bytes([_FLAG]) + _bit_stuff(body) + bytes([_FLAG])


def _bit_stuff(data: bytes) -> bytes:
    bits: list[int] = []
    ones = 0
    for byte in data:
        for i in range(7, -1, -1):
            b = (byte >> i) & 1
            bits.append(b)
            ones = ones + 1 if b else 0
            if ones == 5:
                bits.append(0)               # 连续 5 个 1 后插 0
                ones = 0
    return _pack_bits(bits)


def _pack_bits(bits: list[int]) -> bytes:
    while len(bits) % 8:
        bits.append(0)
    out = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for b in bits[i:i + 8]:
            v = (v << 1) | b
        out.append(v)
    return bytes(out)


# ---------------------------------------------------------------- 发送（模拟帧）
def nrzi_encode(bits: list[int]) -> list[int]:
    """HDLC NRZI：bit0 → 电平翻转，bit1 → 保持。起始电平 1（Mark）。"""
    out = []
    level = 1
    for b in bits:
        if b == 0:
            level = 1 - level
        out.append(level)
    return out


def fsk_modulate(levels: list[int], sample_rate: float = 48_000.0) -> np.ndarray:
    """Bell 202 FSK：电平 1 → 1200Hz，电平 0 → 2200Hz，连续相位。"""
    sps = max(4, int(round(sample_rate / BAUD)))
    freq = (np.array(levels) * MARK_FREQ
            + (1 - np.array(levels)) * SPACE_FREQ)
    freq = np.repeat(freq, sps)
    t = np.arange(freq.size) / sample_rate
    return np.exp(1j * 2 * np.pi * np.cumsum(freq) / sample_rate)


def encode_text_aprs(text: str, sample_rate: float = 48_000.0,
                     snr_db: float = 20.0, seed: int = 1) -> np.ndarray:
    """生成 APRS 模拟帧 IQ：文本 → AX.25 → NRZI → FSK → 加噪。

    帧布局：8 个前导 flag + 数据帧 + 4 个尾部 flag。
    """
    frame = build_ax25_frame("APRS", "N0CALL", text.encode("ascii", "replace"))
    hdlc = bytes([_FLAG]) * 8 + frame + bytes([_FLAG]) * 4
    raw: list[int] = []
    for byte in hdlc:
        for i in range(7, -1, -1):
            raw.append((byte >> i) & 1)
    iq = fsk_modulate(nrzi_encode(raw), sample_rate)
    # 归一化 + 高斯噪声（SNR 定义：信号功率=1）
    iq /= np.sqrt(np.mean(np.abs(iq) ** 2) + 1e-12)
    rng = np.random.default_rng(seed)
    n = iq.size
    noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * np.sqrt(0.5 * 10 ** (-snr_db / 10))
    return iq + noise


# ---------------------------------------------------------------- 接收
def _nrzi_decode(symbols: np.ndarray, start_level: int = 1) -> list[int]:
    """HDLC NRZI 解码：电平翻转→0、保持→1。起始电平需与发射端对齐
    （发射端起始 mark=1），否则整体滞后一位导致 FCS 失败。"""
    bits = []
    prev = start_level
    for cur in symbols:
        bits.append(0 if cur != prev else 1)
        prev = cur
    return bits


def _unbit_stuff(bitstr: str) -> bytes:
    out: list[int] = []
    ones = 0
    for ch in bitstr:
        b = 1 if ch == "1" else 0
        if ones == 5:
            ones = 0
            continue
        out.append(b)
        ones = ones + 1 if b else 0
    n = len(out) // 8
    return bytes(int("".join(str(x) for x in out[i * 8:(i + 1) * 8]), 2)
                 for i in range(n))


def _parse_ax25(data: bytes) -> str | None:
    if len(data) < 18 or crc_ccitt(data) != FCS_MAGIC:
        return None
    dest, src = data[0:7], data[7:14]
    cs_dest = "".join(chr(b >> 1) for b in dest[:6]).strip()
    cs_src = "".join(chr(b >> 1) for b in src[:6]).strip()
    info = data[16:-2]      # 信息字段（去尾部 FCS 2 字节）
    try:
        info_txt = info.decode("ascii")
    except UnicodeDecodeError:
        return None
    return f"{cs_dest} <- {cs_src}: {info_txt}"


def _try_frames(bits: list[int]) -> str | None:
    bs = "".join("1" if b else "0" for b in bits)
    pos = bs.find(_FLAG_BITS)
    while pos != -1:
        nxt = bs.find(_FLAG_BITS, pos + 8)
        if nxt != -1:
            seg = bs[pos + 8:nxt]
            if seg:
                text = _parse_ax25(_unbit_stuff(seg))
                if text is not None:
                    return text
        pos = bs.find(_FLAG_BITS, pos + 1)
    return None


def decode_afsk1200(iq: np.ndarray, sample_rate: float, **params) -> str:
    """AFSK1200 完整解码，返回文本；找不到有效帧抛 ValueError。"""
    iq = np.asarray(iq)
    sps = max(4, int(round(sample_rate / BAUD)))
    if iq.size < 3 * sps:
        raise ValueError("信号太短，无法 AFSK 解码")
    phase = np.unwrap(np.angle(iq))
    inst = np.diff(phase) * sample_rate / (2 * np.pi)
    # integrate-and-dump：每符号窗口平均瞬时频率再判决（单样本鉴频在加噪下
    # 相位差分抖动 ~0.1rad/样本 ≈ 764Hz，远超 500Hz 判决裕量，必须平滑）
    nwin = inst.size // sps
    if nwin < 16:
        raise ValueError("符号数不足")
    inst_avg = inst[:nwin * sps].reshape(nwin, sps).mean(axis=1)
    s = inst_avg > (MARK_FREQ + SPACE_FREQ) / 2
    # 双极性消 180° 频率极性模糊：
    #   s = (level==0)，发射端起始电平 mark=1 → 首符号前状态为 0；
    #   ~s = (level==1) → 首符号前状态为 1。两解释各试一组起始电平。
    for trial, start in ((s, 0), (~s, 1)):
        text = _try_frames(_nrzi_decode(trial, start))
        if text is not None:
            return text
    raise ValueError("AFSK1200 未找到通过 FCS 校验的 AX.25 帧")
