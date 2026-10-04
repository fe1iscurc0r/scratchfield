# -*- coding: utf-8 -*-
"""LoRaCanary · C3 节点侧纯逻辑镜像（pytest 用，与固件行为逐项对应）。

  - Bme280Probe：镜像固件 bmeInit 的地址自动探测（0x76→0x77，v1 第 9 例）；
  - sensor_sample：镜像 bmeCollect 的 MOCK 降级（v1 第 8 例：mock + 显式标注）；
  - TxRetry：镜像 v1 AA-02 的重传契约（无 ACK 重发 ≤2 次后放弃，v1 第 7 例）。

节点固件本体是 C++（firmware/loracanary/loracanary_c3_node/）；本文件让这些
纯逻辑进 pytest，不依赖真机。样例值均为占位（诚实标注，非实机采集）。
"""

MOCK_SAMPLE = {"t": 25.0, "h": 55.0, "p": 1013.2}  # MOCK 占位采样值（同固件）

# 帧协议常量（与 lora_frame.py 一致，防镜像漂移）
TX_MAX_RETRY = 2
BME_PROBE_ADDRS = (0x76, 0x77)


class Bme280Probe:
    """镜像固件地址探测：按 0x76→0x77 顺序试，成功即停；全败 → MOCK。"""

    def __init__(self, present_addrs=()):
        # present_addrs 模拟总线上真实应答的地址（真机由 Wire 探测）
        self._present = set(present_addrs)
        self.tried: list[int] = []
        self.addr: int | None = None
        self.mock = False

    def probe(self) -> bool:
        for addr in BME_PROBE_ADDRS:
            self.tried.append(addr)
            if addr in self._present:
                self.addr = addr
                return True
        self.mock = True  # 固件同款：均不在线 → mock_bme:true 显式标注
        return False


def sensor_sample(bme_online: bool, reading: dict | None = None) -> dict:
    """镜像 bmeCollect：在线读真值；不在线出 MOCK 且带标注（不静默造假）。"""
    if bme_online and reading is not None:
        return {**reading, "mock_bme": False}
    return {**MOCK_SAMPLE, "mock_bme": True}


class TxRetry:
    """重传镜像（v1 AA-02 契约）：首次发送 + 无 ACK 重发 ≤2 次，仍无 ACK 放弃。

    放弃不阻塞主循环：计数后等下一周期（心跳语义，v1 SPEC 假设表）。
    """

    MAX_RETRY = TX_MAX_RETRY

    def __init__(self) -> None:
        self.attempts = 0  # 已发送次数（含首次）
        self.acked = False

    def send_once(self) -> None:
        self.attempts += 1

    def on_ack(self) -> None:
        self.acked = True

    @property
    def should_retry(self) -> bool:
        return not self.acked and self.attempts < self.MAX_RETRY + 1

    @property
    def gave_up(self) -> bool:
        return not self.acked and self.attempts >= self.MAX_RETRY + 1
