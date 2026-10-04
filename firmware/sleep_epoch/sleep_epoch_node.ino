// 休眠遥测节点 · 主循环状态机（BRAVO B-01 集成）。
//
// 这是哨兵固件的「休眠遥测」变体（LoRa 上报 dcp 帧），与原 sentinel/sentinel.ino
// （OOK 接收 433MHz 传感器、NDJSON 串口输出）角色不同、互不影响：
//   - 本文件：LoRa 遥测节点，状态机「休眠 → CAD 监听 → 唤醒 → epoch 校验 →
//             上报 dcp 帧 → 回睡」；
//   - sentinel.ino：OOK 接收网关，保持不变（现有上报路径兼容）。
//
// 【未编译验证】云服无 ESP32 工具链，本文件未经编译；逻辑与 test_sleep_epoch.cpp
// 的纯逻辑用例对齐，真机侧烧录后按 README「休眠唤醒」章节清单实测。
//
// 构建（与 sentinel 同 core）：
//   arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/sleep_epoch
#include <Arduino.h>

#include "epoch.h"
#include "lowpower.h"
#include "wake_sync.h"

using sleep_epoch::EpochState;
using sleep_epoch::JoinResult;
using sleep_epoch::LowPowerConfig;

// ---------------------------------------------------------------------------
// 节点参数（真机标定点，见 firmware/README.md「休眠唤醒」章节）
// ---------------------------------------------------------------------------
constexpr const char* FW_VERSION = "sleep-epoch-node-v0.1.0";
constexpr uint16_t NODE_ID      = 0x0001;   // 与云服 sleep_sync 跟踪的 node_id 对应
constexpr uint8_t  CHANNEL      = 'A';      // dcp REPORT channel（ASCII）
constexpr uint8_t  PROTOCOL     = 4;        // DCP_PROTO_ACURITE_ATLAS（预留槽位示例）
constexpr uint32_t SLEEP_S      = 60;       // 定时唤醒周期（秒）

static EpochState g_epoch;
static LowPowerConfig g_lp = {
    SLEEP_S,        // sleep_duration_s
    true,           // timer_wake
    true,           // gpio_wake（SX1278 DIO 触发）
    8,              // gpio_wake_pin（沿用 DIO0=8 接线）
    true,           // rtc_keep_epoch
};

// 唤醒源判定（RTC 复位原因）：定时器 / 外部引脚 / 上电复位。
static sleep_epoch::WakeSource wakeSource() {
#if defined(ARDUINO) || defined(ESP32)
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    if (cause == ESP_SLEEP_WAKEUP_TIMER) {
        return sleep_epoch::WakeSource::TIMER;
    }
    if (cause == ESP_SLEEP_WAKEUP_EXT0 || cause == ESP_SLEEP_WAKEUP_GPIO) {
        return sleep_epoch::WakeSource::EXTERNAL;
    }
#endif
    // 上电冷启动 / 主机桩：视为外部/首次（触发重同步）
    return sleep_epoch::WakeSource::EXTERNAL;
}

// 上报一条 epoch 同步帧（type=0x05）。
static void reportEpochFrame(uint32_t epoch, bool resync, uint16_t seq) {
    uint8_t frame[sleep_epoch::EPOCH_PAYLOAD_LEN + 7];
    size_t n = sleep_epoch::wake_build_epoch_frame(&g_epoch, epoch, resync, seq, frame);
    if (n > 0) {
        // 真机：dcp_lora_send(frame, n)；此处为集成占位（LoRa TX 见 dcp_lora/sx1278_lora.cpp）
        (void)frame;
        (void)n;
    }
}

// 上报一条 dcp REPORT 帧（type=0x01，复用 PAPA 格式，现有上报路径兼容）。
static void reportDataFrame(uint16_t seq) {
    uint8_t frame[9 + 7];
    // 传感器读数占位：真机接传感器后替换为实测值
    size_t n = sleep_epoch::wake_build_report_frame(
        /*temp*/ 21.5f, /*hum*/ 55, /*battery*/ 0, /*rssi*/ -85,
        CHANNEL, PROTOCOL, NODE_ID, seq, frame);
    if (n > 0) {
        (void)frame;
        (void)n;
    }
}

void setup() {
    Serial.begin(115200);
    delay(50);

    g_epoch.node_id = NODE_ID;
    // 从 RTC 备份域恢复 epoch（掉电冷启动则 g_rtc_epoch == 0 → 触发重同步）
    g_epoch.epoch_counter = sleep_epoch::lowpower_load_epoch();
    g_epoch.initialized = (g_epoch.epoch_counter != 0);

    Serial.print("{\"src\":\"sleep-epoch\",\"type\":\"boot\",\"firmware\":\"");
    Serial.print(FW_VERSION);
    Serial.println("\",\"wake\":\"boot\"}");
}

void loop() {
    // 1) 唤醒原因 → 计算本次 epoch（定时/外部唤醒各 +1，冷启动从 0 起）
    sleep_epoch::WakeSource src = wakeSource();
    uint32_t current_epoch = sleep_epoch::lowpower_load_epoch() + 1;

    // 2) epoch 校验 + 断点恢复
    JoinResult jr = sleep_epoch::wake_fast_join(&g_epoch, current_epoch);
    bool resync = (jr == JoinResult::RESYNC);

    // 3) 时隙分配（连续则沿用旧 slot_map；重同步则重新分配）
    uint8_t slot = 0;
    sleep_epoch::slot_assign(&g_epoch, &slot);

    // 4) 上报 dcp 帧：先 epoch 同步帧（带 resync 标志），再数据帧
    uint16_t seq = 0;  // 真机由 Transmitter.next_seq() 维护
    reportEpochFrame(current_epoch, resync, seq);
    reportDataFrame(seq);

    // 5) 持久化 epoch 并回睡
    sleep_epoch::lowpower_save_epoch(current_epoch);

    Serial.print("{\"src\":\"sleep-epoch\",\"type\":\"cycle\",\"epoch\":");
    Serial.print(current_epoch);
    Serial.print(",\"slot\":");
    Serial.print(slot);
    Serial.print(",\"resync\":");
    Serial.print(resync ? "true" : "false");
    Serial.print(",\"wake\":\"");
    Serial.print(src == sleep_epoch::WakeSource::TIMER ? "timer" :
                 src == sleep_epoch::WakeSource::EXTERNAL ? "external" : "cad");
    Serial.println("\"}");

    sleep_epoch::lowpower_enter(g_lp);  // 不回退（esp_deep_sleep_start 不返回）
    (void)src;
}
