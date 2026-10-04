"""APC-RLNC C-02 · GF(2^8) 有限域 + 分层 RLNC 编解码测试。

覆盖：GF 运算正确性（AES 向量 + 域公理）/ 编解码往返 / 丢块恢复（丢 1~r 块）/
线性相关块跳过 / 冗余系数映射 / 世代隔离 / 坏块容错 / 打包拆包 / dcp 分包 /
C-01→C-02 集成（聚类档位驱动冗余）。
"""
from __future__ import annotations

import random

from mcpserver.rf_brain.rlnc import (
    EncodedBlock,
    ReliabilityClusterer,
    RlncDecoder,
    RlncEncoder,
    fragment_for_dcp,
    gf_add,
    gf_div,
    gf_inv,
    gf_mul,
    gf_pow,
    gf_sub,
    pack_block,
    reassemble_from_dcp,
    redundancy_blocks,
    unpack_block,
)


def _blocks(k: int, L: int = 8) -> list[bytes]:
    """确定性生成 k 个 L 字节互不相同的原始块。"""
    return [bytes(((i * 31 + j) % 256) for j in range(L)) for i in range(k)]


# ---------- GF(2^8) ----------

def test_gf_mul_known_aes_vectors() -> None:
    """乘法表验证（AES 0x11B 标准向量 + 零元/幺元）。"""
    assert gf_mul(0x02, 0x80) == 0x1B  # xtime(0x80)
    assert gf_mul(0x03, 0x80) == 0x9B  # 0x80 ^ xtime(0x80)
    assert gf_mul(0x53, 0xCA) == 0x01  # 0x53 与 0xCA 互逆
    assert gf_mul(0x00, 0xFF) == 0
    assert gf_mul(0xFF, 0x00) == 0
    assert gf_mul(0x01, 0xAB) == 0xAB


def test_gf_field_axioms() -> None:
    """域公理：逆元 / 自消 / 封闭 / 交换 / 分配律（抽样）。"""
    for a in range(1, 256):
        assert gf_inv(a) != 0
        assert gf_mul(a, gf_inv(a)) == 1
        assert gf_add(a, a) == 0
        assert gf_sub(a, a) == 0
        assert gf_pow(a, 0) == 1
    for a in range(256):
        for b in range(256):
            assert 0 <= gf_mul(a, b) <= 255  # 封闭
            assert gf_mul(a, b) == gf_mul(b, a)  # 交换
            assert gf_add(a, b) == gf_add(b, a)
    # 分配律抽样（全 256^3 过大，取 0..63 子集）
    for a in range(64):
        for b in range(64):
            for c in range(64):
                assert gf_mul(gf_add(a, b), c) == gf_add(gf_mul(a, c), gf_mul(b, c))


def test_gf_div_and_pow() -> None:
    """除法与幂：a/b == a·inv(b)；a^255 == 1（费马小定理，非零元）。"""
    for a in range(1, 256):
        assert gf_pow(a, 255) == 1
        assert gf_pow(a, 2) == gf_mul(a, a)
        for b in range(1, 256):
            assert gf_div(a, b) == gf_mul(a, gf_inv(b))


# ---------- 编解码 ----------

def test_encode_decode_roundtrip() -> None:
    """编解码往返：k 原始块经系统式编码，满秩解码还原。

    注意：前 k 个系统块（单位系数）已张成整个空间，后续冗余块必然线性相关
    （add_block 返回 False 被跳过），故不逐块断言创新，只断言满秩解码正确。
    """
    k = 4
    orig = _blocks(k)
    enc = RlncEncoder(k=k, factor=0.5, generation=1, seed=42)
    coded = enc.encode(orig)
    assert len(coded) == enc.n == k + enc.r
    dec = RlncDecoder(k=k, generation=1)
    for b in coded:
        dec.add_block(b)
    assert dec.rank == k
    assert dec.decode() == orig


def test_loss_recovery_drop_1_to_r() -> None:
    """丢块恢复：丢 1~r 块（任意子集）仍解出原始块。"""
    k, factor = 6, 0.5  # r = floor(6*0.5) = 3
    orig = _blocks(k)
    enc = RlncEncoder(k=k, factor=factor, seed=11)
    coded = enc.encode(orig)
    assert enc.r == 3
    rng = random.Random(5)
    for drop_count in range(1, enc.r + 1):
        drop = set(rng.sample(range(enc.n), drop_count))
        kept = [b for i, b in enumerate(coded) if i not in drop]
        dec = RlncDecoder(k=k)
        for b in kept:
            dec.add_block(b)
        assert dec.decode() == orig, f"丢 {drop_count} 块应仍可解"


def test_linear_dependent_skip() -> None:
    """线性相关块被跳过：重复块 add 返回 False，不破坏解码。"""
    k = 4
    orig = _blocks(k)
    enc = RlncEncoder(k=k, factor=0.5, seed=1)
    coded = enc.encode(orig)
    dec = RlncDecoder(k=k)
    assert dec.add_block(coded[0]) is True
    assert dec.add_block(coded[0]) is False  # 重复 → 线性相关
    assert dec.rank == 1
    for b in coded[1:]:
        dec.add_block(b)
    assert dec.decode() == orig


def test_redundancy_factor_mapping() -> None:
    """冗余系数映射：r = ⌊k × factor⌋，且开销 ≤ 原始块数 × 冗余率。"""
    assert redundancy_blocks(10, 0.6) == 6
    assert redundancy_blocks(4, 0.3) == 1
    assert redundancy_blocks(10, 0.0) == 0
    assert redundancy_blocks(4, 0.99) == 3
    for k in range(1, 32):
        for factor in (0.0, 0.25, 0.5, 0.75, 1.0):
            r = redundancy_blocks(k, factor)
            assert r <= k * factor + 1e-9  # 硬约束


def test_generation_isolation() -> None:
    """世代隔离：不同 generation 的块互不污染，全部被拒。"""
    k = 3
    enc0 = RlncEncoder(k=k, factor=0.5, generation=0, seed=2)
    enc1 = RlncEncoder(k=k, factor=0.5, generation=1, seed=2)
    dec = RlncDecoder(k=k, generation=0)
    for b in enc1.encode(_blocks(k)):
        assert dec.add_block(b) is False
    assert dec.rank == 0


def test_bad_block_tolerance() -> None:
    """坏块容错：错误 k / 错误长度 / 全零系数块被拒，不影响正确块解码。"""
    k = 4
    orig = _blocks(k)
    enc = RlncEncoder(k=k, factor=0.5, seed=3)
    coded = enc.encode(orig)

    wrong_k = EncodedBlock(0, 0, b"\x01\x00\x00", b"\x00" * 8)      # k=3 != 4
    wrong_len = EncodedBlock(0, 99, b"\x00" * k, b"\x00" * 7)       # L=7 != 8
    zero_coeff = EncodedBlock(0, 98, b"\x00" * k, b"\x00" * 8)      # 全零系数

    dec = RlncDecoder(k=k)
    assert dec.add_block(wrong_k) is False
    assert dec.add_block(wrong_len) is False
    assert dec.add_block(zero_coeff) is False
    assert dec.rank == 0
    for b in coded:
        dec.add_block(b)
    assert dec.decode() == orig


# ---------- 打包 / dcp 承载 ----------

def test_packetize_roundtrip() -> None:
    """打包/拆包往返：元信息头 + 系数 + 数据无损；坏包返回 None。"""
    k = 6
    enc = RlncEncoder(k=k, factor=0.5, generation=7, seed=9)
    coded = enc.encode(_blocks(k))
    for b in coded:
        pkt = pack_block(b)
        rb = unpack_block(pkt)
        assert rb is not None
        assert rb.generation == b.generation
        assert rb.block_id == b.block_id
        assert rb.coefficients == b.coefficients
        assert rb.data == b.data
    assert unpack_block(b"") is None
    assert unpack_block(b"\x00\x01\x02") is None  # 过短
    good = pack_block(coded[0])
    assert unpack_block(good[:-1]) is None  # 长度不符


def test_dcp_fragment_reassemble() -> None:
    """dcp payload 切片 + 重组：超过 42B 上限的编码块分包往返。"""
    enc = RlncEncoder(k=16, factor=0.25, generation=3, seed=4)
    coded = enc.encode([bytes([i]) * 40 for i in range(16)])
    pkt = pack_block(coded[-1])
    assert len(pkt) > 42  # 需要分包
    chunks = fragment_for_dcp(pkt, max_payload=42)
    assert all(len(c) <= 42 for c in chunks)
    assert reassemble_from_dcp(chunks) == pkt
    assert unpack_block(reassemble_from_dcp(chunks)) is not None


# ---------- C-01 → C-02 集成 ----------

def test_integration_cluster_drives_redundancy() -> None:
    """集成：聚类档位决定冗余率，驱动编码冗余块数；弱链路高冗余且丢块可恢复。"""
    clusterer = ReliabilityClusterer()
    weak = clusterer.redundancy_for(clusterer.classify(0.2))
    strong = clusterer.redundancy_for(clusterer.classify(0.95))
    assert weak == 0.6
    assert strong == 0.0

    k = 8
    assert redundancy_blocks(k, weak) == 4   # floor(8*0.6)
    assert redundancy_blocks(k, strong) == 0

    orig = _blocks(k)
    enc = RlncEncoder(k=k, factor=weak, seed=8)
    coded = enc.encode(orig)
    assert enc.r == 4
    rng = random.Random(0)
    drop = set(rng.sample(range(enc.n), enc.r))
    kept = [b for i, b in enumerate(coded) if i not in drop]
    dec = RlncDecoder(k=k)
    for b in kept:
        dec.add_block(b)
    assert dec.decode() == orig
