/*
 * denoise_rc.h — Reservoir Computing 漂移补偿 · ESP32-S3 固件骨架（D-02 可选）
 *
 * ⚠️ 未编译验证：本文件仅为 D-02 Python 原型的 C 移植骨架，尚未在
 *    ESP32-S3 / Arduino 工具链下编译通过，权重为固定随机种子（seed=0）
 *    从 Python 原型导出的「示意权重」。正式移植需：
 *      1. 用 mcpserver/rf_brain/denoise/reservoir.py 按目标信号训练读出层，
 *         导出 W_out（数据相关，本骨架只给示例）；
 *      2. 按资源重选 N_UNITS（此处 8，仅为示意，越小越省 RAM）；
 *      3. 在 Arduino 环境编译验证，替换 tanhf 为查表/近似以省 Flash。
 *
 * 状态更新（与 Python 一致，leaking_rate=0.3, spectral_radius=0.9）:
 *     pre[i] = Σ_j W[i][j]*h[j] + W_in[i]*u
 *     new[i] = tanh(pre[i])
 *     h[i] = (1 - 0.3) * h[i] + 0.3 * new[i]
 *
 * 补偿推理（读出层，含 bias）:
 *     y = W_out[0..N-1] · h + W_out[N]   （W_out[N] 为 bias）
 */
#ifndef DENOISE_RC_H
#define DENOISE_RC_H

#ifdef __cplusplus
extern "C" {
#endif

#include <math.h>   /* tanhf */

#define RC_N_UNITS     8
#define RC_LEAK        0.30f

/* 输入投影矩阵 W_in (N x 1)，seed=0 */
static const float RC_W_IN[RC_N_UNITS] = {
    0.273923f, -0.460427f, -0.918053f, -0.966945f,
    0.626540f,  0.825511f,  0.213272f,  0.458993f
};

/* 循环矩阵 W (N x N)，谱半径 0.9，seed=0 */
static const float RC_W[RC_N_UNITS][RC_N_UNITS] = {
    { 0.037098f,  0.369979f,  0.268597f, -0.422864f,  0.303931f, -0.396632f,  0.195296f, -0.275818f},
    { 0.308842f,  0.035258f, -0.170322f, -0.065746f, -0.401110f, -0.319504f,  0.145097f,  0.125168f},
    { 0.098122f, -0.098919f,  0.422820f,  0.408895f,  0.157782f,  0.127948f,  0.160252f, -0.094460f},
    {-0.310309f,  0.188350f,  0.021561f, -0.161368f, -0.012045f,  0.331215f,  0.369104f, -0.120929f},
    { 0.060828f, -0.151480f,  0.080191f, -0.137838f, -0.092166f,  0.331884f, -0.232021f,  0.104757f},
    {-0.353747f,  0.282876f,  0.244144f, -0.221636f,  0.320157f, -0.375387f, -0.139364f, -0.297397f},
    {-0.042231f,  0.251990f, -0.229058f, -0.380955f, -0.081168f, -0.256380f, -0.348018f,  0.068313f},
    {-0.171186f,  0.146262f, -0.255528f,  0.375967f, -0.114708f, -0.335481f,  0.109792f,  0.363246f}
};

/* 读出层权重 W_out (N+1)，示例（正弦目标，seed=0；正式部署需重训练导出） */
static const float RC_W_OUT[RC_N_UNITS + 1] = {
    -1.032601f, -2.113670f, -0.516425f, 0.201630f, -1.333628f,
     2.231034f, -3.218038f, 2.152148f, -0.000024f
};

/* 运行时 reservoir 状态（调用前 rc_reset() 清零） */
static float rc_state[RC_N_UNITS];

static inline void rc_reset(void) {
    for (int i = 0; i < RC_N_UNITS; ++i) rc_state[i] = 0.0f;
}

static inline void rc_step(float u) {
    float next[RC_N_UNITS];
    for (int i = 0; i < RC_N_UNITS; ++i) {
        float pre = RC_W_IN[i] * u;
        for (int j = 0; j < RC_N_UNITS; ++j) {
            pre += RC_W[i][j] * rc_state[j];
        }
        float n = tanhf(pre);
        next[i] = (1.0f - RC_LEAK) * rc_state[i] + RC_LEAK * n;
    }
    for (int i = 0; i < RC_N_UNITS; ++i) rc_state[i] = next[i];
}

static inline float rc_predict(void) {
    float y = RC_W_OUT[RC_N_UNITS];  /* bias */
    for (int i = 0; i < RC_N_UNITS; ++i) y += RC_W_OUT[i] * rc_state[i];
    return y;
}

#ifdef __cplusplus
}
#endif

#endif /* DENOISE_RC_H */
