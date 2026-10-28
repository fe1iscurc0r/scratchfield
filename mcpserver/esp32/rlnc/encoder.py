"""⚠️ **兼容层**，非独立实现 —— 真值源在 ``mcpserver/rf_brain/rlnc/encoder.py``。

为什么不是新实现
----------------
工单 243 §2 任务二假设本仓没有 RLNC 库，要求在 ``mcpserver/esp32/rlnc/`` 新建一套
GF(2^8) 编解码。**实测该假设不成立**：``mcpserver/rf_brain/rlnc/`` 已有完整实现
（``galois`` / ``encoder`` / ``decoder`` / ``clustering`` / ``reliability`` / ``packetize`` /
``peer_state`` / ``apc_mesh_routing``，共 10 文件），其中的 ``encoder.py`` 就是
**系统式分层 RLNC 编码器**（k 原始块 + r=⌊k×factor⌋ 冗余块，随机系数，seed 可复现）。

若按工单字面再建一套，仓内将出现**第二套 GF(2^8) + 编解码**——两处公式各自演进必然漂移，
本仓已把「同一语义被两处定义」列为静默 bug 温床（240 工单踩过跨源重复归属）。

⇒ 本文件按 240 先例做成 **兼容层**：符号一律 ``re-export`` 真值源，只额外补工单字面要求的
``encode_random()`` 薄封装（语义完全等价于 ``RlncEncoder.encode()``）。
**本文件不含任何独立数学实现** —— 改行为请改真值源。
"""
from __future__ import annotations

from mcpserver.rf_brain.rlnc.encoder import EncodedBlock, RlncEncoder, redundancy_blocks

__all__ = ["EncodedBlock", "RlncEncoder", "encode_random", "redundancy_blocks"]


def encode_random(
    blocks: list[bytes],
    *,
    factor: float,
    generation: int = 0,
    seed: int | None = None,
) -> list[EncodedBlock]:
    """工单字面 API：k 个原始块 → n 个编码块（冗余块用随机系数）。

    与 ``RlncEncoder(len(blocks), factor, generation, seed).encode(blocks)`` **完全等价** ——
    这里只是一层具名封装，方便仿真侧按工单的命名调用。``factor`` 为冗余率（r = ⌊k×factor⌋）。
    """
    return RlncEncoder(len(blocks), factor, generation, seed).encode(blocks)
