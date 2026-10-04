/* AC-02 · OTA-ELM 查表推理 · C++ 正本（Arduino-ESP32 / ESP32-S3）
 *
 * 授粉来源（设计参照级）：arXiv 2608.27137（OTA-ELM + 非线性超表面）——
 * ELM 单隐层固定随机输入权重 + 解析解输出权重（无反向传播）；超表面固定
 * 非线性响应 → 预定义查找表。本实现只取设计思想，独立实现。
 *
 * 与 tools/elm_lut.py（Python 正本）逐位同步：
 *   定点特征/整数 MAC/查表激活/定点输出层完全一致；权重与 LUT 由
 *   tools/gen_elm_assets.py 生成（elm_weights.h），黄金向量两侧同源断言。
 *
 * 路径：
 *   infer_lut   —— LUT 推理（交付路径）：整数 MAC + 查表激活，无浮点/无 libm。
 *   infer_float —— float(double) 参考（对照路径）：真 tanh，供精度对比。
 */
#pragma once

#include <stdint.h>
#include <stddef.h>

namespace elm_lut {

constexpr int kFeatureDim = 8;
constexpr int kHidden = 32;
constexpr int kClassN = 3;
constexpr int kXScaleBits = 7;      // x_q = x_real · 2^7（int16 承载）
constexpr int kOutScaleBits = 8;    // wout_q = wout · 2^8（int16）
constexpr int kHScale = 127;        // 隐层输出 int8：h_real = h_q/127
constexpr int kLutStepBits = 5;     // u_real = idx / 2^5（±4.0 饱和区）

/* 收包字节流 → 8 维 Q7 定点特征（与 elm_lut.elm_features_real+quantize_x 一致）。
 * 所有缩放均为 2 的幂（移位实现），跨语言逐位一致：
 *   f0..f3: 4 个 8 点窗 |差分| 能量和（Q7: 窗和 <<3）
 *   f4:     尖峰计数 |差分|>=32（Q7: 计数 <<5）
 *   f5:     窗内均值字节（Q7: Σext <<1）
 *   f6:     帧长（Q7: len <<7）
 *   f7:     帧头旗标 D0 CC（Q7: 128 或 0）
 */
void packet_features_q7(const uint8_t *buf, size_t len, int16_t *x_q);

/* 实数版特征（与 elm_lut.elm_features_real 一致，供 infer_float 对照路径） */
void packet_features_real(const uint8_t *buf, size_t len, double *x_real);

/* LUT 推理（交付路径）：logits_out 容量 3，返回 argmax 类别（并列取先出现）。
 * 热路径：整数 MAC + 移位 + 查表，无浮点无 libm（objdump 可验）。 */
int infer_lut(const int16_t *x_q, int32_t *logits_out);

/* float 参考推理（对照路径，double 与 Python float64 同精度）：真 tanh。 */
int infer_float(const double *x_real, double *logits_out);

}  // namespace elm_lut
