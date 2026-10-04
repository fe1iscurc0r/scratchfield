/* LoRaCanary C3 深度睡眠 · RTC 计数保持实现（AB-03，契约见 rtc_state.h）。
 *
 * RTC_DATA_ATTR 变量放 .rtc.data 段：深睡保持、掉电清零。软复位（RESET 键/
 * esptool 烧录重启）不清零 RTC 段——所以冷启动判定不能只看计数非零，必须用
 * esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_UNDEFINED（非深睡唤醒 =
 * 冷启动），顺手把残留计数清零，防 RESET 后计数「复活」。
 */
#include "rtc_state.h"

#if defined(ARDUINO) && defined(ESP32)
#include <esp_sleep.h>
#endif

namespace loracanary {

bool counters_contiguous(const NodeCounters &before, const NodeCounters &after) {
    return after.seq == before.seq + 1 &&
           after.wake_count == before.wake_count + 1 &&
           after.epoch == before.epoch + 1;
}

void counters_on_wake(NodeCounters *c, bool cold_boot) {
    if (c == nullptr) {
        return;
    }
    if (cold_boot) {
        c->seq = 0;
        c->wake_count = 0;
        c->epoch = 0;
        return;
    }
    c->seq += 1;
    c->wake_count += 1;
    c->epoch += 1;
}

#if defined(ARDUINO) && defined(ESP32)

static RTC_DATA_ATTR uint32_t s_rtc_seq = 0;
static RTC_DATA_ATTR uint32_t s_rtc_wake_count = 0;
static RTC_DATA_ATTR uint32_t s_rtc_epoch = 0;

bool rtc_load(NodeCounters *c) {
    if (c == nullptr) {
        return false;
    }
    bool cold_boot =
        (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_UNDEFINED);
    if (cold_boot) {
        // 掉电重上电（RTC 清零）或 RESET 键（RTC 残留）都归零重计
        s_rtc_seq = 0;
        s_rtc_wake_count = 0;
        s_rtc_epoch = 0;
    }
    c->seq = s_rtc_seq;
    c->wake_count = s_rtc_wake_count;
    c->epoch = s_rtc_epoch;
    counters_on_wake(c, cold_boot);
    return cold_boot;
}

void rtc_commit(const NodeCounters *c) {
    if (c == nullptr) {
        return;
    }
    s_rtc_seq = c->seq;
    s_rtc_wake_count = c->wake_count;
    s_rtc_epoch = c->epoch;
}

#endif  // ARDUINO && ESP32

}  // namespace loracanary
