"""FT4 解码器骨架测试（协议常量 + 注册 + 与 FT8 共享消息层交叉校验 + 诚实降级）。

FT4 是 FT8 的 7.5s 同族变体，共享完全相同的消息/CRC14/LDPC(174,91) 层；
差异仅在物理层（4-GFSK 2bit/符号 vs 8-GFSK 3bit/符号）。本测试核心断言：
对同一条消息，FT4 编码出的 174 bit 码字必须与 FT8 独立编码路径逐位一致。
"""
import pytest

from mcpserver.rf_brain.decoders import ft4, ft8, registry


def _make_msg() -> ft8.StandardMessage:
    return ft8.StandardMessage(ft8.Callsign("K1JT"), ft8.Callsign("W9XYZ"),
                               ft8.SignalReport(-15))


def test_ft4_protocol_constants():
    """FT4 协议常量（来源 QEX 论文 + WSJT-X lib/ft4/）。"""
    assert ft4.baud_rate == 24000 / 1024
    assert ft4.freq_shift == 24000 / 1024
    assert ft4.tone_order == 2
    assert ft4.tone_count == 4
    assert ft4.slot_seconds == 7.5
    # 消息层与 FT8 一致（引用同一组常量）
    assert ft4.msg_bits == 77
    assert ft4.crc_bits == 14
    assert ft4.ldpc_parity_bits == 83
    assert ft4.encoded_bits == 174
    assert ft4.encoded_symbols == 87   # 174 / 2
    assert ft4.total_symbols == 105    # 87 数据 + 18 同步
    assert ft4.gray_map == [0, 1, 3, 2]


def test_registry_has_ft4():
    """ft4 已注册进解码器注册表（demod_mode=fsk）。"""
    assert "ft4" in registry.list_decoders()
    assert registry.get_decoder("ft4").demod_mode == "fsk"


def test_ft4_ft8_share_codeword():
    """对同一条消息，FT4 的 174 bit 码字 == FT8 的 174 bit 码字。

    FT4 与 FT8 共享消息/CRC14/LDPC 层。从 FT8 的 79 符号里剥离出 58 个数据
    符号（3-bit Gray 逆映射）重建 174 bit 码字，与 ft4._encode_codeword 对比。
    """
    msg = _make_msg()
    codeword_ft4 = ft4._encode_codeword(msg)

    # FT8: [costas(7) + 29 data + costas(7) + 29 data + costas(7)]
    ft8_symbols = msg.encode()
    data_symbols = ft8_symbols[7:36] + ft8_symbols[43:72]
    assert len(data_symbols) == 58

    gray_inv = {g: i for i, g in enumerate(ft8.gray_map)}
    codeword_ft8 = 0
    for sym in data_symbols:
        codeword_ft8 = (codeword_ft8 << 3) | gray_inv[sym]

    assert codeword_ft4 == codeword_ft8
    assert codeword_ft4.bit_length() <= 174


def test_ft4_data_symbols():
    """编码侧：消息 → 87 个数据符号，取值 0..3（4-GFSK）。"""
    msg = _make_msg()
    symbols = ft4.encode_data_symbols(msg)
    assert len(symbols) == 87
    assert all(0 <= s < 4 for s in symbols)


def test_ft4_decode_stub_honest():
    """解调链未实现：decode_ft4 抛 ValueError（诚实降级，不编造解码结果）。"""
    with pytest.raises(ValueError, match="解调链未实现"):
        ft4.decode_ft4(None, 24000.0)  # type: ignore[arg-type]
