"""分层 RLNC 解码器：收集 ≥k 个线性无关编码块，RREF 高斯消元还原原始块。

在线增量高斯消元（约化行阶梯形 RREF）：
  - 每个到达块先对既有主元行消元；消元后系数全零 → 线性相关，跳过（返回 False）
  - 否则找首个非零系数列 c，归一化后消去其余行在 c 列的系数，成为新主元行
  - 主元数达到 k（满秩）后 decode 按主元列还原 k 个原始块

坏块容错：世代错 / 系数长度错(k 不符) / 载荷长度错 / 全零系数块一律拒绝
（返回 False），不破坏已收正确块；块级完整性由下层 dcp 帧 CRC 保证。
"""
from __future__ import annotations

from .encoder import EncodedBlock
from .galois import gf_inv, gf_mul, gf_sub


class RlncDecoder:
    """增量 RLNC 解码器，按世代隔离（generation=None 表示接受任意世代）。"""

    def __init__(self, k: int, generation: int | None = None) -> None:
        self.k = k
        self.generation = generation
        self.block_size: int | None = None
        # 主元列 -> (系数向量, 数据)，始终保持 RREF
        self._rows: list[tuple[int, tuple[list[int], bytearray]]] = []

    @property
    def rank(self) -> int:
        """当前收集到的线性无关块数（= 已用主元数）。"""
        return len(self._rows)

    def add_block(self, block: EncodedBlock) -> bool:
        """加入一个编码块。创新（增加秩）返回 True，线性相关/坏块返回 False。"""
        if block.k != self.k:
            return False
        if self.generation is not None and block.generation != self.generation:
            return False
        L = len(block.data)
        if self.block_size is not None and self.block_size != L:
            return False

        coeff = list(block.coefficients)
        data = bytearray(block.data)

        # 对既有主元行消元
        for pivot, (pcoeff, pdata) in self._rows:
            c = coeff[pivot]
            if c != 0:
                coeff = [gf_sub(x, gf_mul(c, pc)) for x, pc in zip(coeff, pcoeff)]
                data = bytearray(gf_sub(d, gf_mul(c, pd)) for d, pd in zip(data, pdata))

        # 找首个非零系数列作为主元
        pivot = next((i for i, x in enumerate(coeff) if x != 0), None)
        if pivot is None:
            return False  # 线性相关

        # 首个创新块才锁定块长（坏块/线性相关块不污染 block_size）
        if self.block_size is None:
            self.block_size = L

        # 归一化：主元系数置 1
        inv = gf_inv(coeff[pivot])
        coeff = [gf_mul(x, inv) for x in coeff]
        data = bytearray(gf_mul(d, inv) for d in data)

        # 消去既有行在该主元列的系数（维持 RREF）
        for idx, (p, (pcoeff, pdata)) in enumerate(self._rows):
            factor = pcoeff[pivot]
            if factor != 0:
                pcoeff = [gf_sub(x, gf_mul(factor, cc)) for x, cc in zip(pcoeff, coeff)]
                pdata = bytearray(gf_sub(d, gf_mul(factor, dd)) for d, dd in zip(pdata, data))
                self._rows[idx] = (p, (pcoeff, pdata))

        self._rows.append((pivot, (coeff, data)))
        return True

    def decode(self) -> list[bytes] | None:
        """满秩（rank==k）时返回 k 个原始块（按块序），否则 None。"""
        if len(self._rows) < self.k:
            return None
        result: dict[int, bytes] = {}
        for pivot, (_, data) in self._rows:
            result[pivot] = bytes(data)
        if set(result) != set(range(self.k)):
            return None
        return [result[i] for i in range(self.k)]


__all__ = ["RlncDecoder"]
