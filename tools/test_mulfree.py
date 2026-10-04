# -*- coding: utf-8 -*-
"""AC-01 · 无乘法特征提取器 pytest（tools/mulfree_features.py 契约测试）。

用例编号：
  F-01 解析用例（Haar 树手算期望）
  F-02 空包/短包延拓语义
  F-03 黄金向量（与 firmware/mulfree/mulfree_features_test.cpp 同源，Python 生成）
  F-04 原型分类精度（held-out 合成集 ≥95%，mock 标注）
  F-05 整数 vs float 路径符号位等价性
  F-06 AST 纯净性：热路径函数无 * / % 乘除取模（Python 侧可执行不变量）
  F-07 镜像副本守卫：草图目录内 C++ 文件与正本逐字节一致
  F-08 生成器可复现：重跑 gen_mulfree_assets.py 产物逐字节稳定
"""
import ast
import json
import random
import timeit
from pathlib import Path

import pytest
from mulfree_features import (
    CLASS_NAMES,
    FEATURE_BITS,
    box_window_max,
    box_window_sums,
    classify_bits,
    float_feature_signs,
    haar_tree,
    make_dataset,
    make_mock_packet,
    packet_feature_bits,
    popcount,
    weighted_distance,
)

REPO = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((REPO / "tools/mulfree_golden.json").read_text(encoding="utf-8"))
GOLDEN_PROTOS = [(p["cls"], int(p["bits"], 16)) for p in GOLDEN["prototypes"]]


# ---- F-01 解析用例 ----

class TestAnalytic:
    def test_f01a_haar_constant(self):
        """F-01a 常量向量：细节全零，均值=7。"""
        d, fa = haar_tree([7] * 32)
        assert all(x == 0 for x in d) and fa == 7

    def test_f01b_haar_step(self):
        """F-01b 阶跃边沿：L1[15]=0，均值=32（边沿呈现在高层系数）。"""
        d, fa = haar_tree([0] * 16 + [64] * 16)
        assert d[15] == 0 and fa == 32

    def test_f01c_haar_ramp(self):
        """F-01c 线性斜坡 0..31：L1[0..3]=-1（地板除），L5=-8，均值=15。"""
        d, fa = haar_tree(list(range(32)))
        assert tuple(d[0:4]) == (-1, -1, -1, -1)
        assert d[30] == -8 and fa == 15

    def test_f01d_window_max_truncated(self):
        """F-01d 窗最大值：31 点按 4 分窗，末窗 3 点截断。"""
        out = box_window_max([1, 200, 3, 4, 5, 6, 7, 8, 9, 10, 250, 12,
                              13, 14, 15, 16] + [0] * 15, 4)
        assert out == (200, 8, 250, 16, 0, 0, 0, 0)

    def test_f01e_popcount_weighted(self):
        """F-01e popcount 与加权汉明（低 32 位权 1 + 高 8 位权 8 = 96）。"""
        assert popcount(0xF) == 4 and popcount(0) == 0
        assert weighted_distance(0, 0xFFFFFFFFFF) == 96

    def test_f01f_box_sums_reference(self):
        """F-01f 盒式滤波参考形态：前缀和窗和与朴素逐窗求和一致。"""
        samples = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9, 3]
        got = box_window_sums(samples, 8)
        want = (sum(samples[:8]), sum(samples[8:16]))
        assert got == want


# ---- F-02 空包/短包 ----

class TestEdge:
    def test_f02a_empty_packet(self):
        """F-02a 空包：符号位全 1（零系数 >=0），仅尾部补零位(bit45)置位。"""
        bits = packet_feature_bits(b"")
        assert bits == 0x00002000FFFFFFFF

    def test_f02b_short_packet_hold_extension(self):
        """F-02b 短包保持末字节延拓：全同字节短包 → 等价常量向量 → 细节全零。"""
        bits = packet_feature_bits(b"\x2A" * 10)
        d, fa = haar_tree([0x2A] * 32)
        assert all(x == 0 for x in d) and fa == 0x2A
        # 符号位 31+1 位全 1；尾部补零位（bit45）置位（延拓零差分 ≥8）
        assert (bits & 0xFFFFFFFF) == 0xFFFFFFFF
        assert (bits >> 45) & 1 == 1

    def test_f02c_header_alignment(self):
        """F-02c 帧头对齐：帧头→载荷的跳变不计入特征窗（无帧头假尖峰）。

        帧头后载荷 80→100 跳变 20 < 阈值 32；同载荷无帧头时窗口含
        CC(204)→80 跳变（-124）→ 尖峰 bit42 置位。对照组证明对齐生效。
        """
        with_head = bytes([0xD0, 0xCC, 80]) + bytes([100] * 30)
        no_head = bytes([0xCC, 80]) + bytes([100] * 30)
        b1, b2 = packet_feature_bits(with_head), packet_feature_bits(no_head)
        assert (b1 >> 42) & 0b111 == 0, "帧头存在: 载荷区无尖峰"
        assert (b2 >> 42) & 0b001 == 1, "无帧头: 头部跳变落入特征窗产生尖峰"
        assert (b1 >> 41) & 1 == 1 and (b2 >> 41) & 1 == 0  # 帧头位


# ---- F-03 黄金向量 ----

class TestGolden:
    def test_f03a_golden_features(self):
        """F-03a 12 条黄金向量：特征位逐条一致（C++ 自测同源）。"""
        assert len(GOLDEN["golden"]) == 12
        for g in GOLDEN["golden"]:
            bits = packet_feature_bits(bytes.fromhex(g["hex"]))
            assert bits == int(g["bits"], 16)

    def test_f03b_golden_classification(self):
        """F-03b 黄金向量分类 ≥10/12（与实测整体精度 95.33% 同口径，
        难例 BAD→NORMAL 误判如实保留，不做向量挑选）。
        NOISE 行必须全对（该类与另两类语义位差异最大）。"""
        correct = 0
        noise_ok = True
        for g in GOLDEN["golden"]:
            bits = packet_feature_bits(bytes.fromhex(g["hex"]))
            pred, _ = classify_bits(bits, GOLDEN_PROTOS)
            correct += pred == g["cls"]
            if g["cls"] == 1:
                noise_ok = noise_ok and pred == 1
        assert correct >= 10
        assert noise_ok

    def test_f03c_golden_metadata(self):
        """F-03c 生成参数冻结：种子/每类样本数/特征位宽不入漂移。"""
        assert GOLDEN["train_seed"] == 20260829
        assert GOLDEN["test_seed"] == 20260830
        assert GOLDEN["golden_seed"] == 20260831
        assert GOLDEN["feature_bits"] == FEATURE_BITS == 46
        assert GOLDEN["protos_per_class"] == 4
        assert len(GOLDEN["prototypes"]) == 12


# ---- F-04 分类精度（合成 mock 集，诚实标注） ----

class TestClassifier:
    def test_f04a_heldout_accuracy(self):
        """F-04a held-out 合成集加权最近原型 ≥95%（三类 mock，非真机数据）。"""
        test, _ = make_dataset(seed=GOLDEN["test_seed"],
                               per_class=GOLDEN["per_class_test"])
        hit = sum(1 for bits, cls in test if classify_bits(bits, GOLDEN_PROTOS)[0] == cls)
        acc = hit / len(test)
        assert acc == pytest.approx(GOLDEN["accuracy"]["test"], abs=1e-9)
        assert acc >= 0.95

    def test_f04b_deterministic_tie_break(self):
        """F-04b 并列确定性：与两原型等距时取表内先出现者
        （生成器按类 0→2 写表，即最小类索引）。"""
        p = GOLDEN_PROTOS[0][1]
        assert classify_bits(p, [(3, p), (9, p)])[0] == 3
        assert classify_bits(p, [(9, p), (3, p)])[0] == 9


# ---- F-05 整数 vs float 等价性 ----

class TestFloatEquivalence:
    def test_f05a_sign_bit_agreement(self):
        """F-05a 符号位（bit0..31）一致率 ≥97%（黄金向量上实测 ~99.7%）。"""
        same = total = 0
        for g in GOLDEN["golden"]:
            pkt = bytes.fromhex(g["hex"])
            x = (packet_feature_bits(pkt) ^ float_feature_signs(pkt)) & 0xFFFFFFFF
            same += 32 - popcount(x)
            total += 32
        assert same / total >= 0.97
        assert same / total == pytest.approx(GOLDEN["sign_agreement_pct"] / 100,
                                             abs=1e-4)

    def test_f05b_float_path_uses_multiplication(self):
        """F-05b 对照组自证：float 参考路径源码含乘法（确保对照成立，非伪装）。"""
        src = (REPO / "tools/mulfree_features.py").read_text(encoding="utf-8")
        seg = src[src.index("def float_haar_tree("):
                  src.index("def float_feature_signs(")]
        assert seg.count(" * 0.5") >= 2


# ---- F-06 AST 纯净性（Python 侧可执行不变量） ----

MULFREE_HOT_FUNCS = {
    "haar_tree", "box_window_sums", "box_window_max", "_abs_i",
    "packet_window", "abs_diffs_31", "packet_feature_bits", "popcount",
    "hamming_distance", "weighted_distance", "classify_bits",
    "train_prototypes_k",
}


class TestMulFreeInvariant:
    def test_f06a_ast_no_mul_div_mod(self):
        """F-06a 热路径函数 AST 无 * / // %（乘除取模）运算。"""
        src = (REPO / "tools/mulfree_features.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in MULFREE_HOT_FUNCS:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.BinOp) and isinstance(
                            sub.op, (ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)):
                        bad.append((node.name, sub.lineno))
                    if isinstance(sub, ast.AugAssign) and isinstance(
                            sub.op, (ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)):
                        bad.append((node.name, sub.lineno))
        assert not bad, f"热路径发现乘除/取模: {bad}"

    def test_f06b_hot_funcs_covered(self):
        """F-06b 守卫覆盖面：热路径函数清单与模块定义一致（防漏检）。
        C++ 正本侧的指令级验收由 tools/objdump_mulfree_check.py 承担。"""
        src = (REPO / "tools/mulfree_features.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        # float_*/make_* 属对照/mock 区，不要求在热路径清单
        assert defined >= MULFREE_HOT_FUNCS


# ---- F-07 镜像副本守卫 ----

class TestMirrorSync:
    def test_f07a_demo_copies_identical(self):
        """F-07a 草图目录镜像副本与正本逐字节一致（loracanary 同款守卫）。"""
        base = REPO / "firmware/mulfree"
        for name in ("mulfree_features.h", "mulfree_features.cpp",
                     "mulfree_prototypes.h", "mulfree_float_ref.h",
                     "mulfree_float_ref.cpp"):
            canonical = (base / name).read_bytes()
            copy = (base / "mulfree_packet_demo" / name).read_bytes()
            assert copy == canonical, f"镜像副本漂移: {name}"


# ---- F-08 生成器可复现 ----

class TestGeneratorReproducible:
    def test_f08a_golden_vector_determinism(self):
        """F-08a 黄金向量决定论：种子重放逐条复现 hex 与特征位
        （生成器输入全为固定种子 → 产物逐字节可复现）。"""
        rng = random.Random(GOLDEN["golden_seed"])
        i = 0
        for cls in (0, 1, 2):
            for _ in range(GOLDEN["protos_per_class"]):
                pkt = make_mock_packet(cls, rng)
                assert pkt.hex() == GOLDEN["golden"][i]["hex"]
                assert packet_feature_bits(pkt) == int(
                    GOLDEN["golden"][i]["bits"], 16)
                i += 1
        assert i == 12


# ---- 基准数据（README 表格来源，非验收阈值） ----

class TestBenchData:
    def test_benchmark_print_only(self):
        """基准参考：CPython 主机 ns/样本（算法级操作数对比，S3 实测待真机）。
        结果写入 README，不做硬阈值断言（主机性能不代表 S3）。"""
        pkt = bytes.fromhex(GOLDEN["golden"][0]["hex"])
        n = 2000
        t_int = timeit.timeit(lambda: packet_feature_bits(pkt), number=n) / n
        t_flt = timeit.timeit(lambda: float_feature_signs(pkt), number=n) / n
        print(f"\n[bench] mul-free: {t_int * 1e9:.0f} ns/样本 | "
              f"float: {t_flt * 1e9:.0f} ns/样本 | ratio {t_flt / t_int:.2f}x "
              f"(CPython 参考, 非固件实测)")
        assert t_int > 0 and t_flt > 0
