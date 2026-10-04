"""编码块打包：EncodedBlock ↔ 自描述字节包，并可切分成 dcp COMMAND payload。

元信息头（4B）：generation(1) + block_id(1) + k(1) + L(1)
  + coefficients(k bytes) + data(L bytes)
总长 = 4 + k + L。

不修改 dcp 帧核心（magic/type/seq/crc 布局不变），只把本字节包作为 dcp COMMAND
payload 承载；超过 dcp payload 上限（默认 42B）时按 max_payload 切片分包，
靠 dcp 帧 seq 保证有序重组（transmit.Deduplicator/Transmitter 已提供序号语义）。
"""
from __future__ import annotations

from .encoder import EncodedBlock

HEADER_LEN = 4


def pack_block(block: EncodedBlock) -> bytes:
    """EncodedBlock → 自描述字节包（generation/block_id/k/L 头 + 系数 + 数据）。"""
    k = block.k
    L = len(block.data)
    if not (0 <= block.generation <= 255 and 0 <= block.block_id <= 255):
        raise ValueError("generation/block_id 超出 1B 范围")
    if not (0 <= k <= 255 and 0 <= L <= 255):
        raise ValueError("k/L 超出 1B 范围")
    if len(block.coefficients) != k:
        raise ValueError("系数向量长度 != k")
    return (
        bytes([block.generation & 0xFF, block.block_id & 0xFF, k, L])
        + block.coefficients
        + block.data
    )


def unpack_block(packet: bytes) -> EncodedBlock | None:
    """字节包 → EncodedBlock；magic 缺省，长度不符/非 bytes 返回 None（不抛错）。"""
    if not isinstance(packet, (bytes, bytearray)) or len(packet) < HEADER_LEN:
        return None
    generation, block_id, k, L = packet[0], packet[1], packet[2], packet[3]
    if len(packet) != HEADER_LEN + k + L:
        return None
    coeff = bytes(packet[HEADER_LEN:HEADER_LEN + k])
    data = bytes(packet[HEADER_LEN + k:])
    return EncodedBlock(generation, block_id, coeff, data)


def fragment_for_dcp(packet: bytes, max_payload: int = 42) -> list[bytes]:
    """按 dcp payload 上限切片（每片 ≤ max_payload），靠 dcp seq 保证顺序。"""
    if max_payload < 1:
        raise ValueError("max_payload 必须 >= 1")
    return [packet[i:i + max_payload] for i in range(0, len(packet), max_payload)]


def reassemble_from_dcp(chunks: list[bytes]) -> bytes:
    """拼接 dcp payload 片，还原完整编码块字节包。"""
    return b"".join(chunks)


__all__ = [
    "HEADER_LEN",
    "pack_block",
    "unpack_block",
    "fragment_for_dcp",
    "reassemble_from_dcp",
]
