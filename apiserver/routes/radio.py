"""X-01: IC-705 CI-V 串口控制面板 + HamLog 通联联动。

职责：
  - CI-V 串口直连（USB，区别于 rsba1_adapter 的 RS-BA1 网络协议）：调频率 / 读频率 /
    切模式 / PTT，pyserial 实现，COM 口可配，无真机时用内存 Mock 串口兜底。
  - 联动：通联完成一键进 HamLog（复用 mcpserver/adapters/hamlog_adapter 的 qso_add，
    自动填 callsign/mode/freq/时间，可补 RST/备注）。
  - QSL 卡债角标数据源（复用 hamlog_adapter.qsl_debts）。

CI-V 协议（Icom 公开标准，非 rsba1 私有）：
  - 帧：FE FE <to> <from> <cmd> [<sub>] [<data>] FD
  - IC-705 电台地址 0xA4；PC 控制器默认地址 0xE0。
  - 频率：0x03 读 / 0x05 写，数据 5 字节 BCD（10 位数字，LSB first，单位 Hz）。
  - 模式：0x04 读 / 0x06 写，模式码 0x01-0x09（LSB/USB/AM/CW/RTTY/FM/WFM/CW-R/RTTY-R）。
  - PTT：0x1C sub 0x00，data 0x00=RX / 0x01=TX；写命令成功应答 0xFB，失败 0xFA。

安全：设频率强制过业余频段白名单（1.8-30 / 50-54 / 144-148 MHz），越界拒绝——
与 rsba1_adapter / rf_brain.amateur_bands 同一道闸门，数值一致。

配置（环境变量）：
  IC705_PORT      COM 口，如 COM3；未设置或 "mock" → 内存 Mock 串口（默认）
  IC705_BAUDRATE  波特率，默认 19200（IC-705 CI-V 默认）
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..naga_auth import require_local_auth

router = APIRouter(prefix="/api/radio", tags=["radio"])
logger = logging.getLogger(__name__)

# ============ CI-V 协议常量（Icom 公开标准） ============

CIV_RADIO = 0xA4  # IC-705 电台地址
CIV_CTRL = 0xE0  # PC 控制器默认地址
_PREAMBLE = b"\xfe\xfe"
_EOM = 0xFD

CMD_READ_FREQ = 0x03
CMD_READ_MODE = 0x04
CMD_SET_FREQ = 0x05
CMD_SET_MODE = 0x06
CMD_PTT = 0x1C
CMD_READ_SMETER = 0x1A  # S 表（sub 0x03，返回 [0x03, raw 0-255]）
CMD_OK = 0xFB
CMD_NG = 0xFA

# IC-705 模式码 → 名称（与 rsba1_adapter.MODE_NAMES 一致）
MODE_NAMES: dict[int, str] = {
    0x01: "LSB", 0x02: "USB", 0x03: "AM", 0x04: "CW", 0x05: "RTTY",
    0x06: "FM", 0x07: "WFM", 0x08: "CW-R", 0x09: "RTTY-R",
}
MODE_CODES: dict[str, int] = {name: code for code, name in MODE_NAMES.items()}

# 业余频段白名单（闭区间 Hz，与 rf_brain.amateur_bands 数值一致）
AMATEUR_BANDS: tuple[tuple[int, int], ...] = (
    (1_800_000, 30_000_000),   # HF 160m - 10m
    (50_000_000, 54_000_000),  # 6m
    (144_000_000, 148_000_000),  # 2m
)

DEFAULT_MOCK_FREQ_HZ = 7_074_000  # 40m FT8 常用，落在白名单内
DEFAULT_MOCK_MODE = 0x02  # USB


class RadioError(RuntimeError):
    """CI-V 串口控制失败统一异常（fail-fast，不静默空返回）。"""


# ============ 频率 BCD 编解码 ============


def encode_freq_bcd(hz: int) -> bytes:
    """10 位十进制频率 → 5 字节 BCD（LSB first，CI-V 标准）。

    例：7_074_000 Hz → 数字 "0007074000" → 高→低字节 0x00 0x07 0x07 0x40 0x00
    → LSB first 发送 0x00 0x40 0x07 0x07 0x00。
    """
    hz = int(hz)
    if not 0 <= hz <= 9_999_999_999:
        raise RadioError(f"频率 {hz} Hz 超出 CI-V 10 位 BCD 表示范围 (0 ~ 9.999999999 GHz)")
    digits = f"{hz:010d}"
    bcd = bytearray()
    for i in range(0, 10, 2):
        bcd.append((int(digits[i]) << 4) | int(digits[i + 1]))
    return bytes(bcd[::-1])  # 低位字节在前


def decode_freq_bcd(data: bytes) -> int:
    """5 字节 BCD（LSB first）→ 频率 Hz。"""
    if len(data) < 5:
        raise RadioError(f"频率 BCD 数据不足 5 字节: {bytes(data).hex()}")
    bcd = bytes(data[:5])[::-1]  # 转回高位字节在前
    hz = 0
    for byte in bcd:
        if (byte >> 4) > 9 or (byte & 0x0F) > 9:
            raise RadioError(f"非法 BCD 字节: 0x{byte:02x}")
        hz = hz * 100 + ((byte >> 4) * 10 + (byte & 0x0F))
    return hz


def assert_allowed_freq(hz: int) -> None:
    """断言频率在业余频段白名单内，否则抛 RadioError。"""
    hz = int(hz)
    if not any(lo <= hz <= hi for lo, hi in AMATEUR_BANDS):
        raise RadioError(
            f"频率 {hz} Hz 不在业余频段白名单内 (MHz 区间: "
            + ", ".join(f"{lo/1e6:.1f}-{hi/1e6:.1f}" for lo, hi in AMATEUR_BANDS)
            + ")"
        )


# ============ 帧构造 / 解析 ============


def build_frame(cmd: int, data: bytes = b"", sub: int | None = None) -> bytes:
    """构造控制器 → 电台的 CI-V 请求帧。"""
    body = bytearray([CIV_RADIO, CIV_CTRL, cmd])
    if sub is not None:
        body.append(sub)
    body.extend(data)
    return _PREAMBLE + bytes(body) + bytes([_EOM])


def build_response(cmd: int, data: bytes = b"") -> bytes:
    """构造电台 → 控制器的 CI-V 响应帧。"""
    return _PREAMBLE + bytes([CIV_CTRL, CIV_RADIO, cmd]) + data + bytes([_EOM])


def parse_frame(frame: bytes) -> tuple[int, int, int, bytes] | None:
    """解析 CI-V 帧 → (to_addr, from_addr, cmd, data)；帧不完整返回 None。"""
    if len(frame) < 5 or frame[:2] != _PREAMBLE or frame[-1] != _EOM:
        return None
    return frame[2], frame[3], frame[4], frame[5:-1]


# ============ 内存 Mock 串口（无真机兜底） ============


class MockSerial:
    """无真机的内存电台模拟，实现 pyserial 写/读子集（write/read/in_waiting）。

    收到 CI-V 命令后在内存维护频率/模式/PTT 状态，并按真实响应帧回包，
    使 CiVRadio 上层无需感知真机 / mock 差异。
    """

    def __init__(self) -> None:
        self._freq_hz = DEFAULT_MOCK_FREQ_HZ
        self._mode = DEFAULT_MOCK_MODE
        self._ptt = False
        self._smeter = 100  # mock S 表原始值（0-255，约 S5 附近）
        self._buf = bytearray()

    # ---- pyserial 兼容子集 ----
    def write(self, frame: bytes) -> int:
        resp = self._handle(frame)
        if resp:
            self._buf.extend(resp)
        return len(frame)

    def read(self, n: int = 1) -> bytes:
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    @property
    def in_waiting(self) -> int:
        return len(self._buf)

    def close(self) -> None:
        self._buf.clear()

    # ---- 命令处理 ----
    def _handle(self, frame: bytes) -> bytes:
        parsed = parse_frame(frame)
        if parsed is None:
            return b""
        _, _, cmd, data = parsed
        if cmd == CMD_READ_FREQ:
            return build_response(CMD_READ_FREQ, encode_freq_bcd(self._freq_hz))
        if cmd == CMD_SET_FREQ:
            self._freq_hz = decode_freq_bcd(data)
            return build_response(CMD_OK)
        if cmd == CMD_READ_MODE:
            return build_response(CMD_READ_MODE, bytes([self._mode, 0x01]))
        if cmd == CMD_READ_SMETER:
            return build_response(CMD_READ_SMETER, bytes([0x03, self._smeter]))
        if cmd == CMD_SET_MODE:
            if data:
                self._mode = data[0]
            return build_response(CMD_OK)
        if cmd == CMD_PTT:
            # 请求帧 body = [sub=0x00, data]，PTT 值在 sub 之后的最后一个字节
            self._ptt = bool(data[-1]) if data else False
            return build_response(CMD_OK)
        return build_response(CMD_NG)  # 未知命令 → NG

    def get_state(self) -> dict:
        """暴露内部状态，供测试断言 mock 是否正确响应。"""
        return {"freq_hz": self._freq_hz, "mode": self._mode, "ptt": self._ptt}


# ============ CI-V 串口控制器 ============


class CiVRadio:
    """IC-705 CI-V 串口控制器（真机 pyserial / 无真机 mock 双后端）。"""

    def __init__(self, port: str = "mock", baudrate: int = 19200) -> None:
        self.port = str(port).strip() or "mock"
        self.baudrate = int(baudrate)
        self._ser = None  # 懒打开

    @property
    def is_mock(self) -> bool:
        return self.port.lower() in ("mock", "none", "")

    def _open(self) -> None:
        if self._ser is not None:
            return
        if self.is_mock:
            self._ser = MockSerial()
            return
        try:
            import serial  # 延迟导入：mock 模式无需 pyserial
        except ImportError as exc:  # pragma: no cover - 取决于部署环境
            raise RadioError(
                "未安装 pyserial，无法打开真实串口。请 pip install pyserial，"
                "或把 IC705_PORT 设为 mock 走内存模拟。"
            ) from exc
        try:
            self._ser = serial.Serial(self.port, self.baudrate, timeout=0.5)
        except Exception as exc:  # SerialException 等
            raise RadioError(f"无法打开串口 {self.port}（波特率 {self.baudrate}）: {exc}") from exc

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    # ---- 底层读写 ----
    def _read_response(self, timeout: float = 1.5) -> bytes:
        deadline = time.time() + timeout
        buf = bytearray()
        while time.time() < deadline:
            try:
                waiting = self._ser.in_waiting
            except Exception:
                waiting = 0
            if waiting > 0:
                buf.extend(self._ser.read(waiting))
                if buf and buf[-1] == _EOM:
                    break
            time.sleep(0.01)
        return bytes(buf)

    def _transact(self, cmd: int, data: bytes = b"", sub: int | None = None) -> tuple[int, bytes]:
        """发送请求并读回响应 → (resp_cmd, resp_data)。"""
        self._open()
        self._ser.write(build_frame(cmd, data, sub))
        resp = self._read_response()
        parsed = parse_frame(resp)
        if parsed is None:
            raise RadioError(f"CI-V 无响应（cmd=0x{cmd:02x}），请确认电台已开机且 USB 串口已连接")
        _, _, resp_cmd, resp_data = parsed
        if resp_cmd == CMD_NG:
            raise RadioError(f"电台拒绝命令 cmd=0x{cmd:02x}（返回 0xFA NG）")
        return resp_cmd, resp_data

    # ---- 高层命令 ----
    def read_freq(self) -> int:
        cmd, data = self._transact(CMD_READ_FREQ)
        if cmd != CMD_READ_FREQ:
            raise RadioError(f"读频率应答命令异常: 0x{cmd:02x}")
        return decode_freq_bcd(data)

    def set_freq(self, hz: int) -> int:
        hz = int(hz)
        assert_allowed_freq(hz)
        self._transact(CMD_SET_FREQ, encode_freq_bcd(hz))
        return hz

    def read_mode(self) -> str:
        cmd, data = self._transact(CMD_READ_MODE)
        if cmd != CMD_READ_MODE or not data:
            raise RadioError("读模式应答异常")
        return MODE_NAMES.get(data[0], f"未知({data[0]})")

    def read_smeter(self) -> dict:
        """读 S 表（0x1A/0x03），返回 {s_raw, s_unit, s_db}。真机未应答时降级 mock。"""
        try:
            cmd, data = self._transact(CMD_READ_SMETER, sub=0x03)
            if cmd != CMD_READ_SMETER or len(data) < 2 or data[0] != 0x03:
                raise RadioError("S 表应答格式异常")
            raw = data[1]
        except RadioError:
            raw = 100  # 降级：读不到 S 表时返回 mock 中值
        s_unit, s_db = _smeter_approx(raw)
        return {"s_raw": raw, "s_unit": s_unit, "s_db": s_db}

    def set_mode(self, mode: str) -> str:
        name = str(mode).strip().upper()
        code = MODE_CODES.get(name)
        if code is None:
            raise RadioError(f"不支持的模式 {mode!r}，可选: {', '.join(MODE_CODES)}")
        self._transact(CMD_SET_MODE, bytes([code, 0x01]))
        return name

    def set_ptt(self, on: bool) -> bool:
        on = bool(on)
        self._transact(CMD_PTT, bytes([0x01 if on else 0x00]), sub=0x00)
        return on


# ============ 单例（懒初始化，串口参数可配） ============

_radio: CiVRadio | None = None
_radio_lock = threading.Lock()


def _configured_port() -> str:
    return os.environ.get("IC705_PORT", "").strip() or "mock"


def _configured_baudrate() -> int:
    try:
        return int(os.environ.get("IC705_BAUDRATE", "19200"))
    except ValueError:
        return 19200


def get_radio() -> CiVRadio:
    """获取全局电台控制器（懒初始化，按环境变量配置）。"""
    global _radio
    with _radio_lock:
        if _radio is None:
            _radio = CiVRadio(port=_configured_port(), baudrate=_configured_baudrate())
        return _radio


def _reset_radio() -> None:
    """测试辅助：丢弃单例，让下次 get_radio 按新环境变量重建。"""
    global _radio
    with _radio_lock:
        if _radio is not None:
            _radio.close()
        _radio = None


# ============ 请求模型 ============


class FrequencyRequest(BaseModel):
    freq_mhz: float = Field(..., gt=0, description="目标频率 (MHz)")


class ModeRequest(BaseModel):
    mode: str = Field(..., min_length=1, max_length=8, description="模式，如 USB/FM/CW")


class PttRequest(BaseModel):
    state: str = Field(..., description="TX 或 RX")


class LogRequest(BaseModel):
    callsign: str = Field(..., min_length=2, max_length=16, description="对方呼号")
    rst_sent: str = Field("59", max_length=8, description="我发给对方的 RST")
    rst_rcvd: str = Field("59", max_length=8, description="对方发给我的 RST")
    remarks: str = Field("", max_length=500, description="备注")
    freq_mhz: float | None = Field(None, description="频率回退值（电台不可用时）")
    mode: str | None = Field(None, description="模式回退值（电台不可用时）")


# ============ 端点 ============


def _radio_status(radio: CiVRadio) -> dict:
    """读组合状态；mock 模式额外暴露内部状态便于前端调试。"""
    freq_hz = radio.read_freq()
    mode = radio.read_mode()
    smeter = radio.read_smeter()
    status = {
        "ok": True,
        "freq_hz": freq_hz,
        "freq_mhz": round(freq_hz / 1e6, 6),
        "mode": mode,
        "ptt": "TX" if _mock_ptt(radio) else "RX",
        "port": radio.port,
        "mock": radio.is_mock,
        "s_unit": smeter["s_unit"],
        "s_db": smeter["s_db"],
    }
    # W131-05：CAT 命令成功后把电台状态上报感知层（IC-705 在线 + 关键指标）
    try:
        from apiserver.device_state import get_device_state_store
        get_device_state_store().update_state("ic705", {
            "freq_hz": status["freq_hz"],
            "mode": status["mode"],
            "s_unit": status["s_unit"],
            "mock": status["mock"],
        })
    except Exception:
        pass  # 感知层失败不阻断电台状态读取（感知是旁路）
    return status


def _smeter_approx(raw: int) -> tuple[int, float]:
    """把 IC-705 S 表原始值(0-255) 近似换算为 (s_unit, s_db)。

    线性标称：dBm = -127 + raw*(114/255)，S0~S9 每档 6dB，S9 之上每 +10dB 上一档（封顶 S9+50）。
    """
    raw = max(0, min(255, int(raw)))
    s_db = round(-127.0 + raw * (114.0 / 255.0), 1)
    if s_db <= -73.0:
        s_unit = max(0, int(round((-73.0 - s_db) / 6.0)))
    else:
        s_unit = min(14, 9 + int((s_db + 73.0) / 10.0))
    return s_unit, s_db


def _mock_ptt(radio: CiVRadio) -> bool:
    """mock 后端读 PTT 内部状态；真机不支持读 PTT 时返回 False（安全默认 RX）。"""
    if isinstance(radio._ser, MockSerial):
        return bool(radio._ser.get_state()["ptt"])
    return False


@router.get("/status")
async def get_status(
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """读电台当前状态（频率 / 模式 / PTT / 是否 mock）。"""
    try:
        return _radio_status(get_radio())
    except RadioError as exc:
        raise HTTPException(status_code=502, detail=f"读取电台状态失败: {exc}") from exc


@router.post("/frequency")
async def set_frequency(
    body: FrequencyRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """设置频率（业余频段白名单强制，越界拒绝）。"""
    hz = int(round(body.freq_mhz * 1e6))
    try:
        set_hz = get_radio().set_freq(hz)
    except RadioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "freq_hz": set_hz, "freq_mhz": round(set_hz / 1e6, 6)}


@router.post("/mode")
async def set_mode(
    body: ModeRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """切换工作模式。"""
    try:
        mode = get_radio().set_mode(body.mode)
    except RadioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "mode": mode}


@router.post("/ptt")
async def set_ptt(
    body: PttRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """PTT 控制（TX 会真正发射，真机慎用）。"""
    state = str(body.state).strip().upper()
    if state in ("TX", "ON"):
        on = True
    elif state in ("RX", "OFF"):
        on = False
    else:
        raise HTTPException(status_code=422, detail="state 必须是 TX/RX（或 ON/OFF）")
    try:
        get_radio().set_ptt(on)
    except RadioError as exc:
        raise HTTPException(status_code=502, detail=f"PTT 控制失败: {exc}") from exc
    return {"ok": True, "state": "TX" if on else "RX"}


@router.post("/log")
async def log_qso(
    body: LogRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """通联完成一键进 HamLog：从电台读当前频率/模式自动填充，可补 RST/备注。"""
    from mcpserver.adapters.hamlog_adapter.adapter import HamlogError, qso_add

    radio = get_radio()
    freq_mhz = body.freq_mhz
    mode = body.mode
    # 优先从电台读真值；电台不可用时回退到前端显式传入的值
    try:
        freq_mhz = radio.read_freq() / 1e6
    except RadioError:
        pass
    try:
        mode = radio.read_mode()
    except RadioError:
        pass

    try:
        result = qso_add(
            callsign=body.callsign,
            mode=mode or "USB",
            freq=f"{freq_mhz:.3f}" if freq_mhz is not None else "",
            rst_sent=body.rst_sent,
            rst_rcvd=body.rst_rcvd,
            remarks=body.remarks,
        )
    except HamlogError as exc:
        raise HTTPException(status_code=502, detail=f"HamLog 写入失败: {exc}") from exc
    return {
        "ok": True,
        "qso_id": result.get("qso_id"),
        "callsign": body.callsign.upper(),
        "mode": mode,
        "freq_mhz": round(freq_mhz, 3) if freq_mhz is not None else None,
    }


@router.get("/qsl-debts")
async def qsl_debts(
    direction: str = "all",
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """QSL 卡债清单（前端角标数据源）。direction: owed/owing/all。"""
    from mcpserver.adapters.hamlog_adapter.adapter import HamlogError
    from mcpserver.adapters.hamlog_adapter.adapter import qsl_debts as _debts

    try:
        debts = _debts(direction=direction)
    except HamlogError as exc:
        raise HTTPException(status_code=502, detail=f"HamLog 卡债查询失败: {exc}") from exc
    return {"ok": True, "direction": direction, "count": len(debts), "debts": debts}


# ============ Y-04: SDR 实时频谱 / 瀑布图 ============

_DEFAULT_SPECTRUM_FPS = 4.0          # 2-5fps，与避坑铁律"轻量 UI"对齐
_DEFAULT_SPECTRUM_FFT = 2048
_DEFAULT_SPECTRUM_COLS = 512
_DEFAULT_SPECTRUM_SAMPLE_RATE = 48_000.0  # IC-705 USB 声卡典型


def _spectrum_source(center_hz: float):
    """频谱输入源工厂：真机（IC-705 USB 声卡）优先，失败回退仿真合成音。

    诚实降级：仿真源 name="sim"，前端据此显示 degraded 角标；绝不冒充真机。
    真机路径可通过 SPECTRUM_SOURCE=ic705 强制（需已装 pyaudio + 接好声卡），
    失败不阻断——回退仿真并打 warning。
    """
    kind = os.environ.get("SPECTRUM_SOURCE", "sim").strip().lower()
    if kind == "ic705":
        try:
            from mcpserver.rf_brain.device.ic705 import Ic705UsbAudioSource

            src = Ic705UsbAudioSource(
                sample_rate=_DEFAULT_SPECTRUM_SAMPLE_RATE, center_freq_hz=center_hz
            )
            src.open()
            return src
        except Exception as exc:  # 真机不可用 → 降级，不阻断
            logger.warning("IC-705 声卡频谱源不可用，回退仿真合成音: %r", exc)

    from mcpserver.rf_brain.device.sim import SimulatedSource
    from mcpserver.rf_brain.spectrum import synthetic_spectrum_audio

    return SimulatedSource(
        gen_fn=lambda sr, n: synthetic_spectrum_audio(sr, n, seed=1),
        sample_rate=_DEFAULT_SPECTRUM_SAMPLE_RATE,
        duration_s=0.5,
        center_freq_hz=center_hz,
    )


@router.websocket("/spectrum/ws")
async def spectrum_websocket(websocket: WebSocket) -> None:
    """实时频谱 / 瀑布图推送（2-5fps，频率联动电台当前 VFO）。

    每帧推送一路下采样后的频谱行（freq_hz + spectrum_db），前端 canvas 按行
    滚动拼成瀑布图；payload 保持轻量（单行 ≈ 512 点），不做整张瀑布回传——
    见避坑铁律"Web UI lightweight → canvas throttle/downsample"。

    帧结构见 mcpserver/rf_brain/spectrum.next_spectrum_frame。
    """
    from mcpserver.rf_brain.spectrum import next_spectrum_frame

    await websocket.accept()
    center_hz = DEFAULT_MOCK_FREQ_HZ
    source = None
    try:
        # 先用电台当前频率构造源（过白名单）；后续每帧再读最新 VFO 实现联动
        try:
            center_hz = get_radio().read_freq()
        except RadioError:
            pass
        source = _spectrum_source(center_hz)
        source.open()

        interval = 1.0 / _DEFAULT_SPECTRUM_FPS
        while True:
            t0 = time.monotonic()
            try:
                center_hz = get_radio().read_freq()
            except RadioError:
                pass  # 读频失败保留上次频率，不中断频谱流
            frame = await asyncio.to_thread(
                next_spectrum_frame,
                source,
                center_hz,
                fft_size=_DEFAULT_SPECTRUM_FFT,
                cols=_DEFAULT_SPECTRUM_COLS,
            )
            await websocket.send_json(frame)
            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0.0, interval - elapsed))
    except WebSocketDisconnect:
        logger.info("[SpectrumWS] 客户端断开")
    except Exception as exc:
        logger.error("[SpectrumWS] 频谱推送异常: %r", exc)
    finally:
        if source is not None:
            source.close()
