# -*- coding: utf-8 -*-
"""AC-01 · 资产生成器：训练 farthest-first k 原型 + 生成 C++ 头/黄金向量（Python/C++ 同源）。

运行（仓库根）：
  python tools/gen_mulfree_assets.py
产物（勿手改，重跑可复现——固定种子，pytest 有复现性用例）：
  firmware/mulfree/mulfree_prototypes.h  原型常量 + 黄金向量表（C++ 正本引用）
  tools/mulfree_golden.json               同源黄金向量 + 精度/一致性统计（pytest 断言）

训练/分类全程无乘法：farthest-first 选择用加权汉明（语义位权 8 = 移位实现），
见 mulfree_features.py train_prototypes_k / weighted_distance / classify_bits。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from mulfree_features import (
    CLASS_NAMES,
    FEATURE_BITS,
    WINDOW,
    float_feature_signs,
    make_dataset,
    make_mock_packet,
    packet_feature_bits,
    train_prototypes_k,
    weighted_distance,
)

REPO = Path(__file__).resolve().parents[1]

TRAIN_SEED = 20260829
TEST_SEED = 20260830
GOLDEN_SEED = 20260831
PER_CLASS_TRAIN = 200
PER_CLASS_TEST = 50
GOLDEN_PER_CLASS = 4     # 3 类 × 4 = 12 条黄金向量
PROTOS_PER_CLASS = 4     # 每类 4 个 farthest-first 原型，共 12 个


def build_prototypes():
    train, _ = make_dataset(seed=TRAIN_SEED, per_class=PER_CLASS_TRAIN)
    test, _ = make_dataset(seed=TEST_SEED, per_class=PER_CLASS_TEST)
    # 原型：仅用训练集，每类 k 个 farthest-first 原型（无乘法）
    by_cls = {c: [] for c in (0, 1, 2)}
    for bits, cls in train:
        by_cls[cls].append(bits)
    proto_list = []  # [(cls, bits), ...]
    for c in (0, 1, 2):
        for p in train_prototypes_k(by_cls[c], k=PROTOS_PER_CLASS):
            proto_list.append((c, p))
    # 评估：加权汉明最近原型
    stats = {}
    for split, data in (("train", train), ("test", test)):
        hit = 0
        for bits, cls in data:
            pred = min((weighted_distance(bits, p), c) for c, p in proto_list)[1]
            hit += 1 if pred == cls else 0
        stats[split] = hit / len(data)
    return proto_list, stats


def sign_agreement(golden_pkts):
    """整数路径 vs 乘法规 float 路径的符号位一致率（README 精度对照表数据）。"""
    same = total = 0
    mask = (1 << 32) - 1  # 比符号位 + 均值符号共 32 位（活动/元数据位两条路径同构）
    for pkt in golden_pkts:
        a = packet_feature_bits(pkt)
        b = float_feature_signs(pkt)
        x = (a ^ b) & mask
        same += 32 - x.bit_count()
        total += 32
    return same / total


def main():
    proto_list, stats = build_prototypes()

    # 黄金向量：独立种子合成，逐条记录 输入hex / 期望特征位 / 期望类别
    rng = random.Random(GOLDEN_SEED)
    golden = []
    for cls in (0, 1, 2):
        for _ in range(GOLDEN_PER_CLASS):
            pkt = make_mock_packet(cls, rng)
            bits = packet_feature_bits(pkt)
            golden.append({"hex": pkt.hex(), "bits": f"0x{bits:X}", "cls": cls})

    agree = sign_agreement([bytes.fromhex(g["hex"]) for g in golden])

    # ---- C++ 头 ----
    hdr = REPO / "firmware/mulfree/mulfree_prototypes.h"
    hdr.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "/* AC-01 · 无乘法特征提取器 · farthest-first 原型 + 黄金向量（由 tools/gen_mulfree_assets.py 生成）",
        " *",
        f" * 训练种子 TRAIN_SEED={TRAIN_SEED} / 测试种子 TEST_SEED={TEST_SEED} / 向量种子 GOLDEN_SEED={GOLDEN_SEED}",
        f" * 每类 {PROTOS_PER_CLASS} 原型共 {len(proto_list)} 个；分类：加权汉明最近原型（语义位权 4，移位实现，无乘法）。",
        " * 三类 mock 样例为合成数据（无真机数据，诚实标注）。",
        " * 勿手改；重跑生成脚本可复现（pytest 复现性用例守卫）。",
        " */",
        "#pragma once",
        "#include <stdint.h>",
        "",
        f"#define MULFREE_FEATURE_BITS {FEATURE_BITS}",
        "#define MULFREE_WINDOW " + str(WINDOW),
        "#define MULFREE_CLASS_N 3",
        "",
        "typedef struct {",
        "    uint8_t cls;          /* 原型所属类别 */",
        "    uint64_t bits;        /* 原型特征位（bit[k] 语义见 tools/mulfree_features.py） */",
        "} mulfree_proto_t;",
        "",
        f"#define MULFREE_PROTO_N {len(proto_list)}",
        "static const mulfree_proto_t MULFREE_PROTOTYPES[MULFREE_PROTO_N] = {",
    ]
    for cls, p in proto_list:
        lines.append(f"    {{{cls}, 0x{p:012X}ULL}}, /* {CLASS_NAMES[cls]} */")
    lines += [
        "};",
        "",
        "typedef struct {",
        "    const char *hex;      /* 帧字节流 hex */",
        "    uint64_t bits;        /* 期望特征位 */",
        "    int cls;              /* 期望类别 */",
        "} mulfree_golden_vec_t;",
        "",
        f"#define MULFREE_GOLDEN_N {len(golden)}",
        "static const mulfree_golden_vec_t MULFREE_GOLDEN[MULFREE_GOLDEN_N] = {",
    ]
    for g in golden:
        lines.append(f"    {{\"{g['hex']}\", 0x{g['bits'][2:]}ULL, {g['cls']}}},")
    lines += ["};", ""]
    hdr.write_text("\n".join(lines), encoding="utf-8")

    # ---- JSON（pytest 断言源） ----
    payload = {
        "generator": "tools/gen_mulfree_assets.py",
        "train_seed": TRAIN_SEED,
        "test_seed": TEST_SEED,
        "golden_seed": GOLDEN_SEED,
        "per_class_train": PER_CLASS_TRAIN,
        "per_class_test": PER_CLASS_TEST,
        "protos_per_class": PROTOS_PER_CLASS,
        "feature_bits": FEATURE_BITS,
        "prototypes": [{"cls": c, "bits": f"0x{p:X}"} for c, p in proto_list],
        "accuracy": stats,
        "sign_agreement_pct": round(agree * 100, 2),
        "golden": golden,
    }
    (REPO / "tools/mulfree_golden.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print("原型: " + "  ".join(f"{CLASS_NAMES[c]}=0x{p:012X}" for c, p in proto_list))
    print(f"最近原型准确率: train={stats['train']:.4f} test={stats['test']:.4f}")
    print(f"整数/float 符号位一致率: {agree * 100:.2f}%")
    print(f"黄金向量: {len(golden)} 条 → {hdr.relative_to(REPO)} + tools/mulfree_golden.json")


if __name__ == "__main__":
    main()
