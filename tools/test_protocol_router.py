"""R44 验收测试：轻量协议路由器（≥3× 字节压缩 + 任务成功率不降）。

运行：python -m pytest tools/test_protocol_router.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from protocol_router import ProtocolRouter, compression_ratio

router = ProtocolRouter()


def test_structured_roundtrip_lossless():
    msgs = [
        ("state_sync", {"node_id": 7, "freq_hz": 433_920_000, "seq": 1234}),
        ("spectrum_alloc", {"node_id": 7, "freq_hz": 433_920_000, "bandwidth_hz": 125_000}),
        ("power_ctrl", {"node_id": 7, "power_dbm": -10, "timeslot": 3}),
    ]
    for msg_type, fields in msgs:
        data = router.encode_structured(msg_type, **fields)
        got_type, got = router.decode_structured(data)
        assert got_type == msg_type
        assert got == fields


def test_compression_at_least_3x():
    msgs = [
        {"node_id": 7, "freq_hz": 433_920_000, "seq": 1234},
        {"node_id": 7, "freq_hz": 433_920_000, "bandwidth_hz": 125_000},
        {"node_id": 7, "power_dbm": -10, "timeslot": 3},
    ]
    for m in msgs:
        r = compression_ratio(m)
        assert r is not None and r >= 3.0, f"压缩率 {r} 低于 3×"


def test_natural_language_falls_back_losslessly():
    text = "频谱 433 附近有持续强干扰，请求把功率降到 -20dBm 并避让"
    r = router.route(text)
    assert r.format == "nl"
    assert r.msg_type is None
    assert router.decode_nl(r.payload) == text  # 语义无损


def test_fuzzy_dict_falls_back_to_nl():
    # 带未知字段的 dict → 不匹配任何 schema → 自然语言回退
    fuzzy = {"freq_hz": 433_000_000, "power_dbm": -10, "note": "先降功率再观察"}
    r = router.route(fuzzy)
    assert r.format == "nl"


def test_out_of_range_falls_back_to_nl():
    bad = {"node_id": 7, "power_dbm": -500, "timeslot": 3}  # power_dbm 超范围
    r = router.route(bad)
    assert r.format == "nl"


def test_mixed_batch_success_rate_100():
    """任务成功率不降：结构化无损往返 + 自然语言无损透传。"""
    batch = [
        {"node_id": 1, "freq_hz": 433_920_000, "seq": 1},
        {"node_id": 2, "freq_hz": 433_920_000, "bandwidth_hz": 250_000},
        {"node_id": 3, "power_dbm": -5, "timeslot": 9},
        "这个频点现在噪声很大，先别发了",
        {"freq_hz": 433_000_000, "note": "人工备注：待复核"},
    ]
    ok = 0
    for m in batch:
        r = router.route(m)
        if r.format == "binary":
            got_type, got = router.decode_structured(r.payload)
            ok += int(got_type is not None and got == m)
        else:
            ok += int(router.decode_nl(r.payload) == r.nl_text)
    assert ok == len(batch)


def test_nl_payload_has_fallback_marker():
    r = router.route("hello")
    assert r.payload[0] == 255


def test_decode_auto_dispatch_roundtrip():
    """route → decode 全自动往返（结构化 + 自然语言各覆盖）。"""
    structured = {"node_id": 7, "power_dbm": -10, "timeslot": 3}
    d = router.decode(router.route(structured).payload)
    assert d.format == "binary" and d.msg_type == "power_ctrl"
    assert d.fields == structured

    nl = "频谱 433 附近有持续强干扰，先避让"
    d2 = router.decode(router.route(nl).payload)
    assert d2.format == "nl" and d2.text == nl
