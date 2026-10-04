"""WSPR 解码器冒烟测试（对齐 Phase 6 完整实现：协议常量 + 注册 + 编解码闭环）。

历史说明：本文件原为 Y-02 骨架期断言（SOURCE_BITS/decode_audio/decode_wav 等
期望 API），现实现已进化为完整编解码闭环（encode_wspr_text → decode_wspr），
第四期 W2 工单按"测试对齐现实现"裁决重写。
"""
import numpy as np
import pytest

from mcpserver.rf_brain.decoders import registry, wspr


def test_protocol_constants():
    """协议常量基于公开文档（WSPR 协议规范 / G4JNT 编码过程描述）。"""
    # 50 bit 消息 = 28 呼号 + 15 网格 + 7 功率；帧 162 符号 = (50 + K-1) * r，K=32, r=2
    assert wspr.N_SYMBOLS == (50 + 32 - 1) * 2
    assert len(wspr.SYNC_VECTOR) == wspr.N_SYMBOLS
    # 卷积码生成多项式（K=32, r=1/2，非递归）：G1/G2
    assert wspr.POLY == (0xF2D05351, 0xE4613C47)
    # 键控速率 / 音距 = 12000 / 8192 ≈ 1.4648 Hz；4 音（0..3 符号）
    assert wspr.TONE_SPACING == 12000.0 / 8192.0
    assert wspr.SYMBOL_RATE == wspr.TONE_SPACING
    assert wspr.SAMPLE_RATE == 12000.0
    assert wspr.SYMBOL_SAMPLES == 8192
    assert min(wspr.SYNC_VECTOR) >= 0 and max(wspr.SYNC_VECTOR) <= 1
    # 帧时长 ≈ 110.6 s（162 符号 × 8192 样本 / 12000 Hz）
    frame_dur = wspr.N_SYMBOLS * wspr.SYMBOL_SAMPLES / wspr.SAMPLE_RATE
    assert 110 < frame_dur < 112


def test_registry_has_wspr():
    """wspr 已注册进解码器注册表。"""
    names = registry.list_decoders()
    assert "wspr" in names
    prov = registry.get_decoder("wspr")
    assert prov.demod_mode == "fsk"


def test_encode_decode_roundtrip():
    """编解码闭环：高 SNR 合成帧应无损恢复呼号/网格/功率。"""
    iq = wspr.encode_wspr_text("K1JT", "FN20", 30, snr_db=20.0, seed=7)
    assert iq.size == wspr.N_SYMBOLS * wspr.SYMBOL_SAMPLES
    info = wspr.decode_wspr(iq)
    assert info["callsign"] == "K1JT"
    assert info["grid"] == "FN20"
    assert info["power_dbm"] == 30
    assert info["mode"] == "wspr"


def test_decode_bad_input():
    """坏输入降级：None / 空数组 / 过短信号 → ValueError（诚实不编造）。"""
    with pytest.raises(ValueError):
        wspr.decode_wspr(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        wspr.decode_wspr(np.array([], dtype=complex))
    with pytest.raises(ValueError):
        wspr.decode_wspr(np.zeros(100, dtype=complex))
