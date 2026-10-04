"""Sentinel-Link v1 —— LoRaCanary 节点回传协议（编解码 + CRC32）。

协议定位：节点（ESP32-S3 + SX1278）→ 网关（apiserver）的**单向数据面**
+ 网关 → 节点的**控制面**。传输载体为 JSON Lines（NDJSON），可跑在
serial / WiFi-TCP / 文件（离线回放）三种通道上，帧格式完全一致。

设计纪律（与工单卷187 一致）：
- 字段名**冻结为英文 snake_case**，节点固件按 README.md 实现，避免二次翻译。
- **降级而非崩溃**：坏 JSON / CRC 不匹配 / 未知 type 一律走 `decode()` 返回
  `(None, reason)`，由网关计数丢弃；只有**编码侧参数非法**才抛 `SentinelProtocolError`。
- CRC32 覆盖 **payload 的规范化 JSON 字节**（`sort_keys=True`、`separators=(",",":")`、
  `ensure_ascii=False`），节点侧可照此独立实现，跨语言一致。

帧结构（NDJSON 一行一帧）::

    {"t": "scan", "node_id": "canary-01", "ts": 1743561600.123,
     "fw": "1.1.0", "crc32": "9f3a1c2e", "payload": { ... }}

其中 `payload` 因 `t` 而异：

- `t="scan"`  节点→网关：频谱扫描帧（`rssi_scan` 数组 + 可选 env）
- `t="env"`   节点→网关：纯环境帧（`env` 对象）
- `t="hello"` 节点→网关：上线握手（`fw` / `caps`）
- `t="cmd"`   网关→节点：控制命令（`cmd` / 参数）
- `t="ack"`   节点→网关：命令回执（`cmd_id` / `ok`）
"""
from __future__ import annotations

import json
import zlib
from dataclasses import asdict, dataclass, field
from typing import Any

__all__ = [
    "CRC_HEX_LEN",
    "DEFAULT_SF_SET",
    "FRAME_TYPES",
    "NODE_FRAME_TYPES",
    "GATEWAY_FRAME_TYPES",
    "SentinelProtocolError",
    "ScanBin",
    "EnvSample",
    "canonical_payload_bytes",
    "compute_crc32",
    "encode_frame",
    "decode_frame",
    "decode",
    "make_scan_frame",
    "make_env_frame",
    "make_hello_frame",
    "make_cmd_frame",
    "make_ack_frame",
    "parse_scan_config",
]

# ── 常量（协议契约，勿随意改动）──────────────────────────────────────────
CRC_HEX_LEN = 8                       # CRC32 十六进制长度
DEFAULT_SF_SET = [7, 9, 10, 12]       # SX1278 常用扩频因子
DEFAULT_FREQ_RANGE = [433.0, 434.7]   # MHz，Canary 默认扫描区间
DEFAULT_DWELL_MS = 120

FRAME_TYPES = frozenset({"scan", "env", "hello", "cmd", "ack"})
NODE_FRAME_TYPES = frozenset({"scan", "env", "hello", "ack"})
GATEWAY_FRAME_TYPES = frozenset({"cmd"})


class SentinelProtocolError(ValueError):
    """协议层**编码侧**错误（参数非法，fail-fast，不参与降级）。"""


# ── 数据模型 ─────────────────────────────────────────────────────────────

@dataclass
class ScanBin:
    """单个频点的扫描结果。"""

    freq_mhz: float
    rssi_dbm: float
    sf: int = 0            # 0 = 未指定/宽扫

    def to_dict(self) -> dict[str, Any]:
        return {"freq_mhz": round(float(self.freq_mhz), 4),
                "rssi_dbm": round(float(self.rssi_dbm), 2),
                "sf": int(self.sf)}

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "ScanBin":
        if not isinstance(obj, dict):
            raise SentinelProtocolError("rssi_scan 元素必须是对象")
        try:
            freq = float(obj["freq_mhz"])
            rssi = float(obj["rssi_dbm"])
        except KeyError as e:
            raise SentinelProtocolError(f"rssi_scan 缺少字段: {e}") from e
        except (TypeError, ValueError) as e:
            raise SentinelProtocolError(f"rssi_scan 字段类型非法: {e}") from e
        return cls(freq_mhz=freq, rssi_dbm=rssi, sf=int(obj.get("sf") or 0))


@dataclass
class EnvSample:
    """环境采样（温湿压 + 电池 + 可选 GPS）。任一字段可为 None（传感器缺失）。"""

    temp_c: float | None = None
    hum_pct: float | None = None
    pres_hpa: float | None = None
    bat_mv: int | None = None
    lat: float | None = None
    lon: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "EnvSample":
        if obj is None:
            return cls()
        if not isinstance(obj, dict):
            raise SentinelProtocolError("env 必须是对象")
        def _f(key: str) -> float | None:
            v = obj.get(key)
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError) as e:
                raise SentinelProtocolError(f"env.{key} 类型非法: {e}") from e
        bat = obj.get("bat_mv")
        try:
            bat_mv = int(bat) if bat is not None else None
        except (TypeError, ValueError) as e:
            raise SentinelProtocolError(f"env.bat_mv 类型非法: {e}") from e
        return cls(temp_c=_f("temp_c"), hum_pct=_f("hum_pct"),
                   pres_hpa=_f("pres_hpa"), bat_mv=bat_mv,
                   lat=_f("lat"), lon=_f("lon"))


# ── CRC32 ────────────────────────────────────────────────────────────────

def canonical_payload_bytes(payload: Any) -> bytes:
    """把 payload 序列化为**规范化 JSON 字节**（CRC 的输入）。

    规范化 = `sort_keys=True` + 紧凑分隔符 + `ensure_ascii=False`。
    节点固件（C/Arduino）按同样规则拼串即可得到一致 CRC。
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def compute_crc32(payload: Any) -> str:
    """算 payload 的 CRC32，返回 8 位小写十六进制。"""
    return format(zlib.crc32(canonical_payload_bytes(payload)) & 0xFFFFFFFF, "08x")


# ── 编码 ─────────────────────────────────────────────────────────────────

def encode_frame(frame_type: str, node_id: str, ts: float, fw: str,
                 payload: dict[str, Any], *, with_crc: bool = True) -> str:
    """构造一帧 NDJSON 字符串（不含换行）。

    :raises SentinelProtocolError: 帧类型未知 / node_id 为空 / payload 非对象。
    """
    ftype = str(frame_type or "").strip()
    if ftype not in FRAME_TYPES:
        raise SentinelProtocolError(f"未知帧类型: {frame_type!r}（可用: {sorted(FRAME_TYPES)}）")
    nid = str(node_id or "").strip()
    if not nid:
        raise SentinelProtocolError("node_id 不能为空")
    if not isinstance(payload, dict):
        raise SentinelProtocolError("payload 必须是对象")
    try:
        ts_f = float(ts)
    except (TypeError, ValueError) as e:
        raise SentinelProtocolError(f"ts 不是数字: {ts!r}") from e

    frame: dict[str, Any] = {"t": ftype, "node_id": nid, "ts": round(ts_f, 3),
                             "fw": str(fw or ""), "payload": payload}
    if with_crc:
        frame["crc32"] = compute_crc32(payload)
    return json.dumps(frame, ensure_ascii=False, separators=(",", ":"))


def make_scan_frame(node_id: str, ts: float, fw: str, bins: list[ScanBin],
                    env: EnvSample | None = None,
                    event: str | None = None, **kw: Any) -> str:
    """频谱扫描帧（节点→网关）。`event` 取值 "cad_busy" / "packet" / None。"""
    payload: dict[str, Any] = {"rssi_scan": [b.to_dict() for b in bins]}
    if env is not None:
        e = env.to_dict()
        if e:
            payload["env"] = e
    if event:
        payload["event"] = str(event)
    return encode_frame("scan", node_id, ts, fw, payload, **kw)


def make_env_frame(node_id: str, ts: float, fw: str, env: EnvSample, **kw: Any) -> str:
    """纯环境帧（节点→网关）。"""
    return encode_frame("env", node_id, ts, fw, {"env": env.to_dict()}, **kw)


def make_hello_frame(node_id: str, ts: float, fw: str,
                     caps: dict[str, Any] | None = None, **kw: Any) -> str:
    """上线握手帧（节点→网关）。"""
    payload: dict[str, Any] = {"fw": str(fw or ""), "caps": caps or {}}
    return encode_frame("hello", node_id, ts, fw, payload, **kw)


def make_cmd_frame(gateway_id: str, ts: float, cmd: str,
                   params: dict[str, Any] | None = None,
                   cmd_id: str | None = None, **kw: Any) -> str:
    """控制命令帧（网关→节点）。`cmd` 如 "scan_config" / "reboot" / "sync_time"。"""
    payload: dict[str, Any] = {"cmd": str(cmd)}
    if params:
        payload.update(params)
    if cmd_id:
        payload["cmd_id"] = str(cmd_id)
    return encode_frame("cmd", gateway_id, ts, "gateway", payload, **kw)


def make_ack_frame(node_id: str, ts: float, fw: str, cmd_id: str, ok: bool,
                   detail: str = "", **kw: Any) -> str:
    """命令回执帧（节点→网关）。"""
    payload: dict[str, Any] = {"cmd_id": str(cmd_id), "ok": bool(ok)}
    if detail:
        payload["detail"] = str(detail)
    return encode_frame("ack", node_id, ts, fw, payload, **kw)


# ── 解码 ─────────────────────────────────────────────────────────────────

def decode_frame(line: str, *, verify_crc: bool = True) -> dict[str, Any]:
    """解析一帧 NDJSON。

    :raises SentinelProtocolError: 任何结构/类型/CRC 问题（调用方负责降级计数）。
    """
    if line is None or not str(line).strip():
        raise SentinelProtocolError("空帧")
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        raise SentinelProtocolError(f"坏 JSON: {e}") from e
    if not isinstance(obj, dict):
        raise SentinelProtocolError("帧必须是 JSON 对象")

    ftype = str(obj.get("t") or "").strip()
    if ftype not in FRAME_TYPES:
        raise SentinelProtocolError(f"未知帧类型: {ftype!r}")
    node_id = str(obj.get("node_id") or "").strip()
    if not node_id:
        raise SentinelProtocolError("缺少 node_id")
    if "ts" not in obj:
        raise SentinelProtocolError("缺少 ts")
    try:
        ts = float(obj["ts"])
    except (TypeError, ValueError) as e:
        raise SentinelProtocolError(f"ts 非法: {obj.get('ts')!r}") from e
    payload = obj.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise SentinelProtocolError("payload 必须是对象")

    if verify_crc:
        got = str(obj.get("crc32") or "").strip().lower()
        if not got:
            raise SentinelProtocolError("缺少 crc32")
        if len(got) != CRC_HEX_LEN:
            raise SentinelProtocolError(f"crc32 长度非法: {got!r}")
        want = compute_crc32(payload)
        if got != want:
            raise SentinelProtocolError(f"CRC 不匹配: 收到 {got} 期望 {want}")

    return {"t": ftype, "node_id": node_id, "ts": ts,
            "fw": str(obj.get("fw") or ""), "payload": payload,
            "crc32": obj.get("crc32")}


def decode(line: str, *, verify_crc: bool = True) -> tuple[dict[str, Any] | None, str]:
    """**降级版**解码：返回 `(frame, "")` 或 `(None, 原因)`，永不抛异常。

    网关消费热路径一律用这个；要 fail-fast 的测试/编码校验用 `decode_frame`。
    """
    try:
        return decode_frame(line, verify_crc=verify_crc), ""
    except SentinelProtocolError as e:
        return None, str(e)
    except Exception as e:                       # noqa: BLE001 - 兜底绝不崩
        return None, f"未预期错误: {type(e).__name__}: {e}"


# ── 扫描配置（控制面参数校验）────────────────────────────────────────────

def parse_scan_config(payload: dict[str, Any]) -> dict[str, Any]:
    """校验并归一化 `scan_config` 命令的 payload。

    :raises SentinelProtocolError: 频段倒置 / 空 sf_set / 非法 dwell_ms。
    """
    if not isinstance(payload, dict):
        raise SentinelProtocolError("scan_config payload 必须是对象")

    rng = payload.get("freq_range")
    if rng is None:
        rng = DEFAULT_FREQ_RANGE      # 未提供 → 用默认
    if not isinstance(rng, (list, tuple)) or len(rng) != 2:
        raise SentinelProtocolError("freq_range 必须是 [lo, hi]")
    try:
        lo, hi = float(rng[0]), float(rng[1])
    except (TypeError, ValueError) as e:
        raise SentinelProtocolError(f"freq_range 非数值: {e}") from e
    if lo >= hi:
        raise SentinelProtocolError(f"freq_range 倒置: {lo} >= {hi}")
    if lo < 400.0 or hi > 1000.0:
        raise SentinelProtocolError(f"freq_range 超出 400-1000MHz: {lo}-{hi}")

    dwell = payload.get("dwell_ms", DEFAULT_DWELL_MS)
    try:
        dwell_ms = int(dwell)
    except (TypeError, ValueError) as e:
        raise SentinelProtocolError(f"dwell_ms 非整数: {dwell!r}") from e
    if dwell_ms < 10 or dwell_ms > 5000:
        raise SentinelProtocolError(f"dwell_ms 越界(10-5000): {dwell_ms}")

    sfs = payload.get("sf_set")
    if sfs is None:
        sfs = DEFAULT_SF_SET          # 未提供 → 用默认；提供空数组视为非法
    if not isinstance(sfs, (list, tuple)) or not sfs:
        raise SentinelProtocolError("sf_set 必须是非空数组")
    try:
        sf_set = sorted({int(s) for s in sfs})
    except (TypeError, ValueError) as e:
        raise SentinelProtocolError(f"sf_set 非整数数组: {e}") from e
    if any(s < 6 or s > 12 for s in sf_set):
        raise SentinelProtocolError(f"sf 越界(6-12): {sf_set}")

    step = payload.get("step_khz", 200)
    try:
        step_khz = int(step)
    except (TypeError, ValueError) as e:
        raise SentinelProtocolError(f"step_khz 非整数: {step!r}") from e
    if step_khz < 1 or step_khz > 10000:
        raise SentinelProtocolError(f"step_khz 越界(1-10000): {step_khz}")

    return {"freq_range": [lo, hi], "dwell_ms": dwell_ms,
            "sf_set": sf_set, "step_khz": step_khz}


# 兼容别名：老写法 `from protocol import decode` 取到的是降级版，语义正确。
ScanConfigDict = dict[str, Any]

# 模块自检（`python -m ...protocol`）
if __name__ == "__main__":                       # pragma: no cover
    _bins = [ScanBin(433.0, -108.2), ScanBin(434.0, -61.5, sf=9)]
    _line = make_scan_frame("canary-01", 1743561600.123, "1.1.0", _bins,
                            EnvSample(temp_c=23.4, hum_pct=41, pres_hpa=1008.2, bat_mv=3980),
                            event="cad_busy")
    print("FRAME:", _line)
    _f, _err = decode(_line)
    print("DECODE ok:", _f is not None, "err:", _err)
    print("CRC:", _f["crc32"] if _f else None)
    print("CONFIG:", parse_scan_config({"freq_range": [433.0, 434.7], "dwell_ms": 120}))
