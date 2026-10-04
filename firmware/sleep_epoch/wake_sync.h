// 休眠遥测节点 · 唤醒 + epoch 快速入网序列（BRAVO B-01）。
//
// 唤醒后快速入网：先对比 epoch，连续则跳过完整重同步（沿用 slot_map 断点恢复），
// 不连续则触发重同步；随后构造 dcp 帧上报。帧构造复用 dcp_lora/dcp_frame.h 的
// dcp_encode / dcp_build_report_payload，与 PAPA 帧格式严格兼容。
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "epoch.h"

namespace sleep_epoch {

// 唤醒源（低功耗域寄存器回读结果）
enum class WakeSource : uint8_t {
    NONE     = 0,  // 未检测到唤醒（非法/查询态）
    TIMER    = 1,  // 深睡定时器唤醒
    CAD      = 2,  // LoRa CAD（信道活动检测）唤醒
    EXTERNAL = 3,  // 外部 GPIO 唤醒
};

// 唤醒后快速入网序列：
//   1. 对 current_epoch 做连续性检查 / 断点恢复（见 epoch_checkpoint_resume）；
//   2. 连续 → 返回 FAST_RESUME（跳过完整重同步）；不连续 → 返回 RESYNC。
JoinResult wake_fast_join(EpochState* s, uint32_t current_epoch);

// 构造唤醒后的 epoch 同步 dcp 帧（type=DCP_EPOCH，payload 8B）→ out，返回帧长；
// payload 超长/非法返回 0。resync_requested 由调用方按 JoinResult 置位。
size_t wake_build_epoch_frame(const EpochState* s, uint32_t epoch,
                              bool resync_requested, uint16_t seq, uint8_t* out);

// 构造唤醒后的 dcp REPORT 帧（type=DCP_REPORT，payload 9B，复用 PAPA 格式）→ out，
// 返回帧长；参数非法返回 0。与 sentinel 现有上报路径字段对齐。
size_t wake_build_report_frame(float temperature_c, uint8_t humidity_pct,
                               uint8_t battery, int8_t rssi_dbm,
                               uint8_t channel, uint8_t protocol,
                               uint16_t device_id, uint16_t seq, uint8_t* out);

}  // namespace sleep_epoch
