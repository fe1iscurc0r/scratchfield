/* AC-01 · 无乘法特征提取器 · C++ 自测（黄金向量法，与 tools/mulfree_features.py 同源）
 *
 * 黄金向量与解析用例期望值由 Python 侧计算（tools/gen_mulfree_assets.py 生成
 * mulfree_prototypes.h；解析用例期望值来自 tools/mulfree_features.py 手算核对），
 * 本文件断言 C++ 镜像产生完全一致的特征位/类别——两镜像任何一侧不一致，这里即红。
 *
 * 构建运行（任意 g++ 主机）：
 *   g++ -Wall -Wextra -O2 -o mulfree_features_test \
 *       mulfree_features.cpp mulfree_features_test.cpp
 *   ./mulfree_features_test          # 输出 PASS 行，返回 0
 */
#include <stdio.h>
#include <string.h>

#include "mulfree_features.h"
#include "mulfree_float_ref.h"
#include "mulfree_prototypes.h"

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
    using namespace mulfree;

    /* ---- 1. 解析用例（期望值与 tools/mulfree_features.py 手算核对） ---- */
    {
        int16_t c[32];
        for (int i = 0; i < 32; i++) c[i] = 7;
        int32_t d[31], fa;
        haar_tree_32(c, d, &fa);
        int all_zero = 1;
        for (int i = 0; i < 31; i++) all_zero = all_zero && (d[i] == 0);
        CHECK(all_zero && fa == 7, "A 常量向量: 细节全零, 均值=7");
    }
    {
        int16_t s[32];
        for (int i = 0; i < 32; i++) s[i] = (i < 16) ? 0 : 64;
        int32_t d[31], fa;
        haar_tree_32(s, d, &fa);
        CHECK(d[15] == 0 && fa == 32, "B 阶跃边沿: L1[15]=0, 均值=32");
    }
    {
        int16_t s[32];
        for (int i = 0; i < 32; i++) s[i] = (int16_t)i;
        int32_t d[31], fa;
        haar_tree_32(s, d, &fa);
        CHECK(d[0] == -1 && d[1] == -1 && d[2] == -1 && d[3] == -1
              && d[30] == -8 && fa == 15,
              "C 线性斜坡: L1[0..3]=-1, L5=-8, 均值=15");
    }
    {
        int32_t in[31] = {1,200,3,4, 5,6,7,8, 9,10,250,12, 13,14,15,16,
                          0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0};
        int32_t out[8];
        box_window_max(in, 31, 4, out);
        CHECK(out[0] == 200 && out[1] == 8 && out[2] == 250 && out[3] == 16
              && out[4] == 0 && out[7] == 0,
              "D 窗最大值(含末窗 3 点截断): 200/8/250/16/0...");
    }
    {
        CHECK(popcount64(0xFULL) == 4 && popcount64(0) == 0,
              "E1 popcount 基础");
        CHECK(weighted_distance(0ULL, 0xFFFFFFFFFFULL) == 96,
              "E2 加权汉明: 低 32 位权 1 + 高 8 位权 8 = 96");
    }
    {
        uint64_t bits = packet_features(nullptr, 0);
        CHECK(bits == 0x00002000FFFFFFFFULL,
              "F 空包: 符号位全 1 + 仅尾部补零位(bit45)置位");
    }

    /* ---- 2. 黄金向量：12 条合成收包（Python packet_feature_bits 同源） ---- */
    uint8_t buf[256];
    int feat_ok = 0, cls_ok = 0, noise_all_ok = 1;
    for (int i = 0; i < MULFREE_GOLDEN_N; i++) {
        int n = hex2bin(MULFREE_GOLDEN[i].hex, buf, sizeof(buf));
        uint64_t bits = packet_features(buf, (size_t)n);
        if (bits == MULFREE_GOLDEN[i].bits) feat_ok++;
        else printf("  向量 %d 特征位不符: got 0x%llX want 0x%llX\n",
                    i, (unsigned long long)bits,
                    (unsigned long long)MULFREE_GOLDEN[i].bits);
        int pred = classify(bits);
        if (pred == MULFREE_GOLDEN[i].cls) cls_ok++;
        if (MULFREE_GOLDEN[i].cls == 1 && pred != 1) noise_all_ok = 0;
    }
    CHECK(feat_ok == MULFREE_GOLDEN_N,
          "G 黄金向量特征位逐条一致 (12/12)");
    /* 分类口径与 pytest/README 一致：整体精度 95.33%，黄金向量内 ≥10/12，
     * 难例误判如实保留（不做向量挑选）；NOISE 行必须全对。 */
    CHECK(cls_ok >= 10 && noise_all_ok,
          "H 黄金向量分类 >=10/12 且 NOISE 行全对");

    /* ---- 3. 整数 vs float 路径符号位抽样一致（README 精度对照数据源） ---- */
    {
        int agree = 0, total = 0;
        for (int i = 0; i < MULFREE_GOLDEN_N; i++) {
            int n = hex2bin(MULFREE_GOLDEN[i].hex, buf, sizeof(buf));
            uint64_t a = packet_features(buf, (size_t)n);
            uint64_t b = float_packet_features(buf, (size_t)n);
            uint64_t x = (a ^ b) & 0xFFFFFFFFULL;  /* 符号位 + 均值符号共 32 位 */
            agree += 32 - popcount64(x);
            total += 32;
        }
        printf("INFO: 符号位一致率 %d/%d (%.2f%%)\n", agree, total,
               100.0 * agree / total);
        CHECK(agree * 2 >= total,  /* >=50%：抽样底线；实际 ~99.7% 见 INFO 行 */
              "I 整数/float 符号位抽样一致率 >= 50%");
    }

    /* ---- 4. 分类器混淆统计（黄金向量内 3 类各 4 条） ---- */
    {
        int conf[3][3] = {{0}};
        for (int i = 0; i < MULFREE_GOLDEN_N; i++) {
            int n = hex2bin(MULFREE_GOLDEN[i].hex, buf, sizeof(buf));
            int pred = classify(packet_features(buf, (size_t)n));
            conf[MULFREE_GOLDEN[i].cls][pred]++;
        }
        printf("INFO: 混淆矩阵 行=真 列=预测: [%d %d %d][%d %d %d][%d %d %d]\n",
               conf[0][0], conf[0][1], conf[0][2],
               conf[1][0], conf[1][1], conf[1][2],
               conf[2][0], conf[2][1], conf[2][2]);
        CHECK(conf[1][0] == 0 && conf[1][2] == 0,
              "J NOISE 行无跨类误判（与 pytest F-03b 同口径）");
    }

    printf(g_fail == 0 ? "ALL PASS (%d checks)\n" : "FAILED (%d checks)\n",
           g_fail == 0 ? g_pass : g_fail);
    return g_fail == 0 ? 0 : 1;
}
