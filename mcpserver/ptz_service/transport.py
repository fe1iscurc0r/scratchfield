"""PTZ 连接抽象（卷130 W130-01）——控制器与实体分离。

工单 W130-01 明写：**连接抽象** `PTZTransport` 接口，两个后端——
`SerialTransport`（/dev/ttyUSB* / COMx，9600–115200）与 `LoraBridgeTransport`
（SX1278 无线，文本帧格式同串口命令流）。照 ros2_control「hardware_interface 分离」
的思路：上层控制器不关心命令走的是 USB 还是无线电。

命令面沿用卷129 的 G 代码子集（`ok` / `error:limit` / `error:unknown`），
无线链路上这些回显文本**原样透传**，不做翻译。
"""
from __future__ import annotations

import abc
import time
from typing import Any, Dict, List, Optional

from .rotator_core import protocol as cmd
from .rotator_core.transport import TransportError, TransportUnavailable

#: LoRa 文本帧上限（工单规定 ≤64B）
LORA_FRAME_MAX = 64
#: 帧头（工单格式：`PTZ <cmd>` / 回传 `OK <status>`）
LORA_CMD_PREFIX = "PTZ "
LORA_OK_PREFIX = "OK "
LORA_ERR_PREFIX = "ERR "


# ---------------------------------------------------------------------------
# LoRa 文本帧编解码（纯函数，可单测）
# ---------------------------------------------------------------------------


def checksum(payload: str) -> int:
    """8 位和无进位校验（工单要求「长度/校验和」两重校验）。"""
    return sum(payload.encode("utf-8")) & 0xFF


def encode_frame(payload: str) -> bytes:
    """`<payload>#<SUM2>\n`；超 64B 抛错（不占空中时间）。"""
    text = str(payload or "").strip()
    body = f"{text}#{checksum(text):02X}"
    if len(body) + 1 > LORA_FRAME_MAX:
        raise ValueError(f"LoRa 帧超长（{len(body) + 1} > {LORA_FRAME_MAX}）: {text[:40]}…")
    return (body + "\n").encode("ascii", "replace")


def decode_frame(raw: bytes) -> str | None:
    """校验和/长度不过返回 None（**拒收**，不猜）。"""
    try:
        text = raw.decode("ascii", "replace").strip()
    except Exception:  # noqa: BLE001
        return None
    if not text or len(text) + 1 > LORA_FRAME_MAX or "#" not in text:
        return None
    body, _, digest = text.rpartition("#")
    if len(digest) != 2:
        return None
    try:
        expected = int(digest, 16)
    except ValueError:
        return None
    if checksum(body) != expected:
        return None
    return body.strip()


def encode_command(payload: str) -> bytes:
    return encode_frame(f"{LORA_CMD_PREFIX}{payload}")


def encode_reply(text: str) -> bytes:
    body = text.strip()
    prefix = LORA_ERR_PREFIX if body.startswith("error:") else LORA_OK_PREFIX
    return encode_frame(f"{prefix}{body}")


def decode_reply(body: str) -> str | None:
    """回传帧 → 固件风格回显文本（`ok` / `error:limit`…）。"""
    if body.startswith(LORA_OK_PREFIX):
        rest = body[len(LORA_OK_PREFIX):].strip()
        return rest or "ok"
    if body.startswith(LORA_ERR_PREFIX):
        return body[len(LORA_ERR_PREFIX):].strip()
    return None


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


class PTZTransport(abc.ABC):
    """云台连接抽象。上层只认这个接口——串口/无线/模拟三种后端可互换。"""

    backend = "unknown"

    @abc.abstractmethod
    def send(self, line: str, timeout_s: float = 1.0) -> str:
        """发一条命令，返回一行回显。"""

    def read_status(self, timeout_s: float = 0.5) -> str | None:
        """读一条异步上报（没有则 None）。"""
        return None

    def poll(self) -> None:
        """推进后端内部状态（真机空实现；模拟器跑看门狗）。"""

    def close(self) -> None:
        ...

    @property
    def connected(self) -> bool:
        return True

    @property
    def last_source(self) -> str:
        """最近一次成功的控制来源（`serial` / `lora`）——双路仲裁要显示它。"""
        return self.backend

    def describe(self) -> Dict[str, Any]:
        return {"backend": self.backend, "connected": self.connected,
                "last_source": self.last_source}


# ---------------------------------------------------------------------------
# 串口后端
# ---------------------------------------------------------------------------


class SerialTransport(PTZTransport):
    """USB 串口（卷129 命令面的原生链路）。pyserial 懒加载。"""

    backend = "serial"

    def __init__(self, port: str, baudrate: int = 115200, read_timeout_s: float = 0.5):
        if not (9600 <= int(baudrate) <= 115200):
            raise ValueError(f"波特率需要 9600~115200，收到 {baudrate}")
        self.port = str(port)
        self.baudrate = int(baudrate)
        self.read_timeout_s = float(read_timeout_s)
        self._serial = None

    def _ensure_open(self) -> None:
        if self._serial is not None:
            return
        try:
            import serial  # noqa: PLC0415
        except ImportError as exc:
            raise TransportUnavailable("pyserial 未安装：pip install pyserial 后可用") from exc
        try:
            self._serial = serial.Serial(self.port, self.baudrate,
                                         timeout=self.read_timeout_s, write_timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            raise TransportUnavailable(f"打不开串口 {self.port}: {exc}") from exc

    def send(self, line: str, timeout_s: float = 1.0) -> str:
        self._ensure_open()
        try:
            self._serial.write((cmd.validate_line(line) + "\n").encode("ascii", "replace"))
            self._serial.timeout = timeout_s
            raw = self._serial.readline()
        except Exception as exc:  # noqa: BLE001
            self._serial = None
            raise TransportError(f"串口读写失败（已标记断开）: {exc}") from exc
        if not raw:
            raise TransportError(f"设备无回显（>{timeout_s}s）: {line}")
        return raw.decode("ascii", "replace").strip()

    @property
    def connected(self) -> bool:
        return self._serial is not None and bool(getattr(self._serial, "is_open", True))

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None


# ---------------------------------------------------------------------------
# LoRa 桥后端
# ---------------------------------------------------------------------------


class LoraRadioLink(abc.ABC):
    """SX1278 收发最小接口（真机 RadioLib 实现；无硬件用 LoopbackRadioLink）。"""

    @abc.abstractmethod
    def send_bytes(self, data: bytes) -> bool:
        ...

    @abc.abstractmethod
    def recv_bytes(self, timeout_s: float) -> bytes | None:
        ...

    @property
    def available(self) -> bool:
        return True

    @property
    def rssi_dbm(self) -> int:
        return 0

    def close(self) -> None:
        ...


class LoraBridgeTransport(PTZTransport):
    """LoRa433 遥控后端：文本帧 `PTZ <cmd>`，回传 `OK <status>`，校验和 + 超时重传 2 次。"""

    backend = "lora"

    def __init__(self, link: LoraRadioLink, *, max_retry: int = 2, timeout_s: float = 1.0):
        self.link = link
        self.max_retry = int(max_retry)
        self.timeout_s = float(timeout_s)
        self._pending: List[str] = []
        self.retries = 0
        self.bad_frames = 0

    def send(self, line: str, timeout_s: float = 1.0) -> str:
        if not self.link.available:
            raise TransportError("LoRa 无线电不可用")
        payload = cmd.validate_line(line)
        frame = encode_command(payload)
        attempts = 1 + max(0, self.max_retry)      # 首次 + 重传 2 次 = 最多 3 次
        for _ in range(attempts):
            self.link.send_bytes(frame)
            raw = self.link.recv_bytes(timeout_s or self.timeout_s)
            if raw is None:
                self.retries += 1
                continue
            body = decode_frame(raw)
            if body is None:
                self.bad_frames += 1               # 校验失败拒收，不当成有效回复
                continue
            reply = decode_reply(body)
            if reply is not None:
                return reply
        raise TransportError(f"LoRa 无有效回传（已尝试 {attempts} 次）")

    def read_status(self, timeout_s: float = 0.5) -> str | None:
        if self._pending:
            return self._pending.pop(0)
        raw = self.link.recv_bytes(timeout_s)
        if raw is None:
            return None
        body = decode_frame(raw)
        return decode_reply(body) if body else None

    @property
    def connected(self) -> bool:
        return self.link.available

    def describe(self) -> Dict[str, Any]:
        info = super().describe()
        info.update({"rssi_dbm": self.link.rssi_dbm, "retries": self.retries,
                     "bad_frames": self.bad_frames})
        return info


class LoopbackRadioLink(LoraRadioLink):
    """回环无线电：可注入丢包/坏帧，用来测重传与校验拒收（无硬件可验证的部分）。"""

    def __init__(self, responder=None, drop_rate: float = 0.0, corrupt_rate: float = 0.0):
        self.responder = responder
        self.drop_rate = float(drop_rate)
        self.corrupt_rate = float(corrupt_rate)
        self.sent: List[bytes] = []
        self._rx: List[bytes] = []
        self._seed = 20260918
        self._available = True

    def _rand(self) -> float:
        self._seed = (1103515245 * self._seed + 12345) & 0x7FFFFFFF
        return self._seed / float(0x7FFFFFFF)

    def send_bytes(self, data: bytes) -> bool:
        self.sent.append(bytes(data))
        if self._rand() < self.drop_rate:
            return True
        if self._rand() < self.corrupt_rate:
            self._rx.append(bytes(data[:-2]) + b"ZZ\n")     # 破坏校验和
            return True
        if self.responder is not None:
            reply = self.responder(bytes(data))
            if reply:
                self._rx.append(bytes(reply))
        return True

    def recv_bytes(self, timeout_s: float) -> bytes | None:
        return self._rx.pop(0) if self._rx else None

    @property
    def available(self) -> bool:
        return self._available

    def set_available(self, value: bool) -> None:
        self._available = bool(value)


# ---------------------------------------------------------------------------
# 模拟后端（无硬件跑通全链）
# ---------------------------------------------------------------------------


class SimPTZTransport(PTZTransport):
    """内存模拟对端：语义对齐卷129 固件（解析/软限位/插补时长/失联看门狗）。

    直接复用 `rotator_core.transport.SimTransport` 的实现——**固件语义只有一份**，
    模拟后端不另写一套。
    """

    backend = "sim"

    def __init__(self, device: Any = None, **kwargs: Any):
        """`device`：可选的共享设备体（`SimTransport` 实例）。

        为什么要能共享：双路仲裁（W130-02）模拟的是**同一条机械的一串口 + 一无线
        两条链路**。`enabled`、故障环、当前角度都是**设备上的状态**，不随链路走；
        若两条链路各拿一个独立模拟器，就变成"两台设备"，`ptz_lora("G28")` 会因
        那台"影子设备"没使能而返回 `error:disabled`——那是模拟件的建模错误，
        不是真实故障。默认仍是各建一个（单链路场景），需要时显式共享。
        """
        from .rotator_core.transport import SimTransport

        self._sim = device if device is not None else SimTransport(**kwargs)

    def send(self, line: str, timeout_s: float = 1.0) -> str:
        self._sim.write_line(line)
        reply = self._sim.read_line(timeout_s)
        if reply is None:
            raise TransportError(f"模拟对端无回显: {line}")
        return reply

    def read_status(self, timeout_s: float = 0.5) -> str | None:
        return self._sim.read_line(timeout_s)

    def poll(self) -> None:
        self._sim.poll()

    def close(self) -> None:
        self._sim.close()

    @property
    def connected(self) -> bool:
        return self._sim.connected

    # 测试注入用（转发到底层模拟器）
    def inject_stall(self, detail: str = "current>1.2A") -> None:
        self._sim.inject_stall(detail)

    def inject_disconnect(self, writes: int = 999) -> None:
        self._sim.inject_disconnect(writes)

    def set_silent(self, value: bool = True) -> None:
        """设备沉默但链路可写（W130-04 兜底测试用）。"""
        self._sim.set_silent(value)

    @property
    def command_log(self) -> Any:
        return self._sim.command_log

    @property
    def raw(self) -> Any:
        return self._sim


def open_transport(spec: str, **kwargs: Any) -> PTZTransport:
    """`"sim"` → 模拟；`"COM3"` / `"COM3@9600"` / `"/dev/ttyUSB0"` → 串口。"""
    text = str(spec or "").strip()
    if not text or text.lower() in ("sim", "simulator", "loopback"):
        return SimPTZTransport(**kwargs)
    port, _, baud = text.partition("@")
    baudrate = int(baud) if baud else int(kwargs.pop("baudrate", 115200))
    return SerialTransport(port.strip(), baudrate=baudrate)


__all__ = [
    "LORA_FRAME_MAX", "LORA_CMD_PREFIX", "LORA_OK_PREFIX", "LORA_ERR_PREFIX",
    "checksum", "encode_frame", "decode_frame", "encode_command", "encode_reply", "decode_reply",
    "PTZTransport", "SerialTransport", "LoraBridgeTransport", "LoraRadioLink",
    "LoopbackRadioLink", "SimPTZTransport", "open_transport",
    "TransportError", "TransportUnavailable",
]
