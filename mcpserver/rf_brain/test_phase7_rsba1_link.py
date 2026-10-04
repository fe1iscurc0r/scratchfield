"""rf_brain Phase7 ↔ rsba1_adapter 联动契约测试（W79-02）。

覆盖：
  1. 业余频段白名单同闸门契约（device/amateur_bands ↔ vendored civ_commands 数值 + 功能一致）
  2. ic705_set_freq 越界拒绝走同一道闸门
  3. device_index 透传 pa.open（pyaudio mock）
  4. wavfile 校验失败关句柄（不泄漏）
  5. wave.Error → RuntimeError 人类可读包装
  6. sim 默认生成器按 duration_s/max_samples 契约截断
"""
from __future__ import annotations

import sys
import types
import wave
from unittest.mock import MagicMock

import numpy as np
import pytest

from mcpserver.adapters.rsba1_adapter import adapter
from mcpserver.rf_brain.amateur_bands import AMATEUR_BANDS, assert_allowed_freq
from mcpserver.rf_brain.device import create_source
from mcpserver.rf_brain.device import wavfile as wavfile_mod

# ---------------------------------------------------------------- 1. 同闸门契约

def test_amateur_bands_same_gate_as_rsba1():
    """rf_brain 副本与 vendored civ_commands 的 AMATEUR_BANDS 数值完全一致。"""
    civ = adapter._civmod()
    assert AMATEUR_BANDS == civ.AMATEUR_BANDS


def test_assert_allowed_freq_functional_parity():
    """两处闸门对同一边界集判定一致（拒绝 100MHz/433.92MHz，放行业余段）。"""
    civ = adapter._civmod()
    for bad in (100_000_000, 433_920_000, 1_000_000_000):
        with pytest.raises(ValueError):
            assert_allowed_freq(bad)
        with pytest.raises(ValueError):
            civ.assert_allowed_freq(bad)
    for good in (14_074_000, 50_100_000, 144_390_000):
        assert_allowed_freq(good)     # 不抛
        civ.assert_allowed_freq(good)  # 不抛


def test_ic705_set_freq_rejects_out_of_band_via_same_gate():
    """rsba1_adapter 的 ic705_set_freq 越界拒绝（与 rf_brain 同一道闸门）。"""
    bridge = adapter.Rsba1Ic705Bridge()
    out = bridge._set_freq(433.92)  # 非业余段（ISM 433）
    assert out["ok"] is False and "白名单" in out["error"]


# ---------------------------------------------------------------- 2. device_index 透传

def test_device_index_passed_to_pa_open(monkeypatch):
    """device_index 透传给 pyaudio 的 open(input_device_index=...)。"""
    fake_pa = types.ModuleType("pyaudio")
    fake_pa.paFloat32 = 1
    opened = {}

    class _PyAudio:
        def __init__(self):
            self.terminated = False

        def open(self, **kwargs):
            opened.update(kwargs)
            return MagicMock()

        def terminate(self):
            self.terminated = True

    fake_pa.PyAudio = _PyAudio
    monkeypatch.setitem(sys.modules, "pyaudio", fake_pa)

    from mcpserver.rf_brain.device import ic705
    pa, stream = ic705._lazy_pyaudio_stream(chunk=4096, rate=48000.0, device_index=3)
    assert opened["input_device_index"] == 3
    assert opened["rate"] == 48000


def test_device_index_none_omits_key(monkeypatch):
    """device_index=None 时不传 input_device_index（用系统默认设备）。"""
    fake_pa = types.ModuleType("pyaudio")
    fake_pa.paFloat32 = 1
    opened = {}

    class _PyAudio:
        def open(self, **kwargs):
            opened.update(kwargs)
            return MagicMock()

    fake_pa.PyAudio = _PyAudio
    monkeypatch.setitem(sys.modules, "pyaudio", fake_pa)

    from mcpserver.rf_brain.device import ic705
    ic705._lazy_pyaudio_stream(chunk=4096, rate=48000.0, device_index=None)
    assert "input_device_index" not in opened


# ---------------------------------------------------------------- 3. wavfile 关句柄

def test_wavfile_validation_failure_closes_handle(monkeypatch, tmp_path):
    """open 成功但校验失败（非 16-bit）→ 抛错且句柄已关闭。"""
    path = tmp_path / "fake.wav"
    path.write_bytes(b"\x00" * 64)  # 构造/校验只在 open 内触发，文件仅需存在

    fake_wf = MagicMock()
    fake_wf.getsampwidth.return_value = 4  # 不支持位宽 → 触发校验失败
    monkeypatch.setattr(wavfile_mod.wave, "open", lambda *a, **k: fake_wf)

    src = wavfile_mod.WavFileSource(path=path)
    with pytest.raises(RuntimeError, match="仅支持 16-bit"):
        src.open()
    fake_wf.close.assert_called_once()  # 校验失败必须关句柄


def test_wavfile_wave_error_wrapped_runtime_error(monkeypatch, tmp_path):
    """wave.Error → RuntimeError（人类可读包装，不泄漏底层异常）。"""
    path = tmp_path / "bad.wav"
    path.write_bytes(b"not a wav")

    def _raise(*a, **k):
        raise wave.Error("file does not start with RIFF id")

    monkeypatch.setattr(wavfile_mod.wave, "open", _raise)

    src = wavfile_mod.WavFileSource(path=path)
    with pytest.raises(RuntimeError, match="无法打开 WAV 文件"):
        src.open()


# ---------------------------------------------------------------- 4. sim 截断契约

def test_sim_default_read_truncated_to_n():
    """sim 默认 read() 不超 duration_s 契约帧长（DTMF 序列超长时按 _n 截断）。

    DTMF "12345" 在 48kHz 下约 28800 样本；duration_s=0.1 → _n=4800，超长部分
    必须被截断（_default_gen 的 x[:n] 契约）。"""
    with create_source("sim", sample_rate=48000.0, duration_s=0.1) as src:
        frame = src.read()
        assert frame.samples.size == 4800


def test_sim_read_respects_max_samples_contract():
    """sim read(max_samples) 单帧不超限且与 duration 契约取小。"""
    with create_source("sim", sample_rate=48000.0, duration_s=0.1) as src:
        frame = src.read(max_samples=500)
        assert frame.samples.size == 500
        frame2 = src.read(max_samples=10_000_000)  # 超过 _n → 截到 _n
        assert frame2.samples.size == 4800


def test_sim_default_generator_deterministic():
    """sim 默认生成器同 seed 同输出（按 n 截断后逐点一致）。"""
    with create_source("sim", sample_rate=48000.0, duration_s=0.1) as a, \
         create_source("sim", sample_rate=48000.0, duration_s=0.1) as b:
        fa, fb = a.read(), b.read()
        assert np.array_equal(fa.samples, fb.samples)
        assert fa.samples.size == 4800
