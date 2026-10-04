"""SSTV 慢扫描电视解码器（Phase 6 · VIS 识别 + 行解码 → PIL 灰度图）

SSTV（Slow Scan Television）把静止图像用音频 FM 传输：瞬时音频频率即像素
亮度（1500 Hz = 黑，2300 Hz = 白），3~120 秒一张图。

实现纪律（授粉）：按公开协议（VIS 起始码 / 行同步 / 扫描时序）独立实现，
仅参考协议描述，未 copy QSSTV / MMSSTV 源码。

支持模式（VIS 码 → 模式，时序为公开协议近似值，真机需校准）：
- Robot 8 BW(8) / 36(36) / 72(72)
- Martin M1(44) / M2(40)
- Scottie S1(60) / S2(56) / DX(76)

输入：音频（实数样本，.wav 文件输入——绕开虚拟声卡音频链坑）。
输出：PIL 灰度图（luma 分量）→ PNG 落盘。彩色重建（chroma）留真机验证，
本模块只取亮度分量并如实标注。

注册：本模块不主动注册，由 decoders/__init__.py 统一导入触发。
"""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# VIS 起始码时序（公开协议：ISO/IEC 与各模式文档一致）
# --------------------------------------------------------------------------- #
VIS_LEADER_HZ = 1900.0        # 导频（leader）频率
VIS_LEADER_MS = 300.0         # 导频时长
VIS_BIT_MS = 30.0             # 单个数据位时长
VIS_START_HZ = 1200.0         # 起始位
VIS_STOP_HZ = 1200.0          # 停止位
VIS_ZERO_HZ = 1100.0          # 逻辑 0
VIS_ONE_HZ = 1300.0           # 逻辑 1

# 行同步 / 亮度频率范围
SYNC_HZ = 1200.0
PORCH_HZ = 1500.0
LUMA_MIN_HZ = 1500.0          # 黑
LUMA_MAX_HZ = 2300.0          # 白

# 频率容差（Hz）
_FREQ_TOL = 150.0


@dataclass(frozen=True)
class SSTVMode:
    """一种 SSTV 模式的几何与行时序（公开协议近似值）。"""

    vis: int
    name: str
    width: int
    height: int
    sync_ms: float
    porch_ms: float
    scan_ms: float
    color: bool
    description: str


# 模式表（VIS 码 → 模式）。scan_ms 为单行图像扫描时长（近似，真机需校准）。
MODE_TABLE: dict[int, SSTVMode] = {
    8: SSTVMode(8, "Robot 8 BW", 160, 120, 7.0, 1.5, 56.0, False, "黑白，约 8 秒"),
    36: SSTVMode(36, "Robot 36", 320, 240, 9.0, 1.5, 88.0, True, "彩色，约 36 秒"),
    72: SSTVMode(72, "Robot 72", 320, 240, 9.0, 1.5, 138.0, True, "彩色，约 72 秒"),
    40: SSTVMode(40, "Martin 2", 160, 256, 4.862, 0.572, 73.2, True, "彩色，约 58 秒"),
    44: SSTVMode(44, "Martin 1", 320, 256, 4.862, 0.572, 146.4, True, "彩色，约 114 秒"),
    56: SSTVMode(56, "Scottie 2", 160, 256, 9.0, 1.5, 73.2, True, "彩色，约 71 秒"),
    60: SSTVMode(60, "Scottie 1", 320, 256, 9.0, 1.5, 138.2, True, "彩色，约 110 秒"),
    76: SSTVMode(76, "Scottie DX", 320, 256, 9.0, 1.5, 345.6, True, "彩色，约 269 秒"),
}


def list_modes() -> list[dict]:
    """列出支持的模式（供 CLI / 测试 / 诊断）。"""
    return [
        {"vis": m.vis, "name": m.name, "width": m.width, "height": m.height,
         "color": m.color, "description": m.description}
        for m in sorted(MODE_TABLE.values(), key=lambda x: x.vis)
    ]


# --------------------------------------------------------------------------- #
# 频率估计
# --------------------------------------------------------------------------- #

def _dominant_freq(seg: np.ndarray, sample_rate: float,
                   lo: float = 800.0, hi: float = 3000.0) -> float | None:
    """短段主频估计（FFT 峰值，加窗去直流）。样本过短返回 None。"""
    x = np.asarray(seg, dtype=float)
    if x.size < 8:
        return None
    x = x - np.mean(x)
    n = x.size
    win = np.hanning(n)
    spec = np.abs(np.fft.rfft(x * win))
    freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)
    band = (freqs >= lo) & (freqs <= hi)
    if not band.any():
        return None
    idx = int(np.argmax(spec[band]))
    return float(freqs[band][idx])


def _instantaneous_freq(audio: np.ndarray, sample_rate: float) -> np.ndarray:
    """过零法瞬时频率（每样本 Hz）。无过零处填 NaN。"""
    x = np.asarray(audio, dtype=float)
    x = x - np.mean(x)
    n = x.size
    freq = np.full(n, np.nan)
    sign = np.sign(x)
    crossings = np.flatnonzero(sign[1:] != sign[:-1])
    if crossings.size < 2:
        return freq
    gaps = np.diff(crossings)
    per_interval = np.clip(sample_rate / (2.0 * gaps), LUMA_MIN_HZ, LUMA_MAX_HZ)
    # 逐区间赋值（过零次数为 O(音频长度/周期)，测试规模下开销可接受）
    for a, b, f in zip(crossings[:-1], crossings[1:], per_interval):
        freq[a:b] = f
    # 首尾补齐
    first_f = per_interval[0] if per_interval.size else LUMA_MIN_HZ
    if crossings[0] > 0:
        freq[:crossings[0]] = first_f
    last_f = per_interval[-1] if per_interval.size else LUMA_MIN_HZ
    if crossings[-1] < n - 1:
        freq[crossings[-1]:] = last_f
    return freq


# --------------------------------------------------------------------------- #
# VIS 识别
# --------------------------------------------------------------------------- #

def _vis_bits_for_code(vis_code: int) -> list[int]:
    """把 7-bit 模式码编码为 8 个传输位（LSB 先，最高位为奇校验）。"""
    code = int(vis_code) & 0x7F
    parity = 0 if bin(code).count("1") % 2 == 1 else 1  # 奇校验
    byte = (parity << 7) | code
    return [(byte >> i) & 1 for i in range(8)]  # LSB 先


def detect_vis(audio: np.ndarray, sample_rate: float) -> tuple[int, int]:
    """识别 VIS 起始码，返回 (vis_code, VIS 结束后的样本偏移)。

    找不到导频 / 起始位错误 / 数据位读取失败抛 ValueError。
    """
    x = np.asarray(audio, dtype=float)
    bit_n = int(round(VIS_BIT_MS / 1000.0 * sample_rate))
    leader_n = int(round(VIS_LEADER_MS / 1000.0 * sample_rate))
    if x.size < leader_n + 10 * bit_n:
        raise ValueError("音频过短，无法识别 VIS 起始码")

    step = max(1, bit_n // 2)
    leader_start = None
    for i in range(0, x.size - bit_n, step):
        f = _dominant_freq(x[i:i + bit_n], sample_rate)
        if f is not None and abs(f - VIS_LEADER_HZ) < _FREQ_TOL:
            leader_start = i
            break
    if leader_start is None:
        raise ValueError("未检测到 VIS 导频（1900 Hz）")

    data_start = leader_start + leader_n
    if data_start + 10 * bit_n > x.size:
        raise ValueError("音频在 VIS 数据段提前结束")

    start_f = _dominant_freq(x[data_start:data_start + bit_n], sample_rate)
    if start_f is None or abs(start_f - VIS_START_HZ) > _FREQ_TOL:
        raise ValueError("VIS 起始位（1200 Hz）错误")

    byte = 0
    for k in range(8):
        off = data_start + bit_n + k * bit_n
        f = _dominant_freq(x[off:off + bit_n], sample_rate)
        if f is None:
            raise ValueError(f"VIS 数据位 {k} 读取失败")
        byte |= (1 << k) if f > (VIS_ZERO_HZ + VIS_ONE_HZ) / 2 else 0

    stop_off = data_start + bit_n + 8 * bit_n
    stop_f = _dominant_freq(x[stop_off:stop_off + bit_n], sample_rate)
    if stop_f is None or abs(stop_f - VIS_STOP_HZ) > _FREQ_TOL:
        raise ValueError("VIS 停止位（1200 Hz）错误")

    vis_code = byte & 0x7F
    parity = byte >> 7
    if (bin(vis_code).count("1") + parity) % 2 != 1:
        logger.warning("[sstv] VIS 奇偶校验不匹配: code=%d", vis_code)
    return vis_code, stop_off + bit_n


# --------------------------------------------------------------------------- #
# 解码主入口
# --------------------------------------------------------------------------- #

def decode_sstv(audio: np.ndarray, sample_rate: float, *,
                out_dir: str | Path | None = None, stem: str = "sstv") -> dict:
    """SSTV 音频 → 灰度图 PNG。

    Args:
        audio: 实数音频样本（.wav 读入，绕开音频链）
        sample_rate: 采样率（Hz，取自 wav 文件头）
        out_dir: PNG 输出目录（None 则写临时目录）
        stem: 输出文件主名

    Returns:
        {ok, mode, vis, width, height, color, png, image, note}
        识别失败 / 模式不支持 / 音频不足抛 ValueError（诚实降级，不编造）。
    """
    x = np.asarray(audio, dtype=float)
    if x.size == 0:
        raise ValueError("音频为空，无法解码 SSTV")

    vis_code, vis_end = detect_vis(x, sample_rate)
    mode = MODE_TABLE.get(vis_code)
    if mode is None:
        raise ValueError(f"不支持的 VIS 模式码: {vis_code}（支持: {sorted(MODE_TABLE)}）")

    ifreq = _instantaneous_freq(x, sample_rate)
    sync_n = int(round(mode.sync_ms / 1000.0 * sample_rate))
    porch_n = int(round(mode.porch_ms / 1000.0 * sample_rate))
    scan_n = int(round(mode.scan_ms / 1000.0 * sample_rate))
    line_n = sync_n + porch_n + scan_n

    img = np.zeros((mode.height, mode.width), dtype=np.uint8)
    pos = vis_end
    for row in range(mode.height):
        if pos + line_n > ifreq.size:
            raise ValueError(
                f"音频不足：第 {row}/{mode.height} 行提前结束（可能采样率或模式不符）")
        seg = ifreq[pos + sync_n + porch_n: pos + line_n]
        if seg.size < mode.width:
            raise ValueError(f"第 {row} 行扫描段过短（{seg.size} 样本 < {mode.width} 像素）")
        bins = np.array_split(seg, mode.width)
        pixel_freq = np.array([np.nanmedian(b) if b.size else np.nan for b in bins])
        gray = np.clip((pixel_freq - LUMA_MIN_HZ) / (LUMA_MAX_HZ - LUMA_MIN_HZ), 0.0, 1.0)
        gray = np.nan_to_num(gray, nan=0.0)
        img[row] = (gray * 255.0).astype(np.uint8)
        pos += line_n

    from PIL import Image

    im = Image.fromarray(img, mode="L")
    out_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="sstv_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{stem}.png"
    im.save(png)

    return {
        "ok": True,
        "mode": mode.name,
        "vis": mode.vis,
        "width": mode.width,
        "height": mode.height,
        "color": mode.color,
        "png": str(png),
        "image": im,
        "note": "灰度（luma）解码；彩色 chroma 重建留真机验证",
    }
