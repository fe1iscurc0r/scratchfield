"""Phase 7 测试：IC-705 / SDR 输入抽象（device/）

验收（工单「rf_brain 全自动闭环 Phase7」）：
- provider 注册表：ic705 / wav / sim 三后端注册 + 工厂构造
- 依赖无关：无 pyaudio（本机未装）包可导入；无回调时 open 抛人类可读错误
- 频段白名单：携带射频频率的源过 amateur_bands 校验（与 rsba1_adapter 对齐）
- AudioFrame.to_iq：实音频 → 复基带（analytic signal 频谱正确）
- 全链路闭环：sim/WAV 音频 → to_iq → decoders.decode_all 解出 DTMF
"""
from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain import device  # noqa: F401  顶层不依赖 pyaudio
from mcpserver.rf_brain.amateur_bands import AMATEUR_BANDS
from mcpserver.rf_brain.decoders import aprs, decode_all, dtmf
from mcpserver.rf_brain.device.base import AudioFrame, AudioSource, iq_from_audio
from mcpserver.rf_brain.device.registry import create_source, list_sources
from mcpserver.rf_brain.loop import run_loop


# ---------------------------------------------------------------- 1. 注册表 + 工厂
def test_registry_has_three_sources():
    assert set(list_sources()) == {"ic705", "wav", "sim"}


def test_factory_constructs_all_kinds(tmp_path):
    wav = _write_dtmf_wav(tmp_path / "t.wav", "12", 8000.0)
    assert create_source("wav", path=wav) is not None
    assert create_source("sim") is not None
    assert create_source("ic705", capture_fn=lambda: np.zeros(8)) is not None


def test_factory_rejects_unknown_kind():
    with pytest.raises(KeyError):
        create_source("sdr")  # 未注册


def test_audio_source_is_abstract():
    with pytest.raises(TypeError):
        AudioSource()  # ABC 不可直接实例化


# ---------------------------------------------------------------- 2. WAV 回放
def _write_dtmf_wav(path: Path, digits: str, sample_rate: float = 8000.0) -> Path:
    """合成 DTMF 音频并写 16-bit PCM 单声道 WAV（标准库 wave）。"""
    iq = dtmf.encode_dtmf(digits, sample_rate=sample_rate, snr_db=30.0, seed=3)
    x = np.real(iq)
    x = x / (np.max(np.abs(x)) + 1e-12)
    pcm = (x * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())
    return path


def test_wavfile_source_reads_audio(tmp_path):
    wav = _write_dtmf_wav(tmp_path / "t.wav", "12345")
    src = create_source("wav", path=wav)
    with src as s:
        frame = s.read()
    assert isinstance(frame, AudioFrame)
    assert frame.samples.ndim == 1 and frame.samples.size > 0
    assert frame.sample_rate == 8000.0
    assert frame.samples.dtype == np.float64
    assert frame.center_freq_hz is None  # 不涉及射频


def test_wavfile_source_raises_stopiteration_at_eof(tmp_path):
    wav = _write_dtmf_wav(tmp_path / "t.wav", "1")
    with create_source("wav", path=wav) as src:
        src.read()
        with pytest.raises(StopIteration):
            src.read()  # EOF


def test_wavfile_whitelist_rejects_out_of_band(tmp_path):
    wav = _write_dtmf_wav(tmp_path / "t.wav", "1")
    with pytest.raises(ValueError):
        create_source("wav", path=wav, center_freq_hz=433_920_000)  # 非业余段


# ---------------------------------------------------------------- 3. 实音频 → IQ
def test_iq_from_audio_keeps_positive_sideband_only():
    """analytic signal：+1000Hz 分量保留，-1000Hz 分量清零。"""
    sr, n, f = 8000.0, 1024, 1000.0
    t = np.arange(n) / sr
    x = np.cos(2 * np.pi * f * t)  # 实信号 = 正负双边带
    iq = iq_from_audio(x, sr)
    spec = np.fft.fft(iq)
    pos = int(round(f / sr * n))
    neg = (-pos) % n
    assert abs(spec[pos]) > abs(spec[neg]) * 100, "正频应远强于负频"
    # 实部 ≈ 原信号，虚部 ≈ Hilbert 变换（相位差 π/2 的姊妹信号）
    assert np.allclose(np.real(iq), x, atol=1e-9)


def test_audioframe_to_iq_roundtrip():
    frame = AudioFrame(
        samples=np.sin(2 * np.pi * 697.0 * np.arange(800) / 8000.0),
        sample_rate=8000.0,
        center_freq_hz=144_850_000,
    )
    iq = frame.to_iq()
    assert iq.dtype == np.complex128
    assert iq.size == 800
    assert np.allclose(np.real(iq), frame.samples, atol=1e-9)
    assert frame.info()["center_freq_hz"] == 144_850_000


# ---------------------------------------------------------------- 4. IC-705 输入源
def test_ic705_whitelist_allows_2m():
    src = create_source("ic705", capture_fn=lambda: np.zeros(8),
                        center_freq_hz=144_850_000)
    assert src.center_freq_hz == 144_850_000


@pytest.mark.parametrize("bad", [433_920_000, 49_000_000, 131_500_000, 10_000])
def test_ic705_whitelist_rejects_out_of_band(bad):
    with pytest.raises(ValueError):
        create_source("ic705", capture_fn=lambda: np.zeros(8), center_freq_hz=bad)


def test_ic705_capture_callback_drives_read():
    """capture_fn 回调注入 → read() 包成 AudioFrame（依赖无关后端）。"""
    tone = np.sin(2 * np.pi * 1200.0 * np.arange(4800) / 48000.0)
    src = create_source("ic705", capture_fn=lambda: tone,
                        sample_rate=48000.0, center_freq_hz=145_800_000)
    with src as s:
        frame = s.read()
    assert frame.sample_rate == 48000.0
    assert frame.center_freq_hz == 145_800_000
    assert np.allclose(frame.samples, tone, atol=1e-9)
    assert frame.meta["source"] == "ic705"


def test_ic705_read_respects_max_samples():
    src = create_source("ic705", capture_fn=lambda: np.ones(1000),
                        sample_rate=48000.0)
    with src as s:
        frame = s.read(max_samples=256)
    assert frame.samples.size == 256


def test_ic705_open_without_pyaudio_raises_readable(monkeypatch):
    """无 pyaudio 且无 capture_fn → open 抛人类可读 RuntimeError（不静默）。"""
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "pyaudio":
            raise ImportError("No module named 'pyaudio'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    src = create_source("ic705")  # 无 capture_fn → 走 pyaudio 懒加载
    with pytest.raises(RuntimeError, match="pyaudio"):
        src.open()


def test_device_package_imports_without_pyaudio(monkeypatch):
    """依赖无关：拦截 pyaudio 导入失败，device 包仍可正常导入使用。"""
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "pyaudio":
            raise ImportError("No module named 'pyaudio'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    # 重载验证顶层无 pyaudio import
    import importlib

    import mcpserver.rf_brain.device as dev
    importlib.reload(dev)
    assert set(list_sources()) == {"ic705", "wav", "sim"}


# ---------------------------------------------------------------- 5. 全链路闭环
def test_full_chain_sim_to_decode_all():
    """仿真音频源 → to_iq → 解码器注册表 → DTMF 解码成功（真机链路替身）。"""
    with create_source("sim", digits="12345", sample_rate=8000.0,
                       duration_s=2.0, seed=1) as src:
        frame = src.read()
    iq = frame.to_iq()
    results = decode_all(iq, 8000.0)
    dtmf_res = next(r for r in results if r.decoder == "dtmf")
    assert dtmf_res.success, f"DTMF 解码失败: {dtmf_res.message}"
    assert dtmf_res.payload["digits"] == "12345"


def test_full_chain_loop_converges_to_protocol_leaf():
    """漏斗+树+叶子全链：run_loop 对 APRS 帧最终收敛到协议叶子（aprs）。

    调制层是玩具解调（demod_ref），AFSK1200 可能不收敛；协议层兜底探针
    （decoders 注册表）应独立命中 APRS——这是「树长叶子」的验收点：
    闭环产出从「调制方式」升级到「协议+内容」。
    """
    iq = aprs.encode_text_aprs("CQ TEST DE BG5GXO", snr_db=20, seed=3)
    r = run_loop(iq, sample_rate=48_000.0, center_freq=144_640_000)
    assert r.protocol == "aprs", f"协议叶子未命中: {r.history}"
    assert r.protocol_payload and "BG5GXO" in r.protocol_payload.get("text", "")


def test_full_chain_loop_no_protocol_on_toy_gfsk():
    """玩具 GFSK 合成信号：调制层收敛但协议探针不误报（protocol=None）。"""
    from mcpserver.rf_brain.sensor import generate_iq

    iq = generate_iq(modulation="GFSK", sample_rate=48_000.0,
                     center_freq=145_000_000, duration=0.02, snr_db=20, seed=3)
    r = run_loop(iq, sample_rate=48_000.0, center_freq=145_000_000)
    assert r.protocol is None, f"玩具信号不该命中协议: {r.protocol}"


def test_full_chain_wav_to_decode_all(tmp_path):
    """WAV 回放 → to_iq → 解码器注册表 → DTMF 解码成功（离线真机链路）。

    注：拨号串用无相邻重复键（"8246"）——DTMF 编码器 20ms 静音间隔 + 512
    样本滑动帧的固有特性会把相邻重复键合并（如 "88"→"8"），与 WAV 链路
    无关；本测试只验证输入抽象链路，DTMF 解码语义属 Phase6 已验收范围。
    """
    wav = _write_dtmf_wav(tmp_path / "phone.wav", "8246")
    with create_source("wav", path=wav) as src:
        frame = src.read()
    iq = frame.to_iq()
    results = decode_all(iq, frame.sample_rate)
    dtmf_res = next(r for r in results if r.decoder == "dtmf")
    assert dtmf_res.success
    assert dtmf_res.payload["digits"] == "8246"


# ---------------------------------------------------------------- 6. 白名单对齐哨兵
def test_amateur_bands_aligned_with_rsba1():
    """白名单数值与 rsba1_adapter（civ_commands.AMATEUR_BANDS）对齐。"""
    assert AMATEUR_BANDS == (
        (1_800_000, 30_000_000),
        (50_000_000, 54_000_000),
        (144_000_000, 148_000_000),
    )


# ---------------------------------------------------------------- 7. 契约回归（铁锚审查补）
def test_sim_whitelist_rejects_out_of_band():
    """sim 源越界频率构造同样被白名单拒绝（与 wav/ic705 同闸门）。"""
    with pytest.raises(ValueError):
        create_source("sim", center_freq_hz=433_920_000)  # 非业余段


def test_wav_read_respects_max_samples(tmp_path):
    """WAV read(max_samples) 单帧不超限。"""
    wav = _write_dtmf_wav(tmp_path / "clip.wav", "12345")  # 约 16000 样本
    with create_source("wav", path=wav) as src:
        frame = src.read(max_samples=256)
    assert frame.samples.size == 256


def test_sim_read_respects_max_samples():
    """sim read(max_samples) 契约：默认生成器不再忽略 n（M3 回归）。"""
    with create_source("sim", digits="12345", duration_s=2.0, seed=1) as src:
        frame = src.read(max_samples=256)
    assert frame.samples.size == 256  # 修复前会返回整帧 ~16000 样本


def test_sim_duration_s_governs_frame_len():
    """duration_s 对默认生成器生效（帧长 = sr * duration_s）。"""
    with create_source("sim", duration_s=0.5, sample_rate=8000.0, seed=1) as src:
        frame = src.read()
    assert frame.samples.size == 4000  # 8000 * 0.5


def test_ic705_capture_empty_frame_raises():
    """capture_fn 返回空帧 → 明确 RuntimeError（绝不静默空返回）。"""
    with create_source("ic705", capture_fn=lambda: np.zeros(0)) as src, pytest.raises(RuntimeError, match="空帧"):
        src.read()


def test_ic705_capture_nan_raises():
    """capture_fn 返回含 NaN 样本 → 明确 RuntimeError。"""
    with (
        create_source("ic705", capture_fn=lambda: np.array([0.1, np.nan])) as src,
        pytest.raises(RuntimeError, match="NaN"),
    ):
        src.read()


def test_sim_gen_empty_frame_raises():
    """gen_fn 返回空帧 → 明确 RuntimeError。"""
    with create_source("sim", gen_fn=lambda sr, n: np.zeros(0)) as src, pytest.raises(RuntimeError, match="空帧"):
        src.read()


def test_sim_gen_fn_respects_requested_n():
    """自定义 gen_fn 收到的 n 应为请求样本数（截断契约由源层保证）。"""
    seen = []

    def gen(sr, n):
        seen.append(n)
        return np.zeros(n)

    with create_source("sim", gen_fn=gen, duration_s=1.0, sample_rate=8000.0) as src:
        src.read(max_samples=128)
    assert seen == [128]
