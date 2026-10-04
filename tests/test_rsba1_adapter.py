"""rsba1_adapter 集成测试（W79-01 · vendor 纳入后铁锚验收）。

覆盖：
  1. 懒加载链可用（vendor/rsba1-core/src 定位 + radio_link + civ_commands 可达）
  2. mock RadioLink 直连成功路径：六个 ic705_* 工具
  3. RemoteUty 兜底路径（直连失败 → 兜底成功）
  4. 双路失败 → 人类可读错误（绝不静默）
  5. 业余频段白名单越界拒绝（100 MHz / 1000 MHz）
  6. 无包降级（RSBA1_SRC_PATH 空目录 + find_spec 不可见）→ "无法定位 rsba1 包"
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import sys
import types
from unittest.mock import MagicMock

import pytest

from mcpserver.adapters.rsba1_adapter import adapter

# ---------------------------------------------------------------- 工具函数

def _frame(payload: bytes) -> bytes:
    """构造假 CI-V 帧（5 字节头 + payload + FD 尾），供 fake parse_frame 解包。"""
    return b"\xfe\xfe\x00\xa4\x1a" + payload + b"\xfd"


def _fake_radio_link_module(open_raises: Exception | None = None) -> types.ModuleType:
    """构造假的 rsba1.radio_link 模块（RadioLink 为 MagicMock 类）。"""
    mod = types.ModuleType("rsba1.radio_link")
    link_cls = MagicMock()
    link = MagicMock()
    link.read_freq.return_value = 14_074_000
    link.read_mode.return_value = (0x02, 0x01)          # USB + FIL1（对齐 civ_response.MODE_NAMES）
    link.set_freq.return_value = None
    link.ptt.return_value = None

    def _civ_query(cmd_bytes, resp_cmd, timeout):
        if bytes(cmd_bytes) == bytes([0x1A, 0x03]):     # S-meter 查询
            return _frame(b"\x03\x64")
        if bytes(cmd_bytes) == bytes([0x14, 0x0C]):     # PTT 状态查询 → RX
            return _frame(b"\x00")
        return _frame(b"\x03\x64")

    link._civ_query.side_effect = _civ_query
    if open_raises is not None:
        link.open.side_effect = open_raises
    link_cls.return_value = link
    mod.RadioLink = link_cls
    return mod


def _fake_civmod() -> types.ModuleType:
    """构造假的 civ_commands（parse_frame 从假帧里剥 payload）。"""
    mod = types.ModuleType("fake_civ_commands")

    def parse_frame(data):
        return (0xA4, 0x00, data[4], bytes(data[5:-1]))

    def assert_allowed_freq(hz):
        return None

    mod.parse_frame = parse_frame
    mod.assert_allowed_freq = assert_allowed_freq
    mod.AMATEUR_BANDS = (
        (1_800_000, 30_000_000), (50_000_000, 54_000_000), (144_000_000, 148_000_000),
    )
    return mod


@pytest.fixture()
def mock_link_env(monkeypatch):
    """mock RadioLink 直连成功 + 白名单断言透传（六工具可全跑）。"""
    monkeypatch.setattr(
        adapter, "_import_rsba1",
        lambda module="rsba1.radio_link": _fake_radio_link_module(),
    )
    monkeypatch.setattr(adapter, "_civmod", lambda: _fake_civmod())
    return adapter


# ---------------------------------------------------------------- 1. 懒加载链

def test_lazy_import_chain_available():
    """vendor 纳入后懒加载链完整：radio_link / civ_commands 均可达。"""
    rl = adapter._import_rsba1("rsba1.radio_link")
    assert rl.__name__ == "rsba1.radio_link"
    civ = adapter._civmod()
    assert hasattr(civ, "assert_allowed_freq")
    assert hasattr(civ, "AMATEUR_BANDS")


def test_bridge_import_no_dependency_bomb():
    """import 适配器本身绝不因缺依赖而炸（懒加载设计）。"""
    from mcpserver.adapters.rsba1_adapter.adapter import Rsba1Ic705Bridge  # noqa: F401


# ---------------------------------------------------------------- 2. mock 直连六工具

def test_six_tools_mock_radio_link(mock_link_env):
    bridge = adapter.Rsba1Ic705Bridge()

    freq = bridge._read_freq()
    assert freq["ok"] is True and freq["freq_mhz"] == 14.074

    mode = bridge._read_mode()
    assert mode["ok"] is True and mode["mode"] == "USB" and mode["mode_code"] == 0x02

    smeter = bridge._read_smeter()
    assert smeter["ok"] is True and smeter["s_raw"] == 0x64

    setf = bridge._set_freq(7.074)
    assert setf["ok"] is True and setf["freq_mhz"] == 7.074

    ptt = bridge._ptt("RX")
    assert ptt["ok"] is True and ptt["state"] == "RX"

    status = bridge._get_status()
    assert status["ok"] is True
    assert status["freq_mhz"] == 14.074 and status["mode"] == "USB"
    assert status["ptt"] == "RX"  # payload[-1]==0 → 未发射


# ---------------------------------------------------------------- 3. RemoteUty 兜底

def test_remote_uty_fallback_after_link_fail(monkeypatch):
    """直连失败 → RemoteUty 兜底成功（模拟 pywin32 可用）。"""
    class _AuthErr(Exception):
        pass

    sender = MagicMock()
    sender.query_freq.return_value = 7_074_000
    sender.query_mode.return_value = (0x02, 0x01)
    sender.query_smeter.return_value = 0x64
    sender.send_set_freq.return_value = None
    sender.send_ptt_on.return_value = None
    sender.send_ptt_off.return_value = None
    sender_cls = MagicMock(return_value=sender)

    def _fake_import(module="rsba1.radio_link"):
        if module == "rsba1.radio_link":
            return _fake_radio_link_module(open_raises=_AuthErr("登录认证失败"))
        mod = types.ModuleType(module)
        mod.CivViaExecCmdSender = sender_cls
        return mod

    monkeypatch.setattr(adapter, "_import_rsba1", _fake_import)
    monkeypatch.setattr(adapter, "_civmod", lambda: _fake_civmod())
    monkeypatch.setitem(sys.modules, "win32pipe", MagicMock())  # 模拟 pywin32 可用
    monkeypatch.setenv("RSBA1_ALLOW_REMOTE_UTY", "1")

    bridge = adapter.Rsba1Ic705Bridge()
    freq = bridge._read_freq()
    assert freq["ok"] is True and freq["freq_mhz"] == 7.074
    assert bridge._mode == "remote_uty"


# ---------------------------------------------------------------- 4. 双路失败人类可读

def test_both_paths_fail_human_readable(monkeypatch):
    """直连失败 + 兜底禁用 → {ok: False, error: 人类可读}，绝不静默。"""
    monkeypatch.setattr(
        adapter, "_import_rsba1",
        lambda module="rsba1.radio_link":
            _fake_radio_link_module(open_raises=RuntimeError("ConnectTrans 被拒")),
    )
    monkeypatch.setattr(adapter, "_civmod", lambda: _fake_civmod())
    monkeypatch.setenv("RSBA1_ALLOW_REMOTE_UTY", "0")  # 禁用兜底

    bridge = adapter.Rsba1Ic705Bridge()
    out = bridge._read_freq()
    assert out["ok"] is False
    assert "IC-705" in out["error"] and "连接不可用" in out["error"]


# ---------------------------------------------------------------- 5. 白名单越界

def test_whitelist_rejects_100mhz_and_1000mhz():
    """越界频率（100.0 / 1000.0 MHz）被真实 civ_commands 白名单拒绝（不 mock 闸门）。"""
    for bad in (100.0, 1000.0):
        out = adapter.Rsba1Ic705Bridge()._set_freq(bad)
        assert out["ok"] is False
        assert "白名单" in out["error"]


def test_whitelist_allows_in_band(mock_link_env):
    """业余段内（14.074 MHz）设置成功。"""
    bridge = adapter.Rsba1Ic705Bridge()
    out = bridge._set_freq(14.074)
    assert out["ok"] is True


# ---------------------------------------------------------------- 6. 无包降级

def test_no_package_human_readable(monkeypatch, tmp_path):
    """RSBA1_SRC_PATH 指向空目录 + find_spec 不可见 → "无法定位 rsba1 包"。"""
    monkeypatch.setenv("RSBA1_SRC_PATH", str(tmp_path))  # 空目录
    monkeypatch.setattr(
        adapter.importlib.util, "find_spec",
        lambda name, *a, **k: None,
    )
    with pytest.raises(RuntimeError, match="无法定位 rsba1 包"):
        adapter._import_rsba1("rsba1.radio_link")

    bridge = adapter.Rsba1Ic705Bridge()
    out = bridge._read_freq()
    assert out["ok"] is False and "无法定位 rsba1 包" in out["error"]
