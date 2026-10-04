"""NOAA APT（自动图像传输）解码器（Y-05 · AM 副载波解调 → 帧同步 → 图像）

NOAA 极轨气象卫星在 137 MHz 以 FM 播发 APT。FM 解调后得到基带信号：
- 图像：2400 Hz AM 副载波，视频亮度 = 副载波幅度
- 帧同步：Sync A（1040 Hz × 7）+ Sync B（832 Hz × 7），即每行 0.5s 的
  交替同步脉冲（数字采样层面常记为 0xAC / 0xAA 交替同步标记的模拟源头）

每行 0.5s 结构：
  Sync A → 空间 A（黑参考）→ 图像 A → 遥测 A → Sync B → 空间 B → 图像 B → 遥测 B

实现纪律（授粉）：按公开协议（NOAA APT 时序）独立实现，仅参考协议描述，
未 copy 任何 APT 解码器源码。时序为公开协议近似值，真机需按采样率/几何校准。

输入：基带实数信号（.wav 读入、FM 解调后的 AM 副载波；IQ 取实部兼容）。
输出：两幅灰度图（通道 A 可见光 / 通道 B 红外）→ PNG 落盘。
完整斜距校正（遥测楔 wedge 对齐）留真机验证——本模块按帧同步锚定每行起点去抖。
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 协议常量（NOAA APT，公开时序近似值）
# --------------------------------------------------------------------------- #
SYNC_A_HZ = 1040.0        # Sync A 帧同步音
SYNC_A_CYCLES = 7
SYNC_B_HZ = 832.0         # Sync B 帧同步音
SYNC_B_CYCLES = 7
SYNC_A_SEC = SYNC_A_CYCLES / SYNC_A_HZ   # ≈ 6.73 ms
SYNC_B_SEC = SYNC_B_CYCLES / SYNC_B_HZ   # ≈ 8.41 ms
SPACE_SEC = 0.005         # 黑参考间隔
IMAGE_SEC = 0.208         # 单通道图像扫描时长（两通道各 ~208ms，余量给遥测）
LINE_SEC = 0.5            # 每行时长（2 行/秒）
CARRIER_HZ = 2400.0       # AM 副载波


# --------------------------------------------------------------------------- #
# 基础合成/解调工具
# --------------------------------------------------------------------------- #

def _tone(hz: float, n: int, sample_rate: float, amp: float = 1.0) -> np.ndarray:
    t = np.arange(n, dtype=float) / sample_rate
    return (amp * np.sin(2 * np.pi * hz * t)).astype(np.float64)


def _am_video(video: np.ndarray, sample_rate: float, carrier_hz: float = CARRIER_HZ) -> np.ndarray:
    """把亮度序列 video（0..1）AM 调制到副载波（幅度 = 亮度）。"""
    video = np.asarray(video, dtype=float)
    t = np.arange(video.size, dtype=float) / sample_rate
    carrier = np.sin(2 * np.pi * carrier_hz * t)
    return (video * carrier).astype(np.float64)


def _resample(y: np.ndarray, n_out: int) -> np.ndarray:
    """线性重采样到 n_out 个点（图像行 ↔ 时域样本互转）。"""
    y = np.asarray(y, dtype=float)
    n_in = y.size
    if n_in < 2 or n_out < 1:
        return np.full(n_out, 0.0, dtype=float)
    x_in = np.linspace(0.0, 1.0, n_in, endpoint=False)
    x_out = np.linspace(0.0, 1.0, n_out, endpoint=False)
    return np.interp(x_out, x_in, y)


def _section_samples(sample_rate: float) -> dict:
    """各段样本数（与编码/解码共用同一时序，保证自洽）。"""
    return {
        "sync_a": int(round(SYNC_A_SEC * sample_rate)),
        "sync_b": int(round(SYNC_B_SEC * sample_rate)),
        "space": int(round(SPACE_SEC * sample_rate)),
        "image": int(round(IMAGE_SEC * sample_rate)),
        "line": int(round(LINE_SEC * sample_rate)),
    }


# --------------------------------------------------------------------------- #
# AM 解调 + 帧同步检测
# --------------------------------------------------------------------------- #

def am_demod(signal: np.ndarray, sample_rate: float, carrier_hz: float = CARRIER_HZ) -> np.ndarray:
    """AM 包络检波：整流 + 低通（一个副载波周期滑动平均），归一化到 0..1。"""
    x = np.asarray(signal, dtype=float)
    if x.size == 0:
        raise ValueError("信号为空，无法 AM 解调")
    x = x - np.mean(x)
    env = np.abs(x)
    win = max(1, int(round(sample_rate / carrier_hz)))
    kernel = np.ones(win) / win
    env = np.convolve(env, kernel, mode="same")
    mx = float(env.max())
    if mx > 0:
        env = env / mx
    return env


def _tone_power(signal: np.ndarray, sample_rate: float, freq: float, win_sec: float) -> np.ndarray:
    """滑窗 Goertzel 功率（在 freq 处），返回与 signal 等长的能量序列。"""
    x = np.asarray(signal, dtype=float)
    n = max(1, int(round(win_sec * sample_rate)))
    t = np.arange(x.size, dtype=float) / sample_rate
    ref_s = np.sin(2 * np.pi * freq * t)
    ref_c = np.cos(2 * np.pi * freq * t)
    kernel = np.ones(n)
    s_sum = np.convolve(x * ref_s, kernel, mode="same")
    c_sum = np.convolve(x * ref_c, kernel, mode="same")
    return s_sum ** 2 + c_sum ** 2


def _total_energy(signal: np.ndarray, sample_rate: float, win_sec: float) -> np.ndarray:
    """滑窗总能量（信号平方的滑动和），用于计算同步音占比（拒噪）。"""
    x = np.asarray(signal, dtype=float)
    n = max(1, int(round(win_sec * sample_rate)))
    kernel = np.ones(n)
    return np.convolve(x * x, kernel, mode="same")


def _find_peaks(x: np.ndarray, min_distance: int, threshold: float) -> np.ndarray:
    """简单峰值检测（局部极大 + 非极大值抑制 + 阈值），返回索引数组。"""
    x = np.asarray(x, dtype=float)
    idx: list[int] = []
    last = -min_distance - 1
    for i in range(1, x.size - 1):
        if x[i] > threshold and x[i] > x[i - 1] and x[i] >= x[i + 1]:
            if i - last >= min_distance:
                idx.append(i)
                last = i
    return np.array(idx, dtype=int)


def detect_line_syncs(signal: np.ndarray, sample_rate: float) -> list[tuple[int, int]]:
    """检测每行帧同步，返回 [(sync_a_center, sync_b_center), ...]。

    峰值定位在同步音中心（非起点），图像锚点按中心 + 半同步长 + 空间计算。
    找不到任一同步音返回空列表。
    """
    x = np.asarray(signal, dtype=float)
    min_dist = max(1, int(round(LINE_SEC * sample_rate * 0.5)))
    pa = _tone_power(x, sample_rate, SYNC_A_HZ, SYNC_A_SEC)
    pb = _tone_power(x, sample_rate, SYNC_B_HZ, SYNC_B_SEC)
    ta = _total_energy(x, sample_rate, SYNC_A_SEC)
    tb = _total_energy(x, sample_rate, SYNC_B_SEC)
    if pa.size == 0 or pb.size == 0:
        return []
    eps = 1e-12
    # 同步音占比：纯音在窗内 Goertzel 功率 ≈ N/2；832↔1040 互串扰 ≈ 4.66%·N/2，
    # 故取 N/4 作阈值（随采样率缩放，既压串扰又留足纯音余量）。
    ra = pa / (ta + eps)
    rb = pb / (tb + eps)
    n_a = max(1, int(round(SYNC_A_SEC * sample_rate)))
    n_b = max(1, int(round(SYNC_B_SEC * sample_rate)))
    a_idx = _find_peaks(ra, min_distance=min_dist, threshold=n_a / 4.0)
    b_idx = _find_peaks(rb, min_distance=min_dist, threshold=n_b / 4.0)
    gap = int(round(SYNC_A_SEC * sample_rate))
    lines: list[tuple[int, int]] = []
    for a in a_idx:
        after = b_idx[b_idx > a + gap]
        if after.size:
            lines.append((int(a), int(after[0])))
    return lines


# --------------------------------------------------------------------------- #
# 解码主入口
# --------------------------------------------------------------------------- #

def decode_apt(signal: np.ndarray, sample_rate: float, *,
               out_dir: str | Path | None = None, stem: str = "apt",
               image_width: int = 909) -> dict:
    """APT 基带信号 → 通道 A/B 两幅灰度图 PNG。

    Args:
        signal: 基带实数样本（FM 解调后的 AM 副载波）
        sample_rate: 采样率（Hz，取自 wav 文件头）
        out_dir: PNG 输出目录（None 则写临时目录）
        stem: 输出文件主名
        image_width: 每行解码像素宽度（标准 909）

    Returns:
        {ok, n_lines, width, height, png_a, png_b, image_a, image_b, note}
        无帧同步 / 无完整行抛 ValueError（诚实降级，不编造）。
    """
    x = np.asarray(signal, dtype=float)
    if x.size == 0:
        raise ValueError("信号为空，无法解码 APT")

    ss = _section_samples(sample_rate)
    lines = detect_line_syncs(x, sample_rate)
    if not lines:
        raise ValueError("未检测到 APT 帧同步（Sync A/B）")

    env = am_demod(x, sample_rate)
    half_a = ss["sync_a"] // 2
    half_b = ss["sync_b"] // 2
    rows_a: list[np.ndarray] = []
    rows_b: list[np.ndarray] = []
    for a, b in lines:
        sa = a + half_a + ss["space"]          # 中心 + 半同步长 + 空间 → 图像 A 起点
        sb = b + half_b + ss["space"]
        if sa + ss["image"] > x.size or sb + ss["image"] > x.size:
            continue                             # 最后一行不完整，跳过
        rows_a.append(_resample(env[sa:sa + ss["image"]], image_width))
        rows_b.append(_resample(env[sb:sb + ss["image"]], image_width))
    if not rows_a:
        raise ValueError("无完整 APT 行可解码")

    img_a = np.stack(rows_a)
    img_b = np.stack(rows_b)

    def _to_u8(m: np.ndarray) -> np.ndarray:
        return (np.clip(m, 0.0, 1.0) * 255.0).astype(np.uint8)

    from PIL import Image

    im_a = Image.fromarray(_to_u8(img_a), mode="L")
    im_b = Image.fromarray(_to_u8(img_b), mode="L")
    out_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="apt_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    png_a = out_dir / f"{stem}_A.png"
    png_b = out_dir / f"{stem}_B.png"
    im_a.save(png_a)
    im_b.save(png_b)

    return {
        "ok": True,
        "n_lines": len(rows_a),
        "width": image_width,
        "height": len(rows_a),
        "png_a": str(png_a),
        "png_b": str(png_b),
        "image_a": im_a,
        "image_b": im_b,
        "note": "AM 副载波解调 + 帧同步；完整斜距校正（遥测楔）留真机验证",
    }


# --------------------------------------------------------------------------- #
# 合成器（测试 / 演示，诚实标注）
# --------------------------------------------------------------------------- #

def encode_apt(rows_a: list[np.ndarray], rows_b: list[np.ndarray],
               sample_rate: float, carrier_hz: float = CARRIER_HZ) -> np.ndarray:
    """合成 APT 基带信号（测试/演示用，非真实卫星数据）。

    Args:
        rows_a/rows_b: 每行亮度序列（0..1），两通道行数必须一致
        sample_rate: 采样率
    """
    rows_a = [np.asarray(r, dtype=float) for r in rows_a]
    rows_b = [np.asarray(r, dtype=float) for r in rows_b]
    if len(rows_a) != len(rows_b):
        raise ValueError("通道 A/B 行数必须一致")
    ss = _section_samples(sample_rate)
    fixed = ss["sync_a"] + ss["sync_b"] + 2 * ss["space"] + 2 * ss["image"]
    tel = max(0, (ss["line"] - fixed) // 2)     # 遥测占位（黑参考）
    lines = []
    for ra, rb in zip(rows_a, rows_b):
        seg = [
            _tone(SYNC_A_HZ, ss["sync_a"], sample_rate),
            _am_video(np.zeros(ss["space"]), sample_rate, carrier_hz),
            _am_video(_resample(ra, ss["image"]), sample_rate, carrier_hz),
            _am_video(np.zeros(tel), sample_rate, carrier_hz),
            _tone(SYNC_B_HZ, ss["sync_b"], sample_rate),
            _am_video(np.zeros(ss["space"]), sample_rate, carrier_hz),
            _am_video(_resample(rb, ss["image"]), sample_rate, carrier_hz),
            _am_video(np.zeros(tel), sample_rate, carrier_hz),
        ]
        lines.append(np.concatenate(seg))
    return np.concatenate(lines)


# --------------------------------------------------------------------------- #
# 可选：TLE 轨道接口
# --------------------------------------------------------------------------- #

def tle_mean_motion(tle_line2: str) -> float | None:
    """从 TLE 第二行第 53~63 列解析平均运动（rev/day）。失败返回 None。"""
    s = str(tle_line2).strip()
    if len(s) < 63:
        return None
    try:
        return float(s[52:63])
    except ValueError:
        return None


def orbit_period_minutes(tle_line1: str, tle_line2: str) -> float | None:
    """可选：TLE 两行 → 轨道周期（分钟）。无法解析返回 None（诚实降级）。"""
    mm = tle_mean_motion(tle_line2)
    if mm is None or mm <= 0:
        return None
    return 1440.0 / mm
