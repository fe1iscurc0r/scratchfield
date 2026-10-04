"""rsba1_adapter - Icom IC-705 远程控制 (RS-BA1 逆向协议栈) 适配层。

架构:
    rsba1   (scratchpad/vendor/rsba1-core/src 或本机 dev sibling src)
        | lazy import
    rsba1_adapter   (本模块: 封装 6 个 ic705_* 工具, manifest 型 bridge)
        | handle_handoff
    mcpserver (unified_call) -> 陆墨

连接策略 (技术要求 1/3):
    优先 RadioLink 直连 IC-705 - 纯 socket, 跨平台, 不依赖 pywin32。
    不可用 (未通电/超时/授权失败) 时, 若本机 Windows 且 pywin32 可用,
    fallback 到 RemoteUty Mailslot 路径 (CivViaExecCmdSender)。
    两路都失败则抛人类可读错误, 绝不静默空返回。

工具 (spec 表):
    ic705_read_freq()  -> {freq_mhz: float}
    ic705_read_mode()  -> {mode: str, filter: int, mode_code: int}
    ic705_read_smeter()-> {s_unit: int, s_db: float, s_raw: int}
    ic705_set_freq(freq_mhz: float) -> {success: bool, freq_mhz: float}
    ic705_ptt(state: "TX"|"RX") -> {success: bool}
    ic705_get_status() -> {freq, mode, filter, s_unit, ptt}

安全 (技术要求 5): ic705_set_freq 走业余频段白名单校验
    (1.8-30MHz / 50-54MHz / 144-148MHz, civ_commands.AMATEUR_BANDS), 越界拒绝。
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CIV_IC705 = 0xA4      # IC-705 CI-V 地址 (收包 from)
CIV_FROM = 0x00       # 控制器地址 (必须 0x00 电台才应答)

# IC-705 模式码 -> 名称 (与 rsba1.mailslot.civ_response.MODE_NAMES 一致, 本地内置)
MODE_NAMES: Dict[int, str] = {
    0x01: "LSB", 0x02: "USB", 0x03: "AM", 0x04: "CW", 0x05: "RTTY",
    0x06: "FM", 0x07: "WFM", 0x08: "CW-R", 0x09: "RTTY-R",
}

# 工具白名单 (handle_handoff 只放行这些)
TOOLS = (
    "ic705_read_freq", "ic705_read_mode", "ic705_read_smeter",
    "ic705_set_freq", "ic705_ptt", "ic705_get_status",
)


# ============================================================
# rsba1 包定位 (懒加载; import 本模块永不负因缺依赖而炸)
# ============================================================

def _candidate_src_paths() -> list:
    """rsba1 包可能的 src 目录 (按优先级; 兼容 scratchpad 布局与 rs-ba1-reverse 仓内放置)。"""
    here = Path(__file__).resolve()
    env = os.environ.get("RSBA1_SRC_PATH", "").strip()
    paths = []
    if env:
        paths.append(Path(env))
    # scratchpad 布局: mcpserver/adapters/rsba1_adapter/adapter.py → parents[3] = scratchpad
    paths.append(here.parents[3] / "vendor" / "rsba1-core" / "src")
    paths.append(here.parents[3].parent / "rs-ba1-reverse" / "src")  # sibling 开发源兜底
    # 自包含: 放在 rs-ba1-reverse/tools/rsba1_adapter/ 时 parents[2] = 仓库根
    paths.append(here.parents[2] / "src")
    return [p for p in paths if (p / "rsba1").is_dir()]


def _rsba1_found() -> bool:
    return importlib.util.find_spec("rsba1") is not None


def _import_rsba1(module: str = "rsba1.radio_link") -> Any:
    """懒导入 rsba1 子模块; 找不到包装成人类可读错误。"""
    for p in _candidate_src_paths():
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    if not _rsba1_found():
        raise RuntimeError(
            "无法定位 rsba1 包: 请克隆 rsba1-core 到 scratchpad/vendor/rsba1-core, "
            "或设置 RSBA1_SRC_PATH 指向含 rsba1/ 的 src 目录。"
        )
    try:
        return importlib.import_module(module)
    except Exception as e:
        raise RuntimeError(f"导入 rsba1 失败 ({module}): {e}") from e


def _civmod() -> Any:
    """懒加载 rsba1.ctypes_wrappers.civ_commands (帧构造 + 白名单)。"""
    return _import_rsba1("rsba1.ctypes_wrappers.civ_commands")


def _smeter_approx(raw: int) -> tuple:
    """Best-effort 把 IC-705 S-meter 原始值(0-255) 换算为 (s_unit, s_db).

    近似 (真机 S 表未定, 线性标称换算; s_raw 为权威原始值):
        dBm = -127 + raw*(114/255):  raw=0 ~ S0(-127dBm), raw=255 ~ S9+60dB(-13dBm)
        S0-S9 每档 6dB; S9 之上每 +10dB 上一当档 (封顶 +50dB)。
    """
    raw = int(raw)
    s_db = round(-127.0 + raw * (114.0 / 255.0), 1)
    if s_db <= -73.0:                                # S0 .. S9
        s_unit = max(0, int(round((-73.0 - s_db) / 6.0)))
        return s_unit, s_db
    over = int((s_db + 73.0) / 10.0)                 # S9 之上每 +10dB
    return min(9 + over, 14), s_db


class Rsba1Ic705Bridge:
    """mcpserver scan_and_register_mcp_agents 入口 (同 hamlog/pdf2md 约定)。"""

    name = "rsba1_ic705"

    def __init__(self) -> None:
        self._link: Any | None = None    # RadioLink 直连会话
        self._sender: Any | None = None  # RemoteUty fallback 发送器
        self._mode: str = "none"            # "radio_link" | "remote_uty" | "none"
        self._init_attempted = False
    # ============================================================
    # 连接管理 (技术要求 1/3: RadioLink 直连优先, RemoteUty 兜底)
    # ============================================================

    def ensure(self) -> None:
        """确保存在一条可用控制通道 (RadioLink 直连优先, RemoteUty 兜底)。

        失败明确报错 (绝不静默): 两路都不可用时抛人类可读 RuntimeError,
        提示可能的原因 (电台未通电 / 不在同一网络 / 授权失败 / 平台不支持兜底)。
        """
        if self._mode != "none":
            return
        if self._init_attempted:
            raise RuntimeError(
                "IC-705 连接不可用: RadioLink 直连与 RemoteUty 兜底均已尝试失败。"
                "请确认电台 RS-BA1 Server Function 已开启、且密钥/凭证与电台侧"
                "RS-BA1 用户一致 (默认 192.168.0.31 / linnan)。见日志详情。"
            )
        # 无包快速失败（W79-01 无包降级）: 先补候选路径再判定, 缺 rsba1 直接给出
        # 「无法定位 rsba1 包」根因提示, 而不是伪装成连接失败。
        for p in _candidate_src_paths():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
        if not _rsba1_found():
            raise RuntimeError(
                "无法定位 rsba1 包: 请克隆 rsba1-core 到 scratchpad/vendor/rsba1-core, "
                "或设置 RSBA1_SRC_PATH 指向含 rsba1/ 的 src 目录。"
            )
        self._init_attempted = True
        if self._try_radio_link():
            return
        if self._try_remote_uty():
            return
        raise RuntimeError(
            "IC-705 连接不可用: RadioLink 直连失败, 且 RemoteUty 兜底不可用 "
            "(非 Windows / 未安装 pywin32 / 已显式禁用)。详细原因见日志。"
        )

    def _try_radio_link(self) -> bool:
        """RadioLink 直连 (纯 socket, 跨平台, 不依赖 pywin32)。失败打日志返回 False。"""
        try:
            rl = _import_rsba1("rsba1.radio_link")
            host = os.environ.get("RSBA1_HOST", "192.168.0.31")
            user = os.environ.get("RSBA1_USER", "linnan")
            pwd = os.environ.get("RSBA1_PASS", "shenyaodiyi")
            link = rl.RadioLink(host, user, pwd, verbose=False)
            link.open(retries=2)
            self._link, self._mode = link, "radio_link"
            return True
        except Exception as e:
            logger.warning("[rsba1] RadioLink 直连失败 (将判断是否兜底): %s", e)
            return False

    def _try_remote_uty(self) -> bool:
        """RemoteUty Mailslot 兜底 (仅 Windows + pywin32 可用 + 未显式禁用)。

        注意: ExecCmd 是 fire-and-forget; 闭环查询 (query_*) 要求
        RemoteController 未运行 (否则响应 mailslot 被占用)。这是 best-effort。
        """
        if os.environ.get("RSBA1_ALLOW_REMOTE_UTY", "1").strip().lower() in (
            "0", "false", "no", "off",
        ):
            return False
        try:
            import win32pipe  # noqa: F401  pywin32 可用性探测
        except Exception:
            return False
        try:
            mod = _import_rsba1("rsba1.mailslot.civ_via_execcmd")
            sender = mod.CivViaExecCmdSender(
                to_addr=CIV_IC705, from_addr=CIV_FROM, sub_cmd=0,
            )
            sender.open()
            self._sender, self._mode = sender, "remote_uty"
            return True
        except Exception as e:
            logger.warning("[rsba1] RemoteUty 兜底不可用: %s", e)
            return False

    def close(self) -> None:
        """释放底层会话 (幂等)。RadioLink 优雅退出; RemoteUty 关 mailslot。"""
        if self._mode == "radio_link" and self._link is not None:
            try:
                self._link.close()
            except Exception as e:
                logger.warning("[rsba1] RadioLink close 出错: %s", e)
        if self._mode == "remote_uty" and self._sender is not None:
            try:
                self._sender.close()
            except Exception as e:
                logger.warning("[rsba1] RemoteUty close 出错: %s", e)
        self._mode = "none"

    def __enter__(self) -> "Rsba1Ic705Bridge":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False

    # ============================================================
    # 6 个工具函数 (对 RadioLink / RemoteUty 双后端做统一封装)
    # 所有异常转为 {ok: False, error: 人类可读消息}, 绝不静默空返回
    # ============================================================

    # ---- RadioLink 后端 ----
    def _rl_smeter(self) -> int:
        """RadioLink 无公开 read_smeter, 用 _civ_query 原语查询 0x1A/0x03。"""
        resp = self._link._civ_query(bytes([0x1A, 0x03]), 0x1A, 2.0)
        _, _, _, payload = _civmod().parse_frame(resp)
        if len(payload) < 2 or payload[0] != 0x03:
            raise RuntimeError(f"S-meter 应答格式异常: payload={payload.hex()}")
        return payload[1]

    def _rl_ptt(self) -> bool:
        """读 PTT 状态 (cmd=0x14 子命令 0x0C) -> True=TX。"""
        resp = self._link._civ_query(bytes([0x14, 0x0C]), 0x14, 2.0)
        _, _, _, payload = _civmod().parse_frame(resp)
        return bool(payload[-1] != 0) if payload else False

    # ---- 双后端读写分派 ----
    def _do_read_freq(self) -> int:
        if self._mode == "radio_link":
            return self._link.read_freq()
        return self._sender.query_freq(timeout_ms=2500)

    def _do_read_mode(self) -> tuple:
        if self._mode == "radio_link":
            return self._link.read_mode()
        return self._sender.query_mode(timeout_ms=2500)

    def _do_read_smeter(self) -> int:
        if self._mode == "radio_link":
            return self._rl_smeter()
        return self._sender.query_smeter(timeout_ms=2500)

    def _do_set_freq(self, hz: int) -> None:
        if self._mode == "radio_link":
            self._link.set_freq(hz)      # 内部含白名单 assert
            return
        self._sender.send_set_freq(hz)   # fire-and-forget (payload 构造时校验白名单)

    def _do_ptt(self, on: bool) -> None:
        if self._mode == "radio_link":
            self._link.ptt(on)
            return
        (self._sender.send_ptt_on if on else self._sender.send_ptt_off)()

    # ---- 工具入口 ----
    def _read_freq(self) -> dict:
        """读当前频率 -> {ok, freq_mhz}。"""
        try:
            self.ensure()
            hz = self._do_read_freq()
            return {"ok": True, "freq_mhz": round(hz / 1e6, 6)}
        except Exception as e:
            return {"ok": False, "error": _human_err("读取频率", e)}

    def _read_mode(self) -> dict:
        """读当前模式 -> {ok, mode, filter, mode_code}。"""
        try:
            self.ensure()
            mode_code, filt = self._do_read_mode()
            return {
                "ok": True,
                "mode": MODE_NAMES.get(mode_code, f"未知({mode_code})"),
                "mode_code": mode_code,
                "filter": filt,
            }
        except Exception as e:
            return {"ok": False, "error": _human_err("读取模式", e)}

    def _read_smeter(self) -> dict:
        """读信号强度 -> {ok, s_unit, s_db, s_raw}。"""
        try:
            self.ensure()
            raw = self._do_read_smeter()
            s_unit, s_db = _smeter_approx(raw)
            return {"ok": True, "s_unit": s_unit, "s_db": s_db, "s_raw": raw}
        except Exception as e:
            return {"ok": False, "error": _human_err("读取信号强度", e)}

    def _set_freq(self, freq_mhz: float) -> dict:
        """设频率 (业余段白名单校验) -> {ok, freq_mhz}。越界拒绝。"""
        try:
            hz = int(round(float(freq_mhz) * 1e6))
            civcmd = _civmod()
            civcmd.assert_allowed_freq(hz)   # 技术要求 5: 白名单强制, 越界抛 ValueError
            self.ensure()
            self._do_set_freq(hz)
            return {"ok": True, "freq_mhz": round(hz / 1e6, 6)}
        except Exception as e:
            return {"ok": False, "error": _human_err("设置频率", e)}

    def _ptt(self, state: str) -> dict:
        """PTT 控制 (state: "TX"|"RX") -> {ok, state}。⚠️ TX 会真正发射。"""
        try:
            s = str(state or "").strip().upper()
            if s not in ("TX", "RX", "ON", "OFF"):
                return {"ok": False, "error": f"state 必须是 TX/RX (或 ON/OFF), 收到: {state!r}"}
            on = s in ("TX", "ON")
            self.ensure()
            self._do_ptt(on)
            return {"ok": True, "state": "TX" if on else "RX"}
        except Exception as e:
            return {"ok": False, "error": _human_err("PTT 控制", e)}

    def _get_status(self) -> dict:
        """组合状态 -> {ok, freq_mhz, mode, filter, s_unit, s_db, ptt}。"""
        try:
            self.ensure()
            hz = self._do_read_freq()
            mode_code, filt = self._do_read_mode()
            raw = self._do_read_smeter()
            s_unit, s_db = _smeter_approx(raw)
            ptt = self._rl_ptt() if self._mode == "radio_link" else None
            return {
                "ok": True,
                "freq_mhz": round(hz / 1e6, 6),
                "mode": MODE_NAMES.get(mode_code, f"未知({mode_code})"),
                "filter": filt,
                "s_unit": s_unit,
                "s_db": s_db,
                "ptt": "TX" if ptt is True else ("RX" if ptt is False else "unknown"),
            }
        except Exception as e:
            return {"ok": False, "error": _human_err("读取电台状态", e)}

    # ============================================================
    # MCP agent 桥 (manifest 型; handle_handoff 统一工具分发)
    # ============================================================

    def _tools(self) -> dict:
        return {
            "ic705_read_freq": self._read_freq,
            "ic705_read_mode": self._read_mode,
            "ic705_read_smeter": self._read_smeter,
            "ic705_set_freq": self._set_freq,
            "ic705_ptt": self._ptt,
            "ic705_get_status": self._get_status,
        }

    async def handle_handoff(self, task: dict) -> str:
        """unified_call 入口: 分发到 6 个 ic705_* 工具, 返回 JSON 字符串。

        参数解析同 pdf2md 约定: 平铺在 task 里 / 兼容嵌套 params、arguments。
        空 dict 也是合法参数集 (无参工具), 因此用键存在判断而非真值。
        """
        tool_name = str(task.get("tool_name") or "").strip()
        tools = self._tools()
        if not tool_name:
            return json.dumps(
                {"status": "error", "message": "缺少 tool_name", "data": {}},
                ensure_ascii=False,
            )
        fn = tools.get(tool_name)
        if fn is None:
            return json.dumps(
                {"status": "error", "message": f"未知工具 {tool_name}，可用: {', '.join(TOOLS)}", "data": {}},
                ensure_ascii=False,
            )
        if isinstance(task.get("params"), dict):
            arguments = task["params"]
        elif isinstance(task.get("arguments"), dict):
            arguments = task["arguments"]
        else:
            arguments = {
                k: v for k, v in task.items()
                if k not in ("tool_name", "agentType", "service_name", "_tool_call_id")
            }
        try:
            data = fn(**arguments)
            if isinstance(data, dict) and data.get("ok") is False:
                return json.dumps(
                    {"status": "error", "message": data.get("error", "未知错误"), "data": data},
                    ensure_ascii=False,
                )
            return json.dumps(
                {"status": "success", "message": "ok", "data": data},
                ensure_ascii=False, default=str,
            )
        except TypeError as e:
            return json.dumps(
                {"status": "error", "message": f"参数错误: {e}", "data": {}},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"status": "error", "message": f"{type(e).__name__}: {e}", "data": {}},
                ensure_ascii=False,
            )


# ============================================================
# 异常转人类可读消息
# ============================================================

def _human_err(action: str, e: Exception) -> str:
    """把底层异常转成带动作上下文的人类可读错误 (不静默)。"""
    msg = str(e)
    base = f"{action}失败: {type(e).__name__}: {e}"
    if "超时" in msg or "Timeout" in type(e).__name__:
        base += " (电台未响应, 请确认 IC-705 已开机且 RS-BA1 Server Function 开启)"
    elif "认证" in msg or "auth" in type(e).__name__.lower() or "Login" in type(e).__name__:
        base += " (IC-705 登录凭证错误, 请检查用户名/密码)"
    elif "ConnectTrans" in msg:
        base += " (连接被拒, 可能是会话被挤占, 需重启电台的网络服务器)"
    return base


# ============================================================
# 最小 MCP stdio server (--stdio, 供 mcporter_bridge 接入; 跨平台)
# ============================================================

def _stdio_main() -> None:
    import asyncio
    bridge = Rsba1Ic705Bridge()
    tool_defs = [
        {"name": "ic705_read_freq", "description": "读取 IC-705 当前频率",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "ic705_read_mode", "description": "读取 IC-705 当前模式与滤波器",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "ic705_read_smeter", "description": "读取 IC-705 当前信号强度 (S 档 + dBm)",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "ic705_set_freq", "description": "设置 IC-705 频率 (业余段白名单校验, 单位 MHz)",
         "inputSchema": {"type": "object",
                         "properties": {"freq_mhz": {"type": "number", "description": "频率 (MHz), 如 7.074"}},
                         "required": ["freq_mhz"]}},
        {"name": "ic705_ptt", "description": "控制 IC-705 PTT (TX 会真正发射, 慎用)",
         "inputSchema": {"type": "object",
                         "properties": {"state": {"type": "string", "description": "TX 或 RX", "enum": ["TX", "RX"]}},
                         "required": ["state"]}},
        {"name": "ic705_get_status", "description": "读取 IC-705 组合状态 (频率+模式+信号+PTT)",
         "inputSchema": {"type": "object", "properties": {}}},
    ]

    async def _handle(msg: dict):
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": mid,
                    "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                               "serverInfo": {"name": "rsba1_ic705", "version": "1.0.0"}}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": tool_defs}}
        if method == "tools/call":
            params = msg.get("params") or {}
            raw = await bridge.handle_handoff({
                "tool_name": params.get("name", ""),
                "params": params.get("arguments") or {},
            })
            payload = json.loads(raw)
            return {"jsonrpc": "2.0", "id": mid,
                    "result": {"content": [{"type": "text", "text": raw}],
                               "isError": payload.get("status") != "success"}}
        if method in ("notifications/initialized", "ping"):
            return None
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"method not found: {method}"}}

    loop = asyncio.new_event_loop()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = loop.run_until_complete(_handle(msg))
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        _stdio_main()
    else:
        print("用法: python adapter.py --stdio  (MCP stdio server)")