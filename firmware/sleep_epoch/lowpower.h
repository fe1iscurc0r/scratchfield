// 休眠遥测节点 · ESP32 深睡配置 + 唤醒源注册 + RTC 持久化（BRAVO B-01）。
//
// 功耗目标（理论值，实测留用户）：深睡电流 <50µA（ESP32-S3 deep sleep 典型
// ~7µA + 稳压/传感器漏电裕量）；休眠期间仅保留 RTC 备份寄存器/慢时钟，
// 主 RAM 断电（因此 MAC 状态须由 epoch + slot_map 的 RTC 持久化来断点恢复）。
//
// 依赖 ESP32 Arduino core（esp_sleep.h / RTC_DATA_ATTR / esp_sleep_*）；主机
// 编译时（无 ESP32 头文件）退化为桩实现，仅保留纯逻辑校验（lowpower_validate），
// 供 test_sleep_epoch.cpp 无工具链跑通。
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace sleep_epoch {

// 深睡配置
struct LowPowerConfig {
    uint32_t sleep_duration_s = 0;  // 定时唤醒周期（秒）；0 = 仅外部/无定时唤醒
    bool     timer_wake = false;    // 定时器唤醒源
    bool     gpio_wake  = false;    // 外部 GPIO 唤醒源（SX1278 DIO / 按键）
    uint8_t  gpio_wake_pin = 0;     // 外部唤醒 GPIO 编号
    bool     rtc_keep_epoch = true; // 是否将 epoch_counter 持久化进 RTC 备份域
};

// 深睡配置校验（纯逻辑，无 ESP32 依赖，主机可测）。
// 返回 true 表示配置合理；否则 reason 写入失败原因。
// 目标：休眠电流 <50µA —— 至少一种唤醒源，且不使能 WiFi/蓝牙（本层不含二者）。
bool lowpower_validate(const LowPowerConfig& cfg, char* reason, size_t reason_len);

// 进入深睡（ESP32 依赖）：注册唤醒源 + 写 RTC 备份域后 esp_deep_sleep_start。
void lowpower_enter(const LowPowerConfig& cfg);

// RTC 备份域读写 epoch_counter（32bit 拆进 2 个 32bit 备份寄存器）。
void lowpower_save_epoch(uint32_t epoch);
uint32_t lowpower_load_epoch(void);

}  // namespace sleep_epoch
