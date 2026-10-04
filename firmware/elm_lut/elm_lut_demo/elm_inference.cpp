/* AC-02 · OTA-ELM 查表推理 · C++ 正本实现 */
#include "elm_inference.h"
#include "elm_weights.h"
#include <math.h>

namespace elm_lut {

void packet_features_q7(const uint8_t *buf, size_t len, int16_t *x_q) {
    int n = (len > 255u) ? 255 : (int)len;
    bool has_header = (n >= 2 && buf[0] == 0xD0 && buf[1] == 0xCC);
    int off = has_header ? 2 : 0;

    /* 特征窗：帧头后载荷区 / 无帧头取前 32 字节；保持末字节延拓
     * （与 mulfree::packet_window / elm_lut.packet_window 语义一致） */
    int16_t ext[32];
    for (int i = 0; i < 32; i++) {
        int j = off + i;
        ext[i] = (j < n) ? (int16_t)buf[j] : ((n > 0) ? (int16_t)buf[n - 1] : 0);
    }
    int32_t absd[31];
    for (int i = 0; i < 31; i++) {
        int32_t d = (int32_t)ext[i + 1] - (int32_t)ext[i];
        absd[i] = (d < 0) ? -d : d;
    }

    /* f0..f3：4 个 8 点窗能量和 → Q7 = 窗和 <<3（除 16 乘 128 = 乘 8，移位精确） */
    for (int j = 0; j < 4; j++) {
        int base = j << 3;
        int32_t s = 0;
        for (int i = 0; i < 8; i++) {
            if (base + i < 31) {
                s += absd[base + i];
            }
        }
        x_q[j] = (int16_t)(s << 3);
    }
    /* f4：尖峰计数（>=32）→ Q7 = 计数 <<5 */
    int n_spike = 0;
    for (int i = 0; i < 31; i++) {
        if (absd[i] >= 32) {
            n_spike++;
        }
    }
    x_q[4] = (int16_t)(n_spike << 5);
    /* f5：窗内均值字节 → Q7 = Σext <<1（/64·128 = ×2，移位精确） */
    int32_t esum = 0;
    for (int i = 0; i < 32; i++) {
        esum += ext[i];
    }
    x_q[5] = (int16_t)(esum << 1);
    /* f6：帧长 → Q7 = len <<7 */
    x_q[6] = (int16_t)(n << 7);
    /* f7：帧头旗标 → Q7 = 128 / 0 */
    x_q[7] = has_header ? (int16_t)(1 << 7) : 0;
}

void packet_features_real(const uint8_t *buf, size_t len, double *x_real) {
    int16_t x_q[8];
    /* 实数特征 = 定点特征 / 2^7（定点化全部是 2 的幂缩放，两条路径同源） */
    packet_features_q7(buf, len, x_q);
    for (int i = 0; i < kFeatureDim; i++) {
        x_real[i] = (double)x_q[i] / 128.0;
    }
}

int infer_lut(const int16_t *x_q, int32_t *logits_out) {
    int8_t h[kHidden + 1];
    for (int j = 0; j < kHidden; j++) {
        int32_t acc = (int32_t)ELM_B_Q[j] << kXScaleBits;  /* 偏置入 acc 域 */
        for (int i = 0; i < kFeatureDim; i++) {
            acc += (int32_t)ELM_W_Q[j][i] * x_q[i];        /* 整数 MAC */
        }
        int32_t idx = acc >> kLutStepBits;                 /* 算术移位 → 查表索引 */
        if (idx < -128) idx = -128;                        /* 饱和：tanh 已 ±1 */
        if (idx > 127) idx = 127;
        h[j] = ELM_TANH_LUT[idx + 128];                    /* 查表替代 tanh 计算 */
    }
    h[kHidden] = (int8_t)kHScale;                          /* 偏置列（实数 1.0） */

    for (int c = 0; c < kClassN; c++) {
        int32_t s = 0;
        for (int j = 0; j < kHidden + 1; j++) {
            s += (int32_t)ELM_WOUT_Q[c][j] * h[j];
        }
        logits_out[c] = s;   /* 实数语义 = s / (2^8 · 127)，argmax 无需除法 */
    }
    int best = 0;
    for (int c = 1; c < kClassN; c++) {
        if (logits_out[c] > logits_out[best]) {
            best = c;
        }
    }
    return best;
}

int infer_float(const double *x_real, double *logits_out) {
    double h[kHidden + 1];
    for (int j = 0; j < kHidden; j++) {
        double u = ELM_B_F[j];
        for (int i = 0; i < kFeatureDim; i++) {
            u += ELM_W_F[j][i] * x_real[i];
        }
        h[j] = tanh(u);          /* 对照路径：真 tanh（LUT 交付路径无此调用） */
    }
    h[kHidden] = 1.0;
    for (int c = 0; c < kClassN; c++) {
        double s = 0.0;
        for (int j = 0; j < kHidden + 1; j++) {
            s += ELM_WOUT_F[c][j] * h[j];
        }
        logits_out[c] = s;
    }
    int best = 0;
    for (int c = 1; c < kClassN; c++) {
        if (logits_out[c] > logits_out[best]) {
            best = c;
        }
    }
    return best;
}

}  // namespace elm_lut
