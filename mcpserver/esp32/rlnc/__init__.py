"""``rlnc`` · RLNC 编解码**兼容层**（工单 243 任务二）。

真值源 = ``mcpserver/rf_brain/rlnc/``
------------------------------------
10 文件；**导入链**为标准库 —— ``galois``（GF(2^8) 0x11B 查表）/ ``encoder``（系统式分层 RLNC）/
``decoder``（增量 RREF 高斯消元）/ ``clustering``（**链路可靠度**三档 → 冗余率）/
``reliability``（EWMA + 滑窗）/ ``peer_state`` / ``packetize``（dcp payload 切片）/
``apc_mesh_routing``（⚠️ 该支 ``import numpy``，但**不在** ``__init__`` 导入链上）。

本包**不实现任何编解码数学**，只做两件事：
1. 把真值源的公共符号**全量镜像**到 ``mcpserver.esp32.rlnc`` 命名空间下；
2. 补工单 §2 任务二字面要求的 ``encode_random()`` / ``decode_full()`` 薄封装。

为什么不做成新实现：见本包 ``encoder.py`` 顶部（避免仓内出现第二套 GF(2^8) ⇒ 公式漂移）。
"""
from __future__ import annotations

from mcpserver.esp32.rlnc.decoder import RlncDecoder, decode_full
from mcpserver.esp32.rlnc.encoder import (
    EncodedBlock,
    RlncEncoder,
    encode_random,
    redundancy_blocks,
)
from mcpserver.rf_brain.rlnc import *  # noqa: F403 - 兼容层**刻意**全量镜像真值源
from mcpserver.rf_brain.rlnc import __all__ as _REEXPORTED

__all__ = [*_REEXPORTED, "decode_full", "encode_random"]
