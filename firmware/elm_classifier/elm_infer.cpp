/* elm_infer.cpp — OTA-ELM int8 定点推理实现。
 *
 * 与 tools/elm_train.py 的 QuantizedELM 逐位对齐，关键语义：
 *   1) x_q  = clamp(floor(x*A + B + 0.5), -128, 127)
 *   2) acc1 = Σ x_q*W1_q + B1_q            （int64）
 *   3) hp   = requant64(acc1, M1, S1)      （≈ pre_act / s_pre）
 *   4) h_q  = SIG_LUT[clamp(hp,-128,127)+128]
 *   5) zq   = Σ h_q*B_q + OFF              （int64，= logit 的定点形式）
 *   6) l8   = clamp(requant64(zq, M2, S2), -128, 127)
 *   7) d    = l8max - l8；E = EN_LUT[d]；p = E*1000/ΣE（整数 softmax）
 * requant64(a,m,s) = (a*m + (1<<(s-1))) >> s（算术右移，与 Python floor 一致）。
 *
 * 无浮点超越函数：exp/pow 只出现在 tools/elm_train.py 的 LUT 离线构造中。
 */

#include "elm_infer.h"
#include <math.h>   /* 仅 floor()，非超越函数 */

/* 定点重量化：与 Python 的 requant() 逐位一致（int64 累加 + 算术右移）。 */
static inline int64_t requant64(int64_t acc, int32_t mult, int32_t shift) {
    int64_t half = (shift > 0) ? (1LL << (shift - 1)) : 0;
    return (acc * (int64_t)mult + half) >> shift;
}

static inline int8_t clamp_i8(int64_t v) {
    if (v > 127) return 127;
    if (v < -128) return -128;
    return (int8_t)v;
}

void elm_quantize_input(const double x[ELM_N_FEATURES], int8_t x_q[ELM_N_FEATURES]) {
    for (int i = 0; i < ELM_N_FEATURES; i++) {
        /* v = x*scale + 0.5，再 floor：与 Python floor(x*scale+0.5) 一致 */
        double v = x[i] * ELM_X_A[i] + ELM_X_B[i] + 0.5;
        int32_t q = (int32_t)floor(v);
        if (q > 127) q = 127;
        else if (q < -128) q = -128;
        x_q[i] = (int8_t)q;
    }
}

void elm_run(const int8_t x_q[ELM_N_FEATURES], elm_result_t *out) {
    /* ---- 第 1 层：int64 矩阵乘 + 偏置 + 重量化 + sigmoid LUT ---- */
    int8_t h_q[ELM_N_HIDDEN];
    for (int j = 0; j < ELM_N_HIDDEN; j++) {
        int64_t acc = (int64_t)ELM_B1_Q[j];
        for (int i = 0; i < ELM_N_FEATURES; i++) {
            acc += (int64_t)x_q[i] * ELM_W1_Q[i * ELM_N_HIDDEN + j];
        }
        int64_t hp = requant64(acc, ELM_M1[0], ELM_S1[0]);
        h_q[j] = ELM_SIG_LUT[clamp_i8(hp) + 128];
    }

    /* ---- 第 2 层：int64 累加 + sigmoid 中心偏移折叠 + 重量化 ---- */
    int32_t l8[ELM_N_OUTPUTS];
    for (int k = 0; k < ELM_N_OUTPUTS; k++) {
        int64_t acc = (int64_t)ELM_OFF[k];
        for (int j = 0; j < ELM_N_HIDDEN; j++) {
            acc += (int64_t)h_q[j] * ELM_B_Q[j * ELM_N_OUTPUTS + k];
        }
        l8[k] = (int32_t)clamp_i8(requant64(acc, ELM_M2[0], ELM_S2[0]));
        out->logit_q[k] = l8[k];
    }

    /* ---- 整数 softmax：EN LUT ---- */
    int32_t lmax = l8[0];
    for (int k = 1; k < ELM_N_OUTPUTS; k++) {
        if (l8[k] > lmax) lmax = l8[k];
    }
    uint16_t e[ELM_N_OUTPUTS];
    int32_t sum = 0;
    for (int k = 0; k < ELM_N_OUTPUTS; k++) {
        int32_t d = lmax - l8[k];
        if (d < 0) d = 0;
        else if (d > 255) d = 255;
        e[k] = (uint16_t)ELM_EN_LUT[d];
        sum += e[k];
    }
    if (sum < 1) sum = 1;  /* 防除零（理论不发生，防御性） */

    uint8_t best = 0;
    for (int k = 0; k < ELM_N_OUTPUTS; k++) {
        out->prob_permille[k] = (uint16_t)((e[k] * 1000) / sum);
        if (l8[k] > l8[best]) best = k;  /* 平局取索引小者，与 np.argmax 一致 */
    }
    out->class_index = best;
    out->confidence_permille = out->prob_permille[best];
}
