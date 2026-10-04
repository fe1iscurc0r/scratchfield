"""Y-03 · SSTV 慢扫描电视解码器验收测试（VIS 识别 + 行解码 → PIL 灰度图 PNG）

覆盖工单验收点：
1. VIS 起始码编码（LSB-first + 奇校验）与自动识别（合成音频 → 模式码）
2. 噪声 / 音频过短 → 清晰报错，不误报
3. 完整帧解码 → PIL 灰度图 PNG 落盘（尺寸 / 魔法字节 / 亮度合理）
4. 模式表 list_modes 覆盖 Robot/Martin/Scottie；注册表含 sstv 且噪声拒检

全部用合成音频（诚实标注：真机 .wav 需校准时序），不依赖外部信号源。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain.decoders import (  # noqa: E402
    DecodeResult,
    decode,
    list_decoders,
    sstv,
)

SR = 48_000.0  # 高采样率：保证零过零瞬时频率估算分辨率（真机 .wav 常见 44.1k/48k）


# --------------------------------------------------------------------------- #
# 合成器（VIS 起始码 + 完整帧）
# --------------------------------------------------------------------------- #

def _tone(hz: float, n: int, sr: float = SR, amp: float = 0.9) -> np.ndarray:
    """生成 n 样本的正弦音（瞬时频率 = 亮度，幅度不影响过零判读）。"""
    t = np.arange(n, dtype=float) / sr
    return (amp * np.sin(2 * np.pi * hz * t)).astype(np.float64)


def _vis_signal(vis_code: int, sr: float = SR) -> np.ndarray:
    """合成 SSTV VIS 起始码：导频 1900Hz + 起始位 + 8 数据位 + 停止位。"""
    leader = _tone(sstv.VIS_LEADER_HZ, int(round(sstv.VIS_LEADER_MS / 1000 * sr)), sr)
    start = _tone(sstv.VIS_START_HZ, int(round(sstv.VIS_BIT_MS / 1000 * sr)), sr)
    bits = [
        _tone(sstv.VIS_ONE_HZ if b else sstv.VIS_ZERO_HZ,
              int(round(sstv.VIS_BIT_MS / 1000 * sr)), sr)
        for b in sstv._vis_bits_for_code(vis_code)
    ]
    stop = _tone(sstv.VIS_STOP_HZ, int(round(sstv.VIS_BIT_MS / 1000 * sr)), sr)
    return np.concatenate([leader, start, *bits, stop])


def _sstv_frame(vis_code: int, sr: float = SR, luma_hz: float = 1900.0) -> np.ndarray:
    """合成一整帧：VIS + N 行（行同步 1200 + 门廊 1500 + 扫描 luma_hz）。"""
    mode = sstv.MODE_TABLE[vis_code]
    sync = _tone(sstv.SYNC_HZ, int(round(mode.sync_ms / 1000 * sr)), sr)
    porch = _tone(sstv.PORCH_HZ, int(round(mode.porch_ms / 1000 * sr)), sr)
    scan = _tone(luma_hz, int(round(mode.scan_ms / 1000 * sr)), sr)
    line = np.concatenate([sync, porch, scan])
    return np.concatenate([_vis_signal(vis_code, sr)] + [line] * mode.height)


# --------------------------------------------------------------------------- #
# VIS 编码 + 识别
# --------------------------------------------------------------------------- #

def test_vis_bits_lsb_first_odd_parity():
    # 8 = 0b1000（1 个 1，奇校验位=0）→ LSB 先 [0,0,0,1,0,0,0,0]
    assert sstv._vis_bits_for_code(8) == [0, 0, 0, 1, 0, 0, 0, 0]
    # 44 = 0b101100（3 个 1，奇校验位=0）
    assert sstv._vis_bits_for_code(44) == [0, 0, 1, 1, 0, 1, 0, 0]
    # 3 = 0b11（2 个 1，偶 → 奇校验位=1）
    assert sstv._vis_bits_for_code(3) == [1, 1, 0, 0, 0, 0, 0, 1]


def test_detect_vis_recovers_code():
    for vis_code in (8, 36, 44, 60, 76):
        sig = _vis_signal(vis_code)
        code, end = sstv.detect_vis(sig, SR)
        assert code == vis_code, f"VIS={vis_code} 被识别为 {code}"
        assert end == sig.size, f"VIS={vis_code} 结束偏移 {end} != {sig.size}"


def test_detect_vis_rejects_noise():
    # 纯噪声：任何阶段都应拒检（导频/起始位/停止位任一处失配），绝不返回有效码
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(int(SR * 1.0))  # 需长于 VIS 起始码，走导频扫描分支
    with pytest.raises(ValueError):
        sstv.detect_vis(noise, SR)


def test_detect_vis_rejects_no_leader():
    # 恒定 1000Hz 音：远离 1900Hz 导频 → 明确报"导频"未检测到（确定性分支）
    tone = _tone(1000.0, int(SR * 1.0))
    try:
        sstv.detect_vis(tone, SR)
        raise AssertionError("无导频信号不应识别")
    except ValueError as e:
        assert "导频" in str(e)


def test_detect_vis_rejects_short():
    try:
        sstv.detect_vis(np.zeros(100), SR)
        raise AssertionError("过短音频不应识别出 VIS")
    except ValueError as e:
        assert "过短" in str(e)


def test_decode_sstv_rejects_unsupported_mode():
    # VIS 99 合法编码但不在模式表 → 解码主入口清晰报错
    try:
        sstv.decode_sstv(_vis_signal(99), SR)
        raise AssertionError("不支持的 VIS 模式码应报错")
    except ValueError as e:
        assert "不支持" in str(e) and "99" in str(e)


# --------------------------------------------------------------------------- #
# 完整帧解码 → PNG
# --------------------------------------------------------------------------- #

def test_decode_sstv_produces_png():
    info = sstv.decode_sstv(_sstv_frame(8, luma_hz=1900.0), SR)
    assert info["ok"] is True
    assert info["mode"] == "Robot 8 BW"
    assert info["vis"] == 8
    assert info["width"] == 160 and info["height"] == 120
    assert info["color"] is False

    png = Path(info["png"])
    assert png.exists()
    magic = png.read_bytes()[:8]
    assert magic == b"\x89PNG\r\n\x1a\n", magic

    # 亮度分量为中灰（1900Hz ≈ (1900-1500)/800*255 ≈ 128），非纯黑/纯白
    arr = np.asarray(info["image"])
    assert arr.shape == (120, 160)
    assert 40 < arr.mean() < 220, f"亮度异常: mean={arr.mean():.1f}"


# --------------------------------------------------------------------------- #
# 模式表 + 注册表
# --------------------------------------------------------------------------- #

def test_list_modes_covers_required_modes():
    modes = {m["vis"]: m for m in sstv.list_modes()}
    assert set(modes) == {8, 36, 72, 40, 44, 56, 60, 76}
    for key in ("name", "width", "height", "color", "description"):
        assert all(key in m for m in modes.values()), f"模式缺字段 {key}"
    assert modes[36]["width"] == 320 and modes[36]["color"] is True


def test_registry_has_sstv_and_noise_rejected():
    assert "sstv" in list_decoders()
    rng = np.random.default_rng(11)
    noise = rng.standard_normal(int(SR * 1.0))
    r = decode("sstv", noise, SR)
    assert isinstance(r, DecodeResult)
    assert not r.success, r.message


if __name__ == "__main__":
    test_vis_bits_lsb_first_odd_parity()
    test_detect_vis_recovers_code()
    test_detect_vis_rejects_noise()
    test_detect_vis_rejects_no_leader()
    test_detect_vis_rejects_short()
    test_decode_sstv_rejects_unsupported_mode()
    test_decode_sstv_produces_png()
    test_list_modes_covers_required_modes()
    test_registry_has_sstv_and_noise_rejected()
    print("\n🎉 Y-03 SSTV 解码器全部自测通过")
