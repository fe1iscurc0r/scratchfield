"""FT8 解码器冒烟测试（对齐 Phase 6 完整实现：协议常量 + 注册 + 编解码闭环）。

历史说明：本实现此前从未有编解码闭环测试，解码链路的 numpy 2.x 兼容缺陷
（np.int 已删除、float dft_length、Costas 相关 0/0 NaN 污染候选排序）因此
长期未暴露，第四期后勘察工单修复并补闭环。
"""
import numpy as np
import pytest

from mcpserver.rf_brain.decoders import ft8, registry


def _modulate(symbols: list[int], base_freq: float = 1500.0) -> np.ndarray:
    """CPFSK 调制：每符号 1920 样本（12000 / 6.25 baud），连续相位。"""
    freq = np.repeat(base_freq + np.array(symbols) * ft8.freq_shift, 1920)
    phase = 2 * np.pi * np.cumsum(freq) / 12000.0
    return np.exp(1j * phase)


def test_protocol_constants():
    """协议常量基于公开文档（WSJT-X lib/ft8/）。"""
    # 77 消息 + 14 CRC + 83 LDPC 校验 = 174 bit → 58 符号 + 3×7 Costas = 79
    assert ft8.msg_bits == 77
    assert ft8.crc_bits == 14
    assert ft8.ldpc_parity_bits == 83
    assert ft8.encoded_bits == 174
    assert ft8.encoded_symbols == 58
    assert ft8.total_symbols == 79
    assert ft8.costas == [3, 1, 4, 0, 6, 5, 2]
    assert len(ft8.generator_matrix) == 83
    assert ft8.baud_rate == 12000 / 1920


def test_registry_has_ft8():
    """ft8 已注册进解码器注册表。"""
    names = registry.list_decoders()
    assert "ft8" in names
    prov = registry.get_decoder("ft8")
    assert prov.demod_mode == "fsk"


def test_encode_decode_roundtrip():
    """编解码闭环：无噪合成帧应解出原始标准消息（覆盖此前必崩的 SNR 估算路径）。"""
    msg = ft8.StandardMessage(ft8.Callsign("K1JT"), ft8.Callsign("W9XYZ"),
                              ft8.SignalReport(-15))
    iq = _modulate(msg.encode())
    iq = np.pad(iq, (9600, 192000 - iq.size))  # 前置 0.8s，补足 16s 时隙
    out = ft8.decode_ft8(iq, 12000.0)
    assert out["mode"] == "ft8"
    assert "StandardMessage(K1JT W9XYZ -15)" in out["decodes"]
    assert out["message"] == "StandardMessage(K1JT W9XYZ -15)"
    assert 1400 < out["freq_hz"] < 1600
    assert 0 < out["snr_db"] < 40


def test_decode_bad_input():
    """坏输入降级：采样率不符 / 信号过短 / 纯噪声 → ValueError（诚实不编造）。"""
    with pytest.raises(ValueError):
        ft8.decode_ft8(None, 8000.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ft8.decode_ft8(np.zeros(1000, dtype=complex), 12000.0)
    with pytest.raises(ValueError):
        ft8.decode_ft8(np.zeros(192000, dtype=complex), 12000.0)
