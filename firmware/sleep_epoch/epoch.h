// 休眠遥测节点 · epoch 版本化核心（纯 C++，无 Arduino 依赖，可主机编译）。
//
// 背景（BRAVO B-01，MagPie 授粉）：LoRa 遥测节点休眠时 MAC 状态（路由表/邻居表/
// 信道接入窗口）在 RAM，断电全丢，唤醒后每次从零入网（~5s）。MagPie 解法是低功耗
// RTC/NVS 保持 epoch_counter + slot_map（时隙映射），唤醒后对比 epoch 连续性：
//   - 连续   → 从断点恢复（沿用 slot_map，跳过完整重同步）；
//   - 不连续 → 触发重同步（清 slot_map，重新协商时隙）。
//
// 本文件是纯逻辑层：epoch 递增 / 连续性检查 / 断点恢复 / 时隙分配（幂等），
// 持久化动作（RTC backup 寄存器 / NVS 读写）由 lowpower.cpp 注入，不与本层耦合。
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace sleep_epoch {

// ---- 帧协议扩展（与 mcpserver/rf_brain/sleep_sync.py 逐字节对齐）----
// epoch 同步帧使用新消息类型 0x05（BRAVO 扩展）。刻意不写入 dcp_frame.h 的
// dcp_msg_type 枚举：dcp_encode 不校验 type，可正常发 0x05；而 dcp_decode 对未知
// type 返回 -1，云服侧由 sleep_sync.py 用自己的解码路径解析，避免破坏 PAPA 的
// 枚举边界契约（其单测断言 0x05 非法）。
constexpr uint8_t DCP_EPOCH = 0x05;

// epoch 帧 payload 定长 8B：node_id(2 LE) + epoch_counter(4 LE) + slot(1) + flags(1)
constexpr size_t EPOCH_PAYLOAD_LEN = 8;

// flags 位定义
constexpr uint8_t EPOCH_FLAG_RESYNC = 0x01;  // 节点侧检测到 epoch 不连续，请求重同步

// ---- 时隙映射 ----
constexpr size_t SLOT_MAP_MAX = 32;          // 一个遥测网络的最大节点时隙数（位图）

// 断点恢复 / 重同步结果
enum class JoinResult : uint8_t {
    FAST_RESUME = 0,  // epoch 连续，从断点恢复（跳过完整重同步）
    RESYNC      = 1,  // epoch 不连续，触发重同步
};

// 节点 epoch 状态（低功耗域中需持久化的部分：epoch_counter + slot_map）
struct EpochState {
    uint32_t epoch_counter = 0;   // 单调递增，断电经 RTC/NVS 保持
    uint16_t node_id = 0;         // 本节点 ID（与 dcp REPORT device_id 同源）
    uint8_t  slot = 0;            // 本节点当前时隙
    bool     slot_owned = false;  // 本节点是否已持有时隙（幂等分配依据）
    bool     slot_map[SLOT_MAP_MAX] = {false};  // 时隙占用位图
    bool     initialized = false; // 是否已完成过至少一次 epoch 持久化
};

// epoch 递增：返回 ++epoch_counter（调用方负责持久化到 RTC/NVS）。
uint32_t epoch_increment(EpochState* s);

// epoch 连续性检查：current 相对 last 连续（last 未初始化 / current==last / ==last+1）。
// 不连续（gap > 1 或回退）返回 false。
bool is_epoch_contiguous(uint32_t last, uint32_t current);

// 断点恢复：对 EpochState 施加 current epoch——
//   连续 → 保留 slot_map（断点恢复），返回 JoinResult::FAST_RESUME；
//   不连续 → 清 slot_map 并置位重同步请求，返回 JoinResult::RESYNC。
JoinResult epoch_checkpoint_resume(EpochState* s, uint32_t current);

// 时隙分配（幂等）：本节点已持有且仍占用 → 原样返回；否则分配最小空位。
// 成功返回 true 并写 *out_slot；时隙全满返回 false。
bool slot_assign(EpochState* s, uint8_t* out_slot);

// 释放本节点时隙（重同步前调用）。
void slot_release(EpochState* s);

// 查询某时隙是否被占用。
bool slot_is_assigned(const EpochState* s, uint8_t slot);

// ---- epoch 帧 payload 编解码（8B，纯逻辑）----
// 构造 payload → out（容量 ≥ EPOCH_PAYLOAD_LEN），返回 8。
size_t epoch_build_payload(const EpochState* s, uint32_t epoch,
                           bool resync_requested, uint8_t* out);

// 解析 payload（长度须 == 8）；成功返回 1，失败返回 0。
int epoch_parse_payload(const uint8_t* payload, size_t len,
                        uint32_t* epoch, uint16_t* node_id,
                        uint8_t* slot, uint8_t* flags);

}  // namespace sleep_epoch
