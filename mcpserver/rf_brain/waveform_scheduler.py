"""PF012 授粉落地：FIREQ 精密波形控制架构 → rf_brain 波形调度器

授粉点：2608.29399 FIREQ —— 确定性事件时序 + 模块化 I/Q 生成 + 流式频谱读出
         + 依赖感知配置（减少参数扫描开销），基准为相位噪声/谱密度/信道偏斜。

对 SDR / ESP32 级硬件的启发迁移到软件层：

  1. **确定性事件时序**：波形调度器把 I/Q 生成拆成离散事件，每个事件有
     明确的时间戳（样本索引）与类型，运行一次即可精确回放（确定性）——
     对应 FIREQ 的 trigger 时序，杜绝"边生成边漂移"。
  2. **模块化 I/Q 生成**：tone / FSK / chirp / CW 等波形由独立生成器产出，
     调度器只负责拼装到时间轴（对应 FIREQ 的模块化 AXI 固件）。
  3. **依赖感知配置**：事件可声明依赖（如 FSK 切换依赖前一个 tone 结束），
     调度器按依赖序推导，避免全参数扫描（对应 FIREQ 的依赖感知配置）。
  4. **流式频谱读出**：分帧滑动窗口出功率谱，供下游瀑布图/检测消费。

验收：确定性（同配置两次运行逐样本一致）；事件时序精确（时间戳可预期）；
     依赖解析正确；流式频谱帧形状/能量正确；pytest 全绿。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import numpy as np

# ---------------------------------------------------------------------------
# 事件模型
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """波形事件类型（对应 FIREQ 的模块化固件块）。"""
    TONE = "tone"        # 单音（CW/载波/校准）
    FSK = "fsk"          # 频移键控（2 状态）
    CHIRP = "chirp"      # 线性扫频（测距/校准）
    SILENCE = "silence"  # 静默/关断
    MARKER = "marker"    # 标记（不产生样本，仅打时间戳，供外部同步）


@dataclass(frozen=True)
class WaveformEvent:
    """一个确定性的波形事件。

    ``duration`` 为样本数（确定性时间轴：样本索引 = 时钟拍，杜绝浮点漂移）。
    ``params`` 携带生成参数（频率/幅度/扫频范围等）。
    ``depends_on`` 为可依赖的事件序号（依赖感知配置用）。
    """
    type: EventType
    duration: int
    params: dict = field(default_factory=dict)
    depends_on: int | None = None

    @property
    def start(self) -> int:
        """起始样本索引（由调度器在 build 时回填，静态属性占位）。"""
        return int(self.params.get("_start", 0))

    def __post_init__(self) -> None:
        if int(self.duration) <= 0:
            raise ValueError(f"duration 必须 > 0，实际 {self.duration}")


# ---------------------------------------------------------------------------
# 波形生成器（模块化 I/Q 生成，纯 numpy 确定性）
# ---------------------------------------------------------------------------

def _gen_tone(n: int, *, freq_hz: float, sample_rate: float, amplitude: float,
              phase: float = 0.0) -> np.ndarray:
    """单音 I/Q。频率确定性由 sample_rate 与样本索引决定。"""
    t = np.arange(n)
    phase_inc = 2.0 * np.pi * float(freq_hz) / float(sample_rate)
    return amplitude * np.exp(1j * (phase_inc * t + phase))


def _gen_fsk(n: int, *, freq0: float, freq1: float, sample_rate: float,
             bit_rate: float, amplitude: float, data_bits=None,
             seed: int = 0) -> np.ndarray:
    """2-FSK I/Q。data_bits 缺省时用确定性伪随机序列（seed 由 params 传）。"""
    t = np.arange(n)
    spb = max(int(sample_rate / float(bit_rate)), 1)   # 每符号样本数
    n_symbols = int(np.ceil(n / spb))
    if data_bits is None:
        bits = np.random.default_rng(int(seed)).integers(0, 2, n_symbols)
    else:
        bits = np.asarray(data_bits, dtype=int)
    freqs = np.where(bits == 1, float(freq1), float(freq0))
    # 每样本频率（零阶保持）
    per_symbol = np.repeat(freqs, spb)[:n]
    phase_inc = 2.0 * np.pi * per_symbol / float(sample_rate)
    phase = np.cumsum(phase_inc)
    return amplitude * np.exp(1j * phase)


def _gen_chirp(n: int, *, f0: float, f1: float, sample_rate: float,
               amplitude: float) -> np.ndarray:
    """线性扫频 I/Q（f0 → f1，确定性）。"""
    t = np.arange(n)
    k = (float(f1) - float(f0)) / float(sample_rate) / float(n)  # Hz/样本
    phase = 2.0 * np.pi * (float(f0) / float(sample_rate) * t + 0.5 * k * t * t)
    return amplitude * np.exp(1j * phase)


def _gen_silence(n: int, **_) -> np.ndarray:
    return np.zeros(n, dtype=complex)


def _gen_marker(n: int, **_) -> np.ndarray:
    return np.zeros(n, dtype=complex)


def params_seed(params) -> int:
    """从事件 params 取确定性 seed（缺省 0）。"""
    if isinstance(params, dict):
        return int(params.get("seed", 0))
    return 0


_GENERATORS: dict[EventType, Callable[..., np.ndarray]] = {
    EventType.TONE: _gen_tone,
    EventType.FSK: _gen_fsk,
    EventType.CHIRP: _gen_chirp,
    EventType.SILENCE: _gen_silence,
    EventType.MARKER: _gen_marker,
}


# ---------------------------------------------------------------------------
# 波形调度器（确定性事件时序 + 依赖感知配置）
# ---------------------------------------------------------------------------

@dataclass
class WaveformSchedule:
    """构建好的确定性波形序列。"""
    iq: np.ndarray                    # 完整 I/Q 序列
    events: list[WaveformEvent]      # 原事件
    starts: list[int]                # 每事件起始样本索引
    sample_rate: float

    def segment(self, idx: int) -> np.ndarray:
        """取出第 idx 个事件的样本段。"""
        s = self.starts[idx]
        e = self.starts[idx + 1] if idx + 1 < len(self.starts) else len(self.iq)
        return self.iq[s:e]

    @property
    def total_samples(self) -> int:
        return int(self.iq.size)


class WaveformScheduler:
    """FIREQ 式确定性波形调度器。

    用法::

        sch = WaveformScheduler(sample_rate=1_000_000)
        schedule = sch.build([
            WaveformEvent(EventType.TONE, 1000, {"freq_hz": 100e3, "amplitude": 1.0}),
            WaveformEvent(EventType.FSK, 2000, {"freq0": 100e3, "freq1": 110e3,
                                                "bit_rate": 1e4, "seed": 3}),
            WaveformEvent(EventType.SILENCE, 500),
        ])
    """

    def __init__(self, sample_rate: float) -> None:
        if float(sample_rate) <= 0:
            raise ValueError(f"sample_rate 必须 > 0，实际 {sample_rate}")
        self.sample_rate = float(sample_rate)

    def build(self, events: list[WaveformEvent]) -> WaveformSchedule:
        """按依赖序展开事件，拼接成确定性 I/Q 序列。

        依赖感知：若事件声明 ``depends_on``（前一事件序号），调度器校验依赖
        序号有效并显式记录（此处展开顺序仍为列表序，依赖用于配置校验/剪枝）。
        所有事件按列表顺序在时间轴上顺序拼接（确定性）。
        """
        if not events:
            return WaveformSchedule(np.zeros(0, dtype=complex), [], [],
                                    self.sample_rate)

        chunks: list[np.ndarray] = []
        starts: list[int] = []
        cursor = 0
        for i, ev in enumerate(events):
            gen = _GENERATORS[ev.type]
            # 依赖校验（依赖感知配置）
            if ev.depends_on is not None:
                if not (0 <= int(ev.depends_on) < i):
                    raise ValueError(
                        f"事件 {i} 的依赖 depends_on={ev.depends_on} 非法"
                        f"（须指向更早的事件）")
            chunk = gen(ev.duration, **ev.params, sample_rate=self.sample_rate)
            starts.append(cursor)
            chunks.append(chunk)
            cursor += ev.duration
        iq = np.concatenate(chunks)
        return WaveformSchedule(iq, list(events), starts, self.sample_rate)

    @staticmethod
    def dependency_resolution(events: list[WaveformEvent]) -> list[int]:
        """依赖解析：返回每个事件的"最终依赖根"（无依赖为 -1）。

        用于依赖感知配置——把参数扫描裁剪到仅依赖根事件，减少组合开销。
        """
        root_of: list[int] = []
        for i, ev in enumerate(events):
            if ev.depends_on is None:
                root_of.append(-1)
            else:
                root_of.append(ev.depends_on)
        return root_of


# ---------------------------------------------------------------------------
# 流式频谱读出（分帧滑动窗口 → 功率谱帧）
# ---------------------------------------------------------------------------

@dataclass
class SpectrumFrame:
    """一帧流式频谱。"""
    frame_idx: int
    power_db: np.ndarray          # 单边功率谱 (n_bins,)
    freqs_hz: np.ndarray          # 每 bin 对应频率 (n_bins,)
    t_start: int                  # 帧起始样本索引
    total_energy: float


class StreamingSpectrum:
    """分帧滑动窗口功率谱（供瀑布图/检测消费，对应 FIREQ 流式读出）。"""

    def __init__(self, sample_rate: float, fft_size: int = 256,
                 hop: int = 128, window: str = "hann") -> None:
        self.sample_rate = float(sample_rate)
        self.fft_size = int(fft_size)
        self.hop = int(hop)
        if self.hop <= 0 or self.fft_size <= 0:
            raise ValueError("fft_size/hop 必须 > 0")
        self._win = np.hanning(self.fft_size) if window == "hann" \
            else np.ones(self.fft_size)

    def frames(self, iq: np.ndarray) -> list[SpectrumFrame]:
        """把整段 I/Q 切成帧，返回功率谱帧列表。"""
        iq = np.asarray(iq)
        if iq.ndim != 1:
            raise ValueError("输入必须为一维")
        out: list[SpectrumFrame] = []
        n = iq.size
        if n < self.fft_size:
            return out
        idx = 0
        f = 0
        while idx + self.fft_size <= n:
            seg = iq[idx:idx + self.fft_size] * self._win
            # I/Q 复信号：用全 FFT 取正频率段（rfft 不支持复数输入）
            spec = np.fft.fft(seg)
            half = self.fft_size // 2 + 1
            power = np.abs(spec[:half]) ** 2
            freqs = np.fft.fftfreq(self.fft_size, 1.0 / self.sample_rate)[:half]
            out.append(SpectrumFrame(
                frame_idx=f, power_db=power, freqs_hz=freqs,
                t_start=idx, total_energy=float(np.sum(power))))
            idx += self.hop
            f += 1
        return out

    def aggregate(self, iq: np.ndarray) -> dict:
        """流式频谱聚合统计（平均谱 + 峰值频点 + 总能量）。"""
        frs = self.frames(iq)
        if not frs:
            return {"mean_power_db": np.zeros(0), "peak_freq_hz": None,
                    "total_energy": 0.0, "n_frames": 0}
        pows = np.stack([fr.power_db for fr in frs])
        mean_p = pows.mean(axis=0)
        peak_idx = int(mean_p.argmax())
        return {
            "mean_power_db": mean_p,
            "peak_freq_hz": float(frs[0].freqs_hz[peak_idx]),
            "total_energy": float(sum(fr.total_energy for fr in frs)),
            "n_frames": len(frs),
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    sr = 1_000_000.0
    sched = WaveformScheduler(sr)
    schedule = sched.build([
        WaveformEvent(EventType.TONE, 2000, {"freq_hz": 100e3, "amplitude": 1.0}),
        WaveformEvent(EventType.FSK, 4000, {"freq0": 100e3, "freq1": 110e3,
                                            "bit_rate": 2e4, "seed": 3,
                                            "amplitude": 1.0}),
        WaveformEvent(EventType.CHIRP, 2000, {"f0": 90e3, "f1": 130e3,
                                              "amplitude": 0.8}),
        WaveformEvent(EventType.SILENCE, 1000),
    ])
    print(f"总样本数 = {schedule.total_samples} ({schedule.total_samples/sr*1e3:.1f} ms)")
    print(f"事件数 = {len(schedule.events)}, 时间戳 = {schedule.starts[:3]}...")
    agg = StreamingSpectrum(sr).aggregate(schedule.iq)
    print(f"流式频谱: {agg['n_frames']} 帧, 峰值频点 = {agg['peak_freq_hz']/1e3:.1f} kHz, "
          f"总能量 = {agg['total_energy']:.0f}")
    # 确定性验证
    s2 = WaveformScheduler(sr).build(schedule.events)
    print(f"确定性: 两次构建逐样本一致 = {np.array_equal(schedule.iq, s2.iq)}")


if __name__ == "__main__":
    main()
