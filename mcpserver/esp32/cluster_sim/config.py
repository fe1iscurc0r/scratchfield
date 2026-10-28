"""YAML 配置读取与一次仿真编排。

工单 §2 任务一.2 要求的四项
--------------------------
``nodes``（节点数）/ ``area``（``[宽, 高]``，m）/ ``rssi_threshold``（dBm）/
``simulate_duration``（观测窗口，小时）。

另有扩展项（全部有默认值，可缺省）：``topology`` / ``max_hops`` / ``failure_rate`` /
``seed`` / ``unstable_margin_db`` / ``tx_power_dbm`` / ``freq_hz`` / ``path_loss_exponent``。

⚠️ ``simulate_duration`` 的口径（**别过度解读**）
------------------------------------------------
本单的分簇是**静态快照**：给定布点与阈值，算出这一刻的簇划分与不稳定链路。
``simulate_duration`` 因此只作为**观测窗口**原样记录进输出，**不驱动任何时变过程**
（节点随机加入/退出、链路质量时间序列、重传退避都不在本单范围）。把它当"仿真时长"去
推丢包率是错的 —— 需要时变模型请另开工单。

依赖：``PyYAML``（仓内 ``pyproject.toml`` 已声明 ``PyYAML>=6.0.2``）。
"""
from __future__ import annotations

import random
from pathlib import Path

import yaml

from .cluster import (
    DEFAULT_MAX_HOPS,
    DEFAULT_UNSTABLE_MARGIN_DB,
    cluster_report,
)
from .node import (
    DEFAULT_FREQ_HZ,
    DEFAULT_PATH_LOSS_EXPONENT,
    DEFAULT_TX_POWER_DBM,
    Node,
)
from .topology import TOPOLOGY_KINDS, Topology, generate

DEFAULT_NODES = 50
# 默认区域 30 km × 30 km —— **不是**随手取的：LoRa（SF7/125 kHz，灵敏度约 −123 dBm）
# 单跳覆盖可达数公里，区域一小就退化成单一巨簇，失活率不再改变最大簇规模
# （实测 500 m × 500 m 下 5%~30% 失活全档同一成功率）。
# 30 km + 阈值 −110 dBm + n=2.7 ⇒ 可达半径 r ≈ 4.56 km、解析平均度 λπr² ≈ 3.6，
# **实测平均度 ≈ 3.0**（10 seed 均值 3.06）⇒ 落在随机几何图连通相变（约 4.5）**之下**的
# 多簇区：实测 12 簇（解析上界 ≈ 13.8），分簇与失活率才有可观测影响。
DEFAULT_AREA = (30000.0, 30000.0)
# 可达阈值 −110 dBm：在 30 km 区域下与路损指数 2.7 配合得到上述平均度
DEFAULT_RSSI_THRESHOLD_DBM = -110.0
DEFAULT_SIMULATE_DURATION_H = 1.0

DEFAULT_CONFIG: dict = {
    "nodes": DEFAULT_NODES,
    "area": list(DEFAULT_AREA),
    "rssi_threshold": DEFAULT_RSSI_THRESHOLD_DBM,
    "simulate_duration": DEFAULT_SIMULATE_DURATION_H,
    "topology": "grid",
    "max_hops": DEFAULT_MAX_HOPS,
    "failure_rate": 0.0,
    "unstable_margin_db": DEFAULT_UNSTABLE_MARGIN_DB,
    "tx_power_dbm": DEFAULT_TX_POWER_DBM,
    "freq_hz": DEFAULT_FREQ_HZ,
    "path_loss_exponent": DEFAULT_PATH_LOSS_EXPONENT,
    "seed": None,
}

_FLOAT_KEYS = (
    "rssi_threshold",
    "simulate_duration",
    "failure_rate",
    "unstable_margin_db",
    "tx_power_dbm",
    "freq_hz",
    "path_loss_exponent",
)


def _as_float(raw: object, key: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"配置项 {key!r} 必须是数值，收到 {raw!r}")
    return float(raw)


def _as_int(raw: object, key: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"配置项 {key!r} 必须是整数，收到 {raw!r}")
    return raw


def normalize_config(raw: dict | None) -> dict:
    """校验并补齐配置：缺项取默认值，非法值抛 ``ValueError``（不静默纠正）。"""
    src = dict(DEFAULT_CONFIG)
    for key, value in (raw or {}).items():
        if key not in DEFAULT_CONFIG:
            raise ValueError(f"未知配置项 {key!r}，可选 {sorted(DEFAULT_CONFIG)}")
        src[key] = value

    area = src["area"]
    if not isinstance(area, (list, tuple)) or len(area) != 2:
        raise ValueError(f"配置项 'area' 必须是 [宽, 高]，收到 {area!r}")
    width, height = _as_float(area[0], "area[0]"), _as_float(area[1], "area[1]")
    if width <= 0.0 or height <= 0.0:
        raise ValueError("区域宽高必须为正")

    cfg = {
        "nodes": _as_int(src["nodes"], "nodes"),
        "area": [width, height],
        "topology": src["topology"],
        "seed": src["seed"],
    }
    for key in _FLOAT_KEYS:
        cfg[key] = _as_float(src[key], key)
    cfg["max_hops"] = _as_int(src["max_hops"], "max_hops")

    if cfg["nodes"] <= 0:
        raise ValueError("nodes 必须为正")
    if cfg["max_hops"] < 0:
        raise ValueError("max_hops 不能为负")
    if not 0.0 <= cfg["failure_rate"] <= 1.0:
        raise ValueError("failure_rate 必须在 [0, 1]")
    if cfg["simulate_duration"] <= 0.0:
        raise ValueError("simulate_duration 必须为正（单位：小时）")
    if cfg["topology"] not in TOPOLOGY_KINDS:
        raise ValueError(f"未知 topology {cfg['topology']!r}，可选 {TOPOLOGY_KINDS}")
    if cfg["seed"] is not None:
        cfg["seed"] = _as_int(cfg["seed"], "seed")
    return cfg


def load_config(path: str | Path) -> dict:
    """读 YAML 配置（顶层必须是映射）并归一化。"""
    text = Path(path).read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"配置文件顶层必须是映射（key: value），收到 {type(raw).__name__}")
    return normalize_config(raw)


def build_topology(cfg: dict) -> Topology:
    """按归一化配置生成拓扑。"""
    width, height = cfg["area"]
    return generate(
        cfg["topology"],
        cfg["nodes"],
        width=width,
        height=height,
        seed=cfg["seed"],
        tx_power_dbm=cfg["tx_power_dbm"],
        freq_hz=cfg["freq_hz"],
        path_loss_exponent=cfg["path_loss_exponent"],
    )


def apply_failure(nodes: list[Node], failure_rate: float, *, seed: int | None = None) -> int:
    """按比例随机失活节点（``seed`` 可复现）。返回被失活的节点数。"""
    if not 0.0 <= failure_rate <= 1.0:
        raise ValueError("failure_rate 必须在 [0, 1]")
    count = int(round(len(nodes) * failure_rate))
    if count <= 0:
        return 0
    rng = random.Random(seed)
    for node in rng.sample(nodes, count):
        node.deactivate()
    return count


def simulate(cfg: dict | None = None, *, failure_rate: float | None = None) -> dict:
    """跑一次完整仿真：生成拓扑 → 按失败率失活 → 分簇 → 汇总。

    ``failure_rate`` 显式给出时覆盖配置项（供 dashboard 扫多个失活率复用同一配置）。
    """
    normalized = normalize_config(cfg)
    rate = normalized["failure_rate"] if failure_rate is None else float(failure_rate)
    topo = build_topology(normalized)
    deactivated = apply_failure(topo.nodes, rate, seed=normalized["seed"])
    report = cluster_report(
        topo.nodes,
        threshold_dbm=normalized["rssi_threshold"],
        max_hops=normalized["max_hops"],
        margin_db=normalized["unstable_margin_db"],
        freq_hz=normalized["freq_hz"],
        exponent=normalized["path_loss_exponent"],
    )
    report["topology"] = topo.as_dict()
    report["simulation"] = {
        "failure_rate": rate,
        "deactivated": deactivated,
        "simulate_duration_h": normalized["simulate_duration"],
        "note": "分簇为静态快照；simulate_duration 仅作观测窗口记录，不驱动时变过程。",
    }
    report["config"] = dict(normalized)
    return report


__all__ = [
    "DEFAULT_AREA",
    "DEFAULT_CONFIG",
    "DEFAULT_NODES",
    "DEFAULT_RSSI_THRESHOLD_DBM",
    "DEFAULT_SIMULATE_DURATION_H",
    "apply_failure",
    "build_topology",
    "load_config",
    "normalize_config",
    "simulate",
]
