// 边缘频谱哨兵 · ESP32-S3 固件（Phase 1 · 纯串口，无 WiFi/蓝牙）
//
// 功能：SX1278 以 OOK 模式收 433.92MHz → 采样 RSSI 包络还原脉冲序列 →
//       解码 Acurite/Nexus/Kerui → USB-CDC 串口输出 NDJSON 行。
// 串口命令：STATUS（回固件版本 + SX1278 寄存器状态）；RESET（重配射频）。
//
// 参考 rtl_433（GPL-2.0-or-later）协议文档，仅引「协议格式」公开事实，
// 解码逻辑独立实现（见 ook_decode.h/.cpp，与 N-02 Python 同源端口）。
//
// 构建：Arduino-esp32 core（详见 firmware/README.md）
//   arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/sentinel
#include <Arduino.h>
#include <vector>

#include "sx1278_ook.h"
#include "ook_decode.h"

using sentinel::Frame;
using sentinel::Pulse;
using sentinel::Sx1278Ook;
using sentinel::decode_any_pulse;

// ---------------------------------------------------------------------------
// 硬件接线（可改，默认见 README 接线表）
// ---------------------------------------------------------------------------
#ifndef PIN_SX1278_NSS
#define PIN_SX1278_NSS 10
#endif
#ifndef PIN_SX1278_RESET
#define PIN_SX1278_RESET 9
#endif
#ifndef PIN_SX1278_DIO0
#define PIN_SX1278_DIO0 8
#endif
#ifndef PIN_SCK
#define PIN_SCK 12
#endif
#ifndef PIN_MISO
#define PIN_MISO 13
#endif
#ifndef PIN_MOSI
#define PIN_MOSI 11
#endif

// ---------------------------------------------------------------------------
// 射频 / 采样参数（真机标定点，见 README 第 6 节）
// ---------------------------------------------------------------------------
constexpr const char* FW_VERSION = "sentinel-v1.0.0";
constexpr float RSSI_HI_DBM = -70.0f;   // 载波在（高电平）门限
constexpr float RSSI_LO_DBM = -95.0f;   // 静默（低电平）门限（迟滞）
constexpr unsigned long SAMPLE_BLOCK_US = 5000;  // 每段采样时长（微秒）
constexpr size_t MAX_PULSES = 256;              // 滑动窗口脉冲上限
constexpr unsigned long DEDUP_MS = 800;         // 同帧去重窗口（重复 12~25 次）

Sx1278Ook radio(PIN_SX1278_NSS, PIN_SX1278_RESET, PIN_SX1278_DIO0);

std::vector<Pulse> pulses;
bool armed = false;
int level = 0;
unsigned long lastUs = 0;

String lastKey = "";
unsigned long lastEmitMs = 0;

// ---------------------------------------------------------------------------
// NDJSON 输出
// ---------------------------------------------------------------------------

static const char* acuriteChannelName(int ch) {
    // 0=C 1=B 2=A（ook_decode.cpp 规范）
    return (ch == 0) ? "C" : (ch == 1) ? "B" : (ch == 2) ? "A" : "?";
}

void emitReport(const Frame& f, int rssiDbm) {
    // 去重：同 (protocol,id,cmd) 帧重复上报在 DEDUP_MS 内只发一次
    String key = String(f.protocol.c_str()) + ":" + String(f.id) + ":" + String(f.cmd);
    unsigned long now = millis();
    if (key == lastKey && (now - lastEmitMs) < DEDUP_MS) return;
    lastKey = key;
    lastEmitMs = now;

    Serial.print("{\"src\":\"sentinel\",\"protocol\":\"");
    Serial.print(f.protocol.c_str());
    Serial.print("\",\"id\":");
    Serial.print(f.id);
    if (f.protocol == "acurite") {
        Serial.print(",\"channel\":\"");
        Serial.print(acuriteChannelName(f.channel));
        Serial.print("\",\"temperature\":");
        Serial.print(f.temperature_c, 1);
        Serial.print(",\"humidity\":");
        Serial.print(f.humidity);
        Serial.print(",\"battery\":\"");
        Serial.print(f.battery == 1 ? "OK" : "LOW");
        Serial.print("\"");
    } else if (f.protocol == "nexus") {
        Serial.print(",\"channel\":");
        Serial.print(f.channel);
        Serial.print(",\"temperature\":");
        Serial.print(f.temperature_c, 1);
        Serial.print(",\"humidity\":");
        Serial.print(f.humidity);
        Serial.print(",\"battery\":\"");
        Serial.print(f.battery == 1 ? "OK" : "LOW");
        Serial.print("\"");
    } else if (f.protocol == "kerui") {
        Serial.print(",\"cmd\":");
        Serial.print(f.cmd);
    }
    Serial.print(",\"rssi_dbm\":");
    Serial.print(rssiDbm);
    Serial.print(",\"crc_ok\":");
    if (f.crc_ok == 1) Serial.print("true");
    else if (f.crc_ok == 0) Serial.print("false");
    else Serial.print("null");
    Serial.println("}");
}

void emitStatus() {
    auto r = radio.snapshot();
    Serial.print("{\"src\":\"sentinel\",\"type\":\"status\",\"firmware\":\"");
    Serial.print(FW_VERSION);
    Serial.print("\",\"reg_op_mode\":");
    Serial.print(r.op_mode, HEX);
    Serial.print(",\"reg_rx_bw\":");
    Serial.print(r.rx_bw, HEX);
    Serial.print(",\"reg_lna\":");
    Serial.print(r.lna, HEX);
    Serial.print(",\"reg_ook_peak\":");
    Serial.print(r.ook_peak, HEX);
    Serial.print(",\"reg_ook_fix\":");
    Serial.print(r.ook_fix, HEX);
    Serial.print(",\"reg_rssi_config\":");
    Serial.print(r.rssi_config, HEX);
    Serial.print(",\"chip_version\":");
    Serial.print(r.version, HEX);
    Serial.print(",\"rssi_dbm\":");
    Serial.print(radio.readRssiDbm(), 1);
    Serial.println("}");
}

// ---------------------------------------------------------------------------
// 串口命令
// ---------------------------------------------------------------------------

void handleSerialCommands() {
    if (!Serial.available()) return;
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();
    if (cmd == "STATUS") {
        emitStatus();
    } else if (cmd == "RESET") {
        radio.setStandby();
        radio.setOokRx43392(sentinel::RX_BW_25K);
        pulses.clear();
        armed = false;
        level = 0;
        Serial.println("{\"src\":\"sentinel\",\"type\":\"reset\",\"ok\":true}");
    }
    // 未知命令静默忽略（不崩）
}

// ---------------------------------------------------------------------------
// setup / loop
// ---------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);          // USB-CDC
    delay(200);

    SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_SX1278_NSS);
    radio.begin();
    radio.setOokRx43392(sentinel::RX_BW_25K);

    lastUs = micros();
    Serial.print("{\"src\":\"sentinel\",\"type\":\"boot\",\"firmware\":\"");
    Serial.print(FW_VERSION);
    Serial.println("\",\"freq_hz\":433920000,\"mode\":\"ook\"}");
}

void loop() {
    handleSerialCommands();

    // 采样一段 RSSI 包络，捕捉电平跳变（分段采样，兼顾串口命令响应）
    unsigned long blockStart = micros();
    while (micros() - blockStart < SAMPLE_BLOCK_US) {
        float rssi = radio.readRssiDbm();
        int cur = (rssi > RSSI_HI_DBM) ? 1 : (rssi < RSSI_LO_DBM) ? 0 : level;
        unsigned long now = micros();
        if (cur != level) {
            if (!armed) {
                if (cur == 1) { armed = true; level = 1; lastUs = now; }
            } else {
                pulses.push_back({level, static_cast<float>(now - lastUs)});
                level = cur;
                lastUs = now;
                if (pulses.size() > MAX_PULSES) pulses.erase(pulses.begin());

                // 窗口内尝试全部协议解码（滑动窗口使帧首逐次对齐）
                Frame f;
                if (pulses.size() >= 24 && decode_any_pulse(pulses, f)) {
                    emitReport(f, static_cast<int>(rssi));
                    pulses.clear();
                    armed = false;
                    level = 0;
                }
            }
        }
    }
}
