/* AC-01 · 无乘法特征提取器 · C++ 正本（Arduino-ESP32 / ESP32-S3）
 *
 * 授粉来源（设计参照级）：cs.SD 关键词检测论文 "Signal classification in the
 * absence of multiplications"——dyadic Haar 多分辨率分析 + 符号二值量化 +
 * 加法/移位实现。本实现为独立整数实现，未引用论文代码/数据。
 *
 * 与 tools/mulfree_features.py（Python 正本）逐位同步：
 *   黄金向量由 tools/gen_mulfree_assets.py 生成（mulfree_prototypes.h），
 *   两侧任何一侧破坏一致性，pytest / C++ 自测即红。
 *
 * 热路径不变量（可执行验收）：
 *   本 .cpp 特征提取 + 分类全程无 乘法/除法/取模 指令（仅 加/减/移位/比较/位运算）。
 *   验收手段：tools/objdump_mulfree_check.py 对 xtensa-esp32s3 反汇编按符号 grep。
 *
 * 算术移位注记：(a ± b) >> 1 依赖有符号数算术移位（gcc/xtensa-gcc 定义为
 * 算术移位，C++20 起语言保证），与 Python 的地板除 >> 语义一致——这是
 * 两镜像逐位一致的前提，勿改为除法或逻辑移位。
 */
#pragma once

#include <stdint.h>
#include <stddef.h>

namespace mulfree {

// 与 tools/mulfree_features.py 常量逐项一致
constexpr int kWindow = 32;            // Haar 树输入点数（2^5，5 层）
constexpr int kLevels = 5;
constexpr int kNDetail = 31;           // 31 个细节系数
constexpr int kNActivity = 8;          // 活动位（8 个 4 点窗）
constexpr int kActWin = kWindow / kNActivity;
constexpr int kActThreshold = 32;      // 窗内 |差分| 最大值阈值（2 的幂）
constexpr int kSpikeThreshold = 32;    // 尖峰判定（2 的幂）
constexpr int kSpikeBits = 3;          // >=1 / >=4 / >=16 三档
constexpr int kTailPadMin = 8;         // 尾部补零判定
constexpr int kFeatureBits = 46;       // 31+1+8+2+3+1
constexpr int kSemanticBit0 = 32;      // 语义位区起点（bit0..31 为符号位）
constexpr int kSemanticWeightShift = 3; // 语义位权 8（<<3）
constexpr uint64_t kSignMask = (1ULL << kSemanticBit0) - 1;

constexpr uint8_t kMagic0 = 0xD0;      // LoRaCanary 帧头（SPEC-20 契约）
constexpr uint8_t kMagic1 = 0xCC;

// dyadic Haar 树：avg=(a+b)>>1, diff=(a-b)>>1，仅加减移位。
// 输出 details31[kLevel] 逐层打包（16+8+4+2+1），final_avg 为最终均值系数。
void haar_tree_32(const int16_t *samples, int32_t *details31, int32_t *final_avg);

// 分段窗内最大值（比较实现）；n 须为 win 整数倍，out 容量 n/win。
void box_window_max(const int32_t *samples, int n, int win, int32_t *out);

// 收包字节流 → 46 位特征（bit 语义见 tools/mulfree_features.py 文档注释）。
// 帧头存在时特征窗对齐帧头后载荷区；不足按"保持末字节"延拓；空包全零。
uint64_t packet_features(const uint8_t *buf, size_t len);

int popcount64(uint64_t x);
// 加权汉明：语义位（bit32..45）权 8，符号位权 1（移位实现）
int weighted_distance(uint64_t a, uint64_t b);

// 加权汉明最近原型分类（原型表在 mulfree_prototypes.h，生成器产物）。
// 返回类别 0..2（NORMAL / NOISE / BAD_FRAME），并列取表内最先出现。
int classify(uint64_t bits);

}  // namespace mulfree
