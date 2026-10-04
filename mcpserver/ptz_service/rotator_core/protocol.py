"""云台行协议（卷130 W130-01）——与固件 `cmd/cmd_parser.hpp` 的 REPL 逐字对应。

链路形态：

    host → device    一行命令（G 代码子集 G0/G1/G4/G28 + M17/M18/M114 + 卷130 新增 M112/M115/$X）
    device → host    一行回显：`ok` / `error:<reason>` / 状态行（key=value 空格分隔）

**铁律：回显文本与固件逐字一致，主机侧不做翻译。**
`ok` / `error:limit` / `error:unknown` 这些字符串是**跨层协议**——Lumo 与编排层
用同一套字符串判断，中间加一层"翻译"就等于制造第二份事实源。
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, Optional

#: 单行最大长度（与固件解析器缓冲一致；超长行固件会截断，主机侧一律拒发）
MAX_LINE = 96

REPLY_OK = "ok"
_ERROR_PREFIX = "error:"

#: 固件已实现的 G/M 码（与 cmd_parser.hpp 的 switch 对齐）
SUPPORTED_G = (0, 1, 4, 28)
SUPPORTED_M = (17, 18, 114, 112, 115)

#: 卷130 新增的非 G/M 单字符指令（GRBL 惯例）：$X 显式清故障、! 进给保持、~ 恢复
SUPPORTED_SPECIAL = ("$X", "!", "~")

_KV_PAIR = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(-?\d+(?:\.\d+)?)")


class ReplyKind(str, Enum):
    OK = "ok"
    ERROR = "error"
    STATUS = "status"
    EMPTY = "empty"


class ProtocolError(ValueError):
    """主机侧拒发（还没到固件就被拦下），与固件的 `error:*` 区分开。"""


# ---------------------------------------------------------------------------
# 回显分类
# ---------------------------------------------------------------------------


def classify(reply: str) -> tuple[ReplyKind, str]:
    """把一行回显分类 → (种类, 细节)。细节：错误码 / 状态行原文 / 空串。"""
    text = (reply or "").strip()
    if not text:
        return ReplyKind.EMPTY, ""
    if text == REPLY_OK:
        return ReplyKind.OK, ""
    if text.startswith(_ERROR_PREFIX):
        return ReplyKind.ERROR, text[len(_ERROR_PREFIX):]
    if "=" in text:
        return ReplyKind.STATUS, text
    return ReplyKind.ERROR, text


def is_ok(reply: str) -> bool:
    return classify(reply)[0] is ReplyKind.OK


def error_code(reply: str) -> str:
    kind, detail = classify(reply)
    return detail if kind is ReplyKind.ERROR else ""


# ---------------------------------------------------------------------------
# 命令构造
# ---------------------------------------------------------------------------


def _check_line(line: str) -> str:
    text = str(line or "").strip()
    if not text:
        raise ProtocolError("空命令")
    if len(text) > MAX_LINE:
        raise ProtocolError(f"命令超长（{len(text)} > {MAX_LINE}）")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise ProtocolError("命令含控制字符")
    return text


#: 公开别名：主机侧发任何一行前都过这个闸（空行/超长/控制字符拒发）
validate_line = _check_line


def move(az_deg: float, el_deg: float, feed_deg_s: float | None = None,
         rapid: bool = False) -> str:
    """G0（快速，不保证同时到达）/ G1（直线插补，两轴同时到达）。"""
    parts = ["G0" if rapid else "G1", f"X{float(az_deg):.3f}", f"Y{float(el_deg):.3f}"]
    if feed_deg_s is not None:
        parts.append(f"F{float(feed_deg_s):.3f}")
    return _check_line(" ".join(parts))


def home() -> str:
    return "G28"


def hold(seconds: float) -> str:
    return _check_line(f"G4 P{float(seconds):.3f}")


def enable(on: bool) -> str:
    return "M17" if on else "M18"


def status() -> str:
    return "M114"


def info() -> str:
    """M115：固件/链路信息（卷130 新增，GRBL 惯例）。"""
    return "M115"


def estop() -> str:
    """M112：紧急停止（卷130 新增，GRBL 惯例）。任何通道都不得降级为"稍后重试"。"""
    return "M112"


def clear_fault() -> str:
    """$X：显式清除故障（卷130 新增，GRBL 惯例）。

    必须有这一条：堵转属硬件异常，不能"设个新目标就自动恢复"——
    那会在机械卡死时反复冲击舵机（卷129 W129-03 已定的语义）。
    """
    return "$X"


def feed_hold() -> str:
    """`!`：进给保持 = 平滑停下但保持使能（卷130 新增，GRBL 惯例）。

    失联 failsafe 的「停住」用它，**不用 M112**——M112 是锁死故障，
    而链路抖动不该把云台锁进故障态。
    """
    return "!"


def resume() -> str:
    """`~`：解除进给保持（卷130 新增）。"""
    return "~"


def set_failsafe(code: int, hold_s: float | None = None) -> str:
    """`$FS=<code>[,<hold_s>]`：下发失联策略（卷130 新增）。

    **为什么必须由固件执行**：链路断了主机发不出任何命令，
    失联保护只能在设备侧靠自己的心跳超时判定——主机这条只是"约定策略"。
    """
    text = f"$FS={int(code)}"
    if hold_s is not None:
        text += f",{float(hold_s):.1f}"
    return _check_line(text)


# ---------------------------------------------------------------------------
# 状态行 / 信息行解析
# ---------------------------------------------------------------------------


def parse_kv(text: str) -> Dict[str, Any]:
    """解析 key=value 空格分隔的一行 → dict（值统一转 float，整数在调用方取整）。"""
    out: Dict[str, Any] = {}
    for key, value in _KV_PAIR.findall(text or ""):
        try:
            out[key] = float(value)
        except ValueError:  # pragma: no cover - 正则已保证是数字
            continue
    return out


#: M114 状态行必须包含的字段（缺任一 → 视为畸形回显，不猜测）
_STATUS_REQUIRED = ("az", "el", "moving", "fault", "enabled")


def parse_status(text: str) -> Dict[str, Any] | None:
    """解析 M114 状态行。字段不全返回 None——**不猜**，让调用方按链路异常处理。"""
    raw = parse_kv(text)
    if any(k not in raw for k in _STATUS_REQUIRED):
        return None
    return {
        "az_deg": round(raw["az"], 3),
        "el_deg": round(raw["el"], 3),
        "moving": bool(raw["moving"]),
        "fault": bool(raw["fault"]),
        "enabled": bool(raw["enabled"]),
        "fault_ring": int(raw.get("ring", 0)),
        "link_up": bool(raw.get("link", 1)),
        "heartbeat_age_s": round(raw.get("hb_age", 0.0), 3),
        "held": bool(raw.get("hold", 0)),
    }


def format_status(az_deg: float, el_deg: float, moving: bool, fault: bool, enabled: bool,
                  fault_ring: int = 0, link_up: bool = True,
                  heartbeat_age_s: float = 0.0, held: bool = False) -> str:
    """生成 M114 状态行（固件侧同一格式；测试与模拟器共用）。

    字段顺序固定，`az=`/`el=` 在最前——W129-04 的自检断言 `strstr(..., "az=30.00")`
    依赖这个前缀，后续加字段只能往后追加。
    """
    return (f"az={az_deg:.2f} el={el_deg:.2f} moving={1 if moving else 0} "
            f"fault={1 if fault else 0} ring={int(fault_ring)} enabled={1 if enabled else 0} "
            f"link={1 if link_up else 0} hb_age={heartbeat_age_s:.2f} hold={1 if held else 0}")


def parse_info(text: str) -> Dict[str, Any]:
    """解析 M115 信息行（缺字段给默认值——信息行是尽力而为，不阻断主流程）。"""
    raw = parse_kv(text)
    return {
        "fw_version": str(raw.get("fw", 0.0)),
        "uptime_s": int(raw.get("uptime", 0)),
        "rssi_dbm": int(raw.get("rssi", 0)),
        "transport": "lora" if int(raw.get("lora", 0)) else "serial",
        "failsafe": int(raw.get("failsafe", 0)),
    }


__all__ = [
    "MAX_LINE", "REPLY_OK", "SUPPORTED_G", "SUPPORTED_M", "SUPPORTED_SPECIAL",
    "ReplyKind", "ProtocolError",
    "classify", "is_ok", "error_code", "validate_line",
    "move", "home", "hold", "enable", "status", "info", "estop", "clear_fault",
    "feed_hold", "resume", "set_failsafe",
    "parse_kv", "parse_status", "format_status", "parse_info",
]
