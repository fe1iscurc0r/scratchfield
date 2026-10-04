/* test_elm_infer.cpp — ELM 定点推理核心主机单元测试（g++ 可编译运行）。
 *
 * 编译（无 Arduino 工具链也可跑，纯 C 核心）：
 *   g++ -std=c++17 -Wall -Wextra -O2 \
 *       -I firmware/elm_classifier \
 *       firmware/tests/test_elm_infer.cpp firmware/elm_classifier/elm_infer.cpp \
 *       -o /tmp/test_elm_infer && /tmp/test_elm_infer
 *
 * 期望输出「🎉 ELM 定点推理核心主机测试通过」。
 * 期望值（A/B/C 三类 mock 特征的分类与置信度）由 PC 端
 * tools/elm_train.py 定点仿真给出，用于锁定 PC/固件一致性。
 */

#include <cstdio>
#include <cstring>

#include "elm_infer.h"

static int g_failures = 0;

#define CHECK(cond, msg)                                             \
    do {                                                             \
        if (!(cond)) {                                               \
            std::printf("FAIL: %s\n", msg);                          \
            g_failures++;                                            \
        }                                                            \
    } while (0)

int main() {
    /* mock 特征（三类信号中心点，与 tools/elm_train.py 同源） */
    static const double mock[3][ELM_N_FEATURES] = {
        {-85.0, 6.0, 0.8,  3.2,  0.15, 0.28, 14.0, 0.08},  /* A */
        {-92.0, 4.0, 0.2,  2.8,  0.00, 0.12,  7.0, 0.22},  /* B */
        {-98.0, 2.5, -0.3, 2.5, -0.10, 0.05,  0.0, 0.50},  /* C */
    };
    static const char* expect_class[3] = {"A", "B", "C"};
    /* PC 端定点仿真给出的置信度（千分比），用于交叉锁定 */
    static const uint16_t expect_conf[3] = {583, 602, 572};

    /* 1) mock 输入分类正确 + 置信度与 PC 端一致 */
    for (int s = 0; s < 3; s++) {
        int8_t x_q[ELM_N_FEATURES];
        elm_result_t r;
        elm_quantize_input(mock[s], x_q);
        elm_run(x_q, &r);
        CHECK(std::strcmp(ELM_CLASS_NAMES[r.class_index], expect_class[s]) == 0,
              "mock 分类结果与期望类不符");
        CHECK(r.confidence_permille == expect_conf[s],
              "mock 置信度与 PC 端定点仿真不符");
        /* 2) 概率合法：0~1000，行和≈1000（截断误差 ≤ no-1） */
        int32_t psum = 0;
        for (int k = 0; k < ELM_N_OUTPUTS; k++) {
            CHECK(r.prob_permille[k] <= 1000, "概率千分比越界");
            psum += r.prob_permille[k];
        }
        CHECK(psum >= 1000 - (ELM_N_OUTPUTS - 1) && psum <= 1000,
              "概率千分比行和不≈1000");
    }

    /* 3) sigmoid LUT：中心为 0、非饱和区单调不减 */
    CHECK(ELM_SIG_LUT[128] == 0, "sigmoid LUT 中心应为 0");
    bool sig_mono = true;
    for (int i = 128; i < 255; i++) {
        if (ELM_SIG_LUT[i + 1] < ELM_SIG_LUT[i]) sig_mono = false;
    }
    CHECK(sig_mono, "sigmoid LUT 右半应单调不减");

    /* 4) EN LUT：EN[0]=32767，单调不增、非负 */
    CHECK(ELM_EN_LUT[0] == 32767, "EN LUT[0] 应为 32767");
    bool en_mono = true;
    for (int i = 0; i < 255; i++) {
        if (ELM_EN_LUT[i + 1] > ELM_EN_LUT[i] || ELM_EN_LUT[i] < 0) en_mono = false;
    }
    CHECK(en_mono, "EN LUT 应单调不增且非负");

    /* 5) 确定性：同一输入两次运行结果一致 */
    {
        int8_t x_q[ELM_N_FEATURES];
        elm_result_t r1, r2;
        elm_quantize_input(mock[0], x_q);
        elm_run(x_q, &r1);
        elm_run(x_q, &r2);
        CHECK(r1.class_index == r2.class_index
              && r1.confidence_permille == r2.confidence_permille,
              "推理结果应确定");
    }

    /* 6) 输入量化：量纲一致性（大包络均值 → 负向 int8，高 SNR → 正向 int8） */
    {
        int8_t x_q[ELM_N_FEATURES];
        elm_quantize_input(mock[0], x_q);   /* A：env_mean=-85dBm, snr=14dB */
        elm_quantize_input(mock[2], x_q);   /* C：env_mean=-98dBm, snr=0dB */
        CHECK(x_q[6] < 0, "snr=0dB 量化后应 < 0");
    }

    if (g_failures == 0) {
        std::printf("🎉 ELM 定点推理核心主机测试通过\n");
        return 0;
    }
    std::printf("❌ %d 项失败\n", g_failures);
    return 1;
}
