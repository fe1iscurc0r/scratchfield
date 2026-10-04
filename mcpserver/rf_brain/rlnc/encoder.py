"""分层 RLNC 编码器：k 原始块 + r 冗余块 = n 编码块（系统式）。

系统式编码：前 k 个编码块是原始块（单位系数向量 e_i），后 r 个是随机系数的
线性组合。冗余块数 r = ⌊k × factor⌋，factor 由 C-01 聚类结果决定。

硬约束：编码开销（冗余块数 r）≤ 原始块数 × 冗余率（factor），取 floor 保证
r ≤ k×factor。纯 Python + galois 查表实现，不接真硬件（数学库实现）。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .galois import gf_mul


@dataclass
class EncodedBlock:
    """单个编码块：系数向量（k 字节）+ 数据（L 字节）+ 世代/块编号。

    - generation：世代号（同一批 k 原始块共享，跨世代隔离）
    - block_id：块编号（0..k-1 系统块，k..n-1 冗余块）
    - coefficients：k 个 GF(2^8) 系数
    - data：L 字节载荷（原始块等长，编码块同长）
    """

    generation: int
    block_id: int
    coefficients: bytes
    data: bytes

    @property
    def k(self) -> int:
        return len(self.coefficients)


def redundancy_blocks(k: int, factor: float) -> int:
    """冗余块数映射：r = ⌊k × factor⌋（开销 ≤ 原始块数 × 冗余率）。"""
    if k <= 0:
        raise ValueError("k 必须为正整数")
    if factor < 0:
        raise ValueError("冗余率不能为负")
    return math.floor(k * factor)


class RlncEncoder:
    """RLNC 系统式编码器。r 由冗余率 factor 决定，seed 固定随机系数（可复现）。"""

    def __init__(self, k: int, factor: float, generation: int = 0,
                 seed: int | None = None) -> None:
        self.k = k
        self.factor = factor
        self.r = redundancy_blocks(k, factor)
        self.n = k + self.r
        self.generation = generation
        self._rng = random.Random(seed)

    def encode(self, blocks: list[bytes]) -> list[EncodedBlock]:
        """k 个原始块 → n 个编码块。

        原始块需等长；不一致时按最长补齐 0 字节（补齐量由上层载荷长度语义回收，
        与真实传输层一致——解码后由调用方按消息长度裁剪尾部补齐）。
        """
        if len(blocks) != self.k:
            raise ValueError(f"需恰好 {self.k} 个原始块，收到 {len(blocks)} 个")
        L = max(len(b) for b in blocks)
        padded = [b.ljust(L, b"\x00") for b in blocks]

        out: list[EncodedBlock] = []
        # 系统块：单位系数向量 + 原始数据
        for i in range(self.k):
            coeff = bytes(1 if j == i else 0 for j in range(self.k))
            out.append(EncodedBlock(self.generation, i, coeff, padded[i]))
        # 冗余块：随机非零系数向量 + 线性组合
        for i in range(self.r):
            coeff = self._random_coeffs()
            data = self._linear_combine(coeff, padded)
            out.append(EncodedBlock(self.generation, self.k + i, coeff, data))
        return out

    def _random_coeffs(self) -> bytes:
        """随机系数向量（拒绝全零，避免生成退化块）。"""
        while True:
            coeff = bytes(self._rng.randrange(256) for _ in range(self.k))
            if any(coeff):
                return coeff

    @staticmethod
    def _linear_combine(coeffs: bytes, blocks: list[bytes]) -> bytes:
        """c_0·B_0 ⊕ c_1·B_1 ⊕ … ⊕ c_{k-1}·B_{k-1}（逐字节 GF 乘法 + XOR 累加）。"""
        L = len(blocks[0])
        out = bytearray(L)
        for i, c in enumerate(coeffs):
            if c == 0:
                continue
            blk = blocks[i]
            for pos in range(L):
                out[pos] ^= gf_mul(c, blk[pos])
        return bytes(out)


__all__ = ["EncodedBlock", "redundancy_blocks", "RlncEncoder"]
