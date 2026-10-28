"""⚠️ **兼容层**，非独立实现 —— 真值源在 ``mcpserver/rf_brain/rlnc/decoder.py``。

真值源是**增量 RREF 高斯消元**解码器（``RlncDecoder``）：逐块 ``add_block`` 维护约化行阶梯形，
满秩后 ``decode()`` 还原 k 个原始块；世代错 / 系数长度错 / 载荷长度错 / 全零系数块一律拒绝
（返回 ``False``）且不破坏已收正确块。

本文件只做两件事：``re-export`` 真值源符号 + 补工单字面要求的 ``decode_full()`` 薄封装。
**不含任何独立数学实现** —— 改行为请改真值源（理由见本包 ``encoder.py`` 顶部）。
"""
from __future__ import annotations

from collections import Counter

from mcpserver.rf_brain.rlnc.decoder import RlncDecoder
from mcpserver.rf_brain.rlnc.encoder import EncodedBlock

__all__ = ["RlncDecoder", "decode_full"]


def _infer_k(blocks: list[EncodedBlock]) -> int | None:
    """从系数长度**众数**推断 k（对个别坏块有容错；全部无系数则返回 None）。"""
    lengths = [len(b.coefficients) for b in blocks if b.coefficients]
    if not lengths:
        return None
    return Counter(lengths).most_common(1)[0][0]


def decode_full(
    blocks: list[EncodedBlock],
    *,
    k: int | None = None,
    generation: int | None = None,
) -> list[bytes] | None:
    """工单字面 API：喂入编码块，**满秩**则返回 k 个原始块，否则 ``None``。

    - ``k`` 缺省时从系数长度众数推断；显式给出则以它为准。
    - 坏块 / 线性相关块由真值源 ``add_block`` 拒绝，**不影响**已正确收到的块。
    - ``generation`` 显式给出即按世代隔离（真值源语义）。
    """
    block_list = list(blocks)
    kk = k if k is not None else _infer_k(block_list)
    if not kk or kk <= 0:
        return None
    decoder = RlncDecoder(kk, generation)
    for block in block_list:
        decoder.add_block(block)
    return decoder.decode()
