// LoRa433 手持遥控端（卷130 W130-02 §3，**可选件**）——按键/电位器 → 发送 PTZ 帧
//
// 用途：现场没有主机时，用手持端直接遥控云台。
// 它是**桥的对端**，共用同一套 `lora_line_codec.hpp`（同一份编解码，不是另一套）。
//
// 按键映射（README 里有同一张表）：
//   摇杆 X（电位器 ADC1_CH0 / GPIO1）→ 方位角 0..360°
//   摇杆 Y（电位器 ADC1_CH1 / GPIO2）→ 俯仰角 0..180°
//   键 A（GPIO4）→ 发送定位（G1 到当前摇杆位置）
//   键 B（GPIO5）→ `G28` 回零
//   键 C（GPIO6）→ `!`  停住（进给保持）
//   键 D（GPIO7）→ `M112` 急停（**最高优先，双通道语义在主机侧，遥控端只管发**）
//
// 安全设计：摇杆变化**不自动发**定位，必须按键 A 确认——现场手持设备
// 最容易出的事就是摇杆被碰到导致云台乱转；「显式确认」这一层不能省。
//
// 说明：本文件按工单标为「可选」，本卷提供**完整可编译源码 + 帧协议共用**，
// 但**未上机验证**（本机只有一块板子的位子，且无第二块 ESP32）。

#include <Arduino.h>

#include "lora_line_codec.hpp"

namespace {

using antenna::lora_bridge::kFrameMax;
using antenna::lora_bridge::kCmdPrefix;

#if defined(ANTENNA_ENABLE_RADIOLIB)
#include <RadioLib.h>
#endif

// ---------------- 引脚 ----------------
constexpr int kPinJoyAz = 1;      // ADC1_CH0
constexpr int kPinJoyEl = 2;      // ADC1_CH1
constexpr int kPinKeyGoto = 4;
constexpr int kPinKeyHome = 5;
constexpr int kPinKeyHold = 6;
constexpr int kPinKeyEstop = 7;

//: 摇杆 → 角度映射范围（与卷129 软限位一致）
constexpr float kAzMinDeg = 0.0f, kAzMaxDeg = 360.0f;
constexpr float kElMinDeg = 0.0f, kElMaxDeg = 180.0f;
//: ADC 满量程（ESP32-S3 12 位）
constexpr float kAdcMax = 4095.0f;

//: 按键去抖
constexpr uint32_t kDebounceMs = 30;
//: 发送节流（避免按住键连发同一命令）
constexpr uint32_t kRepeatGuardMs = 250;

uint32_t last_key_ms[4] = {0, 0, 0, 0};

#if defined(ANTENNA_ENABLE_RADIOLIB)
Module* g_module = nullptr;
SX1278* g_radio = nullptr;
#endif

float ReadAngle(int pin, float lo, float hi) {
  const int raw = analogRead(pin);
  const float t = static_cast<float>(raw) / kAdcMax;
  const float clamped = (t < 0.0f) ? 0.0f : ((t > 1.0f) ? 1.0f : t);
  return lo + clamped * (hi - lo);
}

//: 发一条命令帧（**带上 `PTZ ` 前缀**——桥只认这个前缀的帧）
bool SendCommand(const char* cmd) {
  if (cmd == nullptr) return false;
  char payload[kFrameMax] = {0};
  const int n = snprintf(payload, sizeof(payload), "%s%s", kCmdPrefix(), cmd);
  if (n <= 0 || static_cast<size_t>(n) >= sizeof(payload)) return false;

  uint8_t frame[kFrameMax] = {0};
  const size_t used = antenna::lora_bridge::EncodeFrame(payload, frame, sizeof(frame));
  if (used == 0) return false;
#if defined(ANTENNA_ENABLE_RADIOLIB)
  if (g_radio == nullptr) return false;
  g_radio->standby();
  const int16_t st = g_radio->transmit(frame, used);
  g_radio->startReceive();
  return st == RADIOLIB_ERR_NONE;
#else
  (void)frame;
  (void)used;
  return false;                     // 无 RadioLib：逻辑可编，但发不出去（明确失败）
#endif
}

//: 按键边沿检测（按下即触发，带去抖与节流）
bool KeyPressed(int pin, uint32_t now_ms, int slot) {
  if (digitalRead(pin) != LOW) return false;         // 低有效（INPUT_PULLUP）
  if ((now_ms - last_key_ms[slot]) < kDebounceMs) return false;
  if ((now_ms - last_key_ms[slot]) < kRepeatGuardMs) return false;
  last_key_ms[slot] = now_ms;
  return true;
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(kPinKeyGoto, INPUT_PULLUP);
  pinMode(kPinKeyHome, INPUT_PULLUP);
  pinMode(kPinKeyHold, INPUT_PULLUP);
  pinMode(kPinKeyEstop, INPUT_PULLUP);
  analogReadResolution(12);

#if defined(ANTENNA_ENABLE_RADIOLIB)
  // 接线与桥一致（见 lora_bridge/sx1278_radio.hpp 文件头）
  g_module = new Module(/*nss=*/10, /*dio0=*/8, /*rst=*/9, RADIOLIB_NC);
  g_radio = new SX1278(g_module);
  const int16_t st = g_radio->begin(433.0f, 125.0f, 7, 5, 0x12, 17);
  Serial.println(st == RADIOLIB_ERR_NONE ? "ok:remote_ready" : "error:radio_init");
  if (st == RADIOLIB_ERR_NONE) g_radio->startReceive();
#else
  Serial.println("warn:no_radiolib_remote_is_logic_only");
#endif
}

void loop() {
  const uint32_t now = millis();

  if (KeyPressed(kPinKeyGoto, now, 0)) {
    const float az = ReadAngle(kPinJoyAz, kAzMinDeg, kAzMaxDeg);
    const float el = ReadAngle(kPinJoyEl, kElMinDeg, kElMaxDeg);
    char cmd[32] = {0};
    snprintf(cmd, sizeof(cmd), "G1 X%.1f Y%.1f", az, el);
    Serial.println(SendCommand(cmd) ? "sent:goto" : "error:send");
  }
  if (KeyPressed(kPinKeyHome, now, 1)) {
    Serial.println(SendCommand("G28") ? "sent:home" : "error:send");
  }
  if (KeyPressed(kPinKeyHold, now, 2)) {
    Serial.println(SendCommand("!") ? "sent:hold" : "error:send");
  }
  if (KeyPressed(kPinKeyEstop, now, 3)) {
    // 急停：**不做任何本地确认/延迟**——紧急动作不能等
    Serial.println(SendCommand("M112") ? "sent:estop" : "error:send");
  }
  delay(10);
}
