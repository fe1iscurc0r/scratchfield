"""链路传输层（卷130 W130-01）：抽象 + 串口实现 + 固件模拟器。

- `Transport`          抽象：一行命令 / 一行回显
- `SerialTransport`    USB CDC 真机（pyserial 懒加载，缺依赖给安装提示）
- `SimTransport`       **固件语义的 Python 镜像**：无硬件时跑通全链路逻辑

`SimTransport` 不是"随便回个 ok"的假货——它把 `cmd_parser.hpp` 的解析规则、软限位、
直线插补时长、堵转锁死、`$X` 显式清故障、M112 急停都照同一套语义实现。
这样 daemon / MCP 工具 / 编排层的逻辑在**没有硬件**时也能被真测，
与卷129「Python 规格镜像」是同一套方法。
"""
from __future__ import annotations

import abc
import time
from typing import Any, Dict, List, Optional

from . import protocol
from .protocol import ProtocolError
from .safety import DEFAULT_HOLD_S, FailsafeAction, FailsafePolicy, SafetyRing, failsafe_action


class TransportError(RuntimeError):
    """链路层故障（超时/断开）——调用方应触发重连，而不是当成命令失败。"""


class TransportUnavailable(TransportError):
    """依赖缺失或端口不存在——应带可操作提示，不静默降级。"""


class Transport(abc.ABC):
    kind = "unknown"

    @abc.abstractmethod
    def write_line(self, text: str) -> None:
        ...

    @abc.abstractmethod
    def read_line(self, timeout_s: float = 0.5) -> str | None:
        ...

    def close(self) -> None:
        ...

    def reopen(self) -> bool:
        """断开后重新打开。默认：关掉再置空，下次写入时懒重连。

        **不能在这里 new 一个新对象**——daemon 可能持有被注入的传输实例
        （测试用的 SimTransport），换掉实例等于换了台设备。
        """
        self.close()
        return True

    def poll(self) -> None:
        """推进设备侧内部状态（真机为空；模拟器用来跑心跳看门狗）。"""
        ...

    @property
    def descriptor(self) -> Dict[str, Any]:
        return {"kind": self.kind}

    @property
    def connected(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# USB CDC 串口
# ---------------------------------------------------------------------------


class SerialTransport(Transport):
    """USB CDC 串口（真机）。pyserial 懒加载——没装不影响模块导入与其它功能。"""

    kind = "serial"

    def __init__(self, port: str, baudrate: int = 115200, read_timeout_s: float = 0.5):
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
            raise TransportUnavailable(
                "pyserial 未安装：pip install pyserial 后可用") from exc
        try:
            self._serial = serial.Serial(self.port, self.baudrate,
                                         timeout=self.read_timeout_s, write_timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            raise TransportUnavailable(f"打不开串口 {self.port}: {exc}") from exc

    def write_line(self, text: str) -> None:
        self._ensure_open()
        try:
            self._serial.write((text.rstrip("\r\n") + "\n").encode("ascii", "replace"))
        except Exception as exc:  # noqa: BLE001
            self._serial = None
            raise TransportError(f"串口写失败（已标记断开）: {exc}") from exc

    def read_line(self, timeout_s: float = 0.5) -> str | None:
        self._ensure_open()
        try:
            self._serial.timeout = timeout_s
            raw = self._serial.readline()
        except Exception as exc:  # noqa: BLE001
            self._serial = None
            raise TransportError(f"串口读失败（已标记断开）: {exc}") from exc
        if not raw:
            return None
        return raw.decode("ascii", "replace").strip()

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None

    @property
    def connected(self) -> bool:
        return self._serial is not None and bool(getattr(self._serial, "is_open", True))

    @property
    def descriptor(self) -> Dict[str, Any]:
        return {"kind": self.kind, "port": self.port, "baudrate": self.baudrate,
                "connected": self.connected}


# ---------------------------------------------------------------------------
# 固件模拟器
# ---------------------------------------------------------------------------


#: 各轴最大速度（度/秒）——仅模拟器使用，真机由固件参数决定
SIM_MAX_SPEED = {"az": 30.0, "el": 20.0}
#: 软限位（与 planner.hpp 一致：方位 0..360、俯仰 −90..90）
SIM_LIMITS = {"az": (0.0, 360.0), "el": (-90.0, 90.0)}


class SimTransport(Transport):
    """内存固件模拟器——语义与固件命令面/规划器对齐，可注入故障。"""

    kind = "sim"

    def __init__(self, az_deg: float = 0.0, el_deg: float = 0.0,
                 clock=time.monotonic, link_up: bool = True,
                 failsafe_timeout_s: float = 3.0):
        self._clock = clock
        self._replies: List[str] = []
        self._az = float(az_deg)
        self._el = float(el_deg)
        self._enabled = False
        self._fault_ring = SafetyRing.NONE
        self._fault_detail = ""
        self._link_up = bool(link_up)
        self._started = clock()
        self._last_hb = clock()
        self._moves = 0
        self._homes = 0
        self._lines: List[str] = []
        # 运动状态
        self._from = (self._az, self._el)
        self._span = (0.0, 0.0)
        self._to = (self._az, self._el)
        self._move_start = clock()
        self._move_duration = 0.0
        # 注入开关
        self._fail_writes = 0
        self._silent = False
        self._read_backlog: List[str] = []
        # 进给保持（卷130）：暂停但不锁故障
        self._held = False
        self._hold_since = clock()
        # 固件侧失联保护（卷130 W130-05）：心跳超时由**设备自己**判定并执行策略
        self._failsafe_policy = FailsafePolicy.HOLD_THEN_DISABLE
        self._failsafe_hold_s = DEFAULT_HOLD_S
        self._failsafe_timeout_s = float(failsafe_timeout_s)
        self._failsafe_fired = False
        self._failsafe_fire_at = clock()

    # ---- 观测（测试用） ----
    @property
    def lines(self) -> List[str]:
        return list(self._lines)

    @property
    def move_count(self) -> int:
        return self._moves

    @property
    def home_count(self) -> int:
        return self._homes

    @property
    def fault(self) -> bool:
        return self._fault_ring is not SafetyRing.NONE

    # ---- 故障注入 ----
    def inject_stall(self, detail: str = "current>1.2A") -> None:
        self._fault_ring = SafetyRing.STALL
        self._fault_detail = detail
        self._freeze_at_current()

    def inject_encoder_fault(self, detail: str = "read_fail") -> None:
        self._fault_ring = SafetyRing.ENCODER
        self._fault_detail = detail

    def inject_link_loss(self) -> None:
        self._link_up = False
        self._fault_ring = SafetyRing.LINK
        self._fault_detail = "heartbeat_timeout"

    def inject_disconnect(self, writes: int = 999) -> None:
        """模拟拔线：接下来 `writes` 次写操作抛 TransportError。"""
        self._fail_writes = int(writes)

    def set_silent(self, value: bool = True) -> None:
        """模拟「链路可写但设备不回应」——W130-04 兜底命令能送达的那种失联。

        与 `inject_disconnect` 的区别很关键：拔线时主机**发不出**兜底命令，
        只有设备侧看门狗能救；设备沉默但链路活着时，主机侧的 stop/disable
        是能真正送达的。两个场景要分开测。
        """
        self._silent = bool(value)

    @property
    def command_log(self) -> List[str]:
        """收到过的命令原文（含被静默处理前的）——断言兜底命令确实发出去了。"""
        return list(self._lines)

    def inject_line(self, text: str) -> None:
        """模拟设备主动吐一行（例如异步上报）。"""
        self._read_backlog.append(str(text))

    # ---- Transport ----
    def write_line(self, text: str) -> None:
        if self._fail_writes > 0:
            self._fail_writes -= 1
            raise TransportError("模拟断线：写失败")
        line = (text or "").strip()
        self._lines.append(line)
        # 任何入站行都算"主机还活着"——看门狗据此计时
        self._last_hb = self._clock()
        if self._failsafe_fired:
            self._failsafe_fired = False
            self._link_up = True
        if self._silent:
            return                      # 设备沉默：命令收到了，但一条回显都不给
        self._replies.append(self._execute(line))

    def poll(self) -> None:
        """心跳看门狗（固件自己做的事）：超时 → 判失联 → 按已下发的策略执行。

        主机不参与执行——链路断了它发不出命令。这里镜像的正是固件行为。
        """
        now = self._clock()
        age = now - self._last_hb
        if age <= self._failsafe_timeout_s:
            return
        if not self._failsafe_fired:
            self._failsafe_fired = True
            self._failsafe_fire_at = now
            self._link_up = False
            self._fault_ring = SafetyRing.LINK
            self._fault_detail = "heartbeat_timeout"
        self._apply_failsafe(now - self._failsafe_fire_at)

    def _apply_failsafe(self, elapsed_s: float) -> None:
        action = failsafe_action(self._failsafe_policy, elapsed_s, self._failsafe_hold_s)
        if action is FailsafeAction.HOLD:
            self._advance()
            if not self._held:
                self._held = True
                self._hold_since = self._clock()
        elif action is FailsafeAction.DISABLE:
            self._freeze_at_current()
            self._enabled = False
        elif action is FailsafeAction.CENTER:
            self._freeze_at_current()
            self._az = self._el = 0.0
            self._from = self._to = (0.0, 0.0)

    def read_line(self, timeout_s: float = 0.5) -> str | None:
        if self._read_backlog:
            return self._read_backlog.pop(0)
        if self._replies:
            return self._replies.pop(0)
        return None

    @property
    def connected(self) -> bool:
        return self._fail_writes <= 0 and self._link_up

    @property
    def descriptor(self) -> Dict[str, Any]:
        return {"kind": self.kind, "connected": self.connected, "link_up": self._link_up}

    # ---- 内部 ----
    def _freeze_at_current(self) -> None:
        """锁死：停在被锁时刻的位置（机械卡住的样子）。"""
        self._advance()
        self._from = (self._az, self._el)
        self._span = (0.0, 0.0)
        self._to = self._from
        self._move_duration = 0.0
        self._held = False

    def _release_hold(self) -> None:
        """解除进给保持：把暂停时长补回起点，剩余行程照旧走完。"""
        if self._held:
            self._move_start += self._clock() - self._hold_since
            self._held = False

    def _advance(self) -> None:
        if self._move_duration <= 0.0 or self._held:
            return
        now = self._clock()
        ratio = (now - self._move_start) / self._move_duration
        if ratio >= 1.0:
            self._az, self._el = self._to      # 终点 = 原始目标（与固件 current_deg_ = target_deg_ 一致）
            self._move_duration = 0.0
            return
        self._az = self._from[0] + self._span[0] * ratio
        self._el = self._from[1] + self._span[1] * ratio

    @property
    def moving(self) -> bool:
        self._advance()
        return self._move_duration > 0.0

    @property
    def held(self) -> bool:
        return self._held

    def _shortest_delta(self, target: float) -> float:
        return ((float(target) - self._az + 180.0) % 360.0) - 180.0

    def _new_move(self, az: float, el: float, feed: float | None, rapid: bool) -> None:
        from_az, from_el = self._az, self._el
        d_az = self._shortest_delta(az)
        d_el = float(el) - self._el
        if rapid:
            dur_az = abs(d_az) / SIM_MAX_SPEED["az"]
            dur_el = abs(d_el) / SIM_MAX_SPEED["el"]
            duration = max(dur_az, dur_el)
        else:
            feed_v = float(feed) if feed else 10.0
            longest = max(abs(d_az), abs(d_el))
            duration = longest / float(feed_v) if feed_v > 0 else 0.0
        self._from = (from_az, from_el)
        self._span = (d_az, d_el)          # 绕行用增量；终点回落到**原始目标**
        self._to = (float(az), float(el))
        self._move_start = self._clock()
        self._move_duration = max(0.0, duration)
        self._advance()
        if self._move_duration == 0.0:
            self._az, self._el = self._to
        self._moves += 1

    def _limits_ok(self, az: float, el: float) -> bool:
        """**在原始目标值上判限位**——固件 planner.hpp 就是这么做的：

        `if (target_deg < limits.min_deg || target_deg > limits.max_deg)` 发生在
        最短路径归一化**之前**，所以方位 400° 是被**拒绝**的，不是自动折成 40°。
        主机侧不许自作聪明先归一化，那会把一个"越限"变成一次悄悄的真实运动。
        """
        for axis, value in (("az", float(az)), ("el", float(el))):
            low, high = SIM_LIMITS[axis]
            if not (low - 1e-6 <= value <= high + 1e-6):
                return False
        return True

    def _execute(self, line: str) -> str:
        self._advance()
        text = line.upper()

        # 卷130 新增：$X 显式清故障 / ! 进给保持 / ~ 恢复（GRBL 惯例）
        if text.startswith("$"):
            if text in ("$X", "$X;"):
                self._fault_ring = SafetyRing.NONE
                self._fault_detail = ""
                return protocol.REPLY_OK
            if text.startswith("$FS="):
                value = text[4:].split(";", 1)[0].strip()
                parts = [p.strip() for p in value.split(",")]
                self._failsafe_policy = FailsafePolicy.from_code(parts[0])
                if len(parts) > 1 and parts[1]:
                    try:
                        self._failsafe_hold_s = max(0.0, float(parts[1]))
                    except ValueError:
                        return "error:bad_value"
                return protocol.REPLY_OK
            return "error:unknown"
        if text.startswith("!"):
            self._advance()
            self._held = True
            self._hold_since = self._clock()
            return protocol.REPLY_OK
        if text.startswith("~"):
            self._release_hold()
            return protocol.REPLY_OK

        cmd = _parse_line(text)
        if cmd["error"]:
            return f"error:{cmd['error']}"

        code = cmd["code"]
        if code == "M115":
            return (f"fw=0.2 uptime={int(self._clock() - self._started)} "
                    f"rssi={-72 if self._link_up else -128} "
                    f"lora={1 if self._link_up else 0} failsafe={self._failsafe_policy.code}")
        if code == "M112":
            self._freeze_at_current()
            self._fault_ring = SafetyRing.ESTOP
            self._fault_detail = "commanded"
            return protocol.REPLY_OK
        if code == "M17":
            self._enabled = True
            return protocol.REPLY_OK
        if code == "M18":
            self._freeze_at_current()
            self._enabled = False
            return protocol.REPLY_OK
        if code == "M114":
            # 上报 current_deg：绕行途中可能短暂 >360（与固件一致），终点回落到目标值
            return protocol.format_status(
                self._az, self._el, self.moving, self.fault, self._enabled,
                fault_ring=int(self._fault_ring), link_up=self._link_up,
                heartbeat_age_s=max(0.0, self._clock() - self._last_hb),
                held=self._held)
        if code == "G4":
            return protocol.REPLY_OK

        # 以下都是运动类：先过故障闸与使能闸
        if self._fault_ring.blocks_motion:
            return "error:fault"
        if not self._enabled:
            return "error:disabled"

        if code == "G28":
            self._new_move(0.0, 0.0, None, rapid=True)
            self._homes += 1
            return protocol.REPLY_OK
        if code in ("G0", "G1"):
            az = cmd["x"] if cmd["x"] is not None else self._az
            el = cmd["y"] if cmd["y"] is not None else self._el
            if not self._limits_ok(az, el):
                return "error:limit"
            self._new_move(az, el, cmd["f"], rapid=(code == "G0"))
            return protocol.REPLY_OK
        return "error:unknown"

    def close(self) -> None:
        self._replies.clear()

    def reopen(self) -> bool:
        """模拟器"重连"：清掉注入的断线，链路恢复（设备侧故障环仍需显式 $X）。"""
        self._fail_writes = 0
        self._link_up = True
        self._failsafe_fired = False
        self._last_hb = self._clock()
        return True


# ---------------------------------------------------------------------------
# 解析（照 cmd_parser.hpp 的规则，含卷130 新增码）
# ---------------------------------------------------------------------------


def _parse_line(text: str) -> Dict[str, Any]:
    """返回 {code, x, y, f, p, error}；error 非空即解析失败（与固件文本一致）。"""
    out: Dict[str, Any] = {"code": "", "x": None, "y": None, "f": None, "p": None, "error": ""}
    body = text.split(";", 1)[0]
    tokens = body.split()
    have = False
    for token in tokens:
        if token[:1] in ("G", "M"):
            try:
                code = int(token[1:])
            except ValueError:
                out["error"] = "unknown"
                return out
            if token[0] == "G":
                if code not in protocol.SUPPORTED_G:
                    out["error"] = f"unsupported_g{code}"
                    return out
            else:
                if code not in protocol.SUPPORTED_M:
                    out["error"] = f"unsupported_m{code}"
                    return out
            out["code"] = token
            have = True
        elif token[:1] in ("X", "Y", "F", "P"):
            key = {"X": "x", "Y": "y", "F": "f", "P": "p"}[token[0]]
            try:
                out[key] = float(token[1:])
            except ValueError:
                out["error"] = "unknown"
                return out
    if not have:
        out["error"] = "unknown"
    return out


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------


def open_transport(spec: str, **kwargs: Any) -> Transport:
    """`"sim"` → 模拟器；`"COM3"` / `"COM3@115200"` / `"/dev/ttyUSB0"` → 串口。"""
    text = str(spec or "").strip()
    if not text or text.lower() in ("sim", "simulator", "loopback"):
        return SimTransport(**kwargs)
    port, _, baud = text.partition("@")
    baudrate = int(baud) if baud else int(kwargs.pop("baudrate", 115200))
    return SerialTransport(port.strip(), baudrate=baudrate)


__all__ = [
    "TransportError", "TransportUnavailable", "Transport",
    "SerialTransport", "SimTransport", "open_transport",
    "SIM_LIMITS", "SIM_MAX_SPEED",
]
