"""rlnc · APC-RLNC 多跳弱链路自适应编码（C-01 聚类 + C-02 编码）。

模块：
- reliability.py : EWMA 链路可靠度估计 + 滑动窗口丢包率
- clustering.py  : 可靠度阈值三档聚类 + 冗余率映射
- peer_state.py  : 邻居可靠度表 + 上报/查询接口
- galois.py      : GF(2^8) 有限域运算（生成元 0x03 查表）
- encoder.py     : 分层 RLNC 编码器（系统式，r = ⌊k×factor⌋）
- decoder.py     : 增量高斯消元解码器（RREF）
- packetize.py   : 编码块打包/拆包 + dcp payload 切片
"""
from __future__ import annotations

from .clustering import (
    DEFAULT_HIGH_THRESHOLD,
    DEFAULT_LOW_THRESHOLD,
    DEFAULT_REDUNDANCY_FACTOR,
    HIGH,
    LOW,
    MID,
    ReliabilityClusterer,
)
from .decoder import RlncDecoder
from .encoder import EncodedBlock, RlncEncoder, redundancy_blocks
from .galois import (
    GF_GENERATOR,
    GF_ORDER,
    GF_PRIMITIVE_POLY,
    gf_add,
    gf_div,
    gf_inv,
    gf_mul,
    gf_pow,
    gf_sub,
)
from .packetize import (
    HEADER_LEN,
    fragment_for_dcp,
    pack_block,
    reassemble_from_dcp,
    unpack_block,
)
from .peer_state import PeerState
from .reliability import EWMAReliability, LossWindow

__all__ = [
    # 有限域
    "GF_ORDER", "GF_PRIMITIVE_POLY", "GF_GENERATOR",
    "gf_add", "gf_sub", "gf_mul", "gf_div", "gf_inv", "gf_pow",
    # 聚类
    "HIGH", "MID", "LOW",
    "DEFAULT_HIGH_THRESHOLD", "DEFAULT_LOW_THRESHOLD",
    "DEFAULT_REDUNDANCY_FACTOR", "ReliabilityClusterer",
    # 可靠度
    "EWMAReliability", "LossWindow", "PeerState",
    # 编码
    "EncodedBlock", "RlncEncoder", "RlncDecoder", "redundancy_blocks",
    # 打包
    "HEADER_LEN", "pack_block", "unpack_block",
    "fragment_for_dcp", "reassemble_from_dcp",
]
