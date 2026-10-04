// 休眠遥测节点 · ESP32 深睡配置实现（BRAVO B-01）。
//
// 【未编译验证】云服无 ESP32 工具链，本文件的 esp_sleep_* / RTC_DATA_ATTR 调用
// 未经编译；寄存器/API 以 ESP32 Arduino core（esp_sleep.h）公开接口为准，真机
// 侧若有差异按编译错误微调。主机编译（无 ESP32 头文件）走桩实现，仅纯逻辑校验
// lowpower_validate 可测。
#include "lowpower.h"

#include <string.h>

#if defined(ARDUINO) || defined(ESP32)
#include <esp_sleep.h>

// RTC_DATA_ATTR：深睡期间不丢（RTC 慢时钟域），掉电（含硬复位）后清零 → 正是
// 「断电重上电 epoch 不连续」的判据来源。
RTC_DATA_ATTR uint32_t g_rtc_epoch = 0;
#endif

namespace sleep_epoch {

bool lowpower_validate(const LowPowerConfig& cfg, char* reason, size_t reason_len) {
    if (reason != nullptr && reason_len > 0) {
        reason[0] = '\0';
    }
    if (!cfg.timer_wake && !cfg.gpio_wake) {
        if (reason != nullptr && reason_len > 0) {
            snprintf(reason, reason_len, "no wake source (need timer or gpio)");
        }
        return false;
    }
    if (cfg.gpio_wake && cfg.gpio_wake_pin > 45) {
        // ESP32-S3 可用 GPIO 0..45（部分输入专用），超界视为非法
        if (reason != nullptr && reason_len > 0) {
            snprintf(reason, reason_len, "gpio_wake_pin %u out of range", cfg.gpio_wake_pin);
        }
        return false;
    }
    return true;
}

#if defined(ARDUINO) || defined(ESP32)

void lowpower_enter(const LowPowerConfig& cfg) {
    if (cfg.timer_wake) {
        // 深睡时间（微秒）；0 表示仅外部唤醒
        esp_sleep_enable_timer_wakeup((uint64_t)cfg.sleep_duration_s * 1000000ULL);
    }
    if (cfg.gpio_wake) {
        // 低电平唤醒（SX1278 DIO / 按键拉低触发），禁用上拉省电
        esp_sleep_enable_ext0_wakeup((gpio_num_t)cfg.gpio_wake_pin, 0);
    }
    if (cfg.rtc_keep_epoch) {
        // epoch 已在进入深睡前经 lowpower_save_epoch 写入 RTC 备份域
        lowpower_save_epoch(g_rtc_epoch);
    }
    esp_deep_sleep_start();
}

void lowpower_save_epoch(uint32_t epoch) {
    g_rtc_epoch = epoch;
}

uint32_t lowpower_load_epoch(void) {
    return g_rtc_epoch;
}

#else  // 主机桩实现（无 ESP32 头文件）

static uint32_t g_host_epoch = 0;

void lowpower_enter(const LowPowerConfig& cfg) {
    (void)cfg;  // 主机无深睡，空实现（仅编译占位）
}

void lowpower_save_epoch(uint32_t epoch) {
    g_host_epoch = epoch;
}

uint32_t lowpower_load_epoch(void) {
    return g_host_epoch;
}

#endif

}  // namespace sleep_epoch
