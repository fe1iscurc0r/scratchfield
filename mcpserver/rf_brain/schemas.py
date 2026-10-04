"""射频大脑 · 接口协议 schema（Phase 0）

协议无关抽象层的基石：决策层只认 FeatureVector（输入）和 Decision（输出），
底层是 LoRa/BLE/仿真数据都不关心，协议细节封在适配器里。

三个 schema 字段必须与 SPEC 3.x 完全一致。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FeatureVector:
    """感知层 → 决策层的特征向量。

    字段与 SPEC 3.1 完全一致。
    """
    timestamp: str
    center_freq_hz: float
    sample_rate_hz: float
    n_samples: int
    # 核心特征（rule_engine 和 decision_layer 都从这里读）
    peak_freq_hz: float | None          # 频谱主峰频率（相对中心频的偏移 + 中心频）
    bandwidth_hz: float | None          # 信号带宽（-3dB 或等效）
    snr_db: float                          # 信噪比估计
    spectral_flatness: float               # 0~1，越接近 1 越平坦（噪声）
    symbol_rate_estimate_hz: float | None  # 符号率估计
    n_peaks: int                           # 谱峰数量（FSK 类双峰）
    peak_separation_hz: float | None    # 双峰间距（单峰为 None）
    envelope_cv: float = 0.0               # 包络变异系数：OOK 幅度键控→高(~0.8)，FSK/GFSK 恒定包络→低(~0.07)
    freq_transition_slope: float | None = None  # Phase 4：瞬时频率轨迹每样本斜率×符号周期，FSK 硬切换→高(~2×dev)，GFSK 高斯平滑→低
    modulation_candidates: list[str] = field(default_factory=list)  # rule_engine 预筛

    def is_valid_signal(self, snr_threshold_db: float = 5.0, flatness_threshold: float = 0.5) -> bool:
        """有效信号判定：SNR 够高 且 频谱足够集中（flatness 低）。

        噪声频谱平坦（flatness→1），调制信号频谱集中（flatness→0）。
        纯靠 SNR 会误判——噪声峰值天然比中位数高 ~10dB。
        """
        return self.snr_db >= snr_threshold_db and self.spectral_flatness <= flatness_threshold


@dataclass
class Decision:
    """决策层 → 回写层的解调决策。

    字段与 SPEC 3.2 完全一致。
    """
    decision: str                          # 固定 "demodulate"
    modulation: str                        # 选定的调制方式（如 GFSK/FSK/OOK）
    demod_params: dict
    confidence: float
    reasoning: str
    alternatives: list[dict] = field(default_factory=list)  # 候选 + 置信度


@dataclass
class DemodFeedback:
    """回写层 → 决策层的解调结果反馈。

    字段与 SPEC 3.3 完全一致。
    """
    status: str                            # "ok" / "no_signal" / "failed"
    demod_success: bool
    bit_error_rate_estimate: float | None = None
    output_symbol_count: int = 0
    feedback: str = ""


# --------------------------------------------------------------------------- #
# 边缘频谱哨兵（N-04 桥接层 schema）
# --------------------------------------------------------------------------- #

@dataclass
class SentinelReport:
    """哨兵 OOK 传感器上报（与固件 USB-CDC NDJSON 逐字段对齐）。

    字段说明见 firmware/README.md §4.3；`channel` 因协议而异：
    acurite 为字符串 "A"/"B"/"C"，nexus 为整数 1..3，kerui 无（None）。
    """
    protocol: str
    id: int
    src: str = "sentinel"
    channel: "str | int" | None = None   # acurite="A/B/C"；nexus=1..3；kerui=None
    temperature: float | None = None     # 摄氏（分辨率 0.1°C）
    humidity: int | None = None          # 相对湿度 %
    battery: str | None = None           # "OK"/"LOW"
    cmd: int | None = None               # kerui 4bit 命令码
    rssi_dbm: int | None = None
    crc_ok: bool | None = None           # True/False/None(无校验)
    raw_bits: str | None = None

    VALID_PROTOCOLS = ("acurite", "nexus", "kerui")

    @classmethod
    def from_ndjson(cls, line: str) -> "SentinelReport":
        """解析 + 校验一条 NDJSON 行；非法输入抛 ValueError（由桥接层降级）。"""
        if not line or not line.strip():
            raise ValueError("空行")
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"坏 JSON: {e}") from e
        if not isinstance(obj, dict):
            raise ValueError("NDJSON 行必须是 JSON 对象")
        if obj.get("src") != "sentinel":
            raise ValueError(f"非哨兵来源: {obj.get('src')!r}")

        protocol = obj.get("protocol")
        if protocol not in cls.VALID_PROTOCOLS:
            raise ValueError(f"未知协议: {protocol!r}")

        sensor_id = cls._require_int(obj, "id", lo=0)
        rssi = obj.get("rssi_dbm")
        if rssi is not None and not isinstance(rssi, int):
            raise ValueError(f"rssi_dbm 必须是整数: {rssi!r}")

        crc = obj.get("crc_ok")
        if crc is not None and not isinstance(crc, bool):
            raise ValueError(f"crc_ok 必须是布尔或 null: {crc!r}")

        report = cls(protocol=protocol, id=sensor_id, rssi_dbm=rssi, crc_ok=crc,
                     raw_bits=obj.get("raw_bits"))

        if protocol in ("acurite", "nexus"):
            report.temperature = cls._require_float(obj, "temperature")
            report.humidity = cls._require_int(obj, "humidity", lo=0, hi=255)
            battery = obj.get("battery")
            if battery is not None and battery not in ("OK", "LOW"):
                raise ValueError(f"battery 必须是 OK/LOW: {battery!r}")
            report.battery = battery
            if protocol == "acurite":
                ch = obj.get("channel")
                if ch is not None and ch not in ("A", "B", "C"):
                    raise ValueError(f"acurite channel 必须是 A/B/C: {ch!r}")
                report.channel = ch
            else:  # nexus
                report.channel = cls._require_int(obj, "channel", lo=1, hi=3,
                                                  allow_none=True)
        else:  # kerui
            report.cmd = cls._require_int(obj, "cmd", lo=0, hi=15)
        return report

    @staticmethod
    def _require_int(obj: dict, key: str, lo: int | None = None,
                     hi: int | None = None, allow_none: bool = False):
        v = obj.get(key)
        if v is None:
            if allow_none:
                return None
            raise ValueError(f"缺少字段 {key}")
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"{key} 必须是整数: {v!r}")
        if lo is not None and v < lo:
            raise ValueError(f"{key} 越界(< {lo}): {v}")
        if hi is not None and v > hi:
            raise ValueError(f"{key} 越界(> {hi}): {v}")
        return v

    @staticmethod
    def _require_float(obj: dict, key: str):
        v = obj.get(key)
        if v is None:
            raise ValueError(f"缺少字段 {key}")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{key} 必须是数字: {v!r}")
        return float(v)

    def as_dict(self) -> dict:
        """回原为可 JSON 序列化的 dict（保真入库/回读）。"""
        d = {"src": self.src, "protocol": self.protocol, "id": self.id}
        if self.channel is not None:
            d["channel"] = self.channel
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.humidity is not None:
            d["humidity"] = self.humidity
        if self.battery is not None:
            d["battery"] = self.battery
        if self.cmd is not None:
            d["cmd"] = self.cmd
        if self.rssi_dbm is not None:
            d["rssi_dbm"] = self.rssi_dbm
        if self.crc_ok is not None:
            d["crc_ok"] = self.crc_ok
        if self.raw_bits is not None:
            d["raw_bits"] = self.raw_bits
        return d
