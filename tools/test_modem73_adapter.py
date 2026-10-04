"""W58-04 验收测试：MODEM73 KISS TNC 适配器（≥4 用例）。

运行：python -m pytest tools/test_modem73_adapter.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from modem73_adapter import Modem73Adapter, modem73_available


def test_encode_decode_roundtrip():
    """encode_frame / decode_frame KISS 往返无损。"""
    a = Modem73Adapter(modem73_bin="/fake/modem73")  # 显式给二进制 → 非降级
    payload = b"\x01\x02\xC0\xDB\x03"
    frame = a.encode_frame(payload)
    port, back = a.decode_frame(frame)
    assert port == 0
    assert back == payload


def test_kiss_framing_semantics():
    """KISS 帧以 FEND 定界，载荷中的 FEND/FESC 被转义（与桥接脚本对齐）。"""
    a = Modem73Adapter(modem73_bin="/fake/modem73")
    frame = a.encode_frame(b"\xC0\xDB")
    assert frame[0] == 0xC0 and frame[-1] == 0xC0
    assert 0xC0 not in frame[1:-1]  # 载荷内 FEND 被转义


def test_mock_degradation_without_modem73():
    """无 modem73 二进制时 mock 降级（诚实降级显式断言）。"""
    a = Modem73Adapter()  # 不传二进制，按 PATH 检测（通常不存在）
    assert a.degraded is True
    assert a.status()["degraded"] is True
    assert "降级" in a.degraded_reason


def test_ptt_trigger_reflects_degradation():
    """降级态 PTT 返回 False；可用态 PTT 返回 True。"""
    degraded = Modem73Adapter()
    available = Modem73Adapter(modem73_bin="/fake/modem73")
    assert degraded.ptt_trigger() is False
    assert available.ptt_trigger() is True


def test_status_available_when_bin_given():
    """显式给二进制路径 → 视为可用，非降级。"""
    a = Modem73Adapter(modem73_bin="/fake/modem73")
    assert a.status()["available"] is True
    assert a.degraded is False
