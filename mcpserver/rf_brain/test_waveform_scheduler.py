"""PF012 授粉落地验收测试：FIREQ 精密波形控制 → rf_brain 波形调度器。

覆盖：
  1. 确定性：同配置两次构建逐样本一致（FIREQ 确定性事件时序）
  2. 事件时序：起始时间戳精确累加、segment 切片正确
  3. 生成器正确性：tone 频率/FSK 频偏/chirp 扫频/SILENCE 零
  4. 依赖感知：depends_on 合法/非法、依赖根解析
  5. 流式频谱：帧数/形状/峰值频点/能量正确、空输入容错
  6. 参数校验：非法 duration/sample_rate/fft 参数报错
"""
from __future__ import annotations

import numpy as np
import pytest

from mcpserver.rf_brain.waveform_scheduler import (
    EventType,
    SpectrumFrame,
    StreamingSpectrum,
    WaveformEvent,
    WaveformScheduler,
)

SR = 1_000_000.0


def _tone_ev(dur: int = 1000, freq: float = 100e3, amp: float = 1.0,
             **kw) -> WaveformEvent:
    return WaveformEvent(EventType.TONE, dur, {"freq_hz": freq, "amplitude": amp,
                                               **kw})


class TestDeterminism:
    """FIREQ 核心：确定性事件时序。"""

    def test_rebuild_identical(self):
        sched = WaveformScheduler(SR)
        events = [
            _tone_ev(2000, 100e3),
            WaveformEvent(EventType.FSK, 4000, {"freq0": 100e3, "freq1": 110e3,
                                                "bit_rate": 2e4, "seed": 3,
                                                "amplitude": 1.0}),
            WaveformEvent(EventType.SILENCE, 500),
        ]
        a = sched.build(events)
        b = sched.build(events)
        assert np.array_equal(a.iq, b.iq)

    def test_same_seed_same_fsk(self):
        ev = {"freq0": 100e3, "freq1": 110e3, "bit_rate": 2e4, "seed": 7,
              "amplitude": 1.0}
        a = WaveformScheduler(SR).build([WaveformEvent(EventType.FSK, 2000, ev)])
        b = WaveformScheduler(SR).build([WaveformEvent(EventType.FSK, 2000, ev)])
        assert np.array_equal(a.iq, b.iq)

    def test_total_samples_accumulates(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([_tone_ev(1000), _tone_ev(2000), _tone_ev(3000)])
        assert schedule.total_samples == 6000
        assert schedule.starts == [0, 1000, 3000]


class TestEventTiming:
    def test_segment_slices(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([_tone_ev(1000, 100e3), _tone_ev(2000, 110e3)])
        seg0 = schedule.segment(0)
        seg1 = schedule.segment(1)
        assert seg0.shape == (1000,)
        assert seg1.shape == (2000,)
        # 两段拼接等于整体
        assert np.array_equal(np.concatenate([seg0, seg1]), schedule.iq)

    def test_marker_zero_duration_ok(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([
            WaveformEvent(EventType.MARKER, 500, {"tag": "sync"}),
            _tone_ev(1000, 100e3),
        ])
        assert schedule.total_samples == 1500
        assert schedule.segment(0).shape == (500,)


class TestGenerators:
    def test_tone_frequency(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([_tone_ev(4096, 100e3)])
        iq = schedule.iq
        # 瞬时频率（相位差分）应接近 100kHz
        phase = np.unwrap(np.angle(iq))
        inst_freq = np.diff(phase) / (2 * np.pi) * SR
        assert abs(np.median(inst_freq) - 100e3) < 1e3

    def test_tone_amplitude(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([_tone_ev(1000, 100e3, amp=0.7)])
        assert abs(np.abs(schedule.iq).max() - 0.7) < 1e-6

    def test_silence_is_zero(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([WaveformEvent(EventType.SILENCE, 1000)])
        assert np.all(schedule.iq == 0)

    def test_fsk_two_frequencies_present(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([
            WaveformEvent(EventType.FSK, 8000,
                          {"freq0": 100e3, "freq1": 120e3, "bit_rate": 5e3,
                           "seed": 1, "amplitude": 1.0}),
        ])
        phase = np.unwrap(np.angle(schedule.iq))
        inst = np.diff(phase) / (2 * np.pi) * SR
        # 两种频率都应出现（FSK 双态）
        uniq_freqs = np.unique(np.round(inst / 1e3)).astype(int)
        assert 100 in uniq_freqs
        assert 120 in uniq_freqs

    def test_chirp_sweeps(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([
            WaveformEvent(EventType.CHIRP, 4096,
                          {"f0": 90e3, "f1": 130e3, "amplitude": 1.0}),
        ])
        phase = np.unwrap(np.angle(schedule.iq))
        inst = np.diff(phase) / (2 * np.pi) * SR
        assert np.median(inst[:512]) < np.median(inst[-512:]), "chirp 应扫频上升"


class TestDependencyAwareConfig:
    """FIREQ 依赖感知配置：depends_on 校验 + 依赖根解析。"""

    def test_valid_dependency(self):
        events = [
            _tone_ev(1000),
            WaveformEvent(EventType.TONE, 1000, {"freq_hz": 110e3,
                                                 "amplitude": 1.0},
                          depends_on=0),
        ]
        sched = WaveformScheduler(SR)
        schedule = sched.build(events)
        assert schedule.total_samples == 2000

    def test_invalid_dependency(self):
        events = [
            _tone_ev(1000),
            WaveformEvent(EventType.TONE, 1000, {"freq_hz": 110e3,
                                                 "amplitude": 1.0},
                          depends_on=5),  # 指向不存在事件
        ]
        with pytest.raises(ValueError):
            WaveformScheduler(SR).build(events)

    def test_dependency_resolution(self):
        events = [
            _tone_ev(1000),
            WaveformEvent(EventType.TONE, 1000, {"freq_hz": 110e3,
                                                 "amplitude": 1.0},
                          depends_on=0),
            WaveformEvent(EventType.TONE, 1000, {"freq_hz": 120e3,
                                                 "amplitude": 1.0},
                          depends_on=1),
            _tone_ev(1000),
        ]
        roots = WaveformScheduler.dependency_resolution(events)
        assert roots == [-1, 0, 1, -1]

    def test_empty_dependency_roots(self):
        roots = WaveformScheduler.dependency_resolution([_tone_ev(10)])
        assert roots == [-1]


class TestStreamingSpectrum:
    """流式频谱读出（对应 FIREQ 流式传输）。"""

    def test_frames_count_and_shape(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([_tone_ev(4096, 100e3)])
        ss = StreamingSpectrum(SR, fft_size=256, hop=128)
        frames = ss.frames(schedule.iq)
        # (4096-256)/128 + 1 = 31
        assert len(frames) == 31
        assert all(isinstance(f, SpectrumFrame) for f in frames)
        assert frames[0].power_db.shape == (129,)  # 256//2+1

    def test_peak_freq_tone(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([_tone_ev(8192, 100e3)])
        agg = StreamingSpectrum(SR, fft_size=1024, hop=512).aggregate(schedule.iq)
        # 峰值频点应接近 100kHz（FFT bin 分辨率 ~977Hz）
        assert abs(agg["peak_freq_hz"] - 100e3) < 2e3

    def test_peak_freq_silence(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([WaveformEvent(EventType.SILENCE, 4096)])
        agg = StreamingSpectrum(SR, fft_size=256, hop=128).aggregate(schedule.iq)
        assert agg["total_energy"] == 0.0
        assert agg["n_frames"] == 31  # (4096-256)//128 + 1

    def test_short_input_empty(self):
        ss = StreamingSpectrum(SR, fft_size=256, hop=128)
        assert ss.frames(np.zeros(100)) == []
        agg = ss.aggregate(np.zeros(100))
        assert agg["n_frames"] == 0

    def test_frame_energy_positive(self):
        sched = WaveformScheduler(SR)
        schedule = sched.build([_tone_ev(1024, 100e3)])
        ss = StreamingSpectrum(SR, fft_size=256, hop=128)
        frames = ss.frames(schedule.iq)
        assert frames[0].total_energy > 0


class TestValidation:
    def test_invalid_duration(self):
        with pytest.raises(ValueError):
            WaveformEvent(EventType.TONE, 0, {"freq_hz": 100e3})

    def test_invalid_sample_rate(self):
        with pytest.raises(ValueError):
            WaveformScheduler(0)

    def test_invalid_fft_params(self):
        with pytest.raises(ValueError):
            StreamingSpectrum(SR, fft_size=0, hop=128)

    def test_empty_events(self):
        schedule = WaveformScheduler(SR).build([])
        assert schedule.total_samples == 0

    def test_unknown_event_type(self):
        with pytest.raises(KeyError):
            WaveformScheduler(SR).build([
                WaveformEvent("bogus", 100, {})])  # type: ignore[arg-type]
