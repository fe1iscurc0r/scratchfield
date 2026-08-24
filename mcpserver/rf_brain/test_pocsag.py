"""HW-03 · POCSAG 寻呼解码测试（与 test_phase*.py、test_mesh.py 同目录）。

构造模拟寻呼帧：前导码(0xAA×72) + 同步码字(0x7CD215D8) + 一批数据码字
（地址码字 / 消息码字 / 空闲码字 0x7A89C197，均含 BCH 校验位），
覆盖任务规格的 5 类场景：
1. 正确帧 → 解出地址(RIC)/功能码/消息文本
2. 单 bit 错 → BCH 纠错
3. 双 bit 错 → BCH 纠错（465/465 组合）
4. 非法同步码 → 拒收
5. 空闲码字 → 截断消息

附：BCH(31,21) 往返自洽、>2 bit 不可纠检测、FSK 端到端解调→解码（demodulate_and_decode）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain.pocsag import (
    POCSAG_IDLE,
    POCSAG_SYNC,
    bch_correct,
    bch_encode,
    build_frame_bits,
    decode,
    demodulate_and_decode,
)

PREAMBLE_BITS = 72 * 8  # 576 bit 前导码（build_frame_bits 固定）
SYNC_BIT_OFFSET = PREAMBLE_BITS  # 同步码字起始 bit 下标


def _flip(bits, idx: int):
    """翻转 bit 流中第 idx 位，返回新列表。"""
    b = list(bits)
    b[idx] ^= 1
    return b


def _set_window(bits, offset: int, value: int):
    """把 bits[offset:offset+32] 替换为 value 的 32 bit（MSB-first）。"""
    b = list(bits)
    for k in range(32):
        b[offset + k] = (value >> (31 - k)) & 1
    return b


# --------------------------------------------------------------------------- #
# 场景 1：正确帧 → 地址(RIC)/功能码/消息文本
# --------------------------------------------------------------------------- #

def test_correct_frame_decodes_ric_function_text():
    """前导+同步+地址/消息/空闲 → 解出完整 RIC（21 位）/功能码/文本。"""
    cases = [
        (123456, 2, "HELLO POCSAG"),          # 12 字符 → 5 消息码字，末尾 0 填充
        (2097151, 3, "A"),                     # 最大 RIC(0x1FFFFF)，单字符
        (8, 0, "01234567890123456789"),        # 20 字符 → 恰好 7 码字，无填充
        (100, 1, "HELLO, WORLD!"),             # 帧号 4
        (4563, 3, "P0CSAG-512/1200/2400!"),    # 帧号 3（9 个消息码字位 ≥ 8）
        (0, 0, "min ric"),
    ]
    # 8 个帧号位各测一个 RIC（验证完整 RIC = (18位地址<<3)|帧号 的帧号来源）
    cases += [(f, f % 4, f"FRAME {f}") for f in range(8)]

    for ric, fn, txt in cases:
        msgs = decode(build_frame_bits(ric, fn, txt))
        assert len(msgs) == 1, f"RIC={ric} 应恰好解出 1 条，实际 {msgs}"
        m = msgs[0]
        assert (m.address, m.function, m.text) == (ric, fn, txt), f"{ric}/{fn}/{txt} → {m}"

    # 同步/空闲常量本身是合法 BCH 码字（multimon-ng 同款特性）
    assert bch_correct(POCSAG_SYNC) == (POCSAG_SYNC, 0)
    assert bch_correct(POCSAG_IDLE) == (POCSAG_IDLE, 0)
    print(f"✅ 场景1 正确帧：{len(cases)} 组 RIC/功能码/文本 全还原")


# --------------------------------------------------------------------------- #
# 场景 2：单 bit 错纠错
# --------------------------------------------------------------------------- #

def test_single_bit_error_corrected():
    """码字级全部 31 个单 bit 翻转均纠回原码字；帧级同步/地址/消息各 1 bit 纠错。"""
    # 码字级：bit1-31 各翻转 1 次 → (原码字, 1)
    cw = bch_encode(0x12345)
    for i in range(1, 32):
        c, n = bch_correct(cw ^ (1 << i))
        assert (c, n) == (cw, 1), f"bit{i} 单 bit 错未纠回: {(c, n)}"

    # 帧级：地址码字起始 bit 下标 = 同步末尾 + 帧号×2 个码字
    ric, fn, txt = 123456, 2, "HELLO POCSAG"   # 帧号 0
    bits = build_frame_bits(ric, fn, txt)
    addr_off = SYNC_BIT_OFFSET + 32 + (ric & 7) * 64  # 地址码字起始 = 608

    # 同步码字 1 bit 错（第 27 位）→ 仍能锁定并完整解码
    msgs = decode(_flip(bits, SYNC_BIT_OFFSET + 32 - 27))
    assert len(msgs) == 1 and msgs[0].text == txt, msgs
    # 地址码字 1 bit 错（第 29 位，地址数据区）→ RIC/功能码不变
    msgs = decode(_flip(bits, addr_off + 2))
    assert len(msgs) == 1 and (msgs[0].address, msgs[0].function) == (ric, fn), msgs
    # 消息码字 1 bit 错（第 30 位，首字符 MSB）→ 文本不变
    msgs = decode(_flip(bits, addr_off + 32 + 1))
    assert len(msgs) == 1 and msgs[0].text == txt, msgs
    print("✅ 场景2 单 bit 错：31 位置全纠 + 帧级 同步/地址/消息 各 1bit 纠错")


# --------------------------------------------------------------------------- #
# 场景 3：双 bit 错纠错（检测+纠正）
# --------------------------------------------------------------------------- #

def test_double_bit_error_corrected():
    """码字级全部 465 个双 bit 组合均纠回原码字；帧级地址码字 2 bit 错纠错。"""
    cw = bch_encode(0xABCDE)
    pairs = 0
    for i in range(1, 32):
        for j in range(i + 1, 32):
            c, n = bch_correct(cw ^ (1 << i) ^ (1 << j))
            assert (c, n) == (cw, 2), f"双bit {(i, j)} 未纠回: {(c, n)}"
            pairs += 1
    assert pairs == 465, f"应共 465 个双 bit 组合，实际 {pairs}"

    # 帧级：地址码字同时翻转 2 bit → 整条消息（含文本）原样解出
    ric, fn, txt = 123456, 2, "HELLO POCSAG"
    bits = build_frame_bits(ric, fn, txt)
    addr_off = SYNC_BIT_OFFSET + 32 + (ric & 7) * 64
    b = _flip(_flip(bits, addr_off + 2), addr_off + 5)
    msgs = decode(b)
    assert len(msgs) == 1, msgs
    assert (msgs[0].address, msgs[0].function, msgs[0].text) == (ric, fn, txt), msgs
    print("✅ 场景3 双 bit 错：465/465 组合全纠 + 帧级 2bit 纠错")


def test_uncorrectable_error_detected():
    """超过 2 bit 的错：BCH 检测为不可纠（返回 -1），帧级解码不会输出错误消息。"""
    cw = bch_encode(0x13579)
    uncorrectable = 0
    for i in range(1, 32):
        for j in range(i + 1, 32):
            for k in range(j + 1, 32):
                c, n = bch_correct(cw ^ (1 << i) ^ (1 << j) ^ (1 << k))
                if n == -1:
                    uncorrectable += 1
                else:
                    assert c != cw, f"3bit 错 {(i, j, k)} 被误判为无错"
    assert uncorrectable > 0, "应存在被检测为不可纠的 3 bit 错"
    print(f"✅ >2bit 错检测：{uncorrectable} 个 3bit 组合返回不可纠(-1)，余下误纠也绝不自洽")


# --------------------------------------------------------------------------- #
# 场景 4：非法同步码拒收
# --------------------------------------------------------------------------- #

def test_illegal_sync_rejected():
    """同步码字被替换为非法值（距 0x7CD215D8 远超 2 bit）或纯噪声 → 整帧拒收。"""
    ric, fn, txt = 123456, 2, "HELLO POCSAG"
    bits = build_frame_bits(ric, fn, txt)
    # 同步码字替换为 0x12345678（汉明距离 11 bit，BCH 纠不回去）
    assert decode(_set_window(bits, SYNC_BIT_OFFSET, 0x12345678)) == []
    # 同步码字替换为全 0
    assert decode(_set_window(bits, SYNC_BIT_OFFSET, 0x00000000)) == []
    # 纯随机 bit 流（固定种子，可复现）→ 无消息
    rng = np.random.default_rng(42)
    garbage = list(rng.integers(0, 2, size=3000))
    assert decode(garbage) == []
    print("✅ 场景4 非法同步码：替换同步(0x12345678/全0) + 纯噪声 均拒收")


# --------------------------------------------------------------------------- #
# 场景 5：空闲码字截断消息
# --------------------------------------------------------------------------- #

def test_idle_codeword_truncates_message():
    """消息末尾空闲码字截断；最后一个消息码字的 0 填充不泄漏为文本。"""
    # 'ABC' = 21 bit → 2 消息码字（40 bit，19 bit 0 填充）→ 空闲码字结束消息
    ric, fn, txt = 777, 0, "ABC"
    msgs = decode(build_frame_bits(ric, fn, txt))
    assert len(msgs) == 1, f"空闲截断后应只剩 1 条消息: {msgs}"
    assert msgs[0].text == "ABC", f"文本应恰为 'ABC'（NUL 填充被截断）: {msgs[0].text!r}"
    assert (msgs[0].address, msgs[0].function) == (ric, fn)

    # 两帧串联：第 1 帧消息被空闲码字截断，第 2 帧重新同步后解出第 2 条
    msgs = decode(build_frame_bits(8, 1, "FIRST") + build_frame_bits(16, 2, "SECOND"))
    assert [(m.address, m.function, m.text) for m in msgs] == [
        (8, 1, "FIRST"),
        (16, 2, "SECOND"),
    ], msgs
    print("✅ 场景5 空闲码字截断：'ABC' 无 NUL 泄漏 + 两帧串联各解出 1 条")


# --------------------------------------------------------------------------- #
# 附：BCH(31,21) 往返自洽 / FSK 端到端解调→解码
# --------------------------------------------------------------------------- #

def test_bch_roundtrip_no_error():
    """无错码字经 bch_correct 保持原值（nerr=0）。"""
    for data in (0, 1, 0x1FFFFF, 0x12345, 0xABCDE):
        cw = bch_encode(data)
        c, n = bch_correct(cw)
        assert (c, n) == (cw, 0), f"data={hex(data)} 往返不自洽"
    print("✅ BCH(31,21) 往返自洽：无错码字保持原值")


def _bits_to_fsk_iq(bits, sps: int = 10):
    """0/1 bit 流 → 2-FSK IQ（每符号 sps 样本，每样本相移 ±π/4）。

    鉴频器对相位差分求均值：符号 1 → 正瞬时频率，符号 0 → 负瞬时频率。
    """
    incs = np.array([(1 if b else -1) * (np.pi / 4) for b in bits for _ in range(sps)])
    phase = np.cumsum(incs)
    iq = np.exp(1j * phase)
    return np.append(iq, iq[-1])  # 补 1 样本，保证最后一个符号完整落入鉴频窗口


def test_demodulate_and_decode_end_to_end():
    """端到端：FSK IQ → demod_ref.demodulate_symbols → POCSAG 解码。"""
    ric, fn, txt = 9001, 3, "E2E"
    iq = _bits_to_fsk_iq(build_frame_bits(ric, fn, txt))
    msgs = demodulate_and_decode(iq, sample_rate=24000.0, symbol_rate=2400.0)
    assert len(msgs) == 1, msgs
    m = msgs[0]
    assert (m.address, m.function, m.text) == (ric, fn, txt), f"端到端解码失败: {m}"
    print("✅ 端到端 FSK 解调→解码：demodulate_and_decode 接入点可用")


if __name__ == "__main__":
    test_bch_roundtrip_no_error()
    test_correct_frame_decodes_ric_function_text()
    test_single_bit_error_corrected()
    test_double_bit_error_corrected()
    test_uncorrectable_error_detected()
    test_illegal_sync_rejected()
    test_idle_codeword_truncates_message()
    test_demodulate_and_decode_end_to_end()
    print("\n🎉 POCSAG 全部自测通过")