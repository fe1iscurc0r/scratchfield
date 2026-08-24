"""sdrtrunk sidecar（W-01）验收测试

覆盖:
1. schema：必填字段、协议/事件类型枚举、JSON 行解析（噪音容忍）
2. bridge：simulate 过桥全链路（音频 → 事件），live 模式 JVM 缺失报错清晰
3. adapter：显式注册接入解码链 + 未给 audio_path 跳过语义
4. 字段完整校验：validate_required_fields
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scratchpad/

from mcpserver.rf_brain.sdrtrunk_bridge import (  # noqa: E402
    REQUIRED_FIELDS,
    SUPPORTED_PROTOCOLS,
    SdrtrunkBridge,
    SdrtrunkBridgeError,
    SdrtrunkEvent,
    parse_json_line,
    simulate_decode,
    validate_event,
    validate_required_fields,
)


def _make_wav(path: Path, *, duration_s: float = 0.2, seed: int = 1) -> Path:
    rng = np.random.default_rng(seed)
    n = int(48000 * duration_s)
    s = 0.3 * rng.standard_normal(n)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes((s * 32767).astype("<i2").tobytes())
    return path


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #

def test_required_fields_are_expected_set():
    assert set(REQUIRED_FIELDS) == {
        "schema", "version", "source", "ts", "protocol", "event_type",
        "frequency_hz", "talkgroup", "from_radio", "to_alias", "details", "payload",
    }


def test_validate_event_ok_and_missing():
    ok, err = validate_event(SdrtrunkEvent(
        protocol="P25P1", event_type="call_start", frequency_hz=855_000_000,
        ts="2026-08-23T00:00:00Z").to_dict())
    assert ok and err == "ok"

    bad = {"protocol": "P25P1", "event_type": "call_start"}
    ok, err = validate_event(bad)
    assert not ok and "缺失字段" in err


def test_validate_event_rejects_bad_protocol_and_type():
    ok, err = validate_event(SdrtrunkEvent(
        protocol="WIFI", event_type="call_start", frequency_hz=1,
        ts="t").to_dict())
    assert not ok and "未知协议" in err
    ok, err = validate_event(SdrtrunkEvent(
        protocol="DMR", event_type="nonsense", frequency_hz=1,
        ts="t").to_dict())
    assert not ok and "未知事件类型" in err


def test_parse_json_line_roundtrip_and_noise():
    ev = SdrtrunkEvent(protocol="DMR", event_type="message", frequency_hz=461_000_000,
                       ts="2026-08-23T00:00:00Z", talkgroup=9, details="hello")
    parsed = parse_json_line(ev.to_json())
    assert parsed is not None
    assert parsed.protocol == "DMR" and parsed.talkgroup == 9
    assert parse_json_line("not json at all") is None
    assert parse_json_line('{"foo": 1}') is None


# --------------------------------------------------------------------------- #
# bridge（simulate）
# --------------------------------------------------------------------------- #

def test_simulate_decode_emits_p25_events(tmp_path):
    wav = _make_wav(tmp_path / "a.wav")
    events = simulate_decode(wav)
    assert len(events) == 3
    assert {e.event_type for e in events} == {"call_start", "frame", "call_end"}
    assert {e.protocol for e in events} == {"P25P1"}
    ok, missing = validate_required_fields(events)
    assert ok, missing


def test_bridge_simulate_decode_all(tmp_path):
    wav = _make_wav(tmp_path / "b.wav")
    bridge = SdrtrunkBridge(mode="simulate", audio_path=wav)
    events = bridge.decode_all()
    assert len(events) == 3
    assert all(e.protocol in SUPPORTED_PROTOCOLS for e in events)


def test_bridge_simulate_requires_audio(tmp_path):
    bridge = SdrtrunkBridge(mode="simulate", audio_path=tmp_path / "missing.wav")
    try:
        bridge.decode_all()
        assert False, "应抛 SdrtrunkBridgeError"
    except SdrtrunkBridgeError as e:
        assert "WAV" in str(e)


def test_bridge_live_reports_jvm_prerequisite():
    # live 模式无 jar → 明确报 JVM 前提错误（不硬做）
    bridge = SdrtrunkBridge(mode="live", java_bin="java", sdrtrunk_jar=None)
    try:
        bridge.decode_all()
        assert False, "应抛 SdrtrunkBridgeError"
    except SdrtrunkBridgeError as e:
        assert "JVM" in str(e) or "sdrtrunk_jar" in str(e)


# --------------------------------------------------------------------------- #
# adapter（显式注册接入解码链）
# --------------------------------------------------------------------------- #

def test_adapter_skips_without_audio_path():
    from mcpserver.rf_brain.sdrtrunk_bridge.adapter import decode_sdrtrunk
    r = decode_sdrtrunk(np.zeros(64, complex), 48000.0)
    assert not r.success and "跳过" in r.message


def test_adapter_registers_and_decodes_via_decode_all(tmp_path):
    from mcpserver.rf_brain.decoders import decode_all, list_decoders, unregister_decoder
    from mcpserver.rf_brain.sdrtrunk_bridge.adapter import register_sdrtrunk_decoder

    assert "sdrtrunk" not in list_decoders()  # 默认不注册，保持既有集合
    register_sdrtrunk_decoder()
    assert "sdrtrunk" in list_decoders()
    try:
        wav = _make_wav(tmp_path / "c.wav")
        results = decode_all(np.zeros(64, complex), 48000.0, audio_path=str(wav))
        r = [x for x in results if x.decoder == "sdrtrunk"][0]
        assert r.success, r.message
        assert r.payload["n_events"] == 3
        assert all({"protocol", "event_type", "frequency_hz", "ts"} <= set(e)
                   for e in r.payload["events"])
    finally:
        # 注销动态注册的解码器，避免污染全局注册表（P6 四解码器集合断言）
        assert unregister_decoder("sdrtrunk")
        assert "sdrtrunk" not in list_decoders()


if __name__ == "__main__":
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="sdrtrunk_bridge_test_"))
    test_required_fields_are_expected_set()
    test_validate_event_ok_and_missing()
    test_validate_event_rejects_bad_protocol_and_type()
    test_parse_json_line_roundtrip_and_noise()
    test_simulate_decode_emits_p25_events(tmp)
    test_bridge_simulate_decode_all(tmp)
    test_bridge_simulate_requires_audio(tmp)
    test_bridge_live_reports_jvm_prerequisite()
    test_adapter_skips_without_audio_path()
    test_adapter_registers_and_decodes_via_decode_all(tmp)
    print("\n🎉 sdrtrunk sidecar 验收测试全部通过")
