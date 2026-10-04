# -*- coding: utf-8 -*-
"""AC-02 · 资产生成器：训练 ELM → 导出 C++ 权重/LUT 头 + 黄金向量 JSON。

运行（仓库根）：
  python tools/gen_elm_assets.py
产物（勿手改，固定种子可复现，pytest 有决定论用例）：
  firmware/elm_lut/elm_weights.h   定点权重 W_q/b_q/Wout_q + tanh LUT + float 参考权重
  tools/elm_golden.json            黄金向量 + 精度/误差/基准统计（pytest 断言源）

ELM"训练"= 固定随机输入权重 + 岭回归解析解（无反向传播，授粉点要义）。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from elm_lut import (
    CLASS_N,
    FEATURE_DIM,
    H_SCALE,
    HIDDEN,
    LUT_N,
    LUT_OUT_MAX,
    LUT_U_STEP_BITS,
    OUT_SCALE_BITS,
    PER_CLASS_TEST,
    PER_CLASS_TRAIN,
    RIDGE_LAMBDA,
    TANH_LUT,
    TEST_SEED_DATA,
    TRAIN_SEED_DATA,
    TRAIN_SEED_W,
    W_SCALE_BITS,
    X_SCALE_BITS,
    _draw_weights,
    _forward_hidden_float,
    _forward_hidden_int,
    _quantize_weights,
    argmax3,
    benchmark_host,
    elm_features_real,
    evaluate,
    infer_float,
    infer_lut,
    lut_error_table,
    make_mock_packet,
    quantize_x,
    train_elm,
)

REPO = Path(__file__).resolve().parents[1]
GOLDEN_SEED = 20260901
GOLDEN_PER_CLASS = 4   # 12 条


def main():
    W, b, Wout_f, Wout_q, W_q, b_q = train_elm()
    stats = evaluate(W, b, Wout_f, Wout_q, W_q, b_q)
    err = lut_error_table()

    # 黄金向量：固定种子合成包 → 双路径 logits/预测
    rng = random.Random(GOLDEN_SEED)
    golden = []
    for cls in (0, 1, 2):
        for _ in range(GOLDEN_PER_CLASS):
            pkt = make_mock_packet(cls, rng)
            feats = elm_features_real(pkt)
            x_q = quantize_x(feats)
            lf = infer_float(feats, W, b, Wout_f)
            ll = infer_lut(x_q, W_q, b_q, Wout_q)
            golden.append({
                "hex": pkt.hex(),
                "x_q": x_q,
                "float_logits": [round(v, 6) for v in lf],
                "lut_logits": ll,
                "pred_float": argmax3(lf),
                "pred_lut": argmax3(ll),
                "cls": cls,
                "margin": round(sorted(lf)[-1] - sorted(lf)[-2], 4),
            })

    bench = benchmark_host()

    # ---- C++ 头 ----
    hdr = REPO / "firmware/elm_lut/elm_weights.h"
    hdr.parent.mkdir(parents=True, exist_ok=True)
    L = [
        "/* AC-02 · OTA-ELM 查表推理 · 权重 + tanh LUT + 黄金向量",
        " * （由 tools/gen_elm_assets.py 生成——勿手改，固定种子可复现）",
        " *",
        f" * 输入权重种子 W_SEED={TRAIN_SEED_W}（固定随机，ELM 不训练输入层）；",
        f" * 训练集种子={TRAIN_SEED_DATA} 每类 {PER_CLASS_TRAIN}；测试集种子={TEST_SEED_DATA} 每类 {PER_CLASS_TEST}；",
        f" * 岭回归 λ={RIDGE_LAMBDA}；定点：x Q{X_SCALE_BITS} / w Q{W_SCALE_BITS} / wout Q{OUT_SCALE_BITS}，隐层输出 /{H_SCALE}；",
        f" * LUT：{LUT_N} 项 int8，u = idx/2^{LUT_U_STEP_BITS}（覆盖 ±4.0 饱和区），输出 Q7 /{H_SCALE}。",
        " * 任务：收包 8 维频谱特征 → 3 类（NORMAL/NOISE/BAD_FRAME，mock 合成数据）。",
        " */",
        "#pragma once",
        "#include <stdint.h>",
        "",
        "#define ELM_FEATURE_DIM 8",
        f"#define ELM_HIDDEN {HIDDEN}",
        "#define ELM_CLASS_N 3",
        f"#define ELM_X_SCALE_BITS {X_SCALE_BITS}",
        f"#define ELM_OUT_SCALE_BITS {OUT_SCALE_BITS}",
        f"#define ELM_H_SCALE {H_SCALE}",
        f"#define ELM_LUT_STEP_BITS {LUT_U_STEP_BITS}",
        "",
        f"/* tanh 查找表 {LUT_N} 项（int8 Q7；超表面固定非线性响应的 MCU 映射） */",
        "static const int8_t ELM_TANH_LUT[256] = {",
    ]
    for row0 in range(0, LUT_N, 16):
        vals = ", ".join(str(v) for v in TANH_LUT[row0:row0 + 16])
        L.append(f"    {vals},")
    L += [
        "};",
        "",
        "/* 输入权重定点 Q8（int16）与偏置 */",
        f"static const int16_t ELM_W_Q[{HIDDEN}][{FEATURE_DIM}] = {{",
    ]
    for row in W_q:
        L.append("    {" + ", ".join(str(v) for v in row) + "},")
    L.append("};")
    L.append("static const int16_t ELM_B_Q[" + str(HIDDEN) + "] = {")
    L.append("    " + ", ".join(str(v) for v in b_q) + ",")
    L += [
        "};",
        "",
        "/* 输出权重定点 Q8（int16），末列为偏置（隐层偏置列固定 127） */",
        f"static const int16_t ELM_WOUT_Q[{CLASS_N}][{HIDDEN + 1}] = {{",
    ]
    for row in Wout_q:
        L.append("    {" + ", ".join(str(v) for v in row) + "},")
    L += [
        "};",
        "",
        "/* float 参考权重（double 字面量，供 infer_float 对照路径） */",
        f"static const double ELM_W_F[{HIDDEN}][{FEATURE_DIM}] = {{",
    ]
    for row in W:
        L.append("    {" + ", ".join(f"{v:.17g}" for v in row) + "},")
    L.append("};")
    L.append("static const double ELM_B_F[" + str(HIDDEN) + "] = {")
    L.append("    " + ", ".join(f"{v:.17g}" for v in b) + ",")
    L.append("};")
    L.append(f"static const double ELM_WOUT_F[{CLASS_N}][{HIDDEN + 1}] = {{")
    for row in Wout_f:
        L.append("    {" + ", ".join(f"{v:.17g}" for v in row) + "},")
    L += [
        "};",
        "",
        "typedef struct {",
        "    const char *hex;             /* mock 收包 hex */",
        "    int cls;                     /* 真实类别 */",
        "    int x_q[ELM_FEATURE_DIM];    /* 定点特征 */",
        "    double float_logits[ELM_CLASS_N];",
        "    int32_t lut_logits[ELM_CLASS_N];",
        "    int pred_float, pred_lut;",
        "} elm_golden_vec_t;",
        "",
        f"#define ELM_GOLDEN_N {len(golden)}",
        "static const elm_golden_vec_t ELM_GOLDEN[ELM_GOLDEN_N] = {",
    ]
    for g in golden:
        xq = ", ".join(str(v) for v in g["x_q"])
        fl = ", ".join(f"{v:.6f}" for v in g["float_logits"])
        ll = ", ".join(str(v) for v in g["lut_logits"])
        L.append(f"    {{\"{g['hex']}\", {g['cls']}, {{{xq}}}, {{{fl}}}, {{{ll}}}, "
                 f"{g['pred_float']}, {g['pred_lut']}}},")
    L += ["};", ""]
    hdr.write_text("\n".join(L), encoding="utf-8")

    # ---- JSON ----
    payload = {
        "generator": "tools/gen_elm_assets.py",
        "seeds": {"w": TRAIN_SEED_W, "train": TRAIN_SEED_DATA,
                  "test": TEST_SEED_DATA, "golden": GOLDEN_SEED},
        "hyper": {"hidden": HIDDEN, "feature_dim": FEATURE_DIM,
                  "per_class_train": PER_CLASS_TRAIN,
                  "per_class_test": PER_CLASS_TEST,
                  "ridge_lambda": RIDGE_LAMBDA},
        "lut_error": err,
        "accuracy": {
            "acc_float": stats["acc_float"], "acc_lut": stats["acc_lut"],
            "acc_delta": stats["acc_delta"],
            "confusion_float": stats["confusion_float"],
            "confusion_lut": stats["confusion_lut"],
            "per_class_float": stats["per_class_float"],
            "per_class_lut": stats["per_class_lut"],
        },
        "bench_host": bench,
        "golden": golden,
    }
    (REPO / "tools/elm_golden.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"精度: float={stats['acc_float']:.4f} lut={stats['acc_lut']:.4f} "
          f"delta={stats['acc_delta']:.4f} (验收线 ≤0.05)")
    print(f"LUT 误差: max={err['max_abs']:.4f} mean={err['mean_abs']:.5f} "
          f"(理论界 {err['theoretical_bound']:.4f})")
    print(f"黄金向量: {len(golden)} 条 (最小 float margin "
          f"{min(g['margin'] for g in golden):.3f})")
    print(f"主机基准(CPython 参考): lut={bench['ns_per_sample_lut']:.0f}ns "
          f"float={bench['ns_per_sample_float']:.0f}ns /样本")
    print(f"→ {hdr.relative_to(REPO)} + tools/elm_golden.json")


if __name__ == "__main__":
    main()
