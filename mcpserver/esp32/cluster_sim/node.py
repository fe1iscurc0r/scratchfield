"""节点行为模型：几何位置、RSSI 估算、发/收包与失活状态机。

口径边界
--------
本模块只负责**信道几何**（距离 → 路损 → RSSI）与**节点生命周期**（活/失活、收发计数），
不掺入任何网络编码逻辑。编码冗余由 ``mcpserver/rf_brain/rlnc/`` 决定，本工单经
``mcpserver/esp32/rlnc`` 兼容层调用。

路损模型
--------
``PL(d) = FSPL(f, 1m) + 10·n·log10(d / 1m)``，即**对数距离路损**模型：
- ``n = 2.0`` 等价自由空间；``n = 2.7`` 为近地/郊区常用值（LoRa 实测区间 2.7~3.5）。
- 参考点取 1 m；``d < 1 m`` 时按 1 m 截断（近场公式不适用，避免 RSSI 虚高到无穷）。

FSPL 常数与 ``mcpserver/rf_workflow/lora_phy.py`` 保持一致
（``20log10(d) + 20log10(f) − 147.55``，d 以 m、f 以 Hz 计），避免仓内出现两套口径。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_FREQ_HZ = 433.92e6
DEFAULT_TX_POWER_DBM = 14.0
DEFAULT_ANTENNA_GAIN_DBI = 0.0
REFERENCE_DISTANCE_M = 1.0
# FSPL 常数：20·log10(4π/c) 取 −147.55（与 lora_phy.py 同源）
FSPL_CONSTANT_DB = 147.55
PATH_LOSS_EXPONENT_FREE_SPACE = 2.0
# 近地/郊区经验值；LoRa 链路预算实测常落在 2.7~3.5
DEFAULT_PATH_LOSS_EXPONENT = 2.7


def free_space_path_loss_db(freq_hz: float, distance_m: float) -> float:
    """自由空间路损 FSPL = 20log10(d) + 20log10(f) − 147.55（d: m, f: Hz）。"""
    if freq_hz <= 0.0:
        raise ValueError("频率必须为正")
    if distance_m <= 0.0:
        raise ValueError("距离必须为正")
    return 20.0 * math.log10(distance_m) + 20.0 * math.log10(freq_hz) - FSPL_CONSTANT_DB


def reference_loss_db(freq_hz: float = DEFAULT_FREQ_HZ) -> float:
    """参考点（1 m）路损——即 433.92 MHz 下的 FSPL(d=1m)。"""
    return free_space_path_loss_db(freq_hz, REFERENCE_DISTANCE_M)


def path_loss_db(
    distance_m: float,
    *,
    freq_hz: float = DEFAULT_FREQ_HZ,
    exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
    ref_distance_m: float = REFERENCE_DISTANCE_M,
) -> float:
    """对数距离路损：PL = FSPL(f, d0) + 10·n·log10(d / d0)，d 按 d0 截断。"""
    if exponent <= 0.0:
        raise ValueError("路损指数必须为正")
    if ref_distance_m <= 0.0:
        raise ValueError("参考距离必须为正")
    d = max(distance_m, ref_distance_m)
    return reference_loss_db(freq_hz) + 10.0 * exponent * math.log10(d / ref_distance_m)


def rssi_dbm(
    distance_m: float,
    *,
    freq_hz: float = DEFAULT_FREQ_HZ,
    tx_power_dbm: float = DEFAULT_TX_POWER_DBM,
    tx_gain_dbi: float = DEFAULT_ANTENNA_GAIN_DBI,
    rx_gain_dbi: float = DEFAULT_ANTENNA_GAIN_DBI,
    exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
) -> float:
    """接收信号强度：RSSI = P_tx + G_tx + G_rx − PL(d)（dBm）。"""
    return (
        tx_power_dbm
        + tx_gain_dbi
        + rx_gain_dbi
        - path_loss_db(distance_m, freq_hz=freq_hz, exponent=exponent)
    )


def max_range_m(
    threshold_dbm: float,
    *,
    freq_hz: float = DEFAULT_FREQ_HZ,
    tx_power_dbm: float = DEFAULT_TX_POWER_DBM,
    tx_gain_dbi: float = DEFAULT_ANTENNA_GAIN_DBI,
    rx_gain_dbi: float = DEFAULT_ANTENNA_GAIN_DBI,
    exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
) -> float:
    """给定灵敏度阈值时的最大可达距离（对数距离模型的解析解，单位 m）。

    解 ``P_tx + G − PL(d) = threshold`` 得 ``d = d0 · 10^((EIRP − thr − PL(d0)) / (10n))``。
    """
    budget = tx_power_dbm + tx_gain_dbi + rx_gain_dbi - reference_loss_db(freq_hz) - threshold_dbm
    return REFERENCE_DISTANCE_M * (10.0 ** (budget / (10.0 * exponent)))


@dataclass
class Node:
    """一个传感网节点（位置 + 射频参数 + 生命周期 + 收发计数）。"""

    node_id: int
    x: float
    y: float
    tx_power_dbm: float = DEFAULT_TX_POWER_DBM
    tx_gain_dbi: float = DEFAULT_ANTENNA_GAIN_DBI
    rx_gain_dbi: float = DEFAULT_ANTENNA_GAIN_DBI
    alive: bool = True
    packets_sent: int = 0
    packets_received: int = 0
    packets_dropped: int = 0

    @property
    def position(self) -> tuple[float, float]:
        return (self.x, self.y)

    def distance_to(self, other: Node) -> float:
        """到另一节点的欧氏距离（m）。"""
        return math.hypot(self.x - other.x, self.y - other.y)

    def rssi_to(
        self,
        other: Node,
        *,
        freq_hz: float = DEFAULT_FREQ_HZ,
        exponent: float = DEFAULT_PATH_LOSS_EXPONENT,
    ) -> float:
        """本节点发、other 收时的 RSSI（dBm）。使用双方各自的天线增益。"""
        return rssi_dbm(
            self.distance_to(other),
            freq_hz=freq_hz,
            tx_power_dbm=self.tx_power_dbm,
            tx_gain_dbi=self.tx_gain_dbi,
            rx_gain_dbi=other.rx_gain_dbi,
            exponent=exponent,
        )

    def transmit(self) -> bool:
        """发一次包：失活节点直接丢包（计数 +1）并返回 False。"""
        if not self.alive:
            self.packets_dropped += 1
            return False
        self.packets_sent += 1
        return True

    def receive(self, rssi: float, *, threshold_dbm: float) -> bool:
        """收一次包：失活或低于阈值即丢包（计数 +1）并返回 False。"""
        if not self.alive or rssi < threshold_dbm:
            self.packets_dropped += 1
            return False
        self.packets_received += 1
        return True

    def deactivate(self) -> None:
        self.alive = False

    def activate(self) -> None:
        self.alive = True

    def as_dict(self) -> dict:
        return {
            "id": self.node_id,
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "alive": self.alive,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "packets_dropped": self.packets_dropped,
        }


__all__ = [
    "DEFAULT_ANTENNA_GAIN_DBI",
    "DEFAULT_FREQ_HZ",
    "DEFAULT_PATH_LOSS_EXPONENT",
    "DEFAULT_TX_POWER_DBM",
    "FSPL_CONSTANT_DB",
    "PATH_LOSS_EXPONENT_FREE_SPACE",
    "REFERENCE_DISTANCE_M",
    "Node",
    "free_space_path_loss_db",
    "max_range_m",
    "path_loss_db",
    "reference_loss_db",
    "rssi_dbm",
]
