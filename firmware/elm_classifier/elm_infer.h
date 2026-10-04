/* elm_infer.h — OTA-ELM int8 定点推理核心（纯 C，无 Arduino 依赖，可主机编译）。
 *
 * 与 tools/elm_train.py 的 QuantizedELM._predict_quantized() 逐位一致：
 *   输入 float 特征 → int8 量化 → int64 矩阵乘 + 乘子/移位重量化 → LUT 激活
 *   → int64 输出累加 → 整数 softmax（EN LUT）→ 类别 + 千分比置信度。
 *
 * 无浮点超越函数（exp/pow/log/sin/cos/tan/sqrt 等一律不出现，全部查表）。
 * 模型表由 elm_model.h（tools/elm_train.py 生成）编译期嵌入。
 *
 * 参考：ELM 论文（Huang 2006）思想独立实现；TFLite Micro 定点重量化思想
 * （Apache-2.0）；超表面查表非线性思想（本线自主做法）。
 */
#ifndef ELM_INFER_H
#define ELM_INFER_H

#include <stdint.h>
#include "elm_model.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 分类结果。prob_permille 为 0~1000 千分比，行和≈1000（整数截断误差 ≤no-1）。 */
typedef struct {
    int32_t  logit_q[ELM_N_OUTPUTS];   /* 量化 logit l8（int8 范围，仅供调试） */
    uint16_t prob_permille[ELM_N_OUTPUTS]; /* 各类概率千分比 */
    uint8_t  class_index;              /* argmax 类别下标（平局取索引小者） */
    uint16_t confidence_permille;      /* 最高类概率千分比 */
} elm_result_t;

/* 输入量化：x_q[i] = clamp(floor(x[i]*A[i] + B[i] + 0.5), -128, 127)。
 * A=s_x/std、B=-mean*s_x/std 由 elm_model.h 给出；floor 非超越函数。 */
void elm_quantize_input(const double x[ELM_N_FEATURES], int8_t x_q[ELM_N_FEATURES]);

/* 定点推理：输入 int8 特征，输出分类结果。全程整数运算。 */
void elm_run(const int8_t x_q[ELM_N_FEATURES], elm_result_t *out);

#ifdef __cplusplus
}
#endif

#endif /* ELM_INFER_H */
