/* AC-01 · 乘法规对照基准（float Haar），仅供主机/真机 benchmark 使用。
 *
 * 与无乘法规等复杂度：同样的 O(N) 加减结构，差异仅在缩放用乘法 0.5（FPU）。
 * 特征位语义与 mulfree::packet_features 对齐（含同样的活动/尖峰阈值），
 * 用于精度等价性对照。不属于固件热路径，不在 objdump 无乘法验收范围内。
 */
#pragma once

#include <stdint.h>
#include <stddef.h>

void float_haar_tree_32(const int16_t *samples, float *details31, float *final_avg);
uint64_t float_packet_features(const uint8_t *buf, size_t len);
