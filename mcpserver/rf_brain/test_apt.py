"""Y-05 · NOAA APT 卫星图像解码器验收测试（AM 副载波解调 + 帧同步 → 灰度图 PNG）

覆盖工单验收点：
1. AM 包络检波：亮度幅度 → 包络（暗段/亮段可分离）
2. 帧同步（Sync A 1040Hz / Sync B 832Hz）检测：合成多行 → 逐行配对
3. 完整解码：通道 A（可见光）渐变 + 通道 B（红外）恒定 → 两幅 PNG 落盘，
   尺寸/魔法字节/亮度合理性
4. 健壮性：噪声 / 空信号 → 清晰报错；行数不一致 → 报错
5. 可选 TLE 接口：平均运动 → 轨道周期；坏输入 → None

全部用合成基带信号（诚实标注：真机 FM 解调 + 斜距校正需按几何校准）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain.satellite import apt  # noqa: E402

SR = 48_000.0
W = 909


# --------------------------------------------------------------------------- #
# 合成亮度行
# --------------------------------------------------------------------------- #

def _grad_rows(n: int = 3, width: int = W) -> list[np.ndarray]:
    g = np.linspace(0.0, 1.0, width)  # 左暗右亮
    return [g.copy() for _ in range(n)]


def _const_rows(n: int = 3, width: int = W, val: float = 0.5) -> list[np.ndarray]:
    return [np.full(width, val) for _ in range(n)]


# --------------------------------------------------------------------------- #
# AM 解调
# --------------------------------------------------------------------------- #

def test_am_demod_scales_with_video():
    n = int(SR * 0.05)
    mixed = np.concatenate([
        apt._am_video(np.full(n, 0.2), SR),
        apt._am_video(np.full(n, 0.9), SR),
    ])
    env = apt.am_demod(mixed, SR)
    mid = n // 4
    lo = env[n - mid: n].mean()
    hi = env[n: n + mid].mean()
    assert hi > lo * 2, f"亮段包络应显著高于暗段: lo={lo:.3f} hi={hi:.3f}"


# --------------------------------------------------------------------------- #
# 帧同步检测
# --------------------------------------------------------------------------- #

def test_detect_line_syncs_finds_lines():
    sig = apt.encode_apt(_grad_rows(3), _const_rows(3), SR)
    lines = apt.detect_line_syncs(sig, SR)
    assert len(lines) == 3, f"应检测到 3 行帧同步，实际 {len(lines)}"
    for a, b in lines:
        assert b > a, "Sync B 必须晚于 Sync A"


def test_detect_line_syncs_rejects_noise():
    rng = np.random.default_rng(3)
    noise = rng.standard_normal(int(SR * 1.5))
    assert apt.detect_line_syncs(noise, SR) == []


# --------------------------------------------------------------------------- #
# 完整解码
# --------------------------------------------------------------------------- #

def test_decode_apt_roundtrip():
    n = 3
    sig = apt.encode_apt(_grad_rows(n), _const_rows(n), SR)
    info = apt.decode_apt(sig, SR, image_width=W)
    assert info["ok"] is True
    assert info["n_lines"] == n
    assert info["width"] == W and info["height"] == n

    for key in ("png_a", "png_b"):
        p = Path(info[key])
        assert p.exists(), key
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", key

    arr_a = np.asarray(info["image_a"])
    arr_b = np.asarray(info["image_b"])
    assert arr_a.shape == (n, W)
    assert arr_b.shape == (n, W)
    # 通道 A 渐变：左暗右亮
    assert arr_a[:, :W // 2].mean() < arr_a[:, W // 2:].mean()
    # 通道 B 恒定 0.5：中灰（容差吸收 AM 检波纹波）
    assert abs(arr_b.mean() - 127.5) < 40, f"通道 B 亮度异常: {arr_b.mean():.1f}"


def test_decode_apt_channels_separable():
    sig = apt.encode_apt(_const_rows(3, val=0.1), _const_rows(3, val=0.9), SR)
    info = apt.decode_apt(sig, SR, image_width=W)
    arr_a = np.asarray(info["image_a"]).mean()
    arr_b = np.asarray(info["image_b"]).mean()
    assert arr_a < 80, f"通道 A 应为暗: {arr_a:.1f}"
    assert arr_b > 170, f"通道 B 应为亮: {arr_b:.1f}"


def test_decode_apt_rejects_empty():
    with pytest.raises(ValueError):
        apt.decode_apt(np.array([]), SR)


def test_decode_apt_rejects_noise():
    rng = np.random.default_rng(5)
    noise = rng.standard_normal(int(SR * 1.5))
    with pytest.raises(ValueError):
        apt.decode_apt(noise, SR)


# --------------------------------------------------------------------------- #
# 合成器参数校验 + 可选 TLE 接口
# --------------------------------------------------------------------------- #

def test_encode_apt_requires_equal_rows():
    with pytest.raises(ValueError):
        apt.encode_apt(_grad_rows(3), _const_rows(2), SR)


def test_orbit_period_minutes():
    def _tle2(mm: float) -> str:
        field = f"{mm:11.8f}"
        assert len(field) == 11
        return ("X" * 52) + field + ("Y" * 6)  # 69 列，平均运动在第 53~63 列

    assert apt.tle_mean_motion(_tle2(15.5)) == pytest.approx(15.5)
    assert apt.orbit_period_minutes("1 X", _tle2(15.5)) == pytest.approx(1440.0 / 15.5)
    assert apt.tle_mean_motion("short") is None
    assert apt.orbit_period_minutes("1 X", "bad") is None


if __name__ == "__main__":
    test_am_demod_scales_with_video()
    test_detect_line_syncs_finds_lines()
    test_detect_line_syncs_rejects_noise()
    test_decode_apt_roundtrip()
    test_decode_apt_channels_separable()
    test_decode_apt_rejects_empty()
    test_decode_apt_rejects_noise()
    test_encode_apt_requires_equal_rows()
    test_orbit_period_minutes()
    print("\n🎉 Y-05 APT 卫星解码器全部自测通过")
