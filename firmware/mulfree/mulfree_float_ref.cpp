/* AC-01 · 乘法规对照基准实现（float Haar，FPU 乘法路径） */
#include "mulfree_float_ref.h"
#include "mulfree_features.h"

void float_haar_tree_32(const int16_t *samples, float *details31, float *final_avg) {
    float work[mulfree::kWindow];
    for (int i = 0; i < mulfree::kWindow; i++) {
        work[i] = (float)samples[i];
    }
    int n = mulfree::kWindow;
    int d = 0;
    while (n > 1) {
        int half = n >> 1;
        for (int i = 0; i < half; i++) {
            float a = work[i << 1];
            float b = work[(i << 1) + 1];
            work[i] = (a + b) * 0.5f;
            details31[d] = (a - b) * 0.5f;
            d++;
        }
        n = half;
    }
    *final_avg = work[0];
}

uint64_t float_packet_features(const uint8_t *buf, size_t len) {
    int n = (len > 255u) ? 255 : (int)len;
    bool has_header = (n >= 2 && buf[0] == mulfree::kMagic0 && buf[1] == mulfree::kMagic1);
    int off = has_header ? 2 : 0;

    int16_t ext[mulfree::kWindow];
    for (int i = 0; i < mulfree::kWindow; i++) {
        int j = off + i;
        ext[i] = (j < n) ? (int16_t)buf[j] : ((n > 0) ? (int16_t)buf[n - 1] : 0);
    }

    float details[mulfree::kNDetail];
    float final_avg;
    float_haar_tree_32(ext, details, &final_avg);

    uint64_t bits = 0;
    int k = 0;
    for (int i = 0; i < mulfree::kNDetail; i++) {
        if (details[i] >= 0.0f) {
            bits |= 1ULL << k;
        }
        k++;
    }
    if (final_avg >= 0.0f) {
        bits |= 1ULL << k;
    }
    k++;

    for (int j = 0; j < mulfree::kNActivity; j++) {
        int base = j * mulfree::kActWin;
        int32_t m = 0;
        for (int i = 0; i < mulfree::kActWin && base + i < mulfree::kWindow - 1; i++) {
            int32_t d = (int32_t)ext[base + i + 1] - (int32_t)ext[base + i];
            if (d < 0) d = -d;
            if (d > m) m = d;
        }
        if (m >= mulfree::kActThreshold) {
            bits |= 1ULL << k;
        }
        k++;
    }

    if (n >= mulfree::kWindow) {
        bits |= 1ULL << k;
    }
    k++;
    if (has_header) {
        bits |= 1ULL << k;
    }
    k++;

    int n_spike = 0;
    for (int i = 0; i < mulfree::kWindow - 1; i++) {
        int32_t d = (int32_t)ext[i + 1] - (int32_t)ext[i];
        if (d < 0) d = -d;
        if (d >= mulfree::kSpikeThreshold) {
            n_spike++;
        }
    }
    if (n_spike >= 1) bits |= 1ULL << k;
    if (n_spike >= 4) bits |= 1ULL << (k + 1);
    if (n_spike >= 16) bits |= 1ULL << (k + 2);
    k += mulfree::kSpikeBits;

    int tail = 0;
    for (int i = mulfree::kWindow - 2; i >= 0; i--) {
        int32_t d = (int32_t)ext[i + 1] - (int32_t)ext[i];
        if (d != 0) break;
        tail++;
    }
    if (tail >= mulfree::kTailPadMin) {
        bits |= 1ULL << k;
    }
    return bits;
}
