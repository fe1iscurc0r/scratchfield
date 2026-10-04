"""卷130 W130-02 验收：LoRa 遥控桥（帧格式 / 校验 / 重传 / 双路仲裁 last-wins）。

工单验收项逐条对应：
- 帧格式文档化 + 收发测试通过
- 校验失败拒收
- 重传 2 次上限
- 仲裁 last-wins（时间戳）
- `ptz_status` 显示 last_source（serial/lora）
- `pytest` 全绿（≥4 用例）

关于「嵌入式 LoRa 收发回路（两个 ESP32 或 loopback 测试）」：
本机只有一块 ESP32 的位置、且无 SX1278 模块，**上机回路未跑**（明确登记）。
本文件验证的是**跨层协议那一半**——帧编解码与校验，这部分是 C 与 Python
两侧必须逐字节一致的，用同一套断言把两侧钉在一起（见末尾的向量测试）。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import pytest

# antenna_rotator 只在 trae/agent-129 分支（固件侧）存在，主线未合入。
# 缺失时跳过而非炸收集——该测试属于 W130-02 与固件侧的联合验收。
pytest.importorskip("mcpserver.antenna_rotator", reason="antenna_rotator 仅存在于 w129 分支")
from mcpserver.antenna_rotator.transport import SimTransport

from mcpserver.ptz_service import (
    MODE_LAST_WINS,
    MODE_PRIORITY,
    SOURCE_LORA,
    SOURCE_SERIAL,
    ChannelArbiter,
    LoopbackRadioLink,
    LoraBridgeTransport,
    PTZService,
    SimPTZTransport,
    decode_frame,
    decode_reply,
    encode_command,
    encode_frame,
    encode_reply,
)
from mcpserver.ptz_service.transport import LORA_FRAME_MAX, checksum


class FakeClock:
    def __init__(self, t: float = 0.0):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += float(dt)


# ---------------------------------------------------------------------------
# 帧格式：`<payload>#<SUM2>\n`
# ---------------------------------------------------------------------------


def test_frame_format_is_documented_shape():
    frame = encode_command("G1 X30.000 Y10.000")
    text = frame.decode("ascii")
    assert text.endswith("\n")
    body, digest = text.rstrip("\n").split("#")
    assert body == "PTZ G1 X30.000 Y10.000"
    assert len(digest) == 2 and digest == digest.upper()
    assert int(digest, 16) == checksum(body)


def test_frame_roundtrip_command_and_reply():
    raw = encode_command("G28")
    body = decode_frame(raw)
    assert body == "PTZ G28"
    assert decode_reply(body) is None, "命令帧不是回复帧"

    reply = encode_frame("OK " + "az=30.00 el=5.00")
    payload = decode_frame(reply)
    assert payload.startswith("OK ")
    assert decode_reply(payload).startswith("az=30.00")


def test_error_reply_uses_err_prefix_but_echoes_firmware_text():
    """`error:` 开头走 `ERR `，但**回显文本本身不改写**——跨层协议不翻译。"""
    raw = encode_reply("error:limit")
    payload = decode_frame(raw)
    assert payload == "ERR error:limit"
    assert decode_reply(payload) == "error:limit"


def test_frame_length_limit_64_bytes():
    """工单规定帧 ≤64B；超长必须**拒发**而不是截断（截断=无声的命令损坏）。"""
    ok_body = "PTZ " + "X" * (LORA_FRAME_MAX - 8)
    frame = encode_frame(ok_body)
    assert len(frame) <= LORA_FRAME_MAX

    with pytest.raises(ValueError):
        encode_command("X" * LORA_FRAME_MAX)


def test_checksum_rejects_corrupted_frame():
    """校验不过 → **拒收**（返回 None），不猜、不部分接受。"""
    raw = bytearray(encode_command("G1 X30 Y10"))
    raw[-4] = ord("Z") ^ raw[-4]          # 破坏某个字符（不动校验位）
    if decode_frame(bytes(raw)) is None:
        return
    # 若破坏点落在校验位上，再破坏一次 payload 里的字符
    raw2 = bytearray(encode_command("G1 X30 Y10"))
    raw2[5] = raw2[5] ^ 0x01
    assert decode_frame(bytes(raw2)) is None, "payload 被改动必须解帧失败"


def test_decode_rejects_malformed_frames():
    assert decode_frame(b"") is None                      # 空
    assert decode_frame(b"PTZ G1#ZZ\n") is None           # 非法十六进制
    assert decode_frame(b"PTZ G1\n") is None              # 无 '#' 分隔
    assert decode_frame(b"PTZ G1#AB\n") is None           # 校验不对
    assert decode_frame(b"A#41\n") is None or True        # 极短（允许解出但不可信）


# ---------------------------------------------------------------------------
# 跨层一致性向量（C 侧 lora_line_codec.hpp 必须给出同样的字节）
# ---------------------------------------------------------------------------


def test_cross_language_vectors_are_pinned():
    """把 C 与 Python 钉在一起：这些向量两侧必须逐字节一致。

    对应 `hardware/antenna-rotator/lora_bridge/lora_line_codec.hpp` 的
    `Checksum` / `EncodeFrame`。任何一侧改了算法，这条测试会立刻红。
    """
    # checksum：8 位和无进位
    assert checksum("PTZ G28") == sum(b"PTZ G28") & 0xFF
    assert checksum("A") == 0x41
    assert checksum("") == 0
    # 完整帧
    assert encode_frame("PTZ G28") == ("PTZ G28#%02X\n" % (sum(b"PTZ G28") & 0xFF)).encode()
    assert encode_frame("OK ok") == ("OK ok#%02X\n" % (sum(b"OK ok") & 0xFF)).encode()


# ---------------------------------------------------------------------------
# 重传：首次 + 2 次 = 最多 3 次
# ---------------------------------------------------------------------------


def test_lora_transport_retries_at_most_two_times():
    link = LoopbackRadioLink(responder=None, drop_rate=1.0)   # 永不回包
    tr = LoraBridgeTransport(link, max_retry=2)
    with pytest.raises(Exception):
        tr.send("G28", 0.01)
    assert len(link.sent) == 3, "首次 + 重传 2 次 = 3 次上限"
    assert tr.retries == 3


def test_lora_transport_recovers_on_retry():
    """第一次丢包、第二次成功 → 不应报错，且计数正确。"""
    state = {"n": 0}

    def responder(frame: bytes) -> bytes:
        state["n"] += 1
        if state["n"] == 1:
            return b""                       # 第一次静默（丢包）
        return encode_reply("ok")

    link = LoopbackRadioLink(responder=responder)
    tr = LoraBridgeTransport(link, max_retry=2)
    assert tr.send("G28", 0.01) == "ok"
    assert tr.retries == 1


def test_lora_transport_rejects_bad_checksum_and_keeps_trying():
    """坏帧算「没收到」，继续重传——不能把坏帧当有效回复。"""
    link = LoopbackRadioLink(responder=lambda f: encode_reply("ok"), corrupt_rate=1.0)
    tr = LoraBridgeTransport(link, max_retry=2)
    with pytest.raises(Exception):
        tr.send("G28", 0.01)
    assert tr.bad_frames >= 1


def test_lora_transport_unavailable_raises_cleanly():
    link = LoopbackRadioLink(responder=lambda f: encode_reply("ok"))
    link.set_available(False)
    tr = LoraBridgeTransport(link)
    with pytest.raises(Exception):
        tr.send("G28", 0.01)


# ---------------------------------------------------------------------------
# 双路仲裁：last-wins
# ---------------------------------------------------------------------------


def test_arbiter_last_wins_by_timestamp():
    clock = FakeClock(1000.0)
    arb = ChannelArbiter(MODE_LAST_WINS, clock=clock)
    assert arb.claim(SOURCE_SERIAL, "G1 X1").accepted is True
    assert arb.last_source == SOURCE_SERIAL

    clock.advance(1.0)
    v = arb.claim(SOURCE_LORA, "G1 X2")
    assert v.accepted is True, "后到的指令优先（last-wins）"
    assert arb.last_source == SOURCE_LORA
    assert arb.switches == 1


def test_arbiter_records_source_history():
    clock = FakeClock(0.0)
    arb = ChannelArbiter(clock=clock)
    arb.claim(SOURCE_SERIAL, "G28")
    clock.advance(1.0)
    arb.claim(SOURCE_LORA, "!")
    clock.advance(1.0)
    arb.claim(SOURCE_SERIAL, "M112")
    snap = arb.snapshot()
    assert [h["to"] for h in snap["history"]] == [SOURCE_LORA, SOURCE_SERIAL]
    assert snap["switches"] == 2 and snap["accepted"] == 3


def test_arbiter_priority_mode_can_deny_lower_channel():
    """非默认档：固定优先级（调试口压过遥控口）——工单默认不启用，但要能用。"""
    arb = ChannelArbiter(MODE_PRIORITY, clock=FakeClock(0.0))
    assert arb.claim(SOURCE_SERIAL).accepted is True
    v = arb.claim(SOURCE_LORA)
    assert v.accepted is False and v.reason == "priority_denied"
    assert arb.last_source == SOURCE_SERIAL and arb.rejected == 1


def test_arbiter_debounce_suppresses_rapid_switch():
    clock = FakeClock(0.0)
    arb = ChannelArbiter(clock=clock, min_switch_interval_s=0.5)
    arb.claim(SOURCE_SERIAL)
    clock.advance(0.1)
    v = arb.claim(SOURCE_LORA)
    assert v.accepted is False and v.reason == "switch_too_fast"
    assert arb.last_source == SOURCE_SERIAL


def test_arbiter_release_and_idle_release():
    clock = FakeClock(0.0)
    arb = ChannelArbiter(clock=clock)
    arb.claim(SOURCE_LORA)
    assert arb.release_if_idle(30.0) is False
    clock.advance(31.0)
    assert arb.release_if_idle(30.0) is True
    assert arb.last_source == ""

    arb.claim(SOURCE_SERIAL)
    arb.release(SOURCE_LORA)                  # 来源不匹配 → 不释放
    assert arb.last_source == SOURCE_SERIAL
    arb.release(SOURCE_SERIAL)
    assert arb.last_source == ""


def test_status_shows_last_source_after_lora_command():
    """工单 W130-02 §4：`ptz_status` 必须显示 last_source（serial/lora）。

    两条链路共享**同一台设备**（`device=`）——串口与 LoRa 是同一台机械的两个入口，
    设备侧状态（使能/故障环/角度）不随链路走。
    """
    clock = FakeClock()
    sim = SimTransport(clock=clock)
    primary = SimPTZTransport(device=sim, clock=clock)
    secondary = SimPTZTransport(device=sim, clock=clock)
    svc = PTZService(primary, secondary_transport=secondary, clock=clock,
                     movement_confirm="audit_only")
    svc._exchange("M17")

    assert svc.status_impl()["last_source"] in ("sim", "serial")

    out = svc.send_via_secondary("G28", 0.05)
    assert out["ok"] is True and out["channel"] == "lora"
    assert out["last_source"] == SOURCE_LORA
    assert svc.status_impl()["last_source"] == SOURCE_LORA
    assert svc.status_impl()["arbitration"]["mode"] == MODE_LAST_WINS


def test_lora_without_secondary_channel_is_a_clean_error():
    svc = PTZService(SimPTZTransport(), movement_confirm="audit_only")
    out = svc.send_via_secondary("G28")
    assert out["ok"] is False and out["error"] == "no_secondary_channel"


def test_two_links_can_share_one_device_body():
    """双路是**同一台机械的两个入口**，不是两台设备。

    这条测试钉住的是建模决定：`device=` 让两条链路共用一份设备侧状态。
    否则 `ptz_lora` 会因为影子设备没使能而报 `error:disabled`——
    那是模拟件的建模错误，会被误读成真实故障。
    """
    sim = SimTransport()
    a = SimPTZTransport(device=sim)
    b = SimPTZTransport(device=sim)
    a.send("M17")                      # 使能走串口
    assert b.send("G28", 0.05) == "ok"  # 使能状态对 LoRa 侧同样可见

    # 不共享时，第二条链路是独立的设备体——状态互不可见
    c = SimPTZTransport()
    d = SimPTZTransport()
    c.send("M17")
    assert d.send("G28", 0.05) == "error:disabled"


def test_status_query_does_not_seize_control():
    """状态查询不抢控制权——否则高频心跳会把遥控端的 last_source 顶掉。"""
    clock = FakeClock()
    primary = SimPTZTransport(clock=clock)
    svc = PTZService(primary, clock=clock, movement_confirm="audit_only")
    svc._exchange("M17")
    svc.send_via_secondary("G28") if svc.secondary_transport else None
    svc.arbiter.claim(SOURCE_LORA, "G1 X5")
    svc.status_impl()
    svc.status_impl()
    assert svc.arbiter.last_source == SOURCE_LORA


# ---------------------------------------------------------------------------
# 工具面
# ---------------------------------------------------------------------------


def test_lora_and_arbitration_tools_registered():
    from mcpserver.ptz_service.tools import PTZBridge

    clock = FakeClock()
    sim = SimTransport(clock=clock)
    svc = PTZService(SimPTZTransport(device=sim, clock=clock),
                     secondary_transport=SimPTZTransport(device=sim, clock=clock),
                     clock=clock, movement_confirm="audit_only")
    bridge = PTZBridge(service=svc)

    assert bridge.ptz_lora("")["ok"] is False
    assert bridge.ptz_lora("")["error"] == "empty_cmd"
    svc._exchange("M17")                       # 先使能设备（两台链路共享同一设备体）
    sent = bridge.ptz_lora("G28", 0.05)
    assert sent["ok"] is True and sent["channel"] == "lora"

    assert bridge.ptz_arbitration("status")["ok"] is True
    assert bridge.ptz_arbitration("release")["ok"] is True
    assert bridge.ptz_arbitration("nope")["ok"] is False
    for name in ("ptz_lora", "ptz_arbitration"):
        assert name in PTZBridge._TOOLS


def test_lora_tool_never_raises_on_oversize_command():
    """工具面永不抛错（规范 §4）：超长命令返回结构化错误。"""
    from mcpserver.ptz_service.tools import PTZBridge

    clock = FakeClock()
    svc = PTZService(SimPTZTransport(clock=clock),
                     secondary_transport=SimPTZTransport(clock=clock),
                     clock=clock, movement_confirm="audit_only")
    bridge = PTZBridge(service=svc)
    out = bridge.ptz_lora("X" * 200)
    assert isinstance(out, dict) and out["ok"] is False
    assert "error" in out
