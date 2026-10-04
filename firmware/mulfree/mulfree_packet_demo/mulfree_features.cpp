/* AC-01 · 无乘法特征提取器 · C++ 正本实现（热路径无乘除/取模） */
#include "mulfree_features.h"
#include "mulfree_prototypes.h"   /* 生成器产物（tools/gen_mulfree_assets.py），classify 引用原型表 */

namespace mulfree {

void haar_tree_32(const int16_t *samples, int32_t *details31, int32_t *final_avg) {
    int32_t work[kWindow];
    for (int i = 0; i < kWindow; i++) {
        work[i] = samples[i];
    }
    int n = kWindow;
    int d = 0;
    while (n > 1) {
        int half = n >> 1;
        for (int i = 0; i < half; i++) {
            int32_t a = work[i << 1];
            int32_t b = work[(i << 1) + 1];
            work[i] = (a + b) >> 1;            /* 均值：加法 + 算术右移 */
            details31[d] = (a - b) >> 1;       /* 细节：减法 + 算术右移 */
            d++;
        }
        n = half;
    }
    *final_avg = work[0];
}

void box_window_max(const int32_t *samples, int n, int win, int32_t *out) {
    /* 末窗不足 win 点时按实际点数截断（与 Python 切片语义一致，防越界） */
    int w = 0;
    for (int base = 0; base < n; base += win) {
        int32_t m = samples[base];
        for (int i = 1; i < win && base + i < n; i++) {
            int32_t v = samples[base + i];
            if (v > m) {
                m = v;
            }
        }
        out[w] = m;
        w++;
    }
}

uint64_t packet_features(const uint8_t *buf, size_t len) {
    int n = (len > 255u) ? 255 : (int)len;   /* SPEC-20 帧 ≤120B，防御性上限 */
    bool has_header = (n >= 2 && buf[0] == kMagic0 && buf[1] == kMagic1);
    int off = has_header ? 2 : 0;

    /* 特征窗：帧头后载荷区 / 无帧头取前 32 字节；保持末字节延拓 */
    int16_t ext[kWindow];
    for (int i = 0; i < kWindow; i++) {
        int j = off + i;
        if (j < n) {
            ext[i] = (int16_t)buf[j];
        } else {
            ext[i] = (n > 0) ? (int16_t)buf[n - 1] : 0;
        }
    }

    int32_t details[kNDetail];
    int32_t final_avg;
    haar_tree_32(ext, details, &final_avg);

    /* 一阶差分 + 绝对值（条件取反） */
    int32_t absd[kWindow - 1];
    for (int i = 0; i < kWindow - 1; i++) {
        int32_t d = (int32_t)ext[i + 1] - (int32_t)ext[i];
        absd[i] = (d < 0) ? -d : d;
    }

    uint64_t bits = 0;
    int k = 0;
    for (int i = 0; i < kNDetail; i++) {       /* bit0..30 Haar 符号 */
        if (details[i] >= 0) {
            bits |= 1ULL << k;
        }
        k++;
    }
    if (final_avg >= 0) {                      /* bit31 均值符号 */
        bits |= 1ULL << k;
    }
    k++;

    int32_t wmax[kNActivity];
    box_window_max(absd, kWindow - 1, kActWin, wmax);
    for (int j = 0; j < kNActivity; j++) {     /* bit32..39 活动位 */
        if (wmax[j] >= kActThreshold) {
            bits |= 1ULL << k;
        }
        k++;
    }

    if (n >= kWindow) {                        /* bit40 长度桶 */
        bits |= 1ULL << k;
    }
    k++;
    if (has_header) {                          /* bit41 帧头 */
        bits |= 1ULL << k;
    }
    k++;

    int n_spike = 0;                           /* bit42..44 尖峰三档 */
    for (int i = 0; i < kWindow - 1; i++) {
        if (absd[i] >= kSpikeThreshold) {
            n_spike++;
        }
    }
    if (n_spike >= 1) {
        bits |= 1ULL << k;
    }
    if (n_spike >= 4) {
        bits |= 1ULL << (k + 1);
    }
    if (n_spike >= 16) {
        bits |= 1ULL << (k + 2);
    }
    k += kSpikeBits;

    int tail = 0;                              /* bit45 尾部补零 */
    for (int i = kWindow - 2; i >= 0; i--) {
        if (absd[i] != 0) {
            break;
        }
        tail++;
    }
    if (tail >= kTailPadMin) {
        bits |= 1ULL << k;
    }
    return bits;
}

int popcount64(uint64_t x) {
    int cnt = 0;
    while (x) {
        cnt += (int)(x & 1ULL);
        x >>= 1;
    }
    return cnt;
}

int weighted_distance(uint64_t a, uint64_t b) {
    uint64_t x = a ^ b;
    return popcount64(x & kSignMask)
           + (popcount64(x >> kSemanticBit0) << kSemanticWeightShift);
}

int classify(uint64_t bits) {
    int best_cls = -1;
    int best_dist = (kFeatureBits + 1) << kSemanticWeightShift;
    const int proto_n = (int)(sizeof(MULFREE_PROTOTYPES) / sizeof(MULFREE_PROTOTYPES[0]));
    for (int i = 0; i < proto_n; i++) {
        int d = weighted_distance(bits, MULFREE_PROTOTYPES[i].bits);
        if (d < best_dist) {
            best_dist = d;
            best_cls = MULFREE_PROTOTYPES[i].cls;
        }
    }
    return best_cls;
}

}  // namespace mulfree
