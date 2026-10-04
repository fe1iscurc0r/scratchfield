"""rsba1_adapter 铁锚集成测试——vendor/rsba1-core 纳入后全链路验证。

设计:
- 不真连电台: RadioLink/RemoteUty 后端用 fake (记录调用)。
- 保留真实协议逻辑: 复用 vendor/rsba1-core 的 civ_commands (parse_frame /
  assert_allowed_freq / AMATEUR_BANDS), 帧构造走真实 CI-V 格式。
- 覆盖: 直连六工具 / 白名单越界拒绝 / RemoteUty 兜底成功+禁用+不可用降级 /
  无包降级(人类可读错误) / close 幂等 / handle_handoff 未知工具。
"""
import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
import asyncio
import sys
import types
from pathlib import Path

import pytest

VENDOR_SRC = Path(__file__).resolve().parents[1] / "vendor" / "rsba1-core" / "src"
if str(VENDOR_SRC) not in sys.path:
    sys.path.insert(0, str(VENDOR_SRC))

from mcpserver.adapters.rsba1_adapter import adapter as rsba1_adapter

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeRadioLink:
    """模拟 RS-BA1 RadioLink 直连会话 (纯 socket 后端)。"""

    def __init__(self, host, user, pwd, verbose=False):
        self.host, self.user, self.pwd = host, user, pwd
        self.calls = []
        self._freq_hz = 7074000          # 7.074 MHz USB
        self._mode = (0x02, 1)           # USB, filter=1
        self._ptt_on = False
        self._smeter_raw = 200

    def open(self, retries=2):
        self.calls.append("open")

    def close(self):
        self.calls.append("close")

    def read_freq(self):
        return self._freq_hz

    def read_mode(self):
        return self._mode

    def set_freq(self, hz):
        self._freq_hz = hz
        self.calls.append(("set_freq", hz))

    def ptt(self, on):
        self._ptt_on = bool(on)
        self.calls.append(("ptt", on))

    def _civ_query(self, cmd, sub, timeout):
        # 标准 CI-V 帧: FE FE TO FR CMD SUBCMD DATA FD
        if cmd == bytes([0x1A, 0x03]):
            return bytes([0xFE, 0xFE, 0x00, 0xA4, 0x1A, 0x03, self._smeter_raw, 0xFD])
        if cmd == bytes([0x14, 0x0C]):
            return bytes([0xFE, 0xFE, 0x00, 0xA4, 0x14, 0x0C,
                          1 if self._ptt_on else 0, 0xFD])
        raise AssertionError(f"unexpected _civ_query: {cmd.hex()}")


class FakeSender:
    """模拟 RemoteUty Mailslot 发送器 (Windows fallback 后端)。"""

    def __init__(self, to_addr, from_addr, sub_cmd):
        self.to_addr, self.from_addr, self.sub_cmd = to_addr, from_addr, sub_cmd
        self.calls = []
        self._freq_hz = 7074000

    def open(self):
        self.calls.append("open")

    def close(self):
        self.calls.append("close")

    def query_freq(self, timeout_ms=2500):
        return self._freq_hz

    def query_mode(self, timeout_ms=2500):
        return (0x03, 1)                 # AM, filter=1

    def query_smeter(self, timeout_ms=2500):
        return 190

    def send_set_freq(self, hz):
        self._freq_hz = hz

    def send_ptt_on(self):
        self.calls.append("ptt_on")

    def send_ptt_off(self):
        self.calls.append("ptt_off")


fake_radio_link_mod = types.SimpleNamespace(RadioLink=FakeRadioLink)
fake_mailslot_mod = types.SimpleNamespace(CivViaExecCmdSender=FakeSender)


def _fake_import(module: str):
    """按模块名分发: radio_link/mailslot 走 fake, civ_commands 走真实实现。"""
    if module == "rsba1.radio_link":
        return fake_radio_link_mod
    if module == "rsba1.mailslot.civ_via_execcmd":
        return fake_mailslot_mod
    if module == "rsba1.ctypes_wrappers.civ_commands":
        import rsba1.ctypes_wrappers.civ_commands as civcmd
        return civcmd
    raise AssertionError(f"unexpected import: {module}")


@pytest.fixture
def bridge(monkeypatch):
    """直连成功路径 bridge (fake RadioLink + 真实 civ_commands)。"""
    monkeypatch.setattr(rsba1_adapter, "_import_rsba1", _fake_import)
    b = rsba1_adapter.Rsba1Ic705Bridge()
    assert b._try_radio_link() is True
    assert b._mode == "radio_link"
    return b


# ---------------------------------------------------------------------------
# RadioLink 直连成功路径 (六工具)
# ---------------------------------------------------------------------------

def test_read_freq_via_radio_link(bridge):
    r = bridge._read_freq()
    assert r["ok"] is True and r["freq_mhz"] == 7.074


def test_read_mode_via_radio_link(bridge):
    r = bridge._read_mode()
    assert r["ok"] is True and r["mode"] == "USB" and r["mode_code"] == 0x02


def test_read_smeter_via_radio_link(bridge):
    r = bridge._read_smeter()
    assert r["ok"] is True and r["s_raw"] == 200
    # raw=200 -> dBm=-127+200*(114/255)=-37.6 -> S9 之上 (over=3) -> S12
    assert r["s_unit"] == 12 and r["s_db"] == pytest.approx(-37.6, abs=0.1)


def test_set_freq_via_radio_link(bridge):
    r = bridge._set_freq(14.270)
    assert r["ok"] is True and r["freq_mhz"] == 14.27
    assert bridge._link.calls[-1] == ("set_freq", 14270000)


def test_ptt_via_radio_link(bridge):
    r = bridge._ptt("TX")
    assert r["ok"] is True and r["state"] == "TX"
    assert bridge._link.calls[-1] == ("ptt", True)
    r2 = bridge._ptt("RX")
    assert r2["ok"] is True and r2["state"] == "RX"


def test_ptt_invalid_state(bridge):
    r = bridge._ptt("MAYBE")
    assert r["ok"] is False and "必须是 TX/RX" in r["error"]


def test_get_status_via_radio_link(bridge):
    r = bridge._get_status()
    assert r["ok"] is True
    assert r["freq_mhz"] == 7.074 and r["mode"] == "USB"
    assert r["ptt"] == "RX"             # fake 初始 RX


# ---------------------------------------------------------------------------
# 业余频段白名单 (真实 assert_allowed_freq 逻辑)
# ---------------------------------------------------------------------------

def test_white_list_accept_amateur(bridge):
    r = bridge._set_freq(145.500)       # 2m 段
    assert r["ok"] is True and r["freq_mhz"] == 145.5


def test_white_list_reject_outside(bridge):
    r = bridge._set_freq(100.0)         # FM 广播段, 越界
    assert r["ok"] is False
    assert "白名单" in r["error"] or "业余频段" in r["error"]


def test_white_list_reject_via_handle_handoff(bridge):
    raw = asyncio.run(bridge.handle_handoff(
        {"tool_name": "ic705_set_freq", "params": {"freq_mhz": 500.0}}))
    assert '"status": "error"' in raw and "白名单" in raw


# ---------------------------------------------------------------------------
# RemoteUty 兜底
# ---------------------------------------------------------------------------

def test_remote_uty_fallback_success(monkeypatch):
    monkeypatch.setattr(rsba1_adapter, "_import_rsba1", _fake_import)
    monkeypatch.setattr(sys, "modules", {**sys.modules, "win32pipe": types.SimpleNamespace()})
    monkeypatch.setenv("RSBA1_ALLOW_REMOTE_UTY", "1")
    b = rsba1_adapter.Rsba1Ic705Bridge()
    # RadioLink 直连失败 -> 兜底
    monkeypatch.setattr(b, "_try_radio_link", lambda: False)
    assert b._try_remote_uty() is True
    assert b._mode == "remote_uty"
    r = b._read_freq()
    assert r["ok"] is True and r["freq_mhz"] == 7.074


def test_remote_uty_disabled_by_env(monkeypatch):
    monkeypatch.setattr(rsba1_adapter, "_import_rsba1", _fake_import)
    monkeypatch.setenv("RSBA1_ALLOW_REMOTE_UTY", "0")
    b = rsba1_adapter.Rsba1Ic705Bridge()
    monkeypatch.setattr(b, "_try_radio_link", lambda: False)
    assert b._try_remote_uty() is False


def test_no_silent_failure_when_both_paths_down(monkeypatch):
    """两路都失败必须抛人类可读错误, 绝不静默空返回。"""
    monkeypatch.setattr(rsba1_adapter, "_import_rsba1", _fake_import)
    # 显式禁用兜底（本机装有 pywin32 时 delenv 会走兜底成功路径，测试不具确定性）
    monkeypatch.setenv("RSBA1_ALLOW_REMOTE_UTY", "0")
    b = rsba1_adapter.Rsba1Ic705Bridge()
    monkeypatch.setattr(b, "_try_radio_link", lambda: False)
    with pytest.raises(RuntimeError, match="IC-705 连接不可用"):
        b.ensure()


# ---------------------------------------------------------------------------
# 无包降级 / close 幂等 / handoff
# ---------------------------------------------------------------------------

def test_no_package_human_error(monkeypatch):
    """rsba1 包缺失时给出"无法定位"人类可读错误。"""
    monkeypatch.setattr(rsba1_adapter, "_rsba1_found", lambda: False)
    with pytest.raises(RuntimeError, match="无法定位 rsba1 包"):
        rsba1_adapter._import_rsba1("rsba1.radio_link")


def test_close_idempotent():
    b = rsba1_adapter.Rsba1Ic705Bridge()   # mode=none
    b.close()                               # 不应抛
    assert b._mode == "none"


def test_handle_handoff_unknown_tool(bridge):
    raw = asyncio.run(bridge.handle_handoff({"tool_name": "ic705_self_destruct"}))
    assert '"status": "error"' in raw and "未知工具" in raw


def test_handle_handoff_missing_tool_name(bridge):
    raw = asyncio.run(bridge.handle_handoff({}))
    assert '"status": "error"' in raw and "缺少 tool_name" in raw
