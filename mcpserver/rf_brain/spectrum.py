"""SDR 频谱 / 瀑布图计算（Y-04 · radio_suite Web 面板后端纯计算）

纯 numpy 实现，无硬件依赖，可离线单元测试。为 `/api/radio/spectrum/ws`
WebSocket 端点提供 2-5fps 的实时频谱帧：

  - compute_spectrum       实/复信号 → FFT 功率谱（dB，峰值归一化 + 底噪钳位）
  - downsample             分块均值降采样（canvas 渲染前节流，避坑铁律"轻量 UI"）
  - Waterfall              滚动频谱行缓冲（deque 有界内存），下采样出 2D 图
  - next_spectrum_frame    从 AudioSource 读一帧 → 可 JSON 序列化的推送帧
  - synthetic_spectrum_audio  合成带内音（无真机时演示/测试用，诚实 degraded）

真机路径：IC-705 USB 声卡（device/ic705.Ic705UsbAudioSource）或未来 RTL-SDR
后端接入同一 AudioSource 协议；无真机时由 SimulatedSource 合成测试音兜底，
帧内 `degraded=true` 诚实标注，绝不冒充真机数据。

频率联动：帧的 `center_freq_hz` 来自调用方传入的电台当前 VFO（rsba1_adapter /
radio.CiVRadio.read_freq 同源），频谱横轴 = center + 相对偏移，切频即联动。
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Iterable

import numpy as np

# 支持的窗函数（归一化频谱显示用，非计量用途）
_WINDOWS = ("hann", "hamming", "blackman", "rect", "boxcar", "none")


def _window(n: int, name: str) -> np.ndarray:
    """返回长度 n 的窗系数；未知名抛 ValueError。"""
    key = str(name).strip().lower()
    if key in ("hann", "hanning"):
        return np.hanning(n)
    if key == "hamming":
        return np.hamming(n)
    if key == "blackman":
        return np.blackman(n)
    if key in ("rect", "boxcar", "none", ""):
        return np.ones(n, dtype=float)
    raise ValueError(f"不支持的窗函数 {name!r}，可选: {', '.join(_WINDOWS)}")


def compute_spectrum(
    samples: np.ndarray,
    sample_rate: float,
    fft_size: int = 1024,
    *,
    window: str = "hann",
    db_floor: float = -120.0,
) -> tuple[np.ndarray, np.ndarray]:
    """计算功率谱。

    参数:
        samples:     1D 实信号（声卡音频）或复信号（IQ 基带）。
        sample_rate: 采样率（Hz）。
        fft_size:    FFT 点数。取最近 fft_size 个样本，不足则零填充。
        window:      窗函数名（hann/hamming/blackman/rect）。
        db_floor:    dB 下界（底噪钳位），输出不会低于该值。

    返回:
        (freqs, db)：
          freqs — 相对中心频率的偏移（Hz）。复信号为 -sr/2..sr/2（全谱，
                  fftshift 后单调递增）；实信号为 0..sr/2（rfft 正半边）。
          db    — 归一化功率谱（峰值 0 dB，向下钳到 db_floor）。
    """
    x = np.asarray(samples)
    if x.size == 0:
        raise ValueError("空样本，无法计算频谱")
    if x.ndim != 1:
        raise ValueError(f"样本必须为一维，实际 ndim={x.ndim}")
    is_complex = bool(np.iscomplexobj(x))
    x = x.astype(complex) if is_complex else x.astype(float)

    n = int(fft_size)
    if n < 8:
        raise ValueError(f"fft_size 过小: {n}（需 >= 8）")
    if x.size > n:
        x = x[-n:]  # 取最近一段（实时性优先）
    elif x.size < n:
        x = np.pad(x, (0, n - x.size))

    w = _window(n, window)
    xw = x * w
    if is_complex:
        X = np.fft.fftshift(np.fft.fft(xw))
        freqs = np.fft.fftshift(np.fft.fftfreq(n, 1.0 / float(sample_rate)))
    else:
        X = np.fft.rfft(xw)
        freqs = np.fft.rfftfreq(n, 1.0 / float(sample_rate))

    power = np.abs(X) ** 2
    peak = float(power.max())
    if peak <= 0.0:
        db = np.full(power.shape, float(db_floor))
    else:
        # 峰值归一化：+eps 防 log(0)，结果 <= 0 dB
        db = 10.0 * np.log10(power / peak + 1e-12)
        db = np.clip(db, float(db_floor), 0.0)
    return freqs.astype(float), db.astype(float)


def downsample(values: np.ndarray, target: int) -> np.ndarray:
    """分块均值降采样到 target 个点（保峰 + 抗混叠，优于隔点抽取）。

    参数:
        values: 1D 数值数组（频谱或时间序列）。
        target: 目标点数（> 0）。不小于原长度时原样返回。

    返回:
        长度 = min(len(values), target) 的 float 数组。
    """
    values = np.asarray(values, dtype=float)
    target = int(target)
    if target <= 0:
        raise ValueError(f"target 必须 > 0，实际 {target}")
    n = values.size
    if n == 0:
        return np.zeros(0, dtype=float)
    if n <= target:
        return values.copy()
    edges = np.linspace(0, n, target + 1)
    out = np.empty(target, dtype=float)
    for i in range(target):
        lo = int(edges[i])
        hi = int(edges[i + 1])
        out[i] = values[lo:hi].mean() if hi > lo else values[min(lo, n - 1)]
    return out


class Waterfall:
    """滚动瀑布图缓冲（内存有界，最新行在底部）。

    每 push 一行频谱（dB），最多保留 height 行；frame() 输出下采样后的
    2D 数组（rows × cols），行不足时顶部以 db_floor 补空。
    """

    def __init__(self, height: int = 128, db_floor: float = -120.0) -> None:
        if height <= 0:
            raise ValueError(f"height 必须 > 0，实际 {height}")
        self.height = int(height)
        self.db_floor = float(db_floor)
        self._rows: deque[np.ndarray] = deque(maxlen=self.height)

    @property
    def count(self) -> int:
        return len(self._rows)

    def push(self, power_db_row: Iterable[float]) -> None:
        row = np.asarray(list(power_db_row), dtype=float)
        self._rows.append(row)

    def clear(self) -> None:
        self._rows.clear()

    def frame(self, *, cols: int = 256, rows: int | None = None) -> np.ndarray:
        """下采样出图。

        参数:
            cols: 频率轴目标列数（列下采样）。
            rows: 时间轴目标行数（默认 = height）。行不足时顶部补 db_floor。

        返回:
            shape=(rows, cols) 的 float 2D 数组（最新行在底部）。
        """
        cols = int(cols)
        if cols <= 0:
            raise ValueError(f"cols 必须 > 0，实际 {cols}")
        rows_out = self.height if rows is None else int(rows)
        if rows_out <= 0:
            raise ValueError(f"rows 必须 > 0，实际 {rows_out}")

        if not self._rows:
            return np.full((rows_out, cols), self.db_floor, dtype=float)

        recent = list(self._rows)[-rows_out:]
        down = [downsample(r, cols) for r in recent]
        if len(down) < rows_out:
            pad = rows_out - len(down)
            empty = np.full((pad, cols), self.db_floor, dtype=float)
            body = np.stack(down) if down else np.empty((0, cols), dtype=float)
            return np.vstack([empty, body])
        return np.stack(down)


def synthetic_spectrum_audio(sample_rate: float, n: int, *, seed: int = 1) -> np.ndarray:
    """合成一段实音频（若干带内音 + 弱底噪），用于无真机时的频谱展示/测试。

    带内音为相对中心频率的音频偏移（Hz），落在 0..sr/2 内，代表 HF 通联里
    的不同载波；振幅随偏移递减模拟真实通带。无真机时由 SimulatedSource 以
    本函数为 gen_fn 注入，帧内 degraded=true。
    """
    sr = float(sample_rate)
    n = int(n)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sr
    x = np.zeros(n, dtype=float)
    for off_hz, amp in ((500.0, 0.9), (1500.0, 0.55), (3200.0, 0.35), (7000.0, 0.18)):
        if off_hz < sr / 2.0:  # 高于 Nyquist 的偏移会被混叠，跳过
            x += amp * np.sin(2.0 * np.pi * off_hz * t)
    x += 0.02 * rng.standard_normal(n)
    peak = float(np.abs(x).max())
    if peak > 0.0:
        x = x / peak * 0.8  # 归一化到 [-0.8, 0.8]，留余量
    return x


def next_spectrum_frame(
    source: Any,
    center_freq_hz: float,
    *,
    fft_size: int = 2048,
    cols: int = 512,
    window: str = "hann",
    db_floor: float = -120.0,
) -> dict[str, Any]:
    """从 AudioSource 读一帧并组装可 JSON 序列化的频谱帧。

    参数:
        source:         AudioSource（须已 open）。read() 返回 AudioFrame。
        center_freq_hz: 当前 VFO 频率（Hz），决定频谱横轴绝对频率。
        fft_size/cols/window/db_floor: 见 compute_spectrum / downsample。

    返回:
        dict（WebSocket 推送帧）：
          type="spectrum", center_freq_hz, center_freq_mhz, sample_rate,
          fft_size, cols, freq_hz（绝对频率轴，已下采样）, spectrum_db
          （当前谱，已下采样）, source, degraded, timestamp。
    """
    frame = source.read(max_samples=fft_size * 4)
    sr = float(frame.sample_rate)
    freqs_off, db = compute_spectrum(
        frame.samples, sr, fft_size, window=window, db_floor=db_floor
    )
    center = float(center_freq_hz)
    freq_abs = center + freqs_off
    ds_freq = downsample(freq_abs, cols)
    ds_db = downsample(db, cols)
    return {
        "type": "spectrum",
        "center_freq_hz": int(round(center)),
        "center_freq_mhz": round(center / 1e6, 6),
        "sample_rate": sr,
        "fft_size": int(fft_size),
        "cols": int(cols),
        "freq_hz": [round(float(f), 1) for f in ds_freq],
        "spectrum_db": [round(float(v), 2) for v in ds_db],
        "source": getattr(source, "name", "unknown"),
        "degraded": getattr(source, "name", "unknown") == "sim",
        "timestamp": time.time(),
    }
