"""rtl_tcp 协议探针（纯协议层 · 不依赖 GPL 代码）。

授粉来源：rtl_tcp_andro（GPL-2.0-or-later）。rtl_tcp 协议本身是公开标准，
可自由参考；本探针独立实现 rtl_tcp 协议的最小交互（greeting + SET 命令编解码），
用 mock 服务验证协议交互结构，不依赖 GPL 代码、不接真实 SDR 设备。

rtl_tcp 协议要点（公开标准）：
- 服务端 greeting：`RTL0`(4 字节 ASCII) + tuner_type(uint32 大端)
- 命令：cmd(1) + dummy(1，填充) + param_len(2 大端) + payload
- 常用 opcode：SET_FREQ=0x01 / SET_SAMPLE_RATE=0x02 / SET_GAIN_MODE=0x03 / SET_GAIN=0x04
"""
from __future__ import annotations

import json
import struct

_MAGIC = b"RTL0"

SET_FREQ = 0x01
SET_SAMPLE_RATE = 0x02
SET_GAIN_MODE = 0x03
SET_GAIN = 0x04

_OPCODE_NAMES = {
    SET_FREQ: "SET_FREQ",
    SET_SAMPLE_RATE: "SET_SAMPLE_RATE",
    SET_GAIN_MODE: "SET_GAIN_MODE",
    SET_GAIN: "SET_GAIN",
}


def _u32(n: int) -> bytes:
    return struct.pack(">I", n)


def _make_greeting(tuner_type: int) -> bytes:
    """服务端 greeting：RTL0 + tuner_type(uint32 大端)。"""
    return _MAGIC + _u32(tuner_type)


def _parse_greeting(data: bytes) -> tuple[str, int]:
    magic = data[:4].decode("ascii")
    tuner = struct.unpack(">I", data[4:8])[0]
    return magic, tuner


def _make_command(opcode: int, payload: bytes) -> bytes:
    """命令：cmd(1) + dummy(1，填充) + param_len(2 大端) + payload。"""
    return bytes([opcode, 0]) + struct.pack(">H", len(payload)) + payload


def _parse_command(data: bytes) -> dict:
    """解析命令，解码已知 payload 字段（freq/sample_rate/gain）。"""
    opcode = data[0]
    dummy = data[1]
    param_len = struct.unpack(">H", data[2:4])[0]
    payload = data[4:4 + param_len]
    result = {
        "cmd": _OPCODE_NAMES.get(opcode, f"0x{opcode:02x}"),
        "dummy": dummy,
        "param_len": param_len,
    }
    if opcode == SET_FREQ and param_len == 4:
        result["freq"] = struct.unpack(">I", payload)[0]
    elif opcode == SET_SAMPLE_RATE and param_len == 4:
        result["sample_rate"] = struct.unpack(">I", payload)[0]
    elif opcode == SET_GAIN and param_len == 4:
        result["gain"] = struct.unpack(">I", payload)[0]
    return result


def probe() -> dict:
    """mock rtl_tcp 交互：greeting + SET_SAMPLE_RATE/SET_FREQ/SET_GAIN 编解码回环。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "greeting",
    "commands", "protocol_fields"}``。
    """
    # 1. mock 服务端 greeting
    magic, tuner = _parse_greeting(_make_greeting(5))

    # 2. 客户端命令（编码→解码回环，验证协议交互结构）
    raw_cmds = [
        _make_command(SET_SAMPLE_RATE, _u32(2_000_000)),
        _make_command(SET_FREQ, _u32(1_090_000_000)),
        _make_command(SET_GAIN, _u32(404)),
    ]
    parsed = [_parse_command(c) for c in raw_cmds]

    return {
        "package": "rtl_tcp",
        "status": "success" if magic == "RTL0" else "degraded",
        "license": "rtl_tcp 协议公开标准（自由参考）/ rtl_tcp_andro 实现 GPL-2.0-or-later（只参考设计）",
        "summary": "mock rtl_tcp 交互：greeting(RTL0+tuner) + SET_SAMPLE_RATE/SET_FREQ/SET_GAIN 命令编解码回环",
        "greeting": {"magic": magic, "tuner_type": tuner},
        "commands": parsed,
        "protocol_fields": ["magic", "tuner_type", "cmd", "dummy", "param_len", "sample_rate", "freq", "gain"],
    }


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
