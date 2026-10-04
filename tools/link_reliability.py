"""LoRaCanary 弱链路增强 · EWMA 可靠度 + XOR FEC 原型（纯标准库，Python 镜像）。

依据 docs/SPEC-20-v1.6-LoRaCanary弱链路增强-总纲.md：
- EWMA 链路可靠度 R_n = alpha*ack_n + (1-alpha)*R_{n-1}
- 分组阈值：R>=0.8 A（单发）/ 0.5<=R<0.8 B（+1 XOR）/ R<0.5 C（+2 XOR）
- XOR 冗余：同 seq 数据帧的逐字节 XOR（短帧补 0），抗随机丢包

仅供算法验证与主机侧参考；ESP32 固件用 C++ 镜像（独立实现）。
"""
from __future__ import annotations

DEFAULT_ALPHA = 0.3

# 分组阈值（SPEC v1.6 第二节）
THRESH_STRONG = 0.8
THRESH_MEDIUM = 0.5


def update_reliability(r: float, ack: bool | int, alpha: float = DEFAULT_ALPHA) -> float:
    """EWMA 更新。ack=True/1 表示帧被网关确认，False/0 表示丢。

    帧级 ACK 语义放宽（SPEC v1.6 风险节）：窗口内 N 帧收到 >=1 ACK 即算成功，
    由调用方把 ack 归约为单次布尔后调用本函数。
    """
    a = 1.0 if ack else 0.0
    return alpha * a + (1.0 - alpha) * r


def group_for(r: float) -> str:
    """按可靠度分组：A 强 / B 中(+1 XOR) / C 弱(+2 XOR)。"""
    if r >= THRESH_STRONG:
        return "A"
    if r >= THRESH_MEDIUM:
        return "B"
    return "C"


def redundancy_count(group: str) -> int:
    """分组对应的 XOR 校验包数量。"""
    return {"A": 0, "B": 1, "C": 2}[group]


def xor_redundancy(payloads: list[bytes]) -> bytes:
    """k 个数据帧 payload 的逐字节 XOR（短帧右补 0 到最长长度）。"""
    if not payloads:
        raise ValueError("payloads 不能为空")
    n = max(len(p) for p in payloads)
    out = bytearray(n)
    for p in payloads:
        for i, b in enumerate(p):
            out[i] ^= b
    return bytes(out)


def recover(payloads: list[bytes | None], xor_pkt: bytes) -> bytes:
    """XOR 恢复：k 个 payload 丢了 1 个（用 None 占位），用 xor_pkt 恢复。"""
    missing = [i for i, p in enumerate(payloads) if p is None]
    if len(missing) != 1:
        raise ValueError(f"XOR 只能恢复恰好 1 个缺失包，当前缺失 {len(missing)} 个")
    n = max([len(xor_pkt)] + [len(p) for p in payloads if p is not None])
    out = bytearray(xor_pkt.ljust(n, b"\x00"))
    for p in payloads:
        if p is not None:
            for i, b in enumerate(p):
                out[i] ^= b
    return bytes(out)
