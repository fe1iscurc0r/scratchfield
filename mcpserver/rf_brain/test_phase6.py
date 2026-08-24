"""Phase 6 · 多协议解码器库验收测试（provider 注册表）

覆盖工单验收点：
1. 注册表架构：四个解码器（aprs/psk31/dtmf/pocsag）声明式注册；
   list_decoders / get_decoder / decode / decode_all 泛型消费，无协议分支
2. APRS/AX.25：模拟帧（文本→AX.25→NRZI→FSK）端到端解码，FCS-16 校验
3. PSK31：Varicode 表关键码字核对 + 全字符表往返 + BPSK 端到端解码
4. DTMF：Goertzel 端到端拨号序列解码
5. 健壮性：未注册名 → 失败 DecodeResult；纯噪声 → 全部解码器拒检（不误报）
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain.decoders import (  # noqa: E402
    DecodeResult,
    decode,
    decode_all,
    get_decoder,
    list_decoders,
    aprs,
    psk31,
    dtmf,
)
from mcpserver.rf_brain.pocsag import build_frame_bits  # noqa: E402


# --------------------------------------------------------------------------- #
# 注册表架构验收
# --------------------------------------------------------------------------- #

def test_registry_has_four_decoders():
    names = list_decoders()
    assert set(names) == {"aprs", "psk31", "dtmf", "pocsag"}, names
    for name, mode in (("aprs", "afsk"), ("psk31", "bpsk"),
                       ("dtmf", "dtmf"), ("pocsag", "fsk")):
        p = get_decoder(name)
        assert p.demod_mode == mode and p.description, name


def test_unknown_decoder_returns_failure():
    r = decode("no_such_decoder", np.zeros(256, complex), 8000.0)
    assert isinstance(r, DecodeResult)
    assert not r.success and "未注册" in r.message


def test_decode_all_is_generic_no_branches():
    """decode_all 只消费注册表：返回全部条目，且全是 DecodeResult。"""
    iq = aprs.encode_text_aprs("CQ TEST", seed=2)
    results = decode_all(iq, 48_000.0)
    assert [r.decoder for r in results] == list_decoders()
    assert all(isinstance(r, DecodeResult) for r in results)


# --------------------------------------------------------------------------- #
# APRS / AX.25（AFSK1200）
# --------------------------------------------------------------------------- #

def test_aprs_roundtrip():
    iq = aprs.encode_text_aprs("CQ DX DE N0CALL", snr_db=20, seed=3)
    r = decode("aprs", iq, 48_000.0)
    assert r.success, r.message
    assert "N0CALL" in r.message and "CQ DX DE N0CALL" in r.message


def test_aprs_low_snr_and_several_seeds():
    for seed in (5, 11, 23):
        iq = aprs.encode_text_aprs("TEST", snr_db=10, seed=seed)
        r = decode("aprs", iq, 48_000.0)
        assert r.success, f"seed={seed}: {r.message}"
        assert "TEST" in r.message


def test_aprs_fcs_rejects_garbage():
    """噪声里随机命中的 0x7E 帧必须被 FCS-16 校验挡住。"""
    rng = np.random.default_rng(7)
    iq = (rng.standard_normal(24000) + 1j * rng.standard_normal(24000)).astype(complex)
    r = decode("aprs", iq, 48_000.0)
    assert not r.success


# --------------------------------------------------------------------------- #
# PSK31（BPSK + Varicode）
# --------------------------------------------------------------------------- #

def test_varicode_key_codes():
    """权威表关键码字核对（codec2 varicode_table.h 三重核实）。"""
    assert psk31.VARICODE[" "] == "1"
    assert psk31.VARICODE["e"] == "11"
    assert psk31.VARICODE["t"] == "101"
    assert psk31.VARICODE["o"] == "111"
    assert psk31.VARICODE["Z"] == "1010101101"     # 最长码（10 bit）
    assert psk31.VARICODE["J"] == "111111101"
    assert psk31.VARICODE["a"] == "1011"          # 小写 a 码字（codec2 截断逻辑）
    assert psk31.VARICODE["z"] == "111010101"


def test_varicode_full_roundtrip():
    chars = "".join(chr(i) for i in range(32, 128))
    bits = psk31.varicode_encode(chars)
    assert psk31.varicode_decode(bits) == chars


def test_psk31_roundtrip():
    text = "CQ CQ PSK31"
    iq = psk31.encode_text_psk31(text, snr_db=20, seed=3)
    r = decode("psk31", iq, 8000.0)
    assert r.success, r.message
    assert text in r.message


def test_psk31_noise_rejected():
    """纯噪声：幅度一致性门限应拒绝，不误报。"""
    rng = np.random.default_rng(7)
    iq = (rng.standard_normal(8000) + 1j * rng.standard_normal(8000)).astype(complex)
    r = decode("psk31", iq, 8000.0)
    assert not r.success


# --------------------------------------------------------------------------- #
# DTMF（Goertzel）
# --------------------------------------------------------------------------- #

def test_dtmf_roundtrip():
    seq = "1234567890*#ABCD"
    iq = dtmf.encode_dtmf(seq, snr_db=20, seed=3)
    r = decode("dtmf", iq, 8000.0)
    assert r.success, r.message
    assert r.message == seq


def test_dtmf_noise_rejected():
    """纯噪声：绝对阈值 + 双音结构判据应拒检。"""
    rng = np.random.default_rng(7)
    iq = rng.standard_normal(16000).astype(complex)
    r = decode("dtmf", iq, 8000.0)
    assert not r.success


# --------------------------------------------------------------------------- #
# POCSAG 注册接入
# --------------------------------------------------------------------------- #

def _bits_to_fsk_iq(bits, sps: int = 10):
    """0/1 bit 流 → 2-FSK IQ（与 test_pocsag 同构，POCSAG 端到端）。"""
    incs = np.array([(1 if b else -1) * (np.pi / 4) for b in bits for _ in range(sps)])
    phase = np.cumsum(incs)
    iq = np.exp(1j * phase)
    return np.append(iq, iq[-1])


def test_pocsag_registered_end_to_end():
    ric, fn, txt = 9001, 3, "E2E"
    iq = _bits_to_fsk_iq(build_frame_bits(ric, fn, txt))
    r = decode("pocsag", iq, 24_000.0)
    assert r.success, r.message
    assert "E2E" in r.message


def test_pocsag_noise_rejected():
    rng = np.random.default_rng(7)
    iq = (rng.standard_normal(24000) + 1j * rng.standard_normal(24000)).astype(complex)
    r = decode("pocsag", iq, 24_000.0)
    assert not r.success


# --------------------------------------------------------------------------- #
# 主流程健壮性：任何输入都不抛异常，返回失败结果
# --------------------------------------------------------------------------- #

def test_decode_all_never_raises_on_noise():
    rng = np.random.default_rng(11)
    iq = (rng.standard_normal(8000) + 1j * rng.standard_normal(8000)).astype(complex)
    for r in decode_all(iq, 8000.0):
        assert isinstance(r, DecodeResult)
        assert not r.success, f"{r.decoder} 对纯噪声误检: {r.message}"


def test_decoder_internal_exception_trapped():
    """decode_fn 内部抛非 ValueError 异常也被注册表捕获成失败结果。

    注意：注册表是全局单例，pytest-randomly 会打乱测试顺序——boom 必须
    finally 清理，否则泄漏进 _DECODERS 会让 test_registry_has_four_decoders
    的精确集合断言失败（实测踩过：Extra items in the left set: 'boom'）。
    """
    from mcpserver.rf_brain.decoders.registry import _DECODERS, register_decoder

    @register_decoder("boom")
    def _boom(iq, sample_rate, **params):
        raise RuntimeError("内部崩溃")

    try:
        r = decode("boom", np.zeros(64, complex), 8000.0)
        assert isinstance(r, DecodeResult)
        assert not r.success and "内部崩溃" in r.message
    finally:
        _DECODERS.pop("boom", None)   # 测试隔离：注册表是全局单例，必须清理


if __name__ == "__main__":
    test_registry_has_four_decoders()
    test_unknown_decoder_returns_failure()
    test_decode_all_is_generic_no_branches()
    test_aprs_roundtrip()
    test_aprs_low_snr_and_several_seeds()
    test_aprs_fcs_rejects_garbage()
    test_varicode_key_codes()
    test_varicode_full_roundtrip()
    test_psk31_roundtrip()
    test_psk31_noise_rejected()
    test_dtmf_roundtrip()
    test_dtmf_noise_rejected()
    test_pocsag_registered_end_to_end()
    test_pocsag_noise_rejected()
    test_decode_all_never_raises_on_noise()
    test_decoder_internal_exception_trapped()
    print("\n🎉 Phase6 多协议解码器库全部自测通过")
