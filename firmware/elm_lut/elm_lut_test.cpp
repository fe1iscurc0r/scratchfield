/* AC-02 · OTA-ELM 查表推理 · C++ 自测（黄金向量法，与 tools/elm_lut.py 同源）
 *
 * 黄金向量由 Python 侧生成（tools/gen_elm_assets.py → elm_weights.h 内嵌），
 * 本文件断言：定点特征逐项一致 / LUT logits 逐位一致 / float logits 容差一致 /
 * 预测一致 / LUT 表与 double tanh 误差上界。两镜像任何一侧不一致，这里即红。
 *
 * 构建运行（任意 g++ 主机）：
 *   g++ -Wall -Wextra -O2 -o elm_lut_test elm_inference.cpp elm_lut_test.cpp
 *   ./elm_lut_test        # 输出 PASS 行，返回 0
 * 本机无主机 g++ 时：xtensa-esp32s3-elf-g++ -fsyntax-only（见 README）。
 */
#include <stdio.h>
#include <math.h>
#include <string.h>

#include "elm_inference.h"
#include "elm_weights.h"

static int g_pass = 0;
static int g_fail = 0;

#define CHECK(cond, name)                                              \
    do {                                                               \
        if (cond) {                                                    \
            printf("PASS: %s\n", name);                                \
            g_pass++;                                                  \
        } else {                                                       \
            printf("FAIL: %s\n", name);                                \
            g_fail++;                                                  \
        }                                                              \
    } while (0)

static int hex2bin(const char *hex, uint8_t *out, int cap) {
    int n = 0;
    for (int i = 0; hex[i] && hex[i + 1] && n < cap; i += 2) {
        unsigned v;
        sscanf(hex + i, "%2x", &v);
        out[n++] = (uint8_t)v;
    }
    return n;
}

int main(void) {
    using namespace elm_lut;

    /* ---- 1. LUT 表自检：逐项 |LUT/127 - tanh(u)| <= 0.02（理论界 0.0196） ---- */
    {
        double max_err = 0.0;
        for (int j = 0; j < 256; j++) {
            double u = (double)(j - 128) / 32.0;
            double err = fabs((double)ELM_TANH_LUT[j] / kHScale - tanh(u));
            if (err > max_err) max_err = err;
        }
        printf("INFO: LUT 逐项最大激活误差 %.5f (理论界 0.0196)\n", max_err);
        CHECK(max_err <= 0.02, "A tanh LUT 量化误差上界");
    }

    /* ---- 2. 黄金向量：特征/LUT logits/float logits/预测 ---- */
    uint8_t buf[256];
    int feat_ok = 0, lut_ok = 0, flt_ok = 0, pred_ok = 0;
    for (int i = 0; i < ELM_GOLDEN_N; i++) {
        int n = hex2bin(ELM_GOLDEN[i].hex, buf, sizeof(buf));
        int16_t x_q[8];
        double x_r[8];
        packet_features_q7(buf, (size_t)n, x_q);
        packet_features_real(buf, (size_t)n, x_r);
        int same_feat = 1;
        for (int j = 0; j < kFeatureDim; j++) {
            same_feat = same_feat && (x_q[j] == ELM_GOLDEN[i].x_q[j]);
        }
        feat_ok += same_feat;

        int32_t ll[3];
        int pred_l = infer_lut(x_q, ll);
        int same_lut = 1;
        for (int c = 0; c < kClassN; c++) {
            same_lut = same_lut && (ll[c] == ELM_GOLDEN[i].lut_logits[c]);
        }
        lut_ok += same_lut;

        double lf[3];
        int pred_f = infer_float(x_r, lf);
        double max_d = 0.0;
        for (int c = 0; c < kClassN; c++) {
            double d = fabs(lf[c] - ELM_GOLDEN[i].float_logits[c]);
            if (d > max_d) max_d = d;
        }
        flt_ok += max_d <= 1e-6;
        pred_ok += (pred_l == ELM_GOLDEN[i].pred_lut)
                   && (pred_f == ELM_GOLDEN[i].pred_float);
    }
    CHECK(feat_ok == ELM_GOLDEN_N, "B 定点特征逐条一致 (12/12)");
    CHECK(lut_ok == ELM_GOLDEN_N, "C LUT logits 逐位一致 (12/12)");
    CHECK(flt_ok == ELM_GOLDEN_N, "D float logits 容差一致 <=1e-6 (12/12)");
    CHECK(pred_ok == ELM_GOLDEN_N, "E 双路径预测一致 (12/12)");

    /* ---- 3. 双路径一致性：LUT logits 与 float logits 判决全等（黄金向量上） ---- */
    {
        int agree = 0;
        for (int i = 0; i < ELM_GOLDEN_N; i++) {
            agree += ELM_GOLDEN[i].pred_lut == ELM_GOLDEN[i].pred_float;
        }
        printf("INFO: 黄金向量双路径判决一致 %d/%d\n", agree, ELM_GOLDEN_N);
        CHECK(agree == ELM_GOLDEN_N, "F 黄金向量上 LUT/float 判决全等");
    }

    printf(g_fail == 0 ? "ALL PASS (%d checks)\n" : "FAILED (%d checks)\n",
           g_fail == 0 ? g_pass : g_fail);
    return g_fail == 0 ? 0 : 1;
}
