"""sdrtrunk sidecar · W-01 验收脚本

验收链路（模拟音频文件过桥）：
1. 生成模拟 P25 语音 WAV 音频文件（C4FM 风格基带 + 能量包络）
2. SdrtrunkBridge(simulate) 过桥 → 解出 P25P1 帧 → 结构化 JSON 事件
3. grep/assert 断言必填字段完整 + 协议/事件类型合法

用法:
    python mcpserver/rf_brain/sdrtrunk_bridge/accept_sdrtrunk_bridge.py [输出JSON路径]

真机（live）模式前提: Java 21+ + sdrtrunk 发行包，见 README.md。
"""
from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # scratchpad/

from mcpserver.rf_brain.sdrtrunk_bridge import (  # noqa: E402
    SdrtrunkBridge,
    REQUIRED_FIELDS,
    validate_event,
    validate_required_fields,
)

_SAMPLE_RATE = 48000
_DURATION_S = 0.6  # 600ms → 30 个 20ms 语音帧


def make_p25_wav(path: Path, *, seed: int = 42) -> None:
    """合成模拟 P25P1 语音 WAV：C4FM 风格四电平基带 + 包络起伏。"""
    rng = np.random.default_rng(seed)
    n = int(_SAMPLE_RATE * _DURATION_S)
    # 四电平 C4FM 类基带（+3/+1/-1/-3），帧间有静音缝隙模拟 TDMA/语音活动检测
    symbols = rng.choice([-3, -1, 1, 3], size=n // 10)
    base = np.repeat(symbols, 10)
    base = base[:n]
    # 能量包络：每 20ms 一帧，模拟语音活动（P25 帧活动率 ~70%）
    frame_len = _SAMPLE_RATE // 50  # 20ms
    n_frames = n // frame_len
    active = (rng.random(n_frames) < 0.7).astype(float)
    env = np.repeat(active, frame_len)
    env = np.resize(env, n)
    samples = (0.35 * base + 0.02 * rng.standard_normal(n)) * env
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes((samples * 32767).astype("<i2").tobytes())


def main() -> int:
    root = Path(__file__).resolve().parent
    audio = root / "_fixture_p25_sim.wav"
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "accept_out.json"

    print(f"[1/3] 生成模拟 P25 音频: {audio.name} ({_DURATION_S}s @ {_SAMPLE_RATE}Hz)")
    make_p25_wav(audio)

    print(f"[2/3] SdrtrunkBridge(simulate) 过桥 {audio.name} → 结构化 JSON")
    bridge = SdrtrunkBridge(mode="simulate", audio_path=audio, sample_rate=_SAMPLE_RATE)
    events = bridge.decode_all()

    records = [ev.to_dict() for ev in events]
    out_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records),
        encoding="utf-8",
    )
    print(f"      事件 {len(records)} 条 → {out_path}")

    print(f"[3/3] grep/assert 断言字段完整")
    all_ok, missing = validate_required_fields(events)
    assert all_ok, f"必填字段缺失: {missing}"
    for i, ev in enumerate(events):
        ok, err = validate_event(ev.to_dict())
        assert ok, f"event#{i} 非法: {err}"
        for f in REQUIRED_FIELDS:
            assert f in ev.to_dict(), f"event#{i} 缺字段 {f}"

    protocols = {ev.protocol for ev in events}
    assert protocols == {"P25P1"}, protocols
    types = {ev.event_type for ev in events}
    assert {"call_start", "frame", "call_end"} <= types, types
    print(f"      ✅ {len(events)} 条事件全部字段完整 | 协议 {sorted(protocols)} | 类型 {sorted(types)}")
    print(f"      ✅ 结构化 JSON 已落盘: {out_path}")
    print("\n🎉 W-01 验收通过：模拟音频文件过桥 → P25P1 帧 → 结构化 JSON（字段完整）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
