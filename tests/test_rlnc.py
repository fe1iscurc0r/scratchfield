"""工单 243 任务二：RLNC 编解码**兼容层**的回归测试。

本文件同时是**兼容层「不重复实现」的守卫**：
- 身份契约：`mcpserver.esp32.rlnc` 的符号必须 `is` `mcpserver.rf_brain.rlnc` 的对象
  （不是拷贝、不是重写）⇒ 任何一边改了数学，另一边立刻同步，不存在两套公式。
- 依赖契约：兼容层**导入链**不得引入 numpy/scipy/torch 等重依赖 ⇒ 由两条用例守住：
  静态断言 `__init__.py` 的镜像模块表不含 numpy 那支（`apc_mesh_routing`），
  以及子进程实证 `import mcpserver.esp32.rlnc` 后 `sys.modules` 无重依赖。

功能覆盖：10 个随机种子的编解码往返 / 少一包边界 / 30% 丢包 / 坏块拒收且不污染 /
块长基准锁定边界（留证）/ k=1 与 factor=0 边界 / 冗余块数取 floor / GF(2^8) 域性质 / k 推断。
"""
from __future__ import annotations

import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

import mcpserver.esp32.rlnc as esp
import mcpserver.rf_brain.rlnc as ref
from mcpserver.esp32.rlnc import (
    EncodedBlock,
    RlncDecoder,
    RlncEncoder,
    decode_full,
    encode_random,
    gf_add,
    gf_inv,
    gf_mul,
    redundancy_blocks,
)

pytestmark = [pytest.mark.core]

K = 8
FACTOR = 0.6
SOURCE = [bytes([i] * 32) for i in range(K)]


def _source(k: int = K) -> list[bytes]:
    return [bytes([(i * 7 + 3) % 256] * 16) for i in range(k)]


# ---------------------------------------------------------------- 身份契约


@pytest.mark.parametrize(
    "name",
    ["EncodedBlock", "RlncEncoder", "RlncDecoder", "redundancy_blocks",
     "gf_mul", "gf_inv", "gf_add", "ReliabilityClusterer", "EWMAReliability",
     "LossWindow", "PeerState", "pack_block", "unpack_block", "HEADER_LEN"],
)
def test_compat_layer_symbols_are_the_truth_source_objects(name: str) -> None:
    assert getattr(esp, name) is getattr(ref, name), f"{name} 不是真值源对象（被重新实现了？）"


def test_compat_layer_mirrors_whole_all_and_adds_only_two() -> None:
    assert set(ref.__all__) <= set(esp.__all__)
    assert sorted(set(esp.__all__) - set(ref.__all__)) == ["decode_full", "encode_random"]


def test_compat_layer_import_chain_has_no_heavy_dependency() -> None:
    """兼容层**镜像的那 7 个模块**必须保持纯标准库。

    ⚠️ 口径修正（实测发现）：`mcpserver/rf_brain/rlnc/` **整包并不是**纯标准库 ——
    同目录的 `apc_mesh_routing.py` 用了 `import numpy as np`。但它**不在**
    `rf_brain/rlnc/__init__.py` 的导入链上，因此兼容层（`from ... import *`）不会拖入 numpy。
    """
    pkg = Path(ref.__file__).resolve().parent
    mirrored = re.findall(r"^from \.(\w+) import", (pkg / "__init__.py").read_text(encoding="utf-8"),
                          re.M)
    assert mirrored, "未解析到 rf_brain.rlnc.__init__ 的镜像模块列表"
    assert "apc_mesh_routing" not in mirrored, "numpy 那支不该进导入链"
    offenders = []
    for name in [*mirrored, "__init__"]:
        text = (pkg / f"{name}.py").read_text(encoding="utf-8")
        for line in text.splitlines():
            if re.match(r"\s*(import|from)\s+(numpy|scipy|torch)", line):
                offenders.append(f"{name}.py: {line.strip()}")
    assert offenders == [], f"导入链上出现重依赖: {offenders}"
    esp_pkg = Path(esp.__file__).resolve().parent
    for name in ("__init__.py", "encoder.py", "decoder.py"):
        text = (esp_pkg / name).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(numpy|scipy|torch)", text, re.M), name


def test_importing_compat_layer_does_not_pull_numpy() -> None:
    """子进程实证：单独 import 兼容层，`numpy` 不出现在 `sys.modules` 里。"""
    repo_root = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        "import mcpserver.esp32.rlnc as m\n"
        "hits = sorted(k for k in sys.modules if k.split('.')[0] in ('numpy', 'scipy', 'torch'))\n"
        "assert not hits, hits\n"
        "assert 'mcpserver.rf_brain.rlnc.apc_mesh_routing' not in sys.modules\n"
        "print(len(m.__all__))\n"
    )
    proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(repo_root), timeout=120, check=False,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert int(proc.stdout.strip()) == len(esp.__all__)


# ---------------------------------------------------------------- 编解码往返


def test_encode_decode_roundtrip_over_ten_seeds() -> None:
    """工单 §2 任务二.2：10 个随机种子下 encode_random → decode_full 通过率 100%。"""
    source = _source()
    for seed in range(10):
        blocks = encode_random(source, factor=FACTOR, seed=seed)
        assert len(blocks) == K + redundancy_blocks(K, FACTOR)
        assert decode_full(blocks, k=K) == source, f"seed={seed} 未还原"


def test_encode_random_matches_encoder_directly() -> None:
    source = _source(6)
    via_helper = encode_random(source, factor=0.5, seed=3)
    via_class = RlncEncoder(6, 0.5, 0, 3).encode(source)
    assert via_helper == via_class


def test_systematic_blocks_come_first() -> None:
    source = _source(5)
    blocks = encode_random(source, factor=0.4, seed=2)
    for i in range(5):
        assert blocks[i].block_id == i
        assert blocks[i].coefficients == bytes(1 if j == i else 0 for j in range(5))
        assert blocks[i].data == source[i]
    # 冗余块系数非零（拒绝退化块）
    for block in blocks[5:]:
        assert any(block.coefficients)


# ---------------------------------------------------------------- 边界


def test_one_block_short_cannot_decode() -> None:
    """少 1 个编码块（只拿到 k-1 个线性无关块）⇒ 必须返回 None，不能瞎猜。"""
    source = _source()
    blocks = encode_random(source, factor=FACTOR, seed=1)
    assert decode_full(blocks[: K - 1], k=K) is None
    assert decode_full(blocks[:K], k=K) == source


def test_factor_zero_gives_systematic_only_and_still_decodes() -> None:
    source = _source(4)
    blocks = encode_random(source, factor=0.0, seed=0)
    assert len(blocks) == 4
    assert decode_full(blocks, k=4) == source
    # 掉一个就废（没有冗余可补）
    assert decode_full(blocks[:3], k=4) is None


def test_redundancy_blocks_uses_floor() -> None:
    assert redundancy_blocks(8, 0.6) == 4
    assert redundancy_blocks(3, 0.9) == 2
    assert redundancy_blocks(1, 0.99) == 0
    with pytest.raises(ValueError):
        redundancy_blocks(0, 0.5)
    with pytest.raises(ValueError):
        redundancy_blocks(4, -0.1)


def test_k_equals_one_boundary() -> None:
    source = [b"\x2a" * 8]
    blocks = encode_random(source, factor=1.0, seed=0)
    assert len(blocks) == 2
    assert decode_full(blocks, k=1) == source
    assert decode_full(blocks[:1], k=1) == source


def test_k_inference_from_coefficient_mode() -> None:
    source = _source(5)
    blocks = encode_random(source, factor=0.6, seed=4)
    assert decode_full(blocks) == source  # k 缺省按系数长度众数推断
    assert decode_full([]) is None
    assert decode_full([EncodedBlock(0, 0, b"", b"")]) is None


# ---------------------------------------------------------------- 丢包 / 坏块


def test_survives_30pct_block_loss_when_enough_blocks_arrive() -> None:
    """工单 §2 任务二.3：传输中丢包 30%。"""
    source = _source()
    enough = 0
    for seed in range(20):
        blocks = encode_random(source, factor=FACTOR, seed=seed)
        rng = random.Random(seed)
        received = [b for b in blocks if rng.random() >= 0.30]
        if len(received) >= K:
            enough += 1
            assert decode_full(received, k=K) == source, f"seed={seed} 收 {len(received)} 块却未还原"
        else:
            assert decode_full(received, k=K) is None
    assert enough >= 8, f"30% 丢包下只有 {enough}/20 次收够块，与冗余设计不符"


def _bad_blocks(good: list[EncodedBlock]) -> list[EncodedBlock]:
    """四类坏块，各一条。`good` 需为同一世的系统式编码块。"""
    return [
        EncodedBlock(99, 0, good[0].coefficients, good[0].data),            # 世代错
        EncodedBlock(0, 1, good[1].coefficients[:2], good[1].data),         # 系数长度错（k 不符）
        EncodedBlock(0, 2, good[2].coefficients, good[2].data + b"\x00"),   # 载荷长度错
        EncodedBlock(0, 3, bytes(4), bytes(len(good[0].data))),             # 全零系数
    ]


def test_bad_blocks_are_rejected_without_polluting_state() -> None:
    """四类坏块一律拒收，且不污染已收正确块。

    口径对齐真值源 `decoder.py`：
    - 世代错 / 系数长度错（k 不符）/ 全零系数：**与 block_size 无关**，冷启动也应拒收。
    - 载荷长度错：仅在 `block_size` 被首个创新块锁定后**才可判定** —— 故本用例先喂一个
      完好块再喂坏块。这条边界单独留证于
      `test_first_accepted_block_locks_block_size_known_boundary`。
    """
    source = _source(4)
    good = encode_random(source, factor=0.5, seed=9)
    assert len(good) >= 4
    block_len = len(good[0].data)

    # 阶段一：冷启动（block_size 未锁定）——与块长无关的三类坏块就该被拒
    cold = RlncDecoder(4, generation=0)
    bad = _bad_blocks(good)
    for block in (bad[0], bad[1], bad[3]):
        assert cold.add_block(block) is False, block
    assert cold.rank == 0
    assert cold.block_size is None
    assert cold.decode() is None

    # 阶段二：锁定块长后，四类坏块全部拒收，且不改块长基准
    decoder = RlncDecoder(4, generation=0)
    assert decoder.add_block(good[0]) is True
    assert decoder.block_size == block_len
    for block in _bad_blocks(good):
        assert decoder.add_block(block) is False, block
    assert decoder.rank == 1
    assert decoder.block_size == block_len
    assert decoder.decode() is None  # 1 < k

    # 阶段三：坏块在前也不影响后续正确块（阶段二的 decoder 已沾满坏块）
    for block in good:
        decoder.add_block(block)
    assert decoder.decode() == source

    # decode_full 走同一条被拒逻辑（顺序敏感：块长基准必须先由好块建立）
    assert decode_full(good[:4] + _bad_blocks(good), k=4) == source
    assert decode_full(_bad_blocks(good), k=4) is None


def test_first_accepted_block_locks_block_size_known_boundary() -> None:
    """⚠️ 真值源已知边界（留证，勿当缺陷「修」）：块长基准由**首个被接受**的块锁定。

    真值源 `decoder.py` 明写「块级完整性由下层 dcp 帧 CRC 保证」⇒ 解码器**无法自证**
    第一个到达块的载荷长度对错。一个多带 1 字节的脏块若最先到达，会被当作块长基准接受
    （rank 变 1），此后长度正确的块反被拒 ⇒ 该代永远解不出。

    这是真值源既有语义，**不是兼容层引入的**；真值源的正确用法是「CRC 先筛，再进解码器」。
    """
    source = _source(4)
    good = encode_random(source, factor=0.5, seed=9)
    block_len = len(good[0].data)
    dirty = EncodedBlock(0, 2, good[2].coefficients, good[2].data + b"\x00")

    decoder = RlncDecoder(4, generation=0)
    assert decoder.add_block(dirty) is True  # 脏块被接受
    assert decoder.block_size == block_len + 1  # 并成为块长基准
    assert decoder.add_block(good[0]) is False  # 长度正确的块反被拒
    assert decoder.rank == 1
    assert decoder.decode() is None  # 本代中毒，不可恢复


def test_rank_ignores_linearly_dependent_blocks() -> None:
    source = _source(3)
    blocks = encode_random(source, factor=0.4, seed=6)
    decoder = RlncDecoder(3)
    for block in blocks:
        decoder.add_block(block)
    assert decoder.rank == 3
    # 重复投递同一块不再增秩
    for block in blocks:
        assert decoder.add_block(block) is False
    assert decoder.rank == 3


# ---------------------------------------------------------------- GF(2^8) 域性质（经兼容层调用真值源）


@pytest.mark.parametrize("a", [1, 2, 3, 17, 128, 255])
def test_gf_multiplicative_inverse(a: int) -> None:
    assert gf_mul(a, gf_inv(a)) == 1


def test_gf_distributivity_and_identity() -> None:
    for a in (0, 1, 7, 129, 254):
        for b in (0, 3, 16, 200, 255):
            for c in (0, 5, 33, 255):
                assert gf_mul(a, gf_add(b, c)) == gf_add(gf_mul(a, b), gf_mul(a, c))
                assert gf_mul(a, 1) == a
                assert gf_mul(a, 0) == 0
