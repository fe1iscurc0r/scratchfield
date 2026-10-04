"""G 代码命令面**规格**测试（卷129 W129-04，主机端）。

固件端证据 = arduino-cli 编译通过 + 上机自检；这里独立实现同一套规格：
G 码子集解析、直线插补速度分配（两轴同时到达）、REPL 回显语义（ok / error:limit / error:unknown）。

运行：.venv/Scripts/python.exe -m pytest hardware/antenna-rotator/tests -q
"""
from __future__ import annotations

import math
import re

GCODE_RE = re.compile(r"^(G|M)(\d+)$", re.IGNORECASE)

SUPPORTED_G = {0: "G0", 1: "G1", 4: "G4", 28: "G28"}
SUPPORTED_M = {17: "M17", 18: "M18", 114: "M114"}


def parse_gcode(line: str) -> dict:
    """规格解析器：返回 {ok, id, x, y, f, p, error}。"""
    out = {"ok": False, "id": None, "x": None, "y": None, "f": None, "p": None, "error": ""}
    if not line:
        out["error"] = "empty"
        return out
    body = line.split(";")[0].strip().upper()
    if not body:
        out["error"] = "unknown"
        return out
    found = False
    for token in body.split():
        m = GCODE_RE.match(token)
        if m:
            kind, code = m.group(1).upper(), int(m.group(2))
            if kind == "G":
                if code not in SUPPORTED_G:
                    out["error"] = f"unsupported_g{code}"
                    return out
                out["id"] = SUPPORTED_G[code]
            else:
                if code not in SUPPORTED_M:
                    out["error"] = f"unsupported_m{code}"
                    return out
                out["id"] = SUPPORTED_M[code]
            found = True
        elif token[0] == "X":
            out["x"] = float(token[1:])
        elif token[0] == "Y":
            out["y"] = float(token[1:])
        elif token[0] == "F":
            out["f"] = float(token[1:])
        elif token[0] == "P":
            out["p"] = float(token[1:])
    if not found:
        out["error"] = "unknown"
        return out
    out["ok"] = True
    return out


def plan_linear(dx: float, dy: float, feed: float) -> dict:
    """直线插补：两轴耗时相等 → 时长 = max|d| / feed，各轴速度按自身行程分配。"""
    longest = max(abs(dx), abs(dy))
    if feed <= 0 or longest <= 1e-6:
        return {"ok": False}
    duration = longest / feed
    return {"ok": True, "duration_s": duration, "v_az": abs(dx) / duration, "v_el": abs(dy) / duration}


class FakeSink:
    def __init__(self):
        self.moves = []
        self.homes = 0
        self.hold_s = 0.0
        self.enabled = False
        self.last = (0.0, 0.0)

    def move_to(self, az, el, feed, linear) -> str | None:
        self.moves.append((az, el, feed, linear))
        if az is not None and not (0.0 <= az <= 360.0):
            return "error:limit"
        self.last = (az or self.last[0], el or self.last[1])
        return None

    def handle(self, line: str) -> str:
        cmd = parse_gcode(line)
        if not cmd["ok"]:
            return f"error:{cmd['error'] or 'unknown'}"
        if cmd["id"] in ("G0", "G1"):
            err = self.move_to(cmd["x"], cmd["y"], cmd["f"] or 10.0, cmd["id"] == "G1")
            return err or "ok"
        if cmd["id"] == "G28":
            self.homes += 1
            return "ok"
        if cmd["id"] == "G4":
            self.hold_s = cmd["p"] or 0.0
            return "ok"
        if cmd["id"] == "M17":
            self.enabled = True
            return "ok"
        if cmd["id"] == "M18":
            self.enabled = False
            return "ok"
        if cmd["id"] == "M114":
            return f"az={self.last[0]:.2f} el={self.last[1]:.2f} moving=0 fault=0 enabled={1 if self.enabled else 0}"
        return "error:unknown"


# ---------------------------------------------------------------------------
# 1. 解析
# ---------------------------------------------------------------------------


def test_parse_basic_commands():
    cmd = parse_gcode("G0 X30 Y-10 F5")
    assert cmd["ok"] and cmd["id"] == "G0"
    assert cmd["x"] == 30.0 and cmd["y"] == -10.0 and cmd["f"] == 5.0

    assert parse_gcode("G1 X12.5 F8")["id"] == "G1"
    assert parse_gcode("M114")["id"] == "M114"
    assert parse_gcode("G4 P1.5")["p"] == 1.5
    assert parse_gcode("g28")["id"] == "G28", "大小写不敏感"
    assert parse_gcode("G0 X1 ; 注释")["x"] == 1.0, "分号后为注释"


def test_parse_errors():
    assert parse_gcode("G99")["error"] == "unsupported_g99"
    assert parse_gcode("M999")["error"] == "unsupported_m999"
    assert parse_gcode("hello")["error"] == "unknown"
    assert parse_gcode("")["error"] == "empty"


# ---------------------------------------------------------------------------
# 2. 直线插补
# ---------------------------------------------------------------------------


def test_linear_interpolation_two_axes_arrive_together():
    plan = plan_linear(90.0, 30.0, 30.0)
    assert plan["ok"]
    assert abs(plan["duration_s"] - 3.0) < 1e-9, "时长 = 最长行程 / F"
    assert abs(plan["v_az"] - 30.0) < 1e-9, "最长行程轴全速"
    assert abs(plan["v_el"] - 10.0) < 1e-9, "短行程轴按比例降速"

    # 同时到达：各自用时相同
    t_az = abs(90.0) / plan["v_az"]
    t_el = abs(30.0) / plan["v_el"]
    assert abs(t_az - t_el) < 1e-9, "两轴耗时相等（同时到达）"


def test_linear_interpolation_edge_cases():
    assert plan_linear(0.0, 0.0, 10.0)["ok"] is False, "零位移不规划"
    assert plan_linear(10.0, 0.0, 0.0)["ok"] is False, "速度非正不规划"
    single = plan_linear(0.0, 20.0, 10.0)
    assert single["ok"] and abs(single["duration_s"] - 2.0) < 1e-9
    assert single["v_az"] == 0.0 and abs(single["v_el"] - 10.0) < 1e-9, "单轴运动另一轴速度为 0"


# ---------------------------------------------------------------------------
# 3. REPL 语义
# ---------------------------------------------------------------------------


def test_repl_round_trip_and_semantics():
    sink = FakeSink()
    assert sink.handle("M17") == "ok" and sink.enabled is True
    assert sink.handle("G0 X30 Y10 F5") == "ok"
    assert sink.handle("G4 P2") == "ok" and abs(sink.hold_s - 2.0) < 1e-9
    status = sink.handle("M114")
    assert "az=30.00" in status and "enabled=1" in status
    assert sink.handle("G28") == "ok" and sink.homes == 1
    assert sink.moves[0] == (30.0, 10.0, 5.0, False), "G0 非插补（linear=False）"
    assert sink.handle("G1 X10") == "ok" and sink.moves[1][3] is True, "G1 走直线插补"


def test_repl_error_semantics():
    sink = FakeSink()
    assert sink.handle("G99") == "error:unsupported_g99"
    assert sink.handle("hello") == "error:unknown"
    assert sink.handle("G0 X400") == "error:limit", "越限回显 error:limit（运动层拒绝）"


def test_repl_default_feed_when_missing():
    sink = FakeSink()
    sink.handle("G0 X5")
    assert sink.moves[0][2] == 10.0, "未给 F 时默认 10°/s"
