/* LoRaCanary C3 深度睡眠 · RTC 计数保持（AB-03）。
 *
 * 移植 firmware/sleep_epoch/lowpower.cpp（BRAVO 骨架）的 RTC 持久化思路到
 * ESP32-C3：RTC_DATA_ATTR 变量在深睡期间保持（RTC 慢时钟域供电），掉电/
 * 硬复位（RESET 键/重新上电）清零——「冷启动归零」是预期语义（v1 SPEC 同款）。
 *
 * 保持内容（工单 AB-03 第 2 条）：node_id（node_config.h 编译期常量，不需 RTC）
 * + seq（帧序号）+ epoch（生命周期计数）跨唤醒不丢。
 *
 * 纯逻辑部分（counters_*）无 Arduino 依赖，可主机编译；ESP32 存取仅真机生效。
 * Python 镜像 tools/loracanary_sleep.py 同语义，pytest 覆盖（S-xx 用例）。
 */
#ifndef LORACANARY_RTC_STATE_H
#define LORACANARY_RTC_STATE_H

#include <stdint.h>

namespace loracanary {

// 深睡保持的计数（帧里 seq 截断为 uint8，这里保持全量 uint32）
struct NodeCounters {
    uint32_t seq = 0;        // GEO 帧序号（每周期 +1）
    uint32_t wake_count = 0; // 唤醒总次数（调试/统计）
    uint32_t epoch = 0;      // 生命周期计数（冷启动从 0 起，深睡连续 +1）
};

// 纯逻辑：热唤醒后计数是否连续（seq/wake_count/epoch 各恰好 +1）。
// 用于自检与 Python 镜像同款判定；伪造 gap（丢醒）返回 false。
bool counters_contiguous(const NodeCounters &before, const NodeCounters &after);

// 纯逻辑：按冷/热唤醒推进计数——冷启动清零（上电语义），热唤醒各 +1。
void counters_on_wake(NodeCounters *c, bool cold_boot);

#if defined(ARDUINO) && defined(ESP32)
// 从 RTC 域恢复计数；返回 cold_boot（true = 掉电/硬复位后的冷启动）。
// 内部用 esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_UNDEFINED 判冷启动，
// 同时把软复位残留的 RTC 计数清零（防止 RESET 键后计数「复活」）。
bool rtc_load(NodeCounters *c);

// 回睡前把计数写回 RTC 域（esp_deep_sleep_start 前调用）。
void rtc_commit(const NodeCounters *c);
#endif

}  // namespace loracanary

#endif /* LORACANARY_RTC_STATE_H */
